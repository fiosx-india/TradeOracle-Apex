"""TradeOracle Apex - Angel One live multi-horizon analysis app."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import streamlit as st
from streamlit_autorefresh import st_autorefresh

from config import (
    ANGELONE_EXCHANGE,
    ANGELONE_HISTORY_BARS,
    ANGELONE_SYMBOL,
    DATA_MODE,
    LIVE_DATA_MAX_AGE_SECONDS,
    MIN_HISTORY_BARS,
    PREDICTION_HORIZONS_MINUTES,
)

from core.orchestrator import ApexOrchestrator
from data.market_data import MarketData
from data.provider_loader import load_market_provider
from dashboard.commodity_view import CommodityView


IST = ZoneInfo("Asia/Kolkata")


# ---------------------------------------------------------------------------
# HORIZONS
# ---------------------------------------------------------------------------

SUPPORTED_HORIZONS = (
    5,
    15,
    30,
    60,
)


def _configured_horizons() -> tuple[int, ...]:
    """
    Read configured horizons and keep only Apex-supported values.
    """

    configured = []

    for value in PREDICTION_HORIZONS_MINUTES:

        try:
            horizon = int(value)
        except (TypeError, ValueError):
            continue

        if horizon in SUPPORTED_HORIZONS:
            configured.append(horizon)

    configured = sorted(
        set(configured)
    )

    if not configured:
        return SUPPORTED_HORIZONS

    return tuple(configured)


HORIZONS = _configured_horizons()


# ---------------------------------------------------------------------------
# PROVIDER
# ---------------------------------------------------------------------------

@st.cache_resource(
    ttl=1800,
    show_spinner=False,
)
def get_provider():
    """
    Create one authenticated Angel One provider per Streamlit
    resource-cache lifetime.
    """

    return load_market_provider()


# ---------------------------------------------------------------------------
# LIVE LTP
# ---------------------------------------------------------------------------

def live_ltp_check(
    provider,
    symbol: str,
) -> dict:

    gateway = MarketData(
        provider=provider,
        max_age_seconds=(
            LIVE_DATA_MAX_AGE_SECONDS
        ),
    )

    result = gateway.latest(
        symbol=symbol
    )

    quality = result.get(
        "quality",
        {},
    )

    record = result.get(
        "record"
    )

    return {
        "provider_connected": (
            provider is not None
        ),
        "status": quality.get(
            "status",
            "UNKNOWN",
        ),
        "fresh": bool(
            quality.get(
                "fresh",
                False,
            )
        ),
        "records": quality.get(
            "count",
            0,
        ),
        "source": result.get(
            "source"
        ),
        "record": record,
        "error": gateway.last_error,
    }


# ---------------------------------------------------------------------------
# ANALYSIS
# ---------------------------------------------------------------------------

def run_analysis(
    provider,
    symbol: str,
) -> dict:

    gateway = MarketData(
        provider=provider,
        max_age_seconds=(
            LIVE_DATA_MAX_AGE_SECONDS
        ),
    )

    orchestrator = ApexOrchestrator(
        market_data=gateway,
        max_age_seconds=(
            LIVE_DATA_MAX_AGE_SECONDS
        ),
    )

    return orchestrator.run(
        symbol=symbol,
        limit=ANGELONE_HISTORY_BARS,
        horizons_minutes=HORIZONS,
    )

    # ---------------------------------------------------------------
    # 3. COMMODITY MARKET — MCX
    # ---------------------------------------------------------------
    st.header("3. MCX Commodity Market")

    commodity_symbols = {
        "Gold": "GOLD",
        "Silver": "SILVER",
        "Copper": "COPPER",
        "Crude Oil": "CRUDEOIL",
    }

    selected_commodity = st.selectbox(
        "Select MCX Commodity",
        list(commodity_symbols.keys()),
        key="mcx_commodity",
    )

    commodity_symbol = commodity_symbols[
        selected_commodity
    ]

    try:
        commodity_ltp = provider.latest(
            symbol=commodity_symbol,
            exchange="MCX",
        )

        record = commodity_ltp.get("record")

        if record:
            commodity_data = {
                "commodities": [
                    {
                        "symbol": record.get(
                            "symbol",
                            commodity_symbol,
                        ),
                        "price": record.get("price"),
                        "change_pct": record.get(
                            "change_pct"
                        ),
                        "timestamp": record.get(
                            "timestamp"
                        ),
                    }
                ]
            }

            commodity_view = CommodityView()

            rendered = commodity_view.render(
                commodity_data
            )

            st.json(rendered)

        else:
            st.info(
                f"No live MCX data available for "
                f"{selected_commodity}."
            )

    except Exception as exc:
        st.warning(
            f"MCX data unavailable for "
            f"{selected_commodity}: "
            f"{type(exc).__name__}: {exc}"
        )


# ---------------------------------------------------------------------------
# SAFE HELPERS
# ---------------------------------------------------------------------------

def _safe_float(
    value,
    default: float = 0.0,
) -> float:

    try:
        return float(value)

    except (
        TypeError,
        ValueError,
    ):
        return default


def _decision(
    brain: dict,
) -> dict:

    value = brain.get(
        "decision",
        {},
    )

    return (
        value
        if isinstance(
            value,
            dict,
        )
        else {}
    )


def _horizon_brain(
    result: dict,
    horizon: int,
) -> dict:

    horizons = result.get(
        "horizons",
        {},
    )

    if not isinstance(
        horizons,
        dict,
    ):
        return {}

    payload = horizons.get(
        str(horizon),
        {},
    )

    if not isinstance(
        payload,
        dict,
    ):
        return {}

    brain = payload.get(
        "master_brain",
        {},
    )

    return (
        brain
        if isinstance(
            brain,
            dict,
        )
        else {}
    )


# ---------------------------------------------------------------------------
# DECISION DISPLAY
# ---------------------------------------------------------------------------

def _show_direction_message(
    direction: str,
    decision_status: str,
) -> None:

    if decision_status == "WITHHELD":

        st.warning(
            "SIGNAL WITHHELD — current market-data "
            "quality, freshness, history or confidence "
            "does not satisfy the decision gate."
        )

        return

    if direction == "UP":

        st.success(
            "UP — current research/prediction evidence "
            "leans upward."
        )

    elif direction == "DOWN":

        st.error(
            "DOWN — current research/prediction evidence "
            "leans downward."
        )

    else:

        st.info(
            "SIDEWAYS — evidence does not justify "
            "a directional call."
        )


# ---------------------------------------------------------------------------
# HORIZON CARD
# ---------------------------------------------------------------------------

def _render_horizon(
    result: dict,
    horizon: int,
) -> None:

    brain = _horizon_brain(
        result,
        horizon,
    )

    st.subheader(
        f"{horizon}-Minute Forecast"
    )

    if not brain:

        st.warning(
            f"No Master Brain result was produced "
            f"for the {horizon}-minute horizon."
        )

        return

    decision = _decision(
        brain
    )

    direction = str(
        decision.get(
            "direction",
            "UNKNOWN",
        )
    ).upper()

    confidence = (
        _safe_float(
            decision.get(
                "confidence",
                0.0,
            )
        )
        * 100.0
    )

    score = _safe_float(
        decision.get(
            "score",
            0.0,
        )
    )

    decision_status = str(
        decision.get(
            "decision_status",
            "UNKNOWN",
        )
    ).upper()

    d1, d2, d3, d4 = st.columns(4)

    d1.metric(
        "Direction",
        direction,
    )

    d2.metric(
        "Confidence",
        f"{confidence:.1f}%",
    )

    d3.metric(
        "Score",
        f"{score:.4f}",
    )

    d4.metric(
        "Decision",
        decision_status,
    )

    _show_direction_message(
        direction,
        decision_status,
    )

    # ---------------------------------------------------------------
    # Derived prediction information
    # ---------------------------------------------------------------

    derived = brain.get(
        "derived",
        {},
    )

    if not isinstance(
        derived,
        dict,
    ):
        derived = {}

    prediction_evidence = brain.get(
        "prediction_evidence",
        [],
    )

    expected_return = None
    expected_move_range = None

    if isinstance(
        prediction_evidence,
        list,
    ):

        for item in prediction_evidence:

            if not isinstance(
                item,
                dict,
            ):
                continue

            if item.get(
                "engine"
            ) == "PredictionEngine":

                if (
                    item.get(
                        "expected_return"
                    )
                    is not None
                ):

                    expected_return = (
                        _safe_float(
                            item.get(
                                "expected_return"
                            )
                        )
                    )

                value = item.get(
                    "expected_move_range"
                )

                if isinstance(
                    value,
                    (list, tuple),
                ) and len(value) >= 2:

                    expected_move_range = (
                        value
                    )

                break

    if expected_return is not None:

        st.caption(
            "Scenario expected return: "
            f"{expected_return * 100:.3f}%"
        )

    if expected_move_range is not None:

        st.caption(
            "Scenario move range: "
            f"{expected_move_range[0] * 100:.3f}% "
            "to "
            f"{expected_move_range[1] * 100:.3f}%"
        )

    # ---------------------------------------------------------------
    # Explainability
    # ---------------------------------------------------------------

    reasons = decision.get(
        "reasons",
        [],
    )

    if isinstance(
        reasons,
        list,
    ) and reasons:

        with st.expander(
            f"{horizon}m — Why this result?"
        ):

            for reason in reasons:

                st.write(
                    f"• {reason}"
                )

    with st.expander(
        f"{horizon}m — Research evidence"
    ):

        st.json(
            brain.get(
                "research_evidence",
                [],
            )
        )

    with st.expander(
        f"{horizon}m — Primary prediction evidence"
    ):

        st.json(
            brain.get(
                "prediction_evidence",
                [],
            )
        )

    with st.expander(
        f"{horizon}m — Derived / meta analysis"
    ):

        st.json(
            derived
        )


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------

def main() -> None:

    st.set_page_config(
        page_title=(
            "TradeOracle Apex - Angel One Live"
        ),
        page_icon="📡",
        layout="wide",
    )

    # 15-second UI refresh.
    #
    # This refreshes the Streamlit page; it does not change the
    # prediction horizon configuration.
    st_autorefresh(
        interval=15000,
        key="angelone_live_refresh",
    )

    st.title(
        "📡 TradeOracle Apex"
    )

    st.subheader(
        "Angel One Live Market Data + "
        "Multi-Horizon AI Analysis"
    )

    st.info(
        "Read-only mode. This application reads Angel One "
        "market data and runs the Apex research/prediction "
        "pipeline. It does not place orders or GTTs."
    )

    # ------------------------------------------------------------------
    # DATA MODE
    # ------------------------------------------------------------------

    if DATA_MODE != "live":

        st.error(
            "APEX_DATA_MODE is not 'live'. "
            "Set it to 'live' for the production "
            "read-only Angel One connection."
        )

        st.stop()

    # ------------------------------------------------------------------
    # SYMBOL
    # ------------------------------------------------------------------

    symbol = st.text_input(
        "Angel One symbol",
        value=ANGELONE_SYMBOL,
        help=(
            "Examples: NIFTY for the index "
            "or SBIN for an NSE equity."
        ),
    ).strip()

    if not symbol:

        symbol = ANGELONE_SYMBOL

    st.caption(
        f"Exchange: {ANGELONE_EXCHANGE}  •  "
        f"History: {ANGELONE_HISTORY_BARS} bars  •  "
        f"Horizons: "
        f"{', '.join(str(x) for x in HORIZONS)} minutes"
    )

    # ------------------------------------------------------------------
    # 1. ANGEL ONE CONNECTION
    # ------------------------------------------------------------------

    st.header(
        "1. Angel One connection"
    )

    try:

        provider = get_provider()

        ltp = live_ltp_check(
            provider,
            symbol,
        )

    except Exception as exc:

        provider = None

        ltp = {
            "provider_connected": False,
            "status": "ERROR",
            "fresh": False,
            "records": 0,
            "source": None,
            "record": None,
            "error": (
                f"{type(exc).__name__}: "
                f"{exc}"
            ),
        }

    c1, c2, c3, c4 = st.columns(4)

    c1.metric(
        "Authentication",
        (
            "CONNECTED"
            if ltp[
                "provider_connected"
            ]
            else "FAILED"
        ),
    )

    c2.metric(
        "LTP",
        (
            str(
                ltp[
                    "record"
                ].get(
                    "price"
                )
            )
            if ltp["record"]
            else "—"
        ),
    )

    c3.metric(
        "Fresh",
        (
            "YES"
            if ltp["fresh"]
            else "NO"
        ),
    )

    c4.metric(
        "Gateway",
        ltp["status"],
    )

    if ltp["error"]:

        st.error(
            ltp["error"]
        )

    if ltp["record"]:

        with st.expander(
            "Latest Angel One record"
        ):

            st.json(
                ltp["record"]
            )

    # ------------------------------------------------------------------
    # 2. REAL MARKET DATA ANALYSIS
    # ------------------------------------------------------------------

    st.header(
        "2. Multi-horizon market analysis"
    )

    if provider is None:

        st.warning(
            "Angel One provider is not connected, "
            "so analysis is stopped."
        )

        st.stop()

    with st.spinner(
        "Fetching Angel One candles once and "
        "running 5 / 15 / 30 / 60 minute Apex analysis..."
    ):

        try:

            result = run_analysis(
                provider,
                symbol,
            )

        except Exception as exc:

            st.error(
                f"{type(exc).__name__}: {exc}"
            )

            st.stop()

    # ------------------------------------------------------------------
    # MARKET DATA STATUS
    # ------------------------------------------------------------------

    md = result.get(
        "market_data",
        {},
    )

    if not isinstance(
        md,
        dict,
    ):
        md = {}

    quality = md.get(
        "quality",
        {},
    )

    if not isinstance(
        quality,
        dict,
    ):
        quality = {}

    m1, m2, m3, m4 = st.columns(4)

    m1.metric(
        "Candles",
        md.get(
            "records",
            0,
        ),
    )

    m2.metric(
        "Data Status",
        quality.get(
            "status",
            "UNKNOWN",
        ),
    )

    m3.metric(
        "Fresh",
        (
            "YES"
            if md.get(
                "fresh"
            )
            else "NO"
        ),
    )

    m4.metric(
        "Source",
        md.get(
            "source"
        )
        or "—",
    )

    # ------------------------------------------------------------------
    # MINIMUM HISTORY GATE
    # ------------------------------------------------------------------

    records = md.get(
        "records",
        0,
    )

    if records < MIN_HISTORY_BARS:

        st.warning(
            f"Prediction is withheld until at least "
            f"{MIN_HISTORY_BARS} valid candles are available. "
            f"Current candles: {records}."
        )

    # ------------------------------------------------------------------
    # HORIZON SUMMARY
    # ------------------------------------------------------------------

    st.subheader(
        "Horizon summary"
    )

    summary = result.get(
        "horizon_summary",
        {},
    )

    if isinstance(
        summary,
        dict,
    ) and summary:

        columns = st.columns(
            len(HORIZONS)
        )

        for index, horizon in enumerate(
            HORIZONS
        ):

            item = summary.get(
                str(horizon),
                {},
            )

            if not isinstance(
                item,
                dict,
            ):
                item = {}

            direction = item.get(
                "direction",
                "UNKNOWN",
            )

            confidence = (
                _safe_float(
                    item.get(
                        "confidence",
                        0.0,
                    )
                )
                * 100.0
            )

            score = _safe_float(
                item.get(
                    "score",
                    0.0,
                )
            )

            status = item.get(
                "decision_status",
                "UNKNOWN",
            )

            with columns[index]:

                st.metric(
                    f"{horizon} Min",
                    direction,
                )

                st.caption(
                    f"Confidence: "
                    f"{confidence:.1f}%"
                )

                st.caption(
                    f"Score: {score:.4f}"
                )

                st.caption(
                    f"Status: {status}"
                )

    else:

        st.warning(
            "No multi-horizon summary was returned "
            "by ApexOrchestrator."
        )

    # ------------------------------------------------------------------
    # INDIVIDUAL HORIZON RESULTS
    # ------------------------------------------------------------------

    st.divider()

    for horizon in HORIZONS:

        _render_horizon(
            result,
            horizon,
        )

        st.divider()

    # ------------------------------------------------------------------
    # 3. APEX RUNTIME
    # ------------------------------------------------------------------

    st.header(
        "3. Apex runtime"
    )

    registered = result.get(
        "registered_engines",
        [],
    )

    st.success(
        f"{len(registered)} validated engines "
        "are registered."
    )

    with st.expander(
        "Engine registry"
    ):

        st.json(
            result.get(
                "registry_report",
                {},
            )
        )

    with st.expander(
        "Runtime registration report"
    ):

        st.json(
            result.get(
                "report",
                [],
            )
        )

    # ------------------------------------------------------------------
    # 4. SAFETY / ORDER STATUS
    # ------------------------------------------------------------------

    st.header(
        "4. Trading status"
    )

    st.success(
        "ORDER PLACEMENT: DISABLED  •  "
        "GTT: DISABLED  •  "
        "READ-ONLY MARKET DATA: ENABLED"
    )

    st.caption(
        "Angel One sessions are subject to broker/API "
        "session rules. The application re-authenticates "
        "when the cached provider expires."
    )

    st.caption(
        "Supported prediction horizons: "
        + ", ".join(
            f"{h} min"
            for h in HORIZONS
        )
    )

    st.caption(
        "Last UI refresh: "
        + datetime.now(
            IST
        ).strftime(
            "%Y-%m-%d %H:%M:%S IST"
        )
    )


if __name__ == "__main__":
    main()
