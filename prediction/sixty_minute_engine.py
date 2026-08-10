from __future__ import annotations

import statistics


def _data(ctx):
    data = getattr(ctx, "data", None)
    return data if isinstance(data, dict) else {}


def _series(ctx, *keys):
    data = _data(ctx)

    for key in keys:
        values = data.get(key)

        if isinstance(values, (list, tuple)):
            output = []

            for value in values:
                try:
                    output.append(float(value))
                except (TypeError, ValueError):
                    continue

            if output:
                return output

    return []


def _clamp(value, low=-1.0, high=1.0):
    try:
        value = float(value)
    except (TypeError, ValueError):
        value = 0.0

    return max(low, min(high, value))


def _ratio(a, b, default=0.0):
    return a / b if b else default


def _prediction_evidence(ctx):
    """
    Use completed primary prediction evidence.

    The 60-minute engine is a META/DERIVED engine.
    Therefore it must consume the prediction stage,
    not accidentally fall back to raw research evidence.
    """

    value = getattr(ctx, "prediction_evidence", None)

    if isinstance(value, list):
        return [
            item
            for item in value
            if isinstance(item, dict)
        ]

    data = _data(ctx)

    value = data.get("prediction_evidence")

    if isinstance(value, list):
        return [
            item
            for item in value
            if isinstance(item, dict)
        ]

    return []


def _result(
    engine,
    score,
    confidence,
    reason,
    weight=1.0,
    **extra,
):
    result = {
        "engine": engine,
        "score": round(_clamp(score), 6),
        "confidence": round(
            max(0.0, min(1.0, float(confidence))),
            6,
        ),
        "weight": max(0.0, float(weight)),
        "reason": reason,
    }

    result.update(extra)

    return result


class SixtyMinuteEngine:
    """
    Rolling 60-minute directional forecast.

    The engine estimates the direction over the NEXT
    60 minutes from the currently available primary
    prediction evidence and recent market volatility.

    This is a model-derived forecast.
    It is NOT a statistically calibrated probability
    unless historical calibration has been performed.
    """

    name = "SixtyMinuteEngine"
    version = "2.1.0"

    capabilities = [
        "PREDICTION",
        "60_MINUTE",
    ]

    def self_test(self):
        return True

    def predict(self, context):
        evidence = _prediction_evidence(context)

        if not evidence:
            return _result(
                self.name,
                0.0,
                0.0,
                "No primary prediction evidence available",
                0.0,
                direction="SIDEWAYS",
                horizon_minutes=60,
                forecast_status="WITHHELD",
            )

        usable = []

        for item in evidence:
            try:
                score = _clamp(
                    item.get("score", 0.0)
                )

                weight = max(
                    0.0,
                    float(
                        item.get(
                            "weight",
                            1.0,
                        )
                    ),
                )

                confidence = max(
                    0.0,
                    min(
                        1.0,
                        float(
                            item.get(
                                "confidence",
                                0.0,
                            )
                        ),
                    ),
                )

            except (
                TypeError,
                ValueError,
            ):
                continue

            if weight <= 0.0 or confidence <= 0.0:
                continue

            usable.append(
                (
                    score,
                    weight,
                    confidence,
                )
            )

        if not usable:
            return _result(
                self.name,
                0.0,
                0.0,
                "Primary prediction evidence is not usable",
                0.0,
                direction="SIDEWAYS",
                horizon_minutes=60,
                forecast_status="WITHHELD",
            )

        weighted_scores = [
            score * weight * confidence
            for score, weight, confidence in usable
        ]

        effective_weights = [
            weight * confidence
            for _, weight, confidence in usable
        ]

        total_weight = sum(
            effective_weights
        )

        score = _ratio(
            sum(weighted_scores),
            total_weight,
        )

        positive_weight = sum(
            weight
            for score_value, weight, _ in usable
            if score_value > 0.05
        )

        negative_weight = sum(
            weight
            for score_value, weight, _ in usable
            if score_value < -0.05
        )

        agreement = _ratio(
            max(
                positive_weight,
                negative_weight,
            ),
            sum(
                weight
                for _, weight, _ in usable
            ),
        )

        direction = (
            "UP"
            if score >= 0.12
            else "DOWN"
            if score <= -0.12
            else "SIDEWAYS"
        )

        # This is model confidence, NOT calibrated probability.
        confidence = min(
            0.97,
            0.20
            + 0.55 * abs(score)
            + 0.35 * agreement,
        )

        close = _series(
            context,
            "close",
            "closes",
            "price",
            "prices",
        )

        volatility = 0.0

        if len(close) >= 6:
            returns = [
                _ratio(
                    current - previous,
                    abs(previous),
                )
                for previous, current
                in zip(
                    close[-6:-1],
                    close[-5:],
                )
                if previous
            ]

            if len(returns) > 1:
                volatility = statistics.pstdev(
                    returns
                )

        expected_return = (
            _clamp(score)
            * max(
                volatility,
                0.002,
            )
            * 2.0
        )

        return _result(
            self.name,
            score,
            confidence,
            (
                "Rolling 60-minute forecast from "
                f"{len(usable)} primary prediction engines; "
                f"score={score:.3f}, "
                f"agreement={agreement:.2f}"
            ),
            1.25,
            direction=direction,
            horizon_minutes=60,
            expected_return=round(
                expected_return,
                6,
            ),
            agreement=round(
                agreement,
                6,
            ),
            uncertainty=round(
                max(
                    0.0,
                    1.0 - confidence,
                ),
                6,
            ),
            forecast_status="ACTIVE",
        )

    analyze = predict
