"""TradeOracle Apex - Angel One live market-data and prediction app.

Responsibilities:
- provide the Streamlit UI for Angel One market data
- allow NSE / MCX exchange selection
- allow NIFTY / equity / commodity symbol selection
- display live LTP and data quality
- run the existing Apex orchestration pipeline
- keep the application strictly read-only

This application does NOT place orders or create/modify/cancel GTTs.
"""

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
    PREDICTION_HORIZON_MINUTES,
    PREDICTION_HORIZONS_MINUTES,
)

from core.orchestrator import ApexOrchestrator
from data.market_data import MarketData
from data.provider_loader import load_market_provider


IST = ZoneInfo("Asia/Kolkata")


# =====================================================================
# PROVIDER
# =====================================================================

@st.cache_resource(
    ttl=1800,
    show_spinner=False,
)
def get_provider():
    """Create one authenticated Angel One provider per Streamlit cache."""
    return load_market_provider()


# =====================================================================
# LIVE LTP CHECK
# =====================================================================

def live_ltp_check(
    provider,
    symbol: str,
    exchange: str,
) -> dict:

    gateway = MarketData(
        provider=provider,
        max_age_seconds=LIVE_DATA_MAX_AGE_SECONDS,
    )

    result = gateway.latest(
        symbol=symbol,
        exchange=exchange,
    )

    quality = result.get(
        "quality",
        {},
    )

    record = result.get(
        "record"
    )

    return {
        "provider_connected":
            provider is not None,

        "status":
            quality.get(
                "status",
                "UNKNOWN",
            ),

        "fresh":
            bool(
                quality.get(
                    "fresh",
                    False,
                )
            ),

        "records":
            quality.get(
                "count",
                0,
            ),

        "source":
            result.get(
                "source"
            ),

        "record":
            record,

        "error":
            gateway.last_error,
    }


# =====================================================================
# APEX ANALYSIS
# =====================================================================

def run_analysis(
    provider,
    symbol: str,
    exchange: str,
    horizon_minutes: int,
) -> dict:
    """Run the existing Apex pipeline using the selected exchange."""

    gateway = MarketData(
        provider=provider,
        max_age_seconds=LIVE_DATA_MAX_AGE_SECONDS,
    )

    orchestrator = ApexOrchestrator(
        market_data=gateway,
        max_age_seconds=LIVE_DATA_MAX_AGE_SECONDS,
    )

    # IMPORTANT:
    #
    # exchange is passed through ApexOrchestrator -> MarketData
    # -> AngelOneProvider.
    #
    # This is required so MCX does not accidentally fall back
    # to the provider's default NSE exchange.
    return orchestrator.run(
        symbol=symbol,
        limit=ANGELONE_HISTORY_BARS,
        horizon_minutes=horizon_minutes,
        exchange=exchange,
    )


# =====================================================================
# SYMBOL HELPERS
# =====================================================================

def default_symbol_for_exchange(
    exchange: str,
) -> str:
    """Return a sensible UI default without changing configuration."""

    configured = (
        ANGELONE_SYMBOL
        or ""
    ).strip()

    if exchange == "MCX":
        if configured.upper() in {
            "NIFTY",
            "NIFTY 50",
            "NIFTY50",
        }:
            return "GOLD"

    return configured


# =====================================================================
# MAIN
# =====================================================================

def main() -> None:

    # -----------------------------------------------------------------
    # PAGE CONFIG
    # -----------------------------------------------------------------

    st.set_page_config(
        page_title=(
            "TradeOracle Apex - Angel One Live"
        ),
        page_icon="📡",
        layout="wide",
    )

    # -----------------------------------------------------------------
    # UI AUTO REFRESH
    #
    # This refreshes the UI/LTP view.
    # Provider authentication remains cached.
    # -----------------------------------------------------------------

    st_autorefresh(
        interval=60000,
        key="angelone_live_refresh",
    )

    # -----------------------------------------------------------------
    # HEADER
    # -----------------------------------------------------------------

    st.title(
        "📡 TradeOracle Apex"
    )

    st.subheader(
        "Angel One Live Market Data + AI Analysis"
    )

    st.info(
        "Read-only mode. This application reads Angel One market data "
        "and runs the Apex research/prediction pipeline. "
        "It does not place orders or GTTs."
    )

    # -----------------------------------------------------------------
    # DATA MODE SAFETY CHECK
    # -----------------------------------------------------------------

    if DATA_MODE != "live":

        st.error(
            "APEX_DATA_MODE is not 'live'. "
            "Set it to 'live' for the production "
            "read-only Angel One connection."
        )

        st.stop()

    # =================================================================
    # MARKET SELECTION
    # =================================================================

    st.header(
        "Market selection"
    )

    # -----------------------------------------------------------------
    # EXCHANGE
    # -----------------------------------------------------------------

    exchange_options = (
        "NSE",
        "MCX",
    )

    configured_exchange = (
        ANGELONE_EXCHANGE
        or "NSE"
    ).strip().upper()

    default_exchange_index = (
        exchange_options.index(
            configured_exchange
        )
        if configured_exchange in exchange_options
        else 0
    )

    exchange = st.selectbox(
        "Angel One exchange",
        options=exchange_options,
        index=default_exchange_index,
        help=(
            "NSE for NIFTY/equities. "
            "MCX for commodities such as GOLD, "
            "SILVER or CRUDEOIL."
        ),
    )

    # -----------------------------------------------------------------
    # SYMBOL
    # -----------------------------------------------------------------

    default_symbol = (
        default_symbol_for_exchange(
            exchange
        )
    )

    symbol = st.text_input(
        "Angel One symbol",
        value=default_symbol,
        help=(
            "Examples: NIFTY or SBIN on NSE; "
            "GOLD, SILVER or CRUDEOIL on MCX."
        ),
    ).strip()

    if not symbol:

        st.error(
            "Please enter an Angel One symbol."
        )

        st.stop()

    # -----------------------------------------------------------------
    # PREDICTION HORIZON
    # -----------------------------------------------------------------

    horizon_options = tuple(
        PREDICTION_HORIZONS_MINUTES
    )

    if not horizon_options:
        st.error(
            "No prediction horizons are configured."
        )
        st.stop()

    configured_horizon = int(
        PREDICTION_HORIZON_MINUTES
    )

    if (
        configured_horizon
        in horizon_options
    ):

        default_horizon_index = (
            horizon_options.index(
                configured_horizon
            )
        )

    else:

        default_horizon_index = (
            len(horizon_options) - 1
        )

    horizon = st.selectbox(
        "Prediction horizon (minutes)",
        options=horizon_options,
        index=default_horizon_index,
        help=(
            "Forecast horizons are configured centrally. "
            "The supported Apex horizons are the configured "
            "5 / 15 / 30 / 60 minute horizons; "
            "no horizon above 60 minutes should be configured."
        ),
    )

    # -----------------------------------------------------------------
    # CURRENT CONFIGURATION
    # -----------------------------------------------------------------

    st.caption(
        f"Exchange: {exchange}  •  "
        f"Symbol: {symbol}  •  "
        f"History: {ANGELONE_HISTORY_BARS} bars  •  "
        f"Horizon: {horizon} minutes"
    )

    # =================================================================
    # 1. ANGEL ONE CONNECTION / LIVE LTP
    # =================================================================

    st.header(
        "1. Angel One connection"
    )

    provider = None

    try:

        provider = get_provider()

        ltp = live_ltp_check(
            provider,
            symbol,
            exchange,
        )

    except Exception as exc:

        provider = None

        ltp = {
            "provider_connected":
                False,

            "status":
                "ERROR",

            "fresh":
                False,

            "records":
                0,

            "source":
                None,

            "record":
                None,

            "error":
                (
                    f"{type(exc).__name__}: "
                    f"{exc}"
                ),
        }

    # -----------------------------------------------------------------
    # LTP STATUS METRICS
    # -----------------------------------------------------------------

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
            if ltp[
                "record"
            ]
            else "—"
        ),
    )

    c3.metric(
        "Fresh",
        (
            "YES"
            if ltp[
                "fresh"
            ]
            else "NO"
        ),
    )

    c4.metric(
        "Gateway",
        ltp[
            "status"
        ],
    )

    # -----------------------------------------------------------------
    # CONNECTION ERROR
    # -----------------------------------------------------------------

    if ltp["error"]:

        st.error(
            ltp["error"]
        )

    # -----------------------------------------------------------------
    # RAW LATEST RECORD
    # -----------------------------------------------------------------

    if ltp["record"]:

        st.write(
            "Latest Angel One record"
        )

        st.json(
            ltp["record"]
        )

    # =================================================================
    # 2. MARKET HISTORY + MASTER BRAIN
    # =================================================================

    st.header(
        "2. Real market-data analysis"
    )

    if provider is None:

        st.warning(
            "Angel One provider is not connected, "
            "so analysis is stopped."
        )

        st.stop()

    # -----------------------------------------------------------------
    # RUN APEX
    # -----------------------------------------------------------------

    with st.spinner(
        "Fetching Angel One candles "
        "and running Apex engines..."
    ):

        try:

            result = run_analysis(
                provider,
                symbol,
                exchange,
                int(horizon),
            )

        except Exception as exc:

            st.error(
                f"{type(exc).__name__}: {exc}"
            )

            st.stop()

    # -----------------------------------------------------------------
    # RESULT SECTIONS
    # -----------------------------------------------------------------

    md = result.get(
        "market_data",
        {},
    )

    quality = md.get(
        "quality",
        {},
    )

    brain = result.get(
        "master_brain",
        {},
    )

    # -----------------------------------------------------------------
    # MARKET DATA METRICS
    # -----------------------------------------------------------------

    a, b, c, d = st.columns(4)

    a.metric(
        "Candles",
        md.get(
            "records",
            0,
        ),
    )

    b.metric(
        "Data Status",
        quality.get(
            "status",
            "UNKNOWN",
        ),
    )

    c.metric(
        "Fresh",
        (
            "YES"
            if md.get(
                "fresh",
                False,
            )
            else "NO"
        ),
    )

    d.metric(
        "Source",
        md.get(
            "source"
        )
        or "—",
    )

    # -----------------------------------------------------------------
    # MARKET DATA VALIDATION
    # -----------------------------------------------------------------

    min_history = int(
        MIN_HISTORY_BARS
    )

    record_count = int(
        md.get(
            "records",
            0,
        )
        or 0
    )

    if record_count < min_history:

        st.warning(
            f"Prediction is withheld until at least "
            f"{min_history} valid candles are available."
        )

    elif not brain:

        st.warning(
            "Master Brain did not produce an analysis result."
        )

    else:

        # =============================================================
        # CURRENT AI ASSESSMENT
        # =============================================================

        decision = brain.get(
            "decision",
            {},
        )

        direction = decision.get(
            "direction",
            "UNKNOWN",
        )

        try:

            confidence = (
                float(
                    decision.get(
                        "confidence",
                        0.0,
                    )
                )
                * 100.0
            )

        except (
            TypeError,
            ValueError,
        ):

            confidence = 0.0

        try:

            score = float(
                decision.get(
                    "score",
                    0.0,
                )
            )

        except (
            TypeError,
            ValueError,
        ):

            score = 0.0

        st.subheader(
            "Current AI assessment"
        )

        p1, p2, p3 = st.columns(3)

        p1.metric(
            "Direction",
            direction,
        )

        p2.metric(
            "Confidence",
            f"{confidence:.1f}%",
        )

        p3.metric(
            "Score",
            f"{score:.4f}",
        )

        # -------------------------------------------------------------
        # DIRECTION MESSAGE
        # -------------------------------------------------------------

        if direction == "UP":

            st.success(
                "UP — research/prediction evidence "
                "currently leans upward."
            )

        elif direction == "DOWN":

            st.error(
                "DOWN — research/prediction evidence "
                "currently leans downward."
            )

        else:

            st.info(
                "SIDEWAYS — evidence does not justify "
                "a directional call."
            )

        # -------------------------------------------------------------
        # DECISION REASONS
        # -------------------------------------------------------------

        reasons = decision.get(
            "reasons",
            [],
        )

        if reasons:

            st.subheader(
                "Why"
            )

            for reason in reasons:

                st.write(
                    f"• {reason}"
                )

        # -------------------------------------------------------------
        # RESEARCH EVIDENCE
        # -------------------------------------------------------------

        with st.expander(
            "Research evidence"
        ):

            st.json(
                brain.get(
                    "research_evidence",
                    [],
                )
            )

        # -------------------------------------------------------------
        # PRIMARY PREDICTION EVIDENCE
        # -------------------------------------------------------------

        with st.expander(
            "Primary prediction evidence"
        ):

            st.json(
                brain.get(
                    "prediction_evidence",
                    [],
                )
            )

        # -------------------------------------------------------------
        # DERIVED / META ANALYSIS
        # -------------------------------------------------------------

        with st.expander(
            "Derived / meta analysis"
        ):

            st.json(
                brain.get(
                    "derived",
                    {},
                )
            )

    # =================================================================
    # 3. APEX RUNTIME
    # =================================================================

    st.header(
        "3. Apex runtime"
    )

    registered = result.get(
        "registered_engines",
        [],
    )

    st.success(
        f"{len(registered)} validated engines are registered."
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

    # =================================================================
    # 4. MARKET DATA QUALITY
    # =================================================================

    st.header(
        "4. Market-data quality"
    )

    quality_status = quality.get(
        "status",
        "UNKNOWN",
    )

    quality_count = quality.get(
        "count",
        record_count,
    )

    quality_fresh = bool(
        quality.get(
            "fresh",
            False,
        )
    )

    q1, q2, q3 = st.columns(3)

    q1.metric(
        "Quality status",
        quality_status,
    )

    q2.metric(
        "Valid records",
        quality_count,
    )

    q3.metric(
        "Fresh",
        (
            "YES"
            if quality_fresh
            else "NO"
        ),
    )

    if quality.get(
        "error"
    ):

        st.warning(
            quality[
                "error"
            ]
        )

    # =================================================================
    # 5. TRADING SAFETY STATUS
    # =================================================================

    st.header(
        "5. Trading status"
    )

    st.success(
        "ORDER PLACEMENT: DISABLED  •  "
        "GTT: DISABLED  •  "
        "READ-ONLY MARKET DATA: ENABLED"
    )

    st.caption(
        "Angel One sessions are subject to broker/API session rules. "
        "The application re-authenticates when the cached provider expires."
    )

    st.caption(
        "Current market selection: "
        f"{exchange}:{symbol}"
    )

    st.caption(
        "Selected forecast horizon: "
        f"{horizon} minutes"
    )

    st.caption(
        "Last UI refresh: "
        + datetime.now(
            IST
        ).strftime(
            "%Y-%m-%d %H:%M:%S IST"
        )
    )


# =====================================================================
# APPLICATION ENTRY POINT
# =====================================================================

if __name__ == "__main__":
    main()
