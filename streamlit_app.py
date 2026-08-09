"""TradeOracle Apex - Angel One live market-data and prediction app."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import streamlit as st
from streamlit_autorefresh import st_autorefresh

from config import (
    ANGELONE_EXCHANGE,
    ANGELONE_HISTORY_BARS,
    ANGELONE_SYMBOL,
    DATA_MODE,
    LIVE_DATA_MAX_AGE_SECONDS,
    PREDICTION_HORIZON_MINUTES,
)
from core.orchestrator import ApexOrchestrator
from data.market_data import MarketData
from data.provider_loader import load_market_provider

ROOT = Path(__file__).resolve().parent
IST = ZoneInfo("Asia/Kolkata")


def file_check(relative_path: str) -> bool:
    return (ROOT / relative_path).is_file()


@st.cache_resource(ttl=1800, show_spinner=False)
def get_provider():
    """Create one authenticated provider per Streamlit resource cache."""
    return load_market_provider()


def live_ltp_check(provider, symbol: str) -> dict:
    gateway = MarketData(
        provider=provider,
        max_age_seconds=LIVE_DATA_MAX_AGE_SECONDS,
    )
    result = gateway.latest(symbol=symbol)
    quality = result.get("quality", {})
    record = result.get("record")

    return {
        "provider_connected": provider is not None,
        "status": quality.get("status", "UNKNOWN"),
        "fresh": bool(quality.get("fresh", False)),
        "records": quality.get("count", 0),
        "source": result.get("source"),
        "record": record,
        "error": gateway.last_error,
    }


def run_analysis(provider, symbol: str) -> dict:
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
        horizon_minutes=PREDICTION_HORIZON_MINUTES,
    )


def main() -> None:
    st.set_page_config(
        page_title="TradeOracle Apex - Angel One Live",
        page_icon="📡",
        layout="wide",
    )

    st_autorefresh(interval=15000, key="angelone_live_refresh")

    st.title("📡 TradeOracle Apex")
    st.subheader("Angel One Live Market Data + AI Analysis")

    st.info(
        "Read-only mode. This version reads Angel One market data and runs "
        "the Apex research/prediction pipeline. It does not place orders or GTTs."
    )

    if DATA_MODE != "live":
        st.error(
            "APEX_DATA_MODE is not 'live'. Set it to 'live' for the production "
            "read-only Angel One connection."
        )
        st.stop()

    symbol = st.text_input(
        "Angel One symbol",
        value=ANGELONE_SYMBOL,
        help="Examples: NIFTY for the index or SBIN for an NSE equity.",
    ).strip() or ANGELONE_SYMBOL

    st.caption(
        f"Exchange: {ANGELONE_EXCHANGE}  •  "
        f"History: {ANGELONE_HISTORY_BARS} bars  •  "
        f"Horizon: {PREDICTION_HORIZON_MINUTES} minutes"
    )

    # ---------------------------------------------------------------
    # 1. AUTHENTICATION / LIVE LTP
    # ---------------------------------------------------------------
    st.header("1. Angel One connection")

    try:
        provider = get_provider()
        ltp = live_ltp_check(provider, symbol)
    except Exception as exc:
        provider = None
        ltp = {
            "provider_connected": False,
            "status": "ERROR",
            "fresh": False,
            "records": 0,
            "source": None,
            "record": None,
            "error": f"{type(exc).__name__}: {exc}",
        }

    c1, c2, c3, c4 = st.columns(4)
    c1.metric(
        "Authentication",
        "CONNECTED" if ltp["provider_connected"] else "FAILED",
    )
    c2.metric("LTP", str(ltp["record"].get("price")) if ltp["record"] else "—")
    c3.metric("Fresh", "YES" if ltp["fresh"] else "NO")
    c4.metric("Gateway", ltp["status"])

    if ltp["error"]:
        st.error(ltp["error"])

    if ltp["record"]:
        st.write("Latest Angel One record")
        st.json(ltp["record"])

    # ---------------------------------------------------------------
    # 2. MARKET HISTORY + MASTER BRAIN
    # ---------------------------------------------------------------
    st.header("2. Real market-data analysis")

    if provider is None:
        st.warning("Angel One provider is not connected, so analysis is stopped.")
        st.stop()

    with st.spinner("Fetching Angel One candles and running Apex engines..."):
        try:
            result = run_analysis(provider, symbol)
        except Exception as exc:
            st.error(f"{type(exc).__name__}: {exc}")
            st.stop()

    md = result.get("market_data", {})
    quality = md.get("quality", {})
    brain = result.get("master_brain", {})

    a, b, c, d = st.columns(4)
    a.metric("Candles", md.get("records", 0))
    b.metric("Data Status", quality.get("status", "UNKNOWN"))
    c.metric("Fresh", "YES" if md.get("fresh") else "NO")
    d.metric("Source", md.get("source") or "—")

    min_history = 30
    if md.get("records", 0) < min_history:
        st.warning(
            f"Prediction is withheld until at least {min_history} valid candles "
            "are available."
        )
    elif not brain:
        st.warning("Master Brain did not produce an analysis result.")
    else:
        decision = brain.get("decision", {})
        direction = decision.get("direction", "UNKNOWN")
        confidence = float(decision.get("confidence", 0.0)) * 100.0
        score = decision.get("score", 0.0)

        st.subheader("Current AI assessment")

        p1, p2, p3 = st.columns(3)
        p1.metric("Direction", direction)
        p2.metric("Confidence", f"{confidence:.1f}%")
        p3.metric("Score", f"{float(score):.4f}")

        if direction == "UP":
            st.success("UP — research/prediction evidence currently leans upward.")
        elif direction == "DOWN":
            st.error("DOWN — research/prediction evidence currently leans downward.")
        else:
            st.info("SIDEWAYS — evidence does not justify a directional call.")

        reasons = decision.get("reasons", [])
        if reasons:
            st.subheader("Why")
            for reason in reasons:
                st.write(f"• {reason}")

        with st.expander("Research evidence"):
            st.json(brain.get("research_evidence", []))

        with st.expander("Primary prediction evidence"):
            st.json(brain.get("prediction_evidence", []))

        with st.expander("Derived / meta analysis"):
            st.json(brain.get("derived", {}))

    # ---------------------------------------------------------------
    # 3. ENGINE REGISTRY
    # ---------------------------------------------------------------
    st.header("3. Apex runtime")

    registered = result.get("registered_engines", [])
    st.success(f"{len(registered)} validated engines are registered.")

    with st.expander("Engine registry"):
        st.json(result.get("registry_report", {}))

    # ---------------------------------------------------------------
    # 4. SAFETY / ORDER STATUS
    # ---------------------------------------------------------------
    st.header("4. Trading status")
    st.success(
        "ORDER PLACEMENT: DISABLED  •  GTT: DISABLED  •  "
        "READ-ONLY MARKET DATA: ENABLED"
    )

    st.caption(
        "Angel One sessions are subject to broker/API session rules. "
        "The application re-authenticates when the cached provider expires."
    )

    st.caption(
        "Last UI refresh: "
        + datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S IST")
    )


if __name__ == "__main__":
    main()
