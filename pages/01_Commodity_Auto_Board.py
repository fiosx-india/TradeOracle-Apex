"""TradeOracle Apex - Commodity Auto Board.

This page is isolated from the existing main Streamlit page.

Responsibilities:
- Commodity-only sidebar configuration
- Reuse the existing authenticated Angel One provider
- Run selected MCX commodities
- Use canonical Apex horizons: 5 / 15 / 30 / 60 minutes
- Display one compact comparison board
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

@st.cache_resource(ttl=1800, show_spinner=False)
def get_provider():
    """Reuse the existing Angel One authentication."""
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

SUPPORTED_HORIZONS = [5, 15, 30, 60]


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

    st.subheader("MCX Commodities")

    selected_commodities = st.multiselect(
        "Select commodities",
        options=list(DEFAULT_COMMODITIES.keys()),
        default=list(DEFAULT_COMMODITIES.keys()),
        key="commodity_symbols",
    )

    st.divider()

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
            format_func=lambda x: f"{x} minutes",
            key=f"commodity_horizon_{commodity}",
        )

        commodity_horizons[commodity] = horizon

    st.divider()

    st.subheader("Auto Refresh")

    auto_refresh = st.checkbox(
        "Auto refresh",
        value=True,
        key="commodity_auto_refresh",
    )

    refresh_seconds = st.selectbox(
        "Refresh interval",
        options=[10, 15, 30, 60],
        index=1,
        format_func=lambda x: f"{x} seconds",
        key="commodity_refresh_seconds",
    )

    st.divider()

    st.subheader("Connection")

    st.caption(
        "Uses the existing Angel One provider/session."
    )

    st.caption(
        "Market-data mode: "
        + str(DATA_MODE).upper()
    )


# ================================================================
# AUTO REFRESH
# ================================================================

if auto_refresh:
    from streamlit_autorefresh import st_autorefresh

    st_autorefresh(
        interval=refresh_seconds * 1000,
        key="commodity_auto_refresh_timer",
    )


# ================================================================
# PAGE HEADER
# ================================================================

st.title("🛢️ Commodity Auto Board")

st.caption(
    "MCX • Angel One Live Market Data • "
    "Apex Multi-Horizon Analysis"
)

if not commodity_enabled:
    st.info(
        "Commodity Auto Board is disabled from the sidebar."
    )
    st.stop()

if not selected_commodities:
    st.warning(
        "Select at least one commodity from the sidebar."
    )
    st.stop()


# ================================================================
# PROVIDER
# ================================================================

try:
    provider = get_provider()

except Exception as exc:
    st.error(
        f"Angel One connection failed: "
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

    gateway = MarketData(
        provider=provider,
        max_age_seconds=LIVE_DATA_MAX_AGE_SECONDS,
    )

    orchestrator = ApexOrchestrator(
        market_data=gateway,
        max_age_seconds=LIVE_DATA_MAX_AGE_SECONDS,
    )

    return orchestrator.run(
        symbol=symbol,
        limit=ANGELONE_HISTORY_BARS,
        horizons_minutes=(horizon,),
    )


# ================================================================
# BOARD
# ================================================================

st.subheader("📊 Commodity Market Board")

results = []


for symbol in selected_commodities:

    horizon = commodity_horizons[symbol]

    try:

        result = run_commodity_analysis(
            symbol,
            horizon,
        )

        horizon_result = (
            result
            .get("horizons", {})
            .get(str(horizon), {})
        )

        brain = horizon_result.get(
            "master_brain",
            {},
        )

        decision = brain.get(
            "decision",
            {},
        )

        market_data = horizon_result.get(
            "market_data",
            {},
        )

        direction = decision.get(
            "direction",
            "UNKNOWN",
        )

        confidence = float(
            decision.get(
                "confidence",
                0.0,
            )
        ) * 100.0

        score = float(
            decision.get(
                "score",
                0.0,
            )
        )

        price = "—"

        if market_data:
            price = market_data.get(
                "last_price",
                market_data.get(
                    "price",
                    "—",
                ),
            )

        results.append(
            {
                "Commodity": symbol,
                "Horizon": f"{horizon} min",
                "Price": price,
                "Direction": direction,
                "Confidence": f"{confidence:.1f}%",
                "Score": f"{score:.4f}",
                "Data": market_data.get(
                    "status",
                    "UNKNOWN",
                ),
                "Fresh": (
                    "YES"
                    if market_data.get(
                        "fresh",
                        False,
                    )
                    else "NO"
                ),
            }
        )

    except Exception as exc:

        results.append(
            {
                "Commodity": symbol,
                "Horizon": f"{horizon} min",
                "Price": "—",
                "Direction": "ERROR",
                "Confidence": "—",
                "Score": "—",
                "Data": "ERROR",
                "Fresh": "NO",
            }
        )


# ================================================================
# DISPLAY
# ================================================================

if results:

    st.dataframe(
        results,
        use_container_width=True,
        hide_index=True,
    )


# ================================================================
# CONNECTION SUMMARY
# ================================================================

st.divider()

c1, c2, c3 = st.columns(3)

c1.metric(
    "Angel One",
    "CONNECTED",
)

c2.metric(
    "Commodities",
    str(len(selected_commodities)),
)

c3.metric(
    "Horizons",
    "5 / 15 / 30 / 60",
)


st.caption(
    "Read-only mode. No orders or GTTs are placed."
      )
