"""
TradeOracle Apex - Commodity Auto Board

Commodity-only Streamlit page.

Design:
- Reuses the existing authenticated Angel One provider.
- Keeps the existing Apex analysis/orchestration untouched.
- Shows a compact comparison board first.
- Shows a short human-readable explanation for each commodity.
- Keeps detailed evidence available inside collapsed sections.
- No order placement / no GTT.
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
    """Reuse the existing Angel One authentication/session."""
    return load_market_provider()


# ================================================================
# COMMODITY DEFAULTS
# ================================================================

DEFAULT_COMMODITIES = {
    "GOLDM": 5,
    "NATURALGAS": 15,
    "CRUDEOILM": 30,
    "SILVERM": 60,
}

SUPPORTED_HORIZONS = [5, 15, 30, 60]

# Keep auto-refresh conservative to avoid unnecessary API pressure.
REFRESH_OPTIONS = [30, 60, 120]


# ================================================================
# HELPERS
# ================================================================

def _safe_float(value, default=0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _first_non_empty(*values, default="") -> str:
    for value in values:
        if value is not None and str(value).strip():
            return str(value).strip()
    return default


def _direction_label(direction: str) -> str:
    direction = str(direction or "UNKNOWN").upper()

    if direction == "UP":
        return "UP"
    if direction == "DOWN":
        return "DOWN"
    if direction == "SIDEWAYS":
        return "SIDEWAYS"
    return direction


def _freshness_text(market_data: dict) -> str:
    status = str(market_data.get("status", "UNKNOWN")).upper()
    fresh = bool(market_data.get("fresh", False))

    if fresh and status == "OK":
        return "Fresh live market data is available."
    if status == "STALE":
        age = market_data.get("age_seconds")
        if age is not None:
            return f"Market data is stale ({_safe_float(age):.0f}s old)."
        return "Market data is stale and should not be treated as a fresh signal."
    if not fresh:
        return "Current market data is not fresh."
    return f"Market-data status: {status}."


def _extract_key_evidence(horizon_result: dict, decision: dict) -> list[str]:
    """
    Extract only the most useful evidence from the existing Apex output.
    No engine calculation is changed here.
    """
    evidence_lines: list[str] = []

    reasons = decision.get("reasons", [])
    if isinstance(reasons, list):
        for reason in reasons[:5]:
            if isinstance(reason, str) and reason.strip():
                evidence_lines.append(reason.strip())

    # Also inspect the already-generated evidence collections.
    for collection_name in (
        "prediction_evidence",
        "research_evidence",
        "meta_evidence",
    ):
        collection = horizon_result.get(collection_name, [])
        if not isinstance(collection, list):
            continue

        for item in collection:
            if not isinstance(item, dict):
                continue

            reason = item.get("reason")
            if isinstance(reason, str) and reason.strip():
                evidence_lines.append(reason.strip())

            if len(evidence_lines) >= 8:
                break

        if len(evidence_lines) >= 8:
            break

    # De-duplicate while preserving order.
    unique: list[str] = []
    seen: set[str] = set()

    for line in evidence_lines:
        normalized = " ".join(line.split())
        if normalized and normalized not in seen:
            seen.add(normalized)
            unique.append(normalized)

    return unique[:6]


def _build_human_summary(
    symbol: str,
    horizon: int,
    decision: dict,
    market_data: dict,
    key_evidence: list[str],
) -> str:
    """
    Build a short human-readable explanation from the existing Apex result.

    This is presentation only. It does not create a new prediction.
    """
    direction = _direction_label(
        decision.get("direction", "UNKNOWN")
    )

    confidence = _safe_float(
        decision.get("confidence", 0.0)
    ) * 100.0

    signal_strength = _first_non_empty(
        decision.get("signal_strength"),
        default="UNKNOWN",
    ).upper()

    status = str(
        market_data.get("status", "UNKNOWN")
    ).upper()

    fresh = bool(market_data.get("fresh", False))

    parts: list[str] = []

    # Opening assessment.
    if direction == "UP":
        parts.append(
            f"{symbol} currently leans upward on the {horizon}-minute horizon."
        )
    elif direction == "DOWN":
        parts.append(
            f"{symbol} currently leans downward on the {horizon}-minute horizon."
        )
    elif direction == "SIDEWAYS":
        parts.append(
            f"{symbol} is currently showing a sideways/uncertain direction on the {horizon}-minute horizon."
        )
    else:
        parts.append(
            f"{symbol} does not currently have a clear directional signal on the {horizon}-minute horizon."
        )

    # Confidence context.
    if confidence >= 70:
        parts.append(
            f"Confidence is {confidence:.1f}%, which is relatively strong."
        )
    elif confidence >= 50:
        parts.append(
            f"Confidence is {confidence:.1f}%, so the signal has moderate support."
        )
    else:
        parts.append(
            f"Confidence is only {confidence:.1f}%, so the directional signal is weak."
        )

    # Data-quality warning always gets priority.
    if status == "STALE" or not fresh:
        parts.append(
            _freshness_text(market_data)
            + " The current direction should therefore be treated cautiously."
        )
    elif status == "OK":
        parts.append(
            "Fresh market data is available for the current assessment."
        )

    # Signal-strength / gate context.
    if signal_strength in {"WITHHELD", "WEAK", "UNCERTAIN"}:
        parts.append(
            f"The Apex signal status is {signal_strength}, so there is not enough confirmation for a strong directional conclusion."
        )
    elif signal_strength not in {"UNKNOWN", ""}:
        parts.append(
            f"The Apex signal strength is {signal_strength}."
        )

    # Add one or two of the most important reasons, not the raw JSON.
    if key_evidence:
        important = key_evidence[:2]
        for reason in important:
            parts.append(reason)

    return " ".join(parts)


def _compact_details(
    symbol: str,
    horizon: int,
    result: dict,
    horizon_result: dict,
    decision: dict,
    market_data: dict,
    key_evidence: list[str],
) -> dict:
    """Return only the important details for the normal expanded UI."""
    quality = market_data.get("quality", {})
    if not isinstance(quality, dict):
        quality = {}

    compact = {
        "Commodity": symbol,
        "Horizon": f"{horizon} minutes",
        "Live price": _first_non_empty(
            market_data.get("last_price"),
            market_data.get("price"),
            default="—",
        ),
        "Direction": _direction_label(
            decision.get("direction", "UNKNOWN")
        ),
        "Confidence": f"{_safe_float(decision.get('confidence', 0.0)) * 100:.1f}%",
        "Score": f"{_safe_float(decision.get('score', 0.0)):.4f}",
        "Signal strength": _first_non_empty(
            decision.get("signal_strength"),
            default="UNKNOWN",
        ),
        "Market status": str(
            market_data.get("status", "UNKNOWN")
        ).upper(),
        "Fresh": "YES" if market_data.get("fresh", False) else "NO",
        "Records": market_data.get(
            "records",
            quality.get("count", "—"),
        ),
        "Key evidence": key_evidence,
    }

    # Pull gate information if Apex already produced it.
    gate_reasons = decision.get("gate_reasons")
    if gate_reasons:
        compact["Decision gate"] = gate_reasons

    return compact


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
            index=SUPPORTED_HORIZONS.index(default_horizon),
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
        index=1,  # 60 seconds by default
        format_func=lambda x: (
            f"{x // 60} minute"
            if x >= 60 and x % 60 == 0 and x == 60
            else f"{x} seconds"
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
        "Market-data mode: " + str(DATA_MODE).upper()
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
    "MCX • Angel One Live Market Data • Apex Multi-Horizon Analysis"
)

if not commodity_enabled:
    st.info("Commodity Auto Board is disabled from the sidebar.")
    st.stop()

if not selected_commodities:
    st.warning("Select at least one commodity from the sidebar.")
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
    st.error("Angel One provider is not connected.")
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
# RUN ANALYSIS
# ================================================================

results = []
detail_results = []

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

        if not isinstance(market_data, dict):
            market_data = {}

        direction = _direction_label(
            decision.get("direction", "UNKNOWN")
        )

        confidence = (
            _safe_float(
                decision.get("confidence", 0.0)
            ) * 100.0
        )

        score = _safe_float(
            decision.get("score", 0.0)
        )

        price = _first_non_empty(
            market_data.get("last_price"),
            market_data.get("price"),
            default="—",
        )

        key_evidence = _extract_key_evidence(
            horizon_result,
            decision,
        )

        human_summary = _build_human_summary(
            symbol=symbol,
            horizon=horizon,
            decision=decision,
            market_data=market_data,
            key_evidence=key_evidence,
        )

        results.append(
            {
                "Commodity": symbol,
                "Horizon": f"{horizon} min",
                "Price": price,
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
                    if market_data.get("fresh", False)
                    else "NO"
                ),
            }
        )

        detail_results.append(
            {
                "symbol": symbol,
                "horizon": horizon,
                "result": result,
                "horizon_result": horizon_result,
                "decision": decision,
                "market_data": market_data,
                "key_evidence": key_evidence,
                "human_summary": human_summary,
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

        detail_results.append(
            {
                "symbol": symbol,
                "horizon": horizon,
                "error": f"{type(exc).__name__}: {exc}",
            }
        )


# ================================================================
# COMPARISON BOARD
# ================================================================

st.subheader("📊 Commodity Comparison")

if results:
    st.dataframe(
        results,
        use_container_width=True,
        hide_index=True,
    )


# ================================================================
# HORIZON SUMMARY
# ================================================================

st.subheader("⏱️ Commodity Horizons")

horizon_columns = st.columns(len(detail_results))

for column, item in zip(horizon_columns, detail_results):

    with column:
        st.metric(
            item["symbol"],
            f"{item['horizon']} min",
        )


# ================================================================
# HUMAN-READABLE ANALYSIS
# ================================================================

st.subheader("🔎 Commodity Analysis")

for item in detail_results:

    symbol = item["symbol"]
    horizon = item["horizon"]

    with st.container(border=True):

        st.markdown(
            f"### 🛢️ {symbol} · {horizon} min"
        )

        if "error" in item:
            st.error(item["error"])
            continue

        decision = item["decision"]
        market_data = item["market_data"]
        horizon_result = item["horizon_result"]
        key_evidence = item["key_evidence"]

        direction = _direction_label(
            decision.get("direction", "UNKNOWN")
        )

        confidence = (
            _safe_float(
                decision.get("confidence", 0.0)
            ) * 100.0
        )

        score = _safe_float(
            decision.get("score", 0.0)
        )

        price = _first_non_empty(
            market_data.get("last_price"),
            market_data.get("price"),
            default="—",
        )

        status = str(
            market_data.get("status", "UNKNOWN")
        ).upper()

        fresh = (
            "YES"
            if market_data.get("fresh", False)
            else "NO"
        )

        c1, c2, c3, c4 = st.columns(4)

        c1.metric("Live Price", price)
        c2.metric("Direction", direction)
        c3.metric("Confidence", f"{confidence:.1f}%")
        c4.metric("Score", f"{score:.4f}")

        c5, c6 = st.columns(2)
        c5.metric("Data", status)
        c6.metric("Fresh", fresh)

        # --------------------------------------------------------
        # SHORT HUMAN SUMMARY
        # --------------------------------------------------------

        st.markdown("#### 🧠 What this means")

        st.info(item["human_summary"])

        # --------------------------------------------------------
        # ONLY THE MOST IMPORTANT SIGNALS
        # --------------------------------------------------------

        if key_evidence:

            st.markdown("#### 📌 Important signals")

            for evidence in key_evidence[:5]:
                st.markdown(f"- {evidence}")

        # --------------------------------------------------------
        # COMPACT IMPORTANT DETAILS
        # --------------------------------------------------------

        compact = _compact_details(
            symbol=symbol,
            horizon=horizon,
            result=item["result"],
            horizon_result=horizon_result,
            decision=decision,
            market_data=market_data,
            key_evidence=key_evidence,
        )

        with st.expander(
            f"📋 {symbol} — Important Analysis Details",
            expanded=False,
        ):
            st.json(compact)

        # --------------------------------------------------------
        # FULL RAW APEX EVIDENCE
        # --------------------------------------------------------

        with st.expander(
            f"🔬 {symbol} — Full Apex Evidence (optional)",
            expanded=False,
        ):
            st.caption(
                "This section contains the existing Apex output "
                "without changing its calculations."
            )
            st.json(horizon_result)


# ================================================================
# CONNECTION SUMMARY
# ================================================================

st.divider()

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
