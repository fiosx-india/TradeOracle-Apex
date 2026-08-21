"""
TradeOracle Apex - Commodity Auto Board

Commodity-only presentation layer.

Responsibilities:
- Commodity-only sidebar configuration
- Reuse the existing authenticated Angel One provider
- Run selected MCX commodities
- Use canonical Apex horizons: 5 / 15 / 30 / 60 minutes
- Display one compact comparison board
- Display human-readable analysis summaries
- Keep full Apex evidence available inside expanders
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
    """
    Reuse the existing Angel One authentication/session.
    """
    return load_market_provider()


# ================================================================
# COMMODITY SETTINGS
# ================================================================

DEFAULT_COMMODITIES = {
    "GOLDM": 5,
    "NATURALGAS": 15,
    "CRUDEOILM": 30,
    "SILVERM": 60,
}

SUPPORTED_HORIZONS = [5, 15, 30, 60]

# Keep refresh conservative to avoid unnecessary API polling.
REFRESH_OPTIONS = [30, 60]


# ================================================================
# SMALL HELPERS
# ================================================================

def safe_float(value, default=0.0):
    """
    Safely convert numeric values.
    """
    try:
        if value is None:
            return default

        return float(value)

    except (TypeError, ValueError):
        return default


def get_horizon_result(result: dict, horizon: int) -> dict:
    """
    Apex may expose horizon keys as strings or integers.
    Handle both without changing the Apex architecture.
    """

    horizons = result.get("horizons", {})

    if not isinstance(horizons, dict):
        return {}

    horizon_result = horizons.get(str(horizon))

    if horizon_result is None:
        horizon_result = horizons.get(horizon)

    if isinstance(horizon_result, dict):
        return horizon_result

    return {}


def get_direction_icon(direction: str) -> str:
    """
    Visual direction indicator.
    """

    direction = str(direction or "").upper()

    if direction == "UP":
        return "🟢"

    if direction == "DOWN":
        return "🔴"

    if direction in {"SIDEWAYS", "NEUTRAL"}:
        return "🔵"

    if direction in {"UNKNOWN", "ERROR"}:
        return "⚪"

    return "⚪"


def format_price(value):
    """
    Keep price readable without changing source data.
    """

    if value in (None, "", "—"):
        return "—"

    try:
        number = float(value)

        if number.is_integer():
            return f"{number:,.0f}"

        return f"{number:,.2f}"

    except (TypeError, ValueError):
        return str(value)


# ================================================================
# HUMAN-READABLE SUMMARY
# ================================================================

def build_meaning_summary(
    symbol: str,
    horizon: int,
    direction: str,
    confidence: float,
    score: float,
    market_data: dict,
    brain: dict,
    decision: dict,
) -> str:
    """
    Convert Apex output into a short human-readable paragraph.

    This function does NOT calculate a new prediction.
    It only explains the existing Apex result.
    """

    direction = str(direction or "UNKNOWN").upper()

    data_status = str(
        market_data.get(
            "status",
            "UNKNOWN",
        )
    ).upper()

    fresh = bool(
        market_data.get(
            "fresh",
            False,
        )
    )

    signal_strength = str(
        decision.get(
            "signal_strength",
            "",
        )
    ).upper()

    agreement = safe_float(
        decision.get(
            "agreement",
            0.0,
        )
    )

    if agreement <= 1:
        agreement_pct = agreement * 100
    else:
        agreement_pct = agreement

    # ------------------------------------------------------------
    # Direction text
    # ------------------------------------------------------------

    if direction == "UP":
        direction_text = "மேல்நோக்கிய"

    elif direction == "DOWN":
        direction_text = "கீழ்நோக்கிய"

    elif direction in {"SIDEWAYS", "NEUTRAL"}:
        direction_text = "தெளிவான திசையில்லாத / sideways"

    else:
        direction_text = "தெளிவாக உறுதி செய்யப்படாத"

    # ------------------------------------------------------------
    # Confidence text
    # ------------------------------------------------------------

    if confidence >= 70:
        confidence_text = "வலுவாக உள்ளது"

    elif confidence >= 50:
        confidence_text = "மிதமான நிலையில் உள்ளது"

    else:
        confidence_text = "பலவீனமாக உள்ளது"

    # ------------------------------------------------------------
    # Data quality text
    # ------------------------------------------------------------

    if data_status == "OK" and fresh:
        data_text = "தற்போதைய market data fresh-ஆக உள்ளது."

    elif data_status == "STALE" or not fresh:
        data_text = (
            "Market data fresh இல்லை; எனவே இந்த signal-ஐ "
            "எச்சரிக்கையுடன் பார்க்க வேண்டும்."
        )

    else:
        data_text = (
            "Market-data status முழுமையாக உறுதி செய்யப்படவில்லை."
        )

    # ------------------------------------------------------------
    # Signal status
    # ------------------------------------------------------------

    if signal_strength == "WITHHELD":
        signal_text = (
            "Apex signal strength-ஐ உறுதிப்படுத்தாமல் வைத்துள்ளது."
        )

    elif agreement_pct > 70:
        signal_text = (
            f"பல analysis signals ஒன்றுக்கொன்று ஆதரவாக உள்ளன "
            f"(agreement சுமார் {agreement_pct:.0f}%)."
        )

    elif agreement_pct > 0:
        signal_text = (
            f"Analysis signals-ல் ஓரளவு agreement உள்ளது "
            f"(சுமார் {agreement_pct:.0f}%)."
        )

    else:
        signal_text = (
            "Analysis signals-ல் போதுமான directional agreement இல்லை."
        )

    # ------------------------------------------------------------
    # Final paragraph
    # ------------------------------------------------------------

    return (
        f"{symbol} தற்போது {horizon}-minute horizon-ல் "
        f"{direction_text} direction-ஐ காட்டுகிறது. "
        f"Confidence {confidence:.1f}% என்பதால் signal {confidence_text}. "
        f"{data_text} "
        f"{signal_text} "
        f"Score {score:.4f} என்பதால் தற்போதைய Apex assessment-ஐ "
        f"மட்டுமே பிரதிபலிக்கிறது; இது புதிய prediction calculation அல்ல."
    )


# ================================================================
# IMPORTANT SIGNAL EXTRACTION
# ================================================================

def extract_important_signals(
    horizon_result: dict,
    decision: dict,
    max_items: int = 5,
) -> list[str]:
    """
    Extract only the most useful human-readable reasons.

    Raw engine JSON is deliberately NOT displayed here.
    """

    signals: list[str] = []

    # ------------------------------------------------------------
    # Master brain / decision reasons
    # ------------------------------------------------------------

    reasons = decision.get(
        "reasons",
        [],
    )

    if isinstance(reasons, list):

        for reason in reasons:

            if not isinstance(reason, str):
                continue

            cleaned = " ".join(
                reason.strip().split()
            )

            if cleaned and cleaned not in signals:
                signals.append(cleaned)

            if len(signals) >= max_items:
                return signals

    # ------------------------------------------------------------
    # Forward prediction evidence
    # ------------------------------------------------------------

    prediction_evidence = horizon_result.get(
        "prediction_evidence",
        [],
    )

    if isinstance(prediction_evidence, list):

        for item in prediction_evidence:

            if not isinstance(item, dict):
                continue

            reason = item.get(
                "reason",
                "",
            )

            if not reason:
                continue

            cleaned = " ".join(
                str(reason).strip().split()
            )

            if cleaned and cleaned not in signals:
                signals.append(cleaned)

            if len(signals) >= max_items:
                return signals

    return signals[:max_items]


# ================================================================
# COMPACT DETAILS
# ================================================================

def render_compact_details(
    symbol: str,
    horizon: int,
    result: dict,
    horizon_result: dict,
    market_data: dict,
    decision: dict,
):
    """
    Display selected important Apex details.

    Full raw evidence remains available below,
    but is collapsed by default.
    """

    # ------------------------------------------------------------
    # Market information
    # ------------------------------------------------------------

    price = market_data.get(
        "last_price",
        market_data.get(
            "price",
            "—",
        ),
    )

    status = str(
        market_data.get(
            "status",
            "UNKNOWN",
        )
    ).upper()

    fresh = (
        "YES"
        if market_data.get(
            "fresh",
            False,
        )
        else "NO"
    )

    st.markdown("### 📊 Market Snapshot")

    c1, c2, c3 = st.columns(3)

    c1.metric(
        "Live Price",
        format_price(price),
    )

    c2.metric(
        "Data",
        status,
    )

    c3.metric(
        "Fresh",
        fresh,
    )

    # ------------------------------------------------------------
    # Apex decision
    # ------------------------------------------------------------

    direction = str(
        decision.get(
            "direction",
            "UNKNOWN",
        )
    ).upper()

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

    signal_strength = str(
        decision.get(
            "signal_strength",
            "",
        )
    )

    agreement = safe_float(
        decision.get(
            "agreement",
            0.0,
        )
    )

    if agreement <= 1:
        agreement_pct = agreement * 100
    else:
        agreement_pct = agreement

    st.markdown("### 🧠 Apex Assessment")

    c1, c2, c3, c4 = st.columns(4)

    c1.metric(
        "Direction",
        f"{get_direction_icon(direction)} {direction}",
    )

    c2.metric(
        "Confidence",
        f"{confidence:.1f}%",
    )

    c3.metric(
        "Score",
        f"{score:.4f}",
    )

    c4.metric(
        "Agreement",
        f"{agreement_pct:.1f}%",
    )

    if signal_strength:
        st.caption(
            f"Signal strength: **{signal_strength}**"
        )

    # ------------------------------------------------------------
    # Raw decision reasons
    # ------------------------------------------------------------

    reasons = decision.get(
        "reasons",
        [],
    )

    if isinstance(reasons, list) and reasons:

        st.markdown("### 📌 Key Reasons")

        displayed = 0

        for reason in reasons:

            if not isinstance(reason, str):
                continue

            cleaned = " ".join(
                reason.strip().split()
            )

            if not cleaned:
                continue

            st.markdown(
                f"- {cleaned}"
            )

            displayed += 1

            if displayed >= 5:
                break


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
        options=list(
            DEFAULT_COMMODITIES.keys()
        ),
        default=list(
            DEFAULT_COMMODITIES.keys()
        ),
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
        options=REFRESH_OPTIONS,
        index=1,
        format_func=lambda x: (
            f"{x} seconds"
            if x < 60
            else "1 minute"
        ),
        key="commodity_refresh_seconds",
    )

    st.caption(
        "Default refresh: 60 seconds. "
        "This avoids unnecessary API polling."
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
# RUN ALL COMMODITIES
# ================================================================

analysis_results: dict[str, dict] = {}

errors: dict[str, str] = {}

for symbol in selected_commodities:

    horizon = commodity_horizons[symbol]

    try:

        analysis_results[symbol] = (
            run_commodity_analysis(
                symbol,
                horizon,
            )
        )

    except Exception as exc:

        errors[symbol] = (
            f"{type(exc).__name__}: {exc}"
        )


# ================================================================
# COMPARISON BOARD
# ================================================================

st.subheader("📊 Commodity Comparison")

comparison_rows = []

for symbol in selected_commodities:

    horizon = commodity_horizons[symbol]

    if symbol in errors:

        comparison_rows.append(
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

        continue

    result = analysis_results.get(
        symbol,
        {},
    )

    horizon_result = get_horizon_result(
        result,
        horizon,
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

    direction = str(
        decision.get(
            "direction",
            "UNKNOWN",
        )
    ).upper()

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

    comparison_rows.append(
        {
            "Commodity": symbol,
            "Horizon": f"{horizon} min",
            "Price": format_price(price),
            "Direction": direction,
            "Confidence": f"{confidence:.1f}%",
            "Score": f"{score:.4f}",
            "Data": str(
                market_data.get(
                    "status",
                    "UNKNOWN",
                )
            ).upper(),
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


if comparison_rows:

    st.dataframe(
        comparison_rows,
        use_container_width=True,
        hide_index=True,
    )


# ================================================================
# HORIZON SUMMARY
# ================================================================

st.subheader("⏱️ Commodity Horizons")

horizon_columns = st.columns(
    max(
        1,
        len(selected_commodities),
    )
)

for column, symbol in zip(
    horizon_columns,
    selected_commodities,
):

    column.metric(
        symbol,
        f"{commodity_horizons[symbol]} min",
    )


# ================================================================
# COMMODITY ANALYSIS
# ================================================================

st.subheader("🔎 Commodity Analysis")


for symbol in selected_commodities:

    horizon = commodity_horizons[symbol]

    # ------------------------------------------------------------
    # Error state
    # ------------------------------------------------------------

    if symbol in errors:

        with st.container(border=True):

            st.markdown(
                f"## 🛢️ {symbol} · {horizon} min"
            )

            st.error(
                "🔴 Market analysis could not be completed."
            )

            st.caption(
                "The Apex calculation was not replaced or "
                "fabricated. The actual runtime error is shown below "
                "for troubleshooting."
            )

            with st.expander(
                f"⚠️ {symbol} — Runtime Error",
                expanded=False,
            ):

                st.code(
                    errors[symbol]
                )

        continue

    # ------------------------------------------------------------
    # Get result
    # ------------------------------------------------------------

    result = analysis_results.get(
        symbol,
        {},
    )

    horizon_result = get_horizon_result(
        result,
        horizon,
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

    direction = str(
        decision.get(
            "direction",
            "UNKNOWN",
        )
    ).upper()

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

    data_status = str(
        market_data.get(
            "status",
            "UNKNOWN",
        )
    ).upper()

    fresh = (
        "YES"
        if market_data.get(
            "fresh",
            False,
        )
        else "NO"
    )

    # ------------------------------------------------------------
    # Main card
    # ------------------------------------------------------------

    with st.container(border=True):

        st.markdown(
            f"## 🛢️ {symbol} · {horizon} min"
        )

        # --------------------------------------------------------
        # Main metrics
        # --------------------------------------------------------

        c1, c2, c3, c4 = st.columns(4)

        c1.metric(
            "Live Price",
            format_price(price),
        )

        c2.metric(
            "Direction",
            f"{get_direction_icon(direction)} {direction}",
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
        # Data status
        # --------------------------------------------------------

        c1, c2 = st.columns(2)

        c1.metric(
            "Data",
            data_status,
        )

        c2.metric(
            "Fresh",
            fresh,
        )

        # --------------------------------------------------------
        # Human-readable explanation
        # --------------------------------------------------------

        st.markdown("### 🧠 What this means")

        meaning = build_meaning_summary(
            symbol=symbol,
            horizon=horizon,
            direction=direction,
            confidence=confidence,
            score=score,
            market_data=market_data,
            brain=brain,
            decision=decision,
        )

        st.info(meaning)

        # --------------------------------------------------------
        # Important signals
        # --------------------------------------------------------

        st.markdown("### 📌 Important signals")

        signals = extract_important_signals(
            horizon_result=horizon_result,
            decision=decision,
            max_items=5,
        )

        if signals:

            for signal in signals:

                st.markdown(
                    f"- {signal}"
                )

        else:

            st.caption(
                "No additional concise signals are available."
            )

        # --------------------------------------------------------
        # Compact selected details
        # --------------------------------------------------------

        with st.expander(
            f"📋 {symbol} — Important Analysis Details",
            expanded=False,
        ):

            render_compact_details(
                symbol=symbol,
                horizon=horizon,
                result=result,
                horizon_result=horizon_result,
                market_data=market_data,
                decision=decision,
            )

        # --------------------------------------------------------
        # Full Apex evidence
        # --------------------------------------------------------

        with st.expander(
            f"🔬 {symbol} — Full Apex Evidence (optional)",
            expanded=False,
        ):

            st.caption(
                "Developer / advanced inspection only. "
                "The complete Apex result is preserved here."
            )

            st.json(
                horizon_result
            )


# ================================================================
# CONNECTION SUMMARY
# ================================================================

st.divider()

st.subheader("🔌 Connection Summary")

c1, c2, c3, c4 = st.columns(4)

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
    str(len(selected_commodities)),
)

c4.metric(
    "Horizons",
    "5 / 15 / 30 / 60",
)

st.caption(
    "Read-only mode. No orders or GTTs are placed."
)
