"""Bounded evidence fusion with duplicate-engine protection.

TradeOracle Apex contract:
- fuse independent primary evidence only
- do not let duplicate engine rows become independent votes
- keep scores, weights and confidence bounded
- reject non-finite numeric evidence
- never manufacture evidence or confidence
- expose explainable fusion output for DecisionEngine

Derived/meta engines such as probability, ensemble, ranking and
movement-path engines are excluded by ApexMasterBrain before this
module is called. This class therefore focuses on safe fusion of the
primary evidence it receives.
"""

from __future__ import annotations

import math
from typing import Any, Iterable


class EvidenceFusion:
    """Combine independent evidence without double-counting engines."""

    name = "EvidenceFusion"
    version = "2.2.0"

    MIN_DIRECTIONAL_SCORE = 0.05
    COVERAGE_TARGET = 5

    # ==================================================================
    # NUMERIC HELPERS
    # ==================================================================

    @staticmethod
    def _finite_float(
        value: Any,
    ) -> float | None:
        if value is None or isinstance(value, bool):
            return None

        try:
            number = float(value)
        except (
            TypeError,
            ValueError,
        ):
            return None

        if not math.isfinite(number):
            return None

        return number

    @staticmethod
    def _clamp(
        value: float,
        low: float,
        high: float,
    ) -> float:
        return max(
            low,
            min(high, value),
        )

    # ==================================================================
    # EMPTY RESULT
    # ==================================================================

    @staticmethod
    def _empty_result(
        evidence: list[dict[str, Any]] | None = None,
        reasons: list[str] | None = None,
    ) -> dict[str, Any]:
        return {
            "score": 0.0,
            "confidence": 0.0,
            "agreement": 0.0,
            "evidence_coverage": 0.0,
            "engine_count": len(evidence or []),
            "evidence": evidence or [],
            "reasons": reasons or [],
        }

    # ==================================================================
    # NORMALIZATION
    # ==================================================================

    def _normalize_item(
        self,
        item: Any,
    ) -> dict[str, Any] | None:
        if not isinstance(item, dict):
            return None

        # Engine identity is required for duplicate protection.
        engine_value = item.get("engine")

        if engine_value is None:
            engine_value = item.get("source")

        if engine_value is None:
            return None

        engine = str(
            engine_value
        ).strip()

        if not engine:
            return None

        score = self._finite_float(
            item.get("score", 0.0)
        )

        weight = self._finite_float(
            item.get("weight", 1.0)
        )

        confidence = self._finite_float(
            item.get("confidence", 0.0)
        )

        if (
            score is None
            or weight is None
            or confidence is None
        ):
            return None

        # Score is a directional evidence value.
        score = self._clamp(
            score,
            -1.0,
            1.0,
        )

        # Negative weight has no valid meaning in this fusion model.
        # Zero weight is non-contributing evidence and is not included.
        weight = max(
            0.0,
            weight,
        )

        confidence = self._clamp(
            confidence,
            0.0,
            1.0,
        )

        if weight <= 0.0:
            return None

        return {
            "engine": engine,
            "score": score,
            "weight": weight,
            "confidence": confidence,
            "reason": str(
                item.get("reason", "")
            ),
        }

    # ==================================================================
    # COMBINE
    # ==================================================================

    def combine(
        self,
        evidence: Iterable[Any] | None,
    ) -> dict[str, Any]:
        """
        Fuse usable primary evidence.

        Duplicate protection is applied only after an evidence row has
        passed validation. Therefore an invalid first row from an engine
        cannot block a later valid row from that same engine.
        """

        usable: list[dict[str, Any]] = []
        seen_engines: set[str] = set()

        skipped_invalid = 0
        skipped_duplicates = 0

        for item in evidence or ():
            normalized = self._normalize_item(item)

            if normalized is None:
                skipped_invalid += 1
                continue

            # Case-insensitive engine identity prevents:
            # RSIEngine / rsiengine / RSIENGINE
            # from becoming separate votes.
            engine_key = normalized["engine"].casefold()

            if engine_key in seen_engines:
                skipped_duplicates += 1
                continue

            seen_engines.add(engine_key)
            usable.append(normalized)

        if not usable:
            result = self._empty_result()
            result["skipped_invalid"] = skipped_invalid
            result["skipped_duplicates"] = skipped_duplicates

            if skipped_invalid:
                result["reasons"] = [
                    f"invalid_evidence_items:{skipped_invalid}"
                ]

            return result

        weighted = [
            item["weight"] * item["confidence"]
            for item in usable
        ]

        total_weight = sum(weighted)

        if (
            total_weight <= 0.0
            or not math.isfinite(total_weight)
        ):
            reasons = [
                item["reason"]
                for item in usable
                if item["reason"]
            ]

            reasons.append(
                "no_positive_effective_evidence_weight"
            )

            result = self._empty_result(
                usable,
                reasons,
            )
            result["skipped_invalid"] = skipped_invalid
            result["skipped_duplicates"] = skipped_duplicates
            return result

        # --------------------------------------------------------------
        # WEIGHTED DIRECTIONAL SCORE
        # --------------------------------------------------------------

        score = sum(
            item["score"] * effective_weight
            for item, effective_weight
            in zip(usable, weighted)
        ) / total_weight

        score = self._clamp(
            score,
            -1.0,
            1.0,
        )

        # --------------------------------------------------------------
        # DIRECTIONAL AGREEMENT
        # --------------------------------------------------------------

        positive = sum(
            effective_weight
            for item, effective_weight
            in zip(usable, weighted)
            if item["score"] > self.MIN_DIRECTIONAL_SCORE
        )

        negative = sum(
            effective_weight
            for item, effective_weight
            in zip(usable, weighted)
            if item["score"] < -self.MIN_DIRECTIONAL_SCORE
        )

        directional = positive + negative

        agreement = (
            max(
                positive,
                negative,
            ) / directional
            if directional > 0.0
            else 0.0
        )

        agreement = self._clamp(
            agreement,
            0.0,
            1.0,
        )

        # --------------------------------------------------------------
        # EVIDENCE COVERAGE
        # --------------------------------------------------------------
        # Coverage prevents a single engine with a strong score from
        # looking like a fully corroborated multi-engine conclusion.
        # It is a confidence-quality component, not a market probability.

        evidence_coverage = self._clamp(
            len(usable) / float(self.COVERAGE_TARGET),
            0.0,
            1.0,
        )

        # --------------------------------------------------------------
        # CONFIDENCE
        # --------------------------------------------------------------
        # Confidence is intentionally NOT abs(score) alone.
        #
        # Strong confidence requires:
        #   - directional strength
        #   - cross-engine agreement
        #   - more than one piece of usable evidence where available
        #
        # It remains an evidence-quality estimate, not a probability of
        # future market outcome.

        confidence = (
            0.45 * abs(score)
            + 0.35 * agreement
            + 0.20 * evidence_coverage
        )

        confidence = self._clamp(
            confidence,
            0.0,
            1.0,
        )

        reasons = [
            item["reason"]
            for item in usable
            if item["reason"]
        ]

        if skipped_invalid:
            reasons.append(
                f"invalid_evidence_items:{skipped_invalid}"
            )

        if skipped_duplicates:
            reasons.append(
                f"duplicate_engines_ignored:{skipped_duplicates}"
            )

        return {
            "score": round(score, 6),
            "confidence": round(confidence, 6),
            "agreement": round(agreement, 6),
            "evidence_coverage": round(
                evidence_coverage,
                6,
            ),
            "engine_count": len(usable),
            "evidence": usable,
            "reasons": reasons,
            "skipped_invalid": skipped_invalid,
            "skipped_duplicates": skipped_duplicates,
        }

    # ==================================================================
    # HEALTH
    # ==================================================================

    def health(self) -> dict[str, Any]:
        return {
            "engine": self.name,
            "version": self.version,
            "min_directional_score": self.MIN_DIRECTIONAL_SCORE,
            "coverage_target": self.COVERAGE_TARGET,
            "status": "READY",
        }
