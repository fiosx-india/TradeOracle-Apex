"""TradeOracle Apex - Streamlit live-data readiness diagnostic."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import streamlit as st

from core.orchestrator import ApexOrchestrator
from data.market_data import MarketData
from commodities.commodity_engine import CommodityEngine


ROOT = Path(__file__).resolve().parent


def file_check(relative_path: str) -> bool:
    return (ROOT / relative_path).is_file()


def runtime_check() -> dict:
    try:
        result = ApexOrchestrator().run()
        return {
            "ok": result.get("status") == "READY",
            "status": result.get("status"),
            "pipeline": result.get("pipeline", []),
            "registered": len(result.get("registered_engines", [])),
            "report": result.get("report", []),
            "error": None,
        }
    except Exception as exc:
        return {
            "ok": False,
            "status": "ERROR",
            "pipeline": [],
            "registered": 0,
            "report": [],
            "error": f"{type(exc).__name__}: {exc}",
        }


def live_gateway_check() -> dict:
    gateway = MarketData(provider=None, max_age_seconds=120)
    result = gateway.fetch(limit=1)
    return {
        "provider_connected": gateway.provider is not None,
        "status": result["quality"]["status"],
        "fresh": result["quality"]["fresh"],
        "records": result["quality"]["count"],
        "source": result["source"],
    }


def main() -> None:
    st.set_page_config(
        page_title="TradeOracle Apex - Live Data Readiness",
        page_icon="📡",
        layout="wide",
    )

    st.title("📡 TradeOracle Apex")
    st.subheader("Live-Data Integration Readiness")

    st.info(
        "Diagnostic only. This page checks the existing Apex architecture "
        "and never invents live market prices."
    )

    st.header("1. Architecture")

    required = [
        "core/orchestrator.py",
        "core/master_brain.py",
        "core/market_context.py",
        "data/market_data.py",
        "commodities/commodity_engine.py",
        "plugins/plugin_loader.py",
        "requirements.txt",
        "main.py",
    ]

    cols = st.columns(3)
    architecture_ok = True

    for i, item in enumerate(required):
        ok = file_check(item)
        architecture_ok = architecture_ok and ok
        with cols[i % 3]:
            if ok:
                st.success(f"✓ {item}")
            else:
                st.error(f"✗ {item}")

    st.header("2. Apex runtime")

    runtime = runtime_check()

    if runtime["ok"]:
        st.success(
            f"Runtime READY — {runtime['registered']} engines registered."
        )
    else:
        st.error(f"Runtime {runtime['status']}")

    if runtime["pipeline"]:
        st.write("Pipeline:", " → ".join(runtime["pipeline"]))

    if runtime["error"]:
        st.code(runtime["error"])

    with st.expander("Registration report"):
        st.json(runtime["report"])

    st.header("3. Live market-data gateway")

    live = live_gateway_check()

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Provider", "CONNECTED" if live["provider_connected"] else "NOT CONNECTED")
    c2.metric("Gateway", live["status"])
    c3.metric("Records", live["records"])
    c4.metric("Fresh", "YES" if live["fresh"] else "NO")

    if not live["provider_connected"]:
        st.warning(
            "No live provider is attached to MarketData. "
            "The repository's gateway accepts a provider callback, "
            "but the current code does not attach one by default."
        )

    st.header("4. Commodity engine")

    commodity = CommodityEngine()
    commodity_ok = bool(commodity.self_test())

    if commodity_ok:
        st.success("CommodityEngine self-test: PASS")
    else:
        st.error("CommodityEngine self-test: FAIL")

    test_result = commodity.analyze(
        {
            "symbol": "READINESS_TEST",
            "price": None,
            "change_pct": 0.0,
            "volume_ratio": 1.0,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "source": "diagnostic",
        }
    )

    with st.expander("Commodity contract test"):
        st.json(test_result)

    st.header("5. Final verdict")

    ready = (
        architecture_ok
        and runtime["ok"]
        and commodity_ok
        and live["provider_connected"]
        and live["fresh"]
    )

    if ready:
        st.success(
            "READY FOR LIVE-DATA CONSUMPTION: all checked components are present "
            "and a fresh provider feed is available."
        )
    else:
        st.error("NOT READY FOR LIVE TRADING")

        if not architecture_ok:
            st.write("• Required project component(s) are missing.")
        if not runtime["ok"]:
            st.write("• Apex runtime self-check failed.")
        if not commodity_ok:
            st.write("• CommodityEngine self-test failed.")
        if not live["provider_connected"]:
            st.write("• No real market-data provider is connected.")
        elif not live["fresh"]:
            st.write("• Provider data is not fresh.")

    st.caption(
        "A READY result is a technical readiness check only; it is not a "
        "trading recommendation and does not validate provider quality."
    )


if __name__ == "__main__":
    main()
