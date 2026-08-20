"""
TradeOracle Apex - Commodity Auto Board.

This page is isolated from the existing main Streamlit page.

Responsibilities:
- Commodity-only sidebar configuration
- Reuse the existing authenticated Angel One provider
- Run selected MCX commodities
- Use canonical Apex horizons: 5 / 15 / 30 / 60 minutes
- Display one compact comparison board
- Display important analysis details for each commodity
- Refresh at a safe interval to reduce unnecessary API pressure
- Explicitly use MCX exchange
- No order placement
"""

from __future__ import annotations

import streamlit as st

from config import (
    ANGELONE_HISTORY_BARS,
    DATA_MODE,
    LIVE_DATA_MAX_AGE_SECONDS,
)

from core.orchestrator import ApexOrchestrator
from data.market_data import MarketData
from data.provider_loader import load_market_provider


# ================================================================
# PAGE CONFIG
# ================================================================

st.set_page_config(
    page_title="TradeOracle Apex - Commodity Auto Board",
    page_icon="🛢️",
    layout="wide",
)


# ================================================================
# EXISTING ANGEL ONE CONNECTION
# ================================================================

@st.cache_resource(
    ttl=1800,
    show_spinner=False,
)
def get_provider():
    """
    Reuse the existing authenticated Angel One provider/session.
    """
    return load_market_provider()


# ================================================================
# COMMODITY DEFAULT SETTINGS
# ================================================================

DEFAULT_COMMODITIES = {
    "GOLDM": 5,
    "NATURALGAS": 15,
    "CRUDEOILM": 30,
    "SILVERM": 60,
}

SUPPORTED_HORIZONS = [
    5,
    15,
    30,
    60,
]


# ================================================================
# SIDEBAR
# ================================================================

with st.sidebar:

    st.header("🛢️ Commodity Auto Board")

    commodity_enabled = st.checkbox(
        "Enable Commodity Board",
        value=True,
        key="commodity_board_enabled",
    )

    st.divider()

    # ------------------------------------------------------------
    # MCX COMMODITIES
    # ------------------------------------------------------------

    st.subheader("MCX Commodities")

    selected_commodities = st.multiselect(
        "Select commodities",
        options=list(
            DEFAULT_COMMODITIES.keys()
        ),
        default=list(
            DEFAULT_COMMODITIES.keys()
        ),
        key="commodity_symbols",
    )

    st.divider()

    # ------------------------------------------------------------
    # PREDICTION HORIZON
    # ------------------------------------------------------------

    st.subheader("Prediction Horizon")

    commodity_horizons: dict[str, int] = {}

    for commodity in selected_commodities:

        default_horizon = DEFAULT_COMMODITIES.get(
            commodity,
            5,
        )

        horizon = st.selectbox(
            commodity,
            options=SUPPORTED_HORIZONS,
            index=SUPPORTED_HORIZONS.index(
                default_horizon
            ),
            format_func=lambda x: (
                f"{x} minutes"
            ),
            key=(
                f"commodity_horizon_"
                f"{commodity}"
            ),
        )

        commodity_horizons[
            commodity
        ] = horizon

    st.divider()

    # ------------------------------------------------------------
    # AUTO REFRESH
    #
    # Default = 60 seconds.
    #
    # The board can run multiple commodities at once.
    # A very short refresh interval would unnecessarily
    # increase repeated market-data/API requests.
    # ------------------------------------------------------------

    st.subheader("Auto Refresh")

    auto_refresh = st.checkbox(
        "Auto refresh",
        value=True,
        key="commodity_auto_refresh",
    )

    refresh_seconds = st.selectbox(
        "Refresh interval",
        options=[
            60,
            120,
            300,
            600,
        ],
        index=0,
        format_func=lambda x: (
            f"{x // 60} minute"
            if x >= 60
            else f"{x} seconds"
        ),
        key="commodity_refresh_seconds",
    )

    st.caption(
        "Default refresh: 60 seconds"
    )

    st.divider()

    # ------------------------------------------------------------
    # CONNECTION
    # ------------------------------------------------------------

    st.subheader("Connection")

    st.caption(
        "Uses the existing Angel One "
        "provider/session."
    )

    st.caption(
        "Exchange: MCX"
    )

    st.caption(
        "Market-data mode: "
        + str(DATA_MODE).upper()
    )

    st.caption(
        "Read-only: Orders/GTT disabled"
    )


# ================================================================
# AUTO REFRESH
# ================================================================

if auto_refresh:

    from streamlit_autorefresh import (
        st_autorefresh,
    )

    st_autorefresh(
        interval=(
            refresh_seconds * 1000
        ),
        key=(
            "commodity_auto_refresh_timer"
        ),
    )


# ================================================================
# PAGE HEADER
# ================================================================

st.title(
    "🛢️ Commodity Auto Board"
)

st.caption(
    "MCX • Angel One Live Market Data • "
    "Apex Multi-Horizon Analysis"
)


# ================================================================
# ENABLE / SELECTION CHECKS
# ================================================================

if not commodity_enabled:

    st.info(
        "Commodity Auto Board is "
        "disabled from the sidebar."
    )

    st.stop()


if not selected_commodities:

    st.warning(
        "Select at least one commodity "
        "from the sidebar."
    )

    st.stop()


# ================================================================
# PROVIDER
# ================================================================

try:

    provider = get_provider()

except Exception as exc:

    st.error(
        "Angel One connection failed: "
        f"{type(exc).__name__}: {exc}"
    )

    st.stop()


if provider is None:

    st.error(
        "Angel One provider is not connected."
    )

    st.stop()


# ================================================================
# SINGLE COMMODITY ANALYSIS
# ================================================================

def run_commodity_analysis(
    symbol: str,
    horizon: int,
) -> dict:
    """
    Run the existing Apex pipeline for one MCX commodity.

    IMPORTANT:
    exchange='MCX' is explicitly passed so that
    commodity requests do not accidentally fall back
    to another exchange.
    """

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
        horizons_minutes=(horizon,),
        exchange="MCX",
    )


# ================================================================
# SAFE VALUE HELPERS
# ================================================================

def safe_float(
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


def get_horizon_result(
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

    return horizons.get(
        str(horizon),
        {},
    )


# ================================================================
# BOARD
# ================================================================

st.subheader(
    "📊 Commodity Market Board"
)

results = []

detail_results = {}


# ================================================================
# RUN ALL SELECTED COMMODITIES
# ================================================================

for symbol in selected_commodities:

    horizon = commodity_horizons[
        symbol
    ]

    try:

        result = run_commodity_analysis(
            symbol,
            horizon,
        )

        detail_results[
            symbol
        ] = result

        horizon_result = (
            get_horizon_result(
                result,
                horizon,
            )
        )

        brain = horizon_result.get(
            "master_brain",
            {},
        )

        decision = brain.get(
            "decision",
            {},
        )

        market_data = (
            horizon_result.get(
                "market_data",
                {},
            )
        )

        if not isinstance(
            market_data,
            dict,
        ):
            market_data = {}

        direction = decision.get(
            "direction",
            "UNKNOWN",
        )

        confidence = (
            safe_float(
                decision.get(
                    "confidence",
                    0.0,
                )
            )
            * 100.0
        )

        score = safe_float(
            decision.get(
                "score",
                0.0,
            )
        )

        price = market_data.get(
            "last_price",
            market_data.get(
                "price",
                "—",
            ),
        )

        data_status = market_data.get(
            "status",
            "UNKNOWN",
        )

        fresh = (
            "YES"
            if market_data.get(
                "fresh",
                False,
            )
            else "NO"
        )

        results.append(
            {
                "Commodity": symbol,
                "Horizon": (
                    f"{horizon} min"
                ),
                "Price": price,
                "Direction": direction,
                "Confidence": (
                    f"{confidence:.1f}%"
                ),
                "Score": (
                    f"{score:.4f}"
                ),
                "Data": data_status,
                "Fresh": fresh,
            }
        )

    except Exception as exc:

        results.append(
            {
                "Commodity": symbol,
                "Horizon": (
                    f"{horizon} min"
                ),
                "Price": "—",
                "Direction": "ERROR",
                "Confidence": "—",
                "Score": "—",
                "Data": "ERROR",
                "Fresh": "NO",
            }
        )

        detail_results[
            symbol
        ] = {
            "_error": (
                f"{type(exc).__name__}: "
                f"{exc}"
            )
        }


# ================================================================
# COMPACT COMPARISON BOARD
# ================================================================

st.subheader(
    "📊 Commodity Comparison"
)

if results:

    st.dataframe(
        results,
        use_container_width=True,
        hide_index=True,
    )


# ================================================================
# QUICK HORIZON SUMMARY
# ================================================================

st.divider()

st.subheader(
    "⏱️ Commodity Horizons"
)

horizon_columns = st.columns(
    len(selected_commodities)
)

for column, symbol in zip(
    horizon_columns,
    selected_commodities,
):

    column.metric(
        symbol,
        (
            f"{commodity_horizons[symbol]}"
            " min"
        ),
    )


# ================================================================
# DETAILED COMMODITY ANALYSIS
# ================================================================

st.divider()

st.subheader(
    "🔎 Commodity Analysis Details"
)


for symbol in selected_commodities:

    horizon = commodity_horizons[
        symbol
    ]

    result = detail_results.get(
        symbol
    )

    # ------------------------------------------------------------
    # NO RESULT
    # ------------------------------------------------------------

    if not result:

        st.error(
            f"{symbol} • "
            f"{horizon} min • "
            "Analysis data unavailable."
        )

        continue

    # ------------------------------------------------------------
    # ERROR RESULT
    # ------------------------------------------------------------

    if "_error" in result:

        st.error(
            f"{symbol} • "
            f"{horizon} min • "
            f"{result['_error']}"
        )

        continue

    horizon_result = (
        get_horizon_result(
            result,
            horizon,
        )
    )

    brain = horizon_result.get(
        "master_brain",
        {},
    )

    decision = brain.get(
        "decision",
        {},
    )

    market_data = (
        horizon_result.get(
            "market_data",
            {},
        )
    )

    if not isinstance(
        market_data,
        dict,
    ):
        market_data = {}

    direction = str(
        decision.get(
            "direction",
            "UNKNOWN",
        )
    )

    confidence = (
        safe_float(
            decision.get(
                "confidence",
                0.0,
            )
        )
        * 100.0
    )

    score = safe_float(
        decision.get(
            "score",
            0.0,
        )
    )

    price = market_data.get(
        "last_price",
        market_data.get(
            "price",
            "—",
        ),
    )

    data_status = market_data.get(
        "status",
        "UNKNOWN",
    )

    fresh = (
        "YES"
        if market_data.get(
            "fresh",
            False,
        )
        else "NO"
    )

    # ------------------------------------------------------------
    # COMMODITY CARD
    # ------------------------------------------------------------

    with st.container(
        border=True
    ):

        st.markdown(
            f"### 🛢️ {symbol} "
            f"• {horizon} min"
        )

        # --------------------------------------------------------
        # PRIMARY METRICS
        # --------------------------------------------------------

        c1, c2, c3, c4 = (
            st.columns(4)
        )

        c1.metric(
            "Live Price",
            str(price),
        )

        c2.metric(
            "Direction",
            direction,
        )

        c3.metric(
            "Confidence",
            f"{confidence:.1f}%",
        )

        c4.metric(
            "Score",
            f"{score:.4f}",
        )

        # --------------------------------------------------------
        # DATA QUALITY
        # --------------------------------------------------------

        c5, c6 = st.columns(2)

        c5.metric(
            "Data",
            str(data_status),
        )

        c6.metric(
            "Fresh",
            fresh,
        )

        # --------------------------------------------------------
        # DIRECTION STATUS
        # --------------------------------------------------------

        direction_upper = (
            direction.upper()
        )

        if direction_upper == "UP":

            st.success(
                f"{symbol} — UP • "
                f"Confidence "
                f"{confidence:.1f}%"
            )

        elif direction_upper == "DOWN":

            st.error(
                f"{symbol} — DOWN • "
                f"Confidence "
                f"{confidence:.1f}%"
            )

        elif (
            direction_upper
            == "SIDEWAYS"
        ):

            st.info(
                f"{symbol} — SIDEWAYS • "
                f"Confidence "
                f"{confidence:.1f}%"
            )

        else:

            st.warning(
                f"{symbol} — "
                f"{direction_upper}"
            )

        # --------------------------------------------------------
        # IMPORTANT DETAILS
        # --------------------------------------------------------

        with st.expander(
            f"📋 {symbol} — "
            "Important Analysis Details"
        ):

            # ====================================================
            # 1. LIVE MARKET DATA
            # ====================================================

            st.markdown(
                "#### 1. Live Market Data"
            )

            if market_data:

                st.json(
                    market_data
                )

            else:

                st.info(
                    "Market-data details "
                    "are not available."
                )

            # ====================================================
            # 2. CURRENT AI ASSESSMENT
            # ====================================================

            st.markdown(
                "#### 2. Current AI Assessment"
            )

            if decision:

                st.json(
                    decision
                )

            else:

                st.info(
                    "Decision details "
                    "are not available."
                )

            # ====================================================
            # 3. MASTER BRAIN
            # ====================================================

            st.markdown(
                "#### 3. Master Brain"
            )

            if brain:

                st.json(
                    brain
                )

            else:

                st.info(
                    "Master Brain details "
                    "are not available."
                )

            # ====================================================
            # 4. FORWARD FORECAST
            # ====================================================

            forward_forecast = (
                horizon_result.get(
                    "forward_forecast"
                )
            )

            if (
                forward_forecast
                is not None
            ):

                st.markdown(
                    "#### 4. Forward Forecast"
                )

                st.json(
                    forward_forecast
                )

            # ====================================================
            # 5. REVERSAL ANALYSIS
            # ====================================================

            reversal_analysis = (
                horizon_result.get(
                    "reversal_analysis"
                )
            )

            if (
                reversal_analysis
                is not None
            ):

                st.markdown(
                    "#### 5. Reversal Analysis"
                )

                st.json(
                    reversal_analysis
                )

            # ====================================================
            # 6. RESEARCH EVIDENCE
            # ====================================================

            research_evidence = (
                horizon_result.get(
                    "research_evidence"
                )
            )

            if (
                research_evidence
                is not None
            ):

                st.markdown(
                    "#### 6. Research Evidence"
                )

                st.json(
                    research_evidence
                )

            # ====================================================
            # 7. PRIMARY PREDICTION EVIDENCE
            # ====================================================

            primary_prediction = (
                horizon_result.get(
                    "primary_prediction_evidence"
                )
            )

            if (
                primary_prediction
                is not None
            ):

                st.markdown(
                    "#### 7. Primary Prediction Evidence"
                )

                st.json(
                    primary_prediction
                )

            # ====================================================
            # 8. DERIVED / META ANALYSIS
            # ====================================================

            derived_analysis = (
                horizon_result.get(
                    "derived_meta_analysis"
                )
            )

            if (
                derived_analysis
                is not None
            ):

                st.markdown(
                    "#### 8. Derived / Meta Analysis"
                )

                st.json(
                    derived_analysis
                )


# ================================================================
# CONNECTION SUMMARY
# ================================================================

st.divider()

st.subheader(
    "🔌 Connection Summary"
)

c1, c2, c3, c4 = (
    st.columns(4)
)

c1.metric(
    "Angel One",
    "CONNECTED",
)

c2.metric(
    "Exchange",
    "MCX",
)

c3.metric(
    "Commodities",
    str(
        len(
            selected_commodities
        )
    ),
)

c4.metric(
    "Horizons",
    "5 / 15 / 30 / 60",
)


# ================================================================
# READ-ONLY SAFETY
# ================================================================

st.success(
    "READ-ONLY MARKET DATA ENABLED • "
    "ORDER PLACEMENT DISABLED • "
    "GTT DISABLED"
)

st.caption(
    "Uses the existing Angel One "
    "provider/session. "
    "No orders or GTTs are placed."
    )
