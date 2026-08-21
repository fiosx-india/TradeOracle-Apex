"""
TradeOracle Apex - Commodity Auto Board

MCX-only commodity presentation layer.

Responsibilities:
- Reuse the existing authenticated Angel One provider
- Force the commodity data path to MCX
- Run selected MCX commodities
- Use canonical Apex horizons: 5 / 15 / 30 / 60 minutes
- Show a compact comparison board and short human-readable explanation
- Keep full Apex evidence collapsed for advanced inspection
- No order placement / GTT operations
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
from config import (
    ANGELONE_HISTORY_BARS,
    DATA_MODE,
    LIVE_DATA_MAX_AGE_SECONDS,
    AUTO_BUY_ENABLED,
    AUTO_BUY_MODE,
    AUTO_BUY_MIN_CONFIDENCE,
    AUTO_BUY_REQUIRE_FRESH,
    AUTO_BUY_REQUIRE_POSITIVE_SCORE,
    AUTO_BUY_MIN_HISTORY,
    AUTO_BUY_MAX_QUANTITY,
)

from trading.auto_buy import (
    AutoBuyDecision,
    PaperOrderExecutor,
)

st.set_page_config(
    page_title="TradeOracle Apex - Commodity Auto Board",
    page_icon="🛢️",
    layout="wide",
)

DEFAULT_COMMODITIES = {
    "GOLDM": 5,
    "NATURALGAS": 15,
    "CRUDEOILM": 30,
    "SILVERM": 60,
}
SUPPORTED_HORIZONS = [5, 15, 30, 60]
REFRESH_OPTIONS = [30, 60]


@st.cache_resource(ttl=1800, show_spinner=False)
def get_provider():
    return load_market_provider()


def safe_float(value, default=0.0):
    try:
        return default if value is None else float(value)
    except (TypeError, ValueError):
        return default


def format_price(value):
    if value in (None, "", "—"):
        return "—"
    try:
        number = float(value)
        return f"{number:,.0f}" if number.is_integer() else f"{number:,.2f}"
    except (TypeError, ValueError):
        return str(value)


def horizon_result(result: dict, horizon: int) -> dict:
    horizons = result.get("horizons", {})
    if not isinstance(horizons, dict):
        return {}
    value = horizons.get(str(horizon), horizons.get(horizon, {}))
    return value if isinstance(value, dict) else {}


def direction_icon(direction: str) -> str:
    value = str(direction or "").upper()
    if value == "UP":
        return "🟢"
    if value == "DOWN":
        return "🔴"
    if value in {"SIDEWAYS", "NEUTRAL"}:
        return "🔵"
    return "⚪"


def build_meaning(
    symbol: str,
    horizon: int,
    direction: str,
    confidence: float,
    score: float,
    market_data: dict,
    decision: dict,
) -> str:
    direction = str(direction or "UNKNOWN").upper()
    status = str(market_data.get("status", "UNKNOWN")).upper()
    fresh = bool(market_data.get("fresh", False))
    strength = str(decision.get("signal_strength", "")).upper()
    agreement = safe_float(decision.get("agreement", 0.0))
    agreement_pct = agreement * 100 if agreement <= 1 else agreement

    direction_text = {
        "UP": "மேல்நோக்கிய",
        "DOWN": "கீழ்நோக்கிய",
        "SIDEWAYS": "தெளிவான திசையில்லாத / sideways",
        "NEUTRAL": "தெளிவான திசையில்லாத / sideways",
    }.get(direction, "தெளிவாக உறுதி செய்யப்படாத")

    if confidence >= 70:
        confidence_text = "வலுவாக"
    elif confidence >= 50:
        confidence_text = "மிதமான அளவில்"
    else:
        confidence_text = "பலவீனமாக"

    if status == "OK" and fresh:
        data_text = "தற்போதைய market data fresh-ஆக உள்ளது."
    elif status == "STALE" or not fresh:
        data_text = "Market data fresh இல்லை; signal-ஐ எச்சரிக்கையுடன் பார்க்க வேண்டும்."
    else:
        data_text = "Market-data status முழுமையாக உறுதி செய்யப்படவில்லை."

    if strength == "WITHHELD":
        signal_text = "Apex signal strength-ஐ உறுதிப்படுத்தாமல் வைத்துள்ளது."
    elif agreement_pct > 70:
        signal_text = f"பல analysis signals ஒன்றுக்கொன்று ஆதரவாக உள்ளன (agreement சுமார் {agreement_pct:.0f}%)."
    elif agreement_pct > 0:
        signal_text = f"Analysis signals-ல் ஓரளவு agreement உள்ளது (சுமார் {agreement_pct:.0f}%)."
    else:
        signal_text = "போதுமான directional agreement இல்லை."

    return (
        f"{symbol} தற்போது {horizon}-minute horizon-ல் {direction_text} direction-ஐ காட்டுகிறது. "
        f"Confidence {confidence:.1f}% என்பதால் signal {confidence_text}. "
        f"{data_text} {signal_text} "
        f"Score {score:.4f}; இது தற்போதைய Apex assessment-ஐ மட்டுமே விளக்குகிறது."
    )


def important_signals(horizon_data: dict, decision: dict, limit: int = 3) -> list[str]:
    signals = []

    for reason in decision.get("reasons", []):
        if isinstance(reason, str):
            cleaned = " ".join(reason.split())
            if cleaned and cleaned not in signals:
                signals.append(cleaned)
        if len(signals) >= limit:
            return signals

    for item in horizon_data.get("prediction_evidence", []):
        if not isinstance(item, dict):
            continue
        reason = item.get("reason")
        if reason:
            cleaned = " ".join(str(reason).split())
            if cleaned and cleaned not in signals:
                signals.append(cleaned)
        if len(signals) >= limit:
            return signals

    return signals[:limit]


with st.sidebar:
    st.header("🛢️ Commodity Auto Board")

    enabled = st.checkbox(
        "Enable Commodity Board",
        value=True,
        key="commodity_board_enabled",
    )

    st.divider()
    st.subheader("MCX Commodities")

    selected = st.multiselect(
        "Select commodities",
        options=list(DEFAULT_COMMODITIES),
        default=list(DEFAULT_COMMODITIES),
        key="commodity_symbols",
    )

    st.divider()
    st.subheader("Prediction Horizon")

    horizons = {}
    for symbol in selected:
        default = DEFAULT_COMMODITIES.get(symbol, 5)
        horizons[symbol] = st.selectbox(
            symbol,
            options=SUPPORTED_HORIZONS,
            index=SUPPORTED_HORIZONS.index(default),
            format_func=lambda x: f"{x} minutes",
            key=f"commodity_horizon_{symbol}",
        )

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
        format_func=lambda x: "1 minute" if x == 60 else f"{x} seconds",
        key="commodity_refresh_seconds",
    )

    st.caption("Default refresh: 60 seconds. This avoids unnecessary API polling.")

    st.divider()
    st.subheader("Connection")
    st.caption("Uses the existing Angel One provider/session.")
    st.caption("Exchange: **MCX**")
    st.caption(f"Market-data mode: **{str(DATA_MODE).upper()}**")
    st.caption("Read-only mode. Orders/GTTs are disabled.")


if auto_refresh:
    from streamlit_autorefresh import st_autorefresh

    st_autorefresh(
        interval=refresh_seconds * 1000,
        key="commodity_auto_refresh_timer",
    )


st.title("🛢️ Commodity Auto Board")
st.caption("MCX • Angel One Live Market Data • Apex Multi-Horizon Analysis")

if not enabled:
    st.info("Commodity Auto Board is disabled from the sidebar.")
    st.stop()

if not selected:
    st.warning("Select at least one commodity from the sidebar.")
    st.stop()


try:
    provider = get_provider()
except Exception as exc:
    st.error(f"Angel One connection failed: {type(exc).__name__}: {exc}")
    st.stop()

if provider is None:
    st.error("Angel One provider is not connected.")
    st.stop()


def run_commodity_analysis(symbol: str, horizon: int) -> dict:
    gateway = MarketData(
        provider=provider,
        max_age_seconds=LIVE_DATA_MAX_AGE_SECONDS,
    )
    orchestrator = ApexOrchestrator(
        market_data=gateway,
        max_age_seconds=LIVE_DATA_MAX_AGE_SECONDS,
    )

    # IMPORTANT:
    # MarketData passes unknown kwargs through to the provider.
    # The provider is exchange-aware and resolves MCX instruments
    # using the explicit exchange value below.
    return orchestrator.run(
        symbol=symbol,
        limit=ANGELONE_HISTORY_BARS,
        horizons_minutes=(horizon,),
        exchange="MCX",
    )


results = {}
errors = {}

for symbol in selected:
    try:
        results[symbol] = run_commodity_analysis(symbol, horizons[symbol])
    except Exception as exc:
        errors[symbol] = f"{type(exc).__name__}: {exc}"


st.subheader("📊 Commodity Comparison")

rows = []
for symbol in selected:
    horizon = horizons[symbol]

    if symbol in errors:
        rows.append({
            "Commodity": symbol,
            "Horizon": f"{horizon} min",
            "Price": "—",
            "Direction": "ERROR",
            "Confidence": "—",
            "Score": "—",
            "Data": "ERROR",
            "Fresh": "NO",
        })
        continue

    result = results.get(symbol, {})
    hr = horizon_result(result, horizon)
    brain = hr.get("master_brain", {})
    decision = brain.get("decision", {}) if isinstance(brain, dict) else {}
    market = hr.get("market_data", {})

# ============================================================
# AUTO BUY DECISION
# ============================================================

auto_buy_result = None
paper_order_result = None

if auto_buy_enabled:

    auto_buy_engine = AutoBuyDecision(
        min_confidence=AUTO_BUY_MIN_CONFIDENCE,
        require_fresh=AUTO_BUY_REQUIRE_FRESH,
        require_positive_score=AUTO_BUY_REQUIRE_POSITIVE_SCORE,
        min_history=AUTO_BUY_MIN_HISTORY,
        max_quantity=AUTO_BUY_MAX_QUANTITY,
    )

    auto_buy_result = auto_buy_engine.evaluate(
        symbol=symbol,
        exchange="MCX",
        horizon_minutes=horizon,
        decision=decision,
        market_data=market,
        quantity=auto_buy_quantity,
    )

    if AUTO_BUY_MODE == "PAPER":
        paper_executor = PaperOrderExecutor()

        paper_order_result = paper_executor.execute(
            auto_buy_result
        )
    confidence = safe_float(decision.get("confidence")) * 100
    rows.append({
        "Commodity": symbol,
        "Horizon": f"{horizon} min",
        "Price": format_price(market.get("last_price", market.get("price"))),
        "Direction": str(decision.get("direction", "UNKNOWN")).upper(),
        "Confidence": f"{confidence:.1f}%",
        "Score": f"{safe_float(decision.get('score')):.4f}",
        "Data": str(market.get("status", "UNKNOWN")).upper(),
        "Fresh": "YES" if market.get("fresh", False) else "NO",
    })

st.dataframe(rows, width="stretch", hide_index=True)


st.subheader("⏱️ Commodity Horizons")
cols = st.columns(max(1, len(selected)))
for col, symbol in zip(cols, selected):
    col.metric(symbol, f"{horizons[symbol]} min")


st.subheader("🔎 Commodity Analysis")

for symbol in selected:
    horizon = horizons[symbol]

    with st.container(border=True):
        st.markdown(f"## 🛢️ {symbol} · {horizon} min")

        if symbol in errors:
            st.error("🔴 Market analysis could not be completed.")
            with st.expander(f"⚠️ {symbol} — Runtime Error", expanded=False):
                st.code(errors[symbol])
            continue

        result = results.get(symbol, {})
        hr = horizon_result(result, horizon)
        brain = hr.get("master_brain", {})
        decision = brain.get("decision", {}) if isinstance(brain, dict) else {}
        market = hr.get("market_data", {})

        direction = str(decision.get("direction", "UNKNOWN")).upper()
        confidence = safe_float(decision.get("confidence")) * 100
        score = safe_float(decision.get("score"))
        price = market.get("last_price", market.get("price", "—"))
        status = str(market.get("status", "UNKNOWN")).upper()
        fresh = "YES" if market.get("fresh", False) else "NO"

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Live Price", format_price(price))
        c2.metric("Direction", f"{direction_icon(direction)} {direction}")
        c3.metric("Confidence", f"{confidence:.1f}%")
        c4.metric("Score", f"{score:.4f}")

        c1, c2 = st.columns(2)
        c1.metric("Data", status)
        c2.metric("Fresh", fresh)

        st.markdown("### 🤖 Auto Buy")

        if not auto_buy_enabled:

            st.info("Auto Buy is disabled.")

        elif auto_buy_result is None:

            st.warning(
                "Auto Buy decision is unavailable."
            )

        elif auto_buy_result.allowed:

            st.success(
                f"🟢 BUY ELIGIBLE • "
                f"{auto_buy_result.symbol} • "
                f"Qty {auto_buy_result.quantity} • "
                f"Confidence "
                f"{auto_buy_result.confidence * 100:.1f}% • "
                f"Score "
                f"{auto_buy_result.score:.4f}"
            )

            if paper_order_result:
                st.json(paper_order_result)

        else:

            st.warning(
                f"🔵 NO BUY • "
                f"{auto_buy_result.reason}"
            )

        st.markdown("### 🧠 What this means")
        st.info(build_meaning(
            symbol=symbol,
            horizon=horizon,
            direction=direction,
            confidence=confidence,
            score=score,
            market_data=market,
            decision=decision,
        ))

        st.markdown("### 📌 Important signals")
        signals = important_signals(hr, decision, limit=3)
        if signals:
            for signal in signals:
                st.markdown(f"- {signal}")
        else:
            st.caption("No additional concise signals are available.")

        with st.expander(f"📋 {symbol} — Important Analysis Details", expanded=False):
            st.markdown("### Market Snapshot")
            st.write({
                "price": format_price(price),
                "data": status,
                "fresh": fresh,
            })
            st.markdown("### Apex Assessment")
            st.write({
                "direction": direction,
                "confidence": f"{confidence:.1f}%",
                "score": f"{score:.4f}",
                "agreement": decision.get("agreement", 0.0),
                "signal_strength": decision.get("signal_strength", ""),
            })

        with st.expander(f"🔬 {symbol} — Full Apex Evidence (optional)", expanded=False):
            st.caption("Developer / advanced inspection only.")
            st.json(hr)


st.divider()
c1, c2, c3, c4 = st.columns(4)
c1.metric("Angel One", "CONNECTED")
c2.metric("Exchange", "MCX")
c3.metric("Commodities", str(len(selected)))
c4.metric("Horizons", "5 / 15 / 30 / 60")
st.caption("Read-only mode. No orders or GTTs are placed.")
