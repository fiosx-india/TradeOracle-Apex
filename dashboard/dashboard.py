"""TradeOracle Apex dashboard layer."""

from .dashboard import Dashboard
from .movement_alert import MovementAlert

__all__ = [
    "Dashboard",
    "MovementAlert",
]


class Dashboard:
    name = "Dashboard"
    version = "2.0.0"
    capabilities = ["DASHBOARD", "ALERTS", "MARKET", "RANKING"]

    def __init__(self, alert_cooldown_seconds: int = 120):
        self.alert_engine = MovementAlert(
            cooldown_seconds=alert_cooldown_seconds
        )

    def self_test(self) -> bool:
        return self.alert_engine.self_test()

    @staticmethod
    def _as_list(value: Any) -> list:
        if isinstance(value, list):
            return value
        if isinstance(value, tuple):
            return list(value)
        return []

    @staticmethod
    def _direction(score: Any) -> str:
        try:
            value = float(score)
        except (TypeError, ValueError):
            return "SIDEWAYS"

        if value >= 0.12:
            return "UP"
        if value <= -0.12:
            return "DOWN"
        return "SIDEWAYS"

    def _normalize_predictions(self, data: Mapping[str, Any]) -> list[dict]:
        raw = data.get("predictions", data.get("companies", []))

        if isinstance(raw, Mapping):
            rows = []
            for symbol, item in raw.items():
                if isinstance(item, Mapping):
                    rows.append({"symbol": symbol, **dict(item)})
            return rows

        return [
            dict(item)
            for item in self._as_list(raw)
            if isinstance(item, Mapping)
        ]

    def _prepare_alert_inputs(self, predictions: Sequence[Mapping]) -> list[dict]:
        rows = []

        for item in predictions:
            row = dict(item)

            if not row.get("symbol"):
                continue

            score = row.get("score", row.get("prediction_score", 0.0))

            row.setdefault("direction", self._direction(score))

            # Support the common naming variants used by research/prediction
            # engines without forcing UI code to know engine internals.
            if "relative_volume" not in row:
                if "volume_ratio" in row:
                    row["relative_volume"] = row["volume_ratio"]
                elif "rv" in row:
                    row["relative_volume"] = row["rv"]

            row.setdefault(
                "early_signal",
                bool(row.get("early_signal", False)),
            )

            rows.append(row)

        return rows

    def build_market_summary(self, data: Mapping[str, Any]) -> dict:
        predictions = self._normalize_predictions(data)

        up = down = sideways = 0
        for item in predictions:
            direction = str(
                item.get("direction")
                or self._direction(item.get("score", 0))
            ).upper()

            if direction == "UP":
                up += 1
            elif direction == "DOWN":
                down += 1
            else:
                sideways += 1

        total = len(predictions)

        return {
            "total_symbols": total,
            "up": up,
            "down": down,
            "sideways": sideways,
            "advance_ratio": up / total if total else 0.0,
            "decline_ratio": down / total if total else 0.0,
        }

    def build_rankings(self, data: Mapping[str, Any], limit: int = 10) -> dict:
        predictions = self._normalize_predictions(data)

        rows = []
        for item in predictions:
            try:
                score = float(item.get("score", 0.0))
                confidence = max(
                    0.0,
                    min(1.0, float(item.get("confidence", 0.0))),
                )
            except (TypeError, ValueError):
                continue

            rank_score = score * confidence

            rows.append({
                "symbol": str(item.get("symbol", "")).upper(),
                "score": round(score, 6),
                "confidence": round(confidence, 6),
                "rank_score": round(rank_score, 6),
                "direction": self._direction(score),
            })

        up = sorted(
            [x for x in rows if x["direction"] == "UP"],
            key=lambda x: x["rank_score"],
            reverse=True,
        )[:max(0, int(limit))]

        down = sorted(
            [x for x in rows if x["direction"] == "DOWN"],
            key=lambda x: x["rank_score"],
        )[:max(0, int(limit))]

        return {
            "top_up": up,
            "top_down": down,
        }

    def build_alerts(self, data: Mapping[str, Any]) -> list[dict]:
        predictions = self._normalize_predictions(data)
        inputs = self._prepare_alert_inputs(predictions)
        return self.alert_engine.build_many(inputs)

    def render(self, data: Mapping[str, Any] | None = None) -> dict:
        """Build the complete UI-ready dashboard state.

        The return value is deliberately framework-neutral so Streamlit,
        another web UI, tests, or an API adapter can consume the same state.
        """
        data = data if isinstance(data, Mapping) else {}

        predictions = self._normalize_predictions(data)
        alerts = self.build_alerts(data)

        return {
            "dashboard": {
                "name": self.name,
                "version": self.version,
                "status": "READY",
            },
            "market": self.build_market_summary(data),
            "rankings": self.build_rankings(data),
            "alerts": alerts,
            "prediction_count": len(predictions),
            "source_timestamp": data.get("timestamp"),
        }

    def reset_alerts(self) -> None:
        self.alert_engine.clear()
