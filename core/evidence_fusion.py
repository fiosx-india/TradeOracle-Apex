"""Weighted, bounded evidence fusion with duplicate-engine protection."""

class EvidenceFusion:
    def combine(self, evidence):
        usable = []
        seen_engines = set()

        for item in evidence or []:
            if not isinstance(item, dict):
                continue

            engine = str(item.get("engine", "unknown"))
            if engine in seen_engines:
                continue
            seen_engines.add(engine)

            try:
                score = float(item.get("score", 0.0))
                weight = max(0.0, float(item.get("weight", 1.0)))
                confidence = min(
                    1.0, max(0.0, float(item.get("confidence", 1.0)))
                )
            except (TypeError, ValueError):
                continue

            score = max(-1.0, min(1.0, score))
            usable.append({
                "engine": engine,
                "score": score,
                "weight": weight,
                "confidence": confidence,
                "reason": str(item.get("reason", "")),
            })

        if not usable:
            return {
                "score": 0.0,
                "confidence": 0.0,
                "agreement": 0.0,
                "evidence": [],
                "reasons": [],
            }

        total_weight = sum(x["weight"] * x["confidence"] for x in usable)
        if total_weight <= 0:
            return {
                "score": 0.0,
                "confidence": 0.0,
                "agreement": 0.0,
                "evidence": usable,
                "reasons": [x["reason"] for x in usable if x["reason"]],
            }

        score = sum(
            x["score"] * x["weight"] * x["confidence"]
            for x in usable
        ) / total_weight

        positive = sum(
            x["weight"] * x["confidence"]
            for x in usable if x["score"] > 0.05
        )
        negative = sum(
            x["weight"] * x["confidence"]
            for x in usable if x["score"] < -0.05
        )
        directional = positive + negative
        agreement = (
            max(positive, negative) / directional
            if directional else 0.0
        )

        # Confidence is evidence quality + directional agreement,
        # not a guarantee of market outcome.
        confidence = min(
            1.0,
            0.5 * abs(score) + 0.5 * agreement
        )

        return {
            "score": round(score, 6),
            "confidence": round(confidence, 6),
            "agreement": round(agreement, 6),
            "evidence": usable,
            "reasons": [x["reason"] for x in usable if x["reason"]],
        }
