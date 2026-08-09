import base64
from pathlib import Path

ROOT = Path(__file__).resolve().parent

def write_b64(path, payload):
    (ROOT / path).write_bytes(base64.b64decode(payload))

def update(path, replacements):
    p = ROOT / path
    text = p.read_text(encoding="utf-8")
    for old_b64, new_b64 in replacements:
        old = base64.b64decode(old_b64).decode()
        new = base64.b64decode(new_b64).decode()
        if old not in text:
            raise RuntimeError(f"Patch anchor not found: {path}")
        text = text.replace(old, new, 1)
    p.write_text(text, encoding="utf-8")
    print("updated", path)

config = ROOT / "config.py"
text = config.read_text(encoding="utf-8")
if "MIN_HISTORY_BARS = int(os.getenv" not in text:
    text = text.rstrip() + "\n\n" + """# Runtime signal-quality gates.
MIN_HISTORY_BARS = int(os.getenv("APEX_MIN_HISTORY_BARS", "30"))
REQUIRE_FRESH_DATA_FOR_SIGNAL = os.getenv(
    "APEX_REQUIRE_FRESH_DATA_FOR_SIGNAL", "true"
).strip().lower() not in {"0", "false", "no", "off"}
NEWS_LOOKBACK_HOURS = int(os.getenv("APEX_NEWS_LOOKBACK_HOURS", "24"))
"""
    config.write_text(text, encoding="utf-8")
    print("updated config.py")

ops = [{"path": "core/orchestrator.py", "replacements": [["from data.market_data import MarketData\n", "from data.market_data import MarketData\nfrom data.context_enricher import MarketContextEnricher\n"], ["        max_age_seconds: int = LIVE_DATA_MAX_AGE_SECONDS,\n    ):\n", "        max_age_seconds: int = LIVE_DATA_MAX_AGE_SECONDS,\n        context_enricher: Optional[MarketContextEnricher] = None,\n    ):\n"], ["        self.brain = ApexMasterBrain(\n            registry=self.registry,\n            router=self.router,\n        )\n", "        self.brain = ApexMasterBrain(\n            registry=self.registry,\n            router=self.router,\n        )\n        self.context_enricher = context_enricher or MarketContextEnricher()\n"], ["        return MarketContext(\n            timestamp=latest_timestamp,\n            symbol=symbol or \"\",\n            sector=sector or \"\",\n            horizon_minutes=int(horizon_minutes),\n            data=data,\n            evidence=[],\n        )\n", "        context = MarketContext(\n            timestamp=latest_timestamp,\n            symbol=symbol or \"\",\n            sector=sector or \"\",\n            horizon_minutes=int(horizon_minutes),\n            data=data,\n            evidence=[],\n        )\n        self.context_enricher.enrich(context)\n        return context\n"]]}, {"path": "core/master_brain.py", "replacements": [["        decision = self.decision.decide(\n            fused\n        )\n", "        market_data_quality = self._get_context_value(\n            context,\n            \"market_data_quality\",\n            {},\n        )\n\n        decision = self.decision.decide(\n            fused,\n            market_data_quality=market_data_quality,\n        )\n"]]}, {"path": "research/volume_engine.py", "replacements": [["        if len(close) < 3 or len(volume) < 3:\n            return _result(self.name, 0.0, \"Insufficient price/volume history\", 0.9, 0.1)\n\n        n = min(len(close), len(volume))\n        close, volume = close[-n:], volume[-n:]\n        baseline = _mean(volume[-21:-1]) if len(volume) > 1 else _mean(volume)\n", "        if len(close) < 3 or len(volume) < 3:\n            return _result(self.name, 0.0, \"Insufficient price/volume history\", 0.9, 0.1)\n\n        n = min(len(close), len(volume))\n        close, volume = close[-n:], volume[-n:]\n\n        # Index instruments such as NIFTY 50 can legitimately report zero\n        # traded volume because the index itself is not a traded instrument.\n        # Do not convert unavailable volume into a synthetic relative-volume\n        # signal.\n        if not any(v > 0 for v in volume):\n            price_change = _safe_ratio(close[-1]-close[-2], abs(close[-2]))\n            score = _clamp(price_change * 6.0)\n            confidence = min(0.55, 0.20 + min(0.25, n / 100.0))\n            return _result(\n                self.name,\n                score,\n                \"volume_unavailable_for_instrument; price_only_confirmation\",\n                weight=0.55,\n                confidence=confidence,\n                relative_volume=None,\n                volume_available=False,\n            )\n\n        baseline = _mean(volume[-21:-1]) if len(volume) > 1 else _mean(volume)\n"]]}, {"path": "streamlit_app.py", "replacements": [["from data.market_data import MarketData\nfrom data.provider_loader import load_market_provider\n", "from data.market_data import MarketData\nfrom data.provider_loader import load_market_provider\nfrom data.context_enricher import MarketContextEnricher\n"], ["    orchestrator = ApexOrchestrator(\n        market_data=gateway,\n        max_age_seconds=LIVE_DATA_MAX_AGE_SECONDS,\n    )\n", "    orchestrator = ApexOrchestrator(\n        market_data=gateway,\n        max_age_seconds=LIVE_DATA_MAX_AGE_SECONDS,\n        context_enricher=MarketContextEnricher(),\n    )\n"], ["        direction = decision.get(\"direction\", \"UNKNOWN\")\n        confidence = float(decision.get(\"confidence\", 0.0)) * 100.0\n        score = decision.get(\"score\", 0.0)\n", "        direction = decision.get(\"direction\", \"UNKNOWN\")\n        confidence = float(decision.get(\"confidence\", 0.0)) * 100.0\n        score = decision.get(\"score\", 0.0)\n        decision_status = decision.get(\"decision_status\", \"UNKNOWN\")\n"], ["        p3.metric(\"Score\", f\"{float(score):.4f}\")\n\n        if direction == \"UP\":\n", "        p3.metric(\"Score\", f\"{float(score):.4f}\")\n\n        if decision_status == \"WITHHELD\":\n            st.warning(\n                \"Directional signal withheld: \"\n                + \"; \".join(decision.get(\"gate_reasons\", []))\n            )\n        elif direction == \"UP\":\n"], ["        with st.expander(\"Derived / meta analysis\"):\n            st.json(brain.get(\"derived\", {}))\n", "        with st.expander(\"Derived / meta analysis\"):\n            st.json(brain.get(\"derived\", {}))\n\n        with st.expander(\"News / event context\"):\n            st.json({\n                \"news_quality\": md.get(\"context_enrichment\", {}).get(\"news\", {}),\n                \"events\": md.get(\"events\", []),\n            })\n"]]}]
for item in ops:
    encoded = []
    for old, new in item["replacements"]:
        encoded.append([
            base64.b64encode(old.encode()).decode(),
            base64.b64encode(new.encode()).decode(),
        ])
    update(item["path"], encoded)

write_b64("core/decision_engine.py", "IiIiVHJhbnNwYXJlbnQgZGlyZWN0aW9uYWwgZGVjaXNpb24gbGF5ZXIgd2l0aCBkYXRhLXF1YWxpdHkgZ2F0aW5nLiIiIgoKZnJvbSBjb25maWcgaW1wb3J0ICgKICAgIERPV05fVEhSRVNIT0xELAogICAgTUlOX0NPTkZJREVOQ0VfRk9SX1NJR05BTCwKICAgIE1JTl9ISVNUT1JZX0JBUlMsCiAgICBSRVFVSVJFX0ZSRVNIX0RBVEFfRk9SX1NJR05BTCwKICAgIFVQX1RIUkVTSE9MRCwKKQpmcm9tIC5zaWduYWxfZ2F0ZSBpbXBvcnQgU2lnbmFsR2F0ZQoKCmNsYXNzIERlY2lzaW9uRW5naW5lOgogICAgZGVmIF9faW5pdF9fKHNlbGYpOgogICAgICAgIHNlbGYuZ2F0ZSA9IFNpZ25hbEdhdGUoCiAgICAgICAgICAgIG1pbl9jb25maWRlbmNlPU1JTl9DT05GSURFTkNFX0ZPUl9TSUdOQUwsCiAgICAgICAgICAgIG1pbl9oaXN0b3J5PU1JTl9ISVNUT1JZX0JBUlMsCiAgICAgICAgICAgIHJlcXVpcmVfZnJlc2g9UkVRVUlSRV9GUkVTSF9EQVRBX0ZPUl9TSUdOQUwsCiAgICAgICAgKQoKICAgIGRlZiBkZWNpZGUoc2VsZiwgZnVzZWQsIG1hcmtldF9kYXRhX3F1YWxpdHk9Tm9uZSk6CiAgICAgICAgc2NvcmUgPSBmbG9hdChmdXNlZC5nZXQoInNjb3JlIiwgMC4wKSkKICAgICAgICBjb25maWRlbmNlID0gZmxvYXQoZnVzZWQuZ2V0KCJjb25maWRlbmNlIiwgMC4wKSkKCiAgICAgICAgaWYgc2NvcmUgPj0gVVBfVEhSRVNIT0xEOgogICAgICAgICAgICBkaXJlY3Rpb24gPSAiVVAiCiAgICAgICAgZWxpZiBzY29yZSA8PSBET1dOX1RIUkVTSE9MRDoKICAgICAgICAgICAgZGlyZWN0aW9uID0gIkRPV04iCiAgICAgICAgZWxzZToKICAgICAgICAgICAgZGlyZWN0aW9uID0gIlNJREVXQVlTIgoKICAgICAgICBzaWduYWxfc3RyZW5ndGggPSAoCiAgICAgICAgICAgICJTVFJPTkciIGlmIGNvbmZpZGVuY2UgPj0gMC44MAogICAgICAgICAgICBlbHNlICJNT0RFUkFURSIgaWYgY29uZmlkZW5jZSA+PSBNSU5fQ09ORklERU5DRV9GT1JfU0lHTkFMCiAgICAgICAgICAgIGVsc2UgIldFQUsiCiAgICAgICAgKQoKICAgICAgICBkZWNpc2lvbiA9IHsKICAgICAgICAgICAgImRpcmVjdGlvbiI6IGRpcmVjdGlvbiwKICAgICAgICAgICAgInNjb3JlIjogcm91bmQoc2NvcmUsIDYpLAogICAgICAgICAgICAiY29uZmlkZW5jZSI6IHJvdW5kKGNvbmZpZGVuY2UsIDYpLAogICAgICAgICAgICAic2lnbmFsX3N0cmVuZ3RoIjogc2lnbmFsX3N0cmVuZ3RoLAogICAgICAgICAgICAiYWdyZWVtZW50IjogZnVzZWQuZ2V0KCJhZ3JlZW1lbnQiLCAwLjApLAogICAgICAgICAgICAicmVhc29ucyI6IGZ1c2VkLmdldCgicmVhc29ucyIsIFtdKSwKICAgICAgICAgICAgImV2aWRlbmNlIjogZnVzZWQuZ2V0KCJldmlkZW5jZSIsIFtdKSwKICAgICAgICAgICAgImV4cGxhaW5hYmxlIjogVHJ1ZSwKICAgICAgICB9CiAgICAgICAgcmV0dXJuIHNlbGYuZ2F0ZS5hcHBseShkZWNpc2lvbiwgbWFya2V0X2RhdGFfcXVhbGl0eSkK")
print("Phase 1 patch applied.")
