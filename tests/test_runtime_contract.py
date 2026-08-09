import unittest
from datetime import datetime, timedelta, timezone

from core.decision_engine import DecisionEngine
from core.signal_gate import SignalGate
from data.market_data import MarketData
from data.news_data import NewsData


class RuntimeContractTests(unittest.TestCase):
    def test_market_data_rejects_future_record(self):
        now = datetime.now(timezone.utc)
        record = {
            "symbol": "NIFTY",
            "timestamp": (now + timedelta(minutes=5)).isoformat(),
            "price": 100.0,
            "close": 100.0,
        }
        quality = MarketData(max_age_seconds=120).quality([record])
        self.assertEqual(quality["status"], "INVALID")
        self.assertFalse(quality["fresh"])

    def test_signal_gate_withholds_stale_data(self):
        decision = DecisionEngine().decide(
            {"score": 0.8, "confidence": 0.95, "evidence": [], "reasons": []},
            {"status": "STALE", "fresh": False, "count": 120},
        )
        self.assertEqual(decision["decision_status"], "WITHHELD")
        self.assertEqual(decision["direction"], "SIDEWAYS")
        self.assertFalse(decision["tradable_signal"])

    def test_signal_gate_withholds_low_confidence(self):
        gate = SignalGate(min_confidence=0.60, min_history=30, require_fresh=False)
        result = gate.apply(
            {"direction": "UP", "confidence": 0.40, "score": 0.7},
            {"status": "OK", "fresh": True, "count": 120},
        )
        self.assertEqual(result["decision_status"], "WITHHELD")
        self.assertEqual(result["direction"], "SIDEWAYS")

    def test_news_normalization_is_explicitly_heuristic(self):
        news = NewsData(api_key="")
        row = news._normalize(
            {
                "title": "Company wins major order",
                "description": "Revenue growth expected",
                "publishedAt": "2026-08-07T10:00:00Z",
                "url": "https://example.com/news",
                "source": {"name": "Example"},
            },
            "ABC",
        )
        self.assertIsNotNone(row)
        self.assertEqual(row["event_type"], "ORDER")
        self.assertEqual(row["event_source"], "news_heuristic")
        self.assertIn("sentiment", row)


if __name__ == "__main__":
    unittest.main()
