"""TradeOracle Apex - Angel One live-data readiness diagnostic."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import streamlit as st

from config import DATA_MODE, LIVE_DATA_MAX_AGE_SECONDS
from core.orchestrator import ApexOrchestrator
from data.market_data import MarketData
from data.provider_loader import load_market_provider
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
    try:
        provider = load_market_provider()

        gateway = MarketData(
            provider=provider,
            max_age_seconds=LIVE_DATA_MAX_AGE_SECONDS,
        )

        result = gateway.fetch(limit=1)
        quality = result.get("quality", {})

        return {
            "provider_connected": gateway.provider is not None,
            "status": quality.get("status", "UNKNOWN"),
            "fresh": bool(quality.get("fresh", False)),
            "records": quality.get("count", 0),
            "source": result.get("source"),
            "records_data": result.get("records", []),
            "error": None,
        }

    except Exception as exc:
        return {
            "provider_connected": False,
            "status": "ERROR",
            "fresh": False,
            "records": 0,
            "source": None,
            "records_data": [],
            "error": f"{type(exc).__name__}: {exc}",
        }


def main() -> None:
    st.set_page_config(
        page_title="TradeOracle Apex - Angel One Live Data",
        page_icon="📡",
        layout="wide",
    )

    st.title("📡 TradeOracle Apex")
    st.subheader("Angel One Live-Data Readiness")

    st.info(
        "Read-only diagnostic. This test checks the Angel One market-data "
        "connection and does not place orders."
    )

    st.header("1. Configuration")
    st.write("Data mode:", DATA_MODE.upper())

    if DATA_MODE != "live":
        st.warning(
            "APEX_DATA_MODE is not 'live'. Set it to 'live' in the deployment "
            "environment before testing Angel One."
        )

    st.header("2. Apex architecture")
    required = [
        "core/orchestrator.py",
        "core/master_brain.py",
        "core/market_context.py",
        "data/market_data.py",
        "data/provider_loader.py",
        "data/angelone_provider.py",
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

    st.header("3. Apex runtime")
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

    st.header("4. Angel One live market-data gateway")
    live = live_gateway_check()

    c1, c2, c3, c4 = st.columns(4)
    c1.metric(
        "Provider",
        "CONNECTED" if live["provider_connected"] else "NOT CONNECTED",
    )
    c2.metric("Gateway", live["status"])
    c3.metric("Records", live["records"])
    c4.metric("Fresh", "YES" if live["fresh"] else "NO")

    if live["error"]:
        st.error(live["error"])

    if live["records_data"]:
        st.write("Latest live record")
        st.json(live["records_data"][0])

    st.header("5. Commodity engine")
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

    st.header("6. Final verdict")

    ready = (
        architecture_ok
        and runtime["ok"]
        and commodity_ok
        and live["provider_connected"]
        and live["fresh"]
    )

    if ready:
        st.success(
            "READY FOR LIVE-DATA CONSUMPTION: Angel One returned a fresh "
            "market-data record."
        )
    else:
        st.error("NOT READY FOR LIVE-DATA CONSUMPTION")

        if not architecture_ok:
            st.write("• Required project component(s) are missing.")
        if not runtime["ok"]:
            st.write("• Apex runtime self-check failed.")
        if not commodity_ok:
            st.write("• CommodityEngine self-test failed.")
        if not live["provider_connected"]:
            st.write("• Angel One provider is not connected.")
        elif not live["fresh"]:
            st.write("• Angel One data is not fresh.")


if __name__ == "__main__":
    main()
