"""
TradeOracle Apex - Auto Buy Decision Layer.

Responsibilities:
- Consume the existing Apex decision.
- Never create a new prediction.
- Never override SignalGate.
- Validate market-data quality.
- Produce a BUY eligibility decision.
- PAPER mode records an intended order only.
- LIVE broker execution is deliberately not performed here.

Architecture:
MarketData
    -> ApexOrchestrator
    -> ApexMasterBrain
    -> DecisionEngine / SignalGate
    -> AutoBuyDecision
    -> OrderExecutor
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


@dataclass(frozen=True)
class AutoBuyResult:
    allowed: bool
    action: str
    reason: str
    symbol: str
    exchange: str
    horizon_minutes: int
    confidence: float
    score: float
    price: float | None
    quantity: int


class AutoBuyDecision:
    """
    Final trading-eligibility layer.

    This class does NOT predict the market.
    It only decides whether an already-gated Apex
    decision is eligible for an automatic BUY.
    """

    name = "AutoBuyDecision"
    version = "1.0.0"

    def __init__(
        self,
        min_confidence: float = 0.60,
        require_fresh: bool = True,
        require_positive_score: bool = True,
        min_history: int = 30,
        max_quantity: int = 1,
    ) -> None:

        self.min_confidence = max(
            0.0,
            min(1.0, float(min_confidence)),
        )

        self.require_fresh = bool(
            require_fresh
        )

        self.require_positive_score = bool(
            require_positive_score
        )

        self.min_history = max(
            1,
            int(min_history),
        )

        self.max_quantity = max(
            1,
            int(max_quantity),
        )

    @staticmethod
    def _float(
        value: Any,
        default: float = 0.0,
    ) -> float:
        try:
            return float(value)
        except (
            TypeError,
            ValueError,
        ):
            return default

    @staticmethod
    def _int(
        value: Any,
        default: int = 0,
    ) -> int:
        try:
            return int(value)
        except (
            TypeError,
            ValueError,
        ):
            return default

    def evaluate(
        self,
        *,
        symbol: str,
        exchange: str,
        horizon_minutes: int,
        decision: Mapping[str, Any],
        market_data: Mapping[str, Any],
        quantity: int = 1,
    ) -> AutoBuyResult:

        direction = str(
            decision.get(
                "direction",
                "UNKNOWN",
            )
        ).upper().strip()

        confidence = self._float(
            decision.get(
                "confidence",
                0.0,
            )
        )

        score = self._float(
            decision.get(
                "score",
                0.0,
            )
        )

        status = str(
            market_data.get(
                "status",
                "UNKNOWN",
            )
        ).upper().strip()

        fresh = bool(
            market_data.get(
                "fresh",
                False,
            )
        )

        valid_count = self._int(
            market_data.get(
                "valid_count",
                market_data.get(
                    "count",
                    0,
                ),
            )
        )

        price_value = market_data.get(
            "last_price",
            market_data.get(
                "price",
            ),
        )

        price = None

        try:
            if price_value is not None:
                price = float(price_value)
        except (
            TypeError,
            ValueError,
        ):
            price = None

        safe_quantity = min(
            max(1, int(quantity)),
            self.max_quantity,
        )

        base_kwargs = {
            "symbol": symbol,
            "exchange": exchange,
            "horizon_minutes": int(
                horizon_minutes
            ),
            "confidence": confidence,
            "score": score,
            "price": price,
            "quantity": safe_quantity,
        }

        # ----------------------------------------------------------
        # MARKET DATA QUALITY
        # ----------------------------------------------------------

        if status in {
            "INVALID",
            "ERROR",
            "UNKNOWN",
        }:

            return AutoBuyResult(
                allowed=False,
                action="NO_BUY",
                reason=(
                    f"market_data_status_{status.lower()}"
                ),
                **base_kwargs,
            )

        # Freshness must be checked BEFORE history.
        # Stale market data must never reach the
        # history/direction/confidence/score gates.

        if self.require_fresh and not fresh:

            return AutoBuyResult(
                allowed=False,
                action="NO_BUY",
                reason="market_data_not_fresh",
                **base_kwargs,
            )

        if valid_count < self.min_history:

            return AutoBuyResult(
                allowed=False,
                action="NO_BUY",
                reason="insufficient_market_history",
                **base_kwargs,
            )
            
        # ----------------------------------------------------------
        # DIRECTION
        # ----------------------------------------------------------

        if direction != "UP":

            return AutoBuyResult(
                allowed=False,
                action="NO_BUY",
                reason=f"direction_is_{direction.lower()}",
                **base_kwargs,
            )

        # ----------------------------------------------------------
        # CONFIDENCE
        # ----------------------------------------------------------

        if confidence < self.min_confidence:

            return AutoBuyResult(
                allowed=False,
                action="NO_BUY",
                reason="confidence_below_auto_buy_threshold",
                **base_kwargs,
            )

        # ----------------------------------------------------------
        # SCORE
        # ----------------------------------------------------------

        if (
            self.require_positive_score
            and score <= 0.0
        ):

            return AutoBuyResult(
                allowed=False,
                action="NO_BUY",
                reason="score_not_positive",
                **base_kwargs,
            )

        # ----------------------------------------------------------
        # PRICE
        # ----------------------------------------------------------

        if price is None or price <= 0:

            return AutoBuyResult(
                allowed=False,
                action="NO_BUY",
                reason="invalid_market_price",
                **base_kwargs,
            )

        # ----------------------------------------------------------
        # FINAL ELIGIBILITY
        # ----------------------------------------------------------

        return AutoBuyResult(
            allowed=True,
            action="BUY",
            reason="all_auto_buy_conditions_passed",
            **base_kwargs,
        )


class PaperOrderExecutor:
    """
    Test executor.

    IMPORTANT:
    This class NEVER contacts Angel One.
    It only creates a simulated order record.
    """

    name = "PaperOrderExecutor"
    version = "1.0.0"

    def execute(
        self,
        order: AutoBuyResult,
    ) -> dict[str, Any]:

        if not order.allowed:
            return {
                "status": "REJECTED",
                "mode": "PAPER",
                "action": "NO_BUY",
                "reason": order.reason,
                "symbol": order.symbol,
                "exchange": order.exchange,
            }

        return {
            "status": "SIMULATED",
            "mode": "PAPER",
            "action": "BUY",
            "symbol": order.symbol,
            "exchange": order.exchange,
            "horizon_minutes": order.horizon_minutes,
            "quantity": order.quantity,
            "price": order.price,
            "confidence": order.confidence,
            "score": order.score,
            "reason": order.reason,
      }
