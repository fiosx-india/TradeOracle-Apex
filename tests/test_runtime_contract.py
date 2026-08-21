import unittest
from datetime import datetime, timedelta, timezone

from core.decision_engine import DecisionEngine
from core.market_context import MarketContext
from core.orchestrator import ApexOrchestrator
from core.signal_gate import SignalGate
from data.market_data import MarketData
from data.news_data import NewsData


class RuntimeContractTests(unittest.TestCase):
    def test_future_data_is_not_fresh(self):
        now = datetime.now(timezone.utc)
        quality = MarketData(max_age_seconds=120).quality([{
            "symbol": "NIFTY",
            "timestamp": (now + timedelta(minutes=5)).isoformat(),
            "price": 100.0,
            "close": 100.0,
        }])
        self.assertFalse(quality["fresh"])

    def test_stale_signal_is_withheld(self):
        result = DecisionEngine().decide(
            {"score": 0.8, "confidence": 0.95, "evidence": [], "reasons": []},
            {"status": "STALE", "fresh": False, "count": 120},
        )
        self.assertEqual(result["decision_status"], "WITHHELD")
        self.assertEqual(result["direction"], "SIDEWAYS")

    def test_low_confidence_is_withheld(self):
        result = SignalGate(0.60, 30, False).apply(
            {"direction": "UP", "confidence": 0.40},
            {"status": "OK", "fresh": True, "count": 120},
        )
        self.assertEqual(result["decision_status"], "WITHHELD")

    def test_market_result_exposes_canonical_last_price(self):
        context = MarketContext(
            timestamp="2026-08-21T10:00:00+00:00",
            symbol="GOLDM",
            data={"price": 1634807.0},
        )
        context.market_data_quality = {
            "status": "OK",
            "fresh": True,
            "count": 60,
        }

        result = ApexOrchestrator._market_result(context)

        self.assertEqual(result["last_price"], 1634807.0)
        self.assertEqual(result["price"], 1634807.0)

    def test_market_result_price_fallbacks(self):
        for key, expected in (
            ("last_price", 100.0),
            ("price", 200.0),
            ("close", 300.0),
        ):
            context = MarketContext(
                timestamp="2026-08-21T10:00:00+00:00",
                symbol="SILVERM",
                data={key: expected},
            )
            context.market_data_quality = {
                "status": "OK",
                "fresh": True,
                "count": 60,
            }

            result = ApexOrchestrator._market_result(context)
            self.assertEqual(result["last_price"], expected)

    def test_news_normalization_contract(self):
        news = NewsData(api_key="")
        self.assertFalse(news.configured)
        self.assertEqual(news.health()["read_only"], True)


if __name__ == "__main__":
    unittest.main()
