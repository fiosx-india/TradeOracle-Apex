"""Apex Master Brain.

Canonical orchestration layer for TradeOracle Apex.

Pipeline per MarketContext / horizon:

    RESEARCH
        ↓
    PRIMARY PREDICTION
        ↓
    DERIVED / META ANALYSIS
        ↓
    PRIMARY EVIDENCE FUSION
        ↓
    FINAL DECISION

Important architecture rules:
- One MarketContext represents exactly one prediction horizon.
- Supported prediction horizons are 5, 15, 30 and 60 minutes.
- Angel One candle interval remains independent from prediction horizon.
- Research and primary prediction evidence are horizon-scoped.
- Derived/meta engines are NOT independent EvidenceFusion votes.
- Evidence from another horizon is rejected.
- Engine failures are diagnostic, not zero-confidence votes.
- No synthetic market data is created here.
- This class orchestrates; it does not place orders or GTTs.
"""

from __future__ import annotations

import math
from typing import Any, Iterable, Mapping

from .decision_engine import DecisionEngine
from .evidence_fusion import EvidenceFusion


# ----------------------------------------------------------------------
# SUPPORTED HORIZONS
# ----------------------------------------------------------------------

try:
    from config import PREDICTION_HORIZONS_MINUTES

    SUPPORTED_HORIZONS = tuple(
        sorted(
            {
                int(value)
                for value in PREDICTION_HORIZONS_MINUTES
            }
        )
    )

except Exception:
    # Safe fallback for isolated imports/tests.
    SUPPORTED_HORIZONS = (
        5,
        15,
        30,
        60,
    )


if not SUPPORTED_HORIZONS:
    raise ValueError(
        "At least one prediction horizon must be configured."
    )


# ----------------------------------------------------------------------
# MASTER BRAIN
# ----------------------------------------------------------------------


class ApexMasterBrain:
    """Sole orchestration layer for one MarketContext at a time."""

    name = "ApexMasterBrain"
    version = "2.4.0"

    capabilities = [
        "MASTER_DECISION",
    ]

    # Derived/meta engines produce information about primary evidence.
    # They must never become independent votes.
    META_CAPABILITIES = {
        "ENSEMBLE",
        "PROBABILITY",
        "RANKING",
        "MOVEMENT_PATH",
    }

    # ------------------------------------------------------------------
    # CONSTRUCTOR
    # ------------------------------------------------------------------

    def __init__(
        self,
        registry=None,
        router=None,
    ):
        self.registry = registry
        self.router = router

        self.fusion = EvidenceFusion()
        self.decision = DecisionEngine()

    # ------------------------------------------------------------------
    # REGISTRY
    # ------------------------------------------------------------------

    def attach_registry(
        self,
        registry,
        router=None,
    ):
        self.registry = registry
        self.router = router

    # ------------------------------------------------------------------
    # CONTEXT HELPERS
    # ------------------------------------------------------------------

    @staticmethod
    def _capabilities(engine) -> set[str]:
        if engine is None:
            return set()

        value = getattr(
            engine,
            "capabilities",
            [],
        )

        if isinstance(
            value,
            (list, tuple, set, frozenset),
        ):
            return {
                str(item).strip().upper()
                for item in value
                if str(item).strip()
            }

        return set()

    @staticmethod
    def _set_context_value(
        context,
        key: str,
        value: Any,
    ) -> None:
        if isinstance(context, dict):
            context[key] = value
            return

        try:
            setattr(
                context,
                key,
                value,
            )
        except Exception:
            # Some immutable/context-wrapper objects may expose
            # read-only fields. The pipeline must not crash merely
            # because a diagnostic field cannot be attached.
            pass

    @staticmethod
    def _get_context_value(
        context,
        key: str,
        default=None,
    ):
        if isinstance(context, Mapping):
            return context.get(
                key,
                default,
            )

        return getattr(
            context,
            key,
            default,
        )

    # ------------------------------------------------------------------
    # HORIZON HELPERS
    # ------------------------------------------------------------------

    @classmethod
    def _get_horizon(
        cls,
        context,
    ) -> int:
        """Resolve and validate the authoritative context horizon."""

        raw = cls._get_context_value(
            context,
            "horizon_minutes",
            None,
        )

        if raw is None:
            raise ValueError(
                "MarketContext.horizon_minutes is required. "
                "The Master Brain will not silently choose a horizon."
            )

        # bool is an int subclass but is not a valid horizon.
        if isinstance(raw, bool):
            raise ValueError(
                "MarketContext.horizon_minutes must be an integer."
            )

        try:
            horizon = int(raw)
        except (
            TypeError,
            ValueError,
        ) as exc:
            raise ValueError(
                "MarketContext.horizon_minutes must be "
                f"an integer. Received: {raw!r}"
            ) from exc

        if horizon not in SUPPORTED_HORIZONS:
            raise ValueError(
                "Unsupported prediction horizon: "
                f"{horizon}. Supported horizons are "
                f"{SUPPORTED_HORIZONS}."
            )

        return horizon

    # ------------------------------------------------------------------
    # ENGINE ITERATION
    # ------------------------------------------------------------------

    def _registered_engines(self) -> list[Any]:
        """Return registry engines deterministically and safely."""

        if self.registry is None:
            return []

        all_fn = getattr(
            self.registry,
            "all",
            None,
        )

        if not callable(all_fn):
            return []

        try:
            registered = all_fn()
        except Exception:
            return []

        if isinstance(
            registered,
            Mapping,
        ):
            return list(
                registered.values()
            )

        if isinstance(
            registered,
            (list, tuple, set, frozenset),
        ):
            return list(
                registered
            )

        return []

    # ------------------------------------------------------------------
    # ENGINE EXECUTION
    # ------------------------------------------------------------------

    def _run_engine(
        self,
        engine,
        context,
        horizon: int,
    ) -> dict[str, Any] | None:
        """
        Execute one engine safely and enforce horizon ownership.

        Important:
        An engine error is returned as diagnostics with weight=0.
        EvidenceFusion will therefore never treat the error as a vote.
        """

        engine_name = str(
            getattr(
                engine,
                "name",
                engine.__class__.__name__,
            )
        ).strip() or engine.__class__.__name__

        try:
            analyze = getattr(
                engine,
                "analyze",
                None,
            )

            predict = getattr(
                engine,
                "predict",
                None,
            )

            if callable(analyze):
                result = analyze(
                    context
                )

            elif callable(predict):
                result = predict(
                    context
                )

            else:
                return {
                    "engine": engine_name,
                    "score": 0.0,
                    "weight": 0.0,
                    "confidence": 0.0,
                    "reason": "engine_has_no_analyze_or_predict",
                    "horizon_minutes": horizon,
                    "horizon_consistent": False,
                    "forecast_available": False,
                }

            if not isinstance(
                result,
                dict,
            ):
                return {
                    "engine": engine_name,
                    "score": 0.0,
                    "weight": 0.0,
                    "confidence": 0.0,
                    "reason": "engine_returned_non_dict",
                    "horizon_minutes": horizon,
                    "horizon_consistent": False,
                    "forecast_available": False,
                }

            item = dict(result)

            item.setdefault(
                "engine",
                engine_name,
            )

            # Keep engine-provided weight/confidence. EvidenceFusion
            # performs final bounded numeric validation.
            item.setdefault(
                "weight",
                1.0,
            )

            item.setdefault(
                "confidence",
                0.0,
            )

            returned_horizon = item.get(
                "horizon_minutes",
                None,
            )

            if returned_horizon is not None:
                if isinstance(
                    returned_horizon,
                    bool,
                ):
                    return {
                        "engine": engine_name,
                        "score": 0.0,
                        "weight": 0.0,
                        "confidence": 0.0,
                        "reason": (
                            "invalid_returned_horizon"
                        ),
                        "horizon_minutes": horizon,
                        "horizon_consistent": False,
                        "forecast_available": False,
                    }

                try:
                    returned_horizon = int(
                        returned_horizon
                    )
                except (
                    TypeError,
                    ValueError,
                ):
                    return {
                        "engine": engine_name,
                        "score": 0.0,
                        "weight": 0.0,
                        "confidence": 0.0,
                        "reason": (
                            "invalid_returned_horizon"
                        ),
                        "horizon_minutes": horizon,
                        "horizon_consistent": False,
                        "forecast_available": False,
                    }

                if returned_horizon != horizon:
                    return {
                        "engine": engine_name,
                        "score": 0.0,
                        "weight": 0.0,
                        "confidence": 0.0,
                        "reason": (
                            "horizon_mismatch:"
                            f"engine={returned_horizon},"
                            f"context={horizon}"
                        ),
                        "horizon_minutes": horizon,
                        "horizon_consistent": False,
                        "forecast_available": False,
                    }

            # The current MarketContext is authoritative.
            item["horizon_minutes"] = horizon
            item["horizon_consistent"] = True

            return item

        except Exception as exc:
            return {
                "engine": engine_name,
                "score": 0.0,
                "weight": 0.0,
                "confidence": 0.0,
                "reason": (
                    "engine_error:"
                    f"{type(exc).__name__}"
                ),
                "error_type": type(exc).__name__,
                "horizon_minutes": horizon,
                "horizon_consistent": False,
                "forecast_available": False,
            }

    # ------------------------------------------------------------------
    # CAPABILITY STAGE
    # ------------------------------------------------------------------

    def _collect_stage(
        self,
        context,
        required_capability: str,
        horizon: int,
    ) -> list[dict[str, Any]]:
        evidence: list[dict[str, Any]] = []

        for engine in self._registered_engines():
            capabilities = self._capabilities(
                engine
            )

            if required_capability not in capabilities:
                continue

            item = self._run_engine(
                engine,
                context,
                horizon,
            )

            if item is not None:
                evidence.append(item)

        return evidence

    # ------------------------------------------------------------------
    # RESEARCH STAGE
    # ------------------------------------------------------------------

    def _collect_research(
        self,
        context,
        horizon: int,
    ) -> list[dict[str, Any]]:
        research = self._collect_stage(
            context,
            "RESEARCH",
            horizon,
        )

        self._set_context_value(
            context,
            "research_evidence",
            research,
        )

        return research

    # ------------------------------------------------------------------
    # PREDICTION STAGE
    # ------------------------------------------------------------------

    def _collect_prediction(
        self,
        context,
        horizon: int,
    ) -> list[dict[str, Any]]:
        prediction: list[dict[str, Any]] = []

        for engine in self._registered_engines():
            capabilities = self._capabilities(
                engine
            )

            if "PREDICTION" not in capabilities:
                continue

            # Meta engines must never become primary votes.
            if capabilities.intersection(
                self.META_CAPABILITIES
            ):
                continue

            item = self._run_engine(
                engine,
                context,
                horizon,
            )

            if item is not None:
                prediction.append(item)

        self._set_context_value(
            context,
            "prediction_evidence",
            prediction,
        )

        return prediction

    # ------------------------------------------------------------------
    # META / DERIVED STAGE
    # ------------------------------------------------------------------

    def _collect_meta(
        self,
        context,
        horizon: int,
    ) -> list[dict[str, Any]]:
        """
        Run derived/meta engines only after research and primary
        prediction evidence have been attached to the context.

        Their results are explanatory/derived outputs, not votes.
        """

        meta: list[dict[str, Any]] = []

        for engine in self._registered_engines():
            capabilities = self._capabilities(
                engine
            )

            if not capabilities.intersection(
                self.META_CAPABILITIES
            ):
                continue

            item = self._run_engine(
                engine,
                context,
                horizon,
            )

            if item is not None:
                meta.append(item)

        self._set_context_value(
            context,
            "meta_evidence",
            meta,
        )

        return meta

    # ------------------------------------------------------------------
    # FINAL VOTING EVIDENCE
    # ------------------------------------------------------------------

    @staticmethod
    def _safe_weight(
        item: Any,
    ) -> float:
        if not isinstance(
            item,
            Mapping,
        ):
            return 0.0

        try:
            value = float(
                item.get(
                    "weight",
                    0.0,
                )
                or 0.0
            )
        except (
            TypeError,
            ValueError,
        ):
            return 0.0

        if not math.isfinite(value):
            return 0.0

        return max(
            0.0,
            value,
        )

    @staticmethod
    def _is_usable_evidence(
        item: Any,
        horizon: int,
    ) -> bool:
        if not isinstance(
            item,
            Mapping,
        ):
            return False

        if not item.get(
            "horizon_consistent",
            True,
        ):
            return False

        item_horizon = item.get(
            "horizon_minutes",
            horizon,
        )

        try:
            return int(item_horizon) == horizon
        except (
            TypeError,
            ValueError,
        ):
            return False

    def _select_final_evidence(
        self,
        research_evidence: Iterable[Any],
        prediction_evidence: Iterable[Any],
        horizon: int,
    ) -> list[dict[str, Any]]:
        """
        Select primary voting evidence.

        Priority:
            1. usable primary prediction evidence
            2. research evidence only when no usable prediction exists

        Meta evidence is never included.
        """

        usable_prediction = [
            dict(item)
            for item in prediction_evidence
            if self._is_usable_evidence(
                item,
                horizon,
            )
            and self._safe_weight(item) > 0.0
        ]

        if usable_prediction:
            return usable_prediction

        return [
            dict(item)
            for item in research_evidence
            if self._is_usable_evidence(
                item,
                horizon,
            )
            and self._safe_weight(item) > 0.0
        ]

    # ------------------------------------------------------------------
    # PUBLIC EVIDENCE COLLECTION
    # ------------------------------------------------------------------

    def collect_evidence(
        self,
        context,
    ) -> list[dict[str, Any]]:
        """
        Execute the staged pipeline for exactly one horizon.

        No evidence from another MarketContext is retained or mixed.
        """

        horizon = self._get_horizon(
            context
        )

        # --------------------------------------------------------------
        # 1. RESEARCH
        # --------------------------------------------------------------

        research_evidence = (
            self._collect_research(
                context,
                horizon,
            )
        )

        # --------------------------------------------------------------
        # 2. PRIMARY PREDICTION
        # --------------------------------------------------------------

        prediction_evidence = (
            self._collect_prediction(
                context,
                horizon,
            )
        )

        # --------------------------------------------------------------
        # 3. DERIVED / META
        # --------------------------------------------------------------

        meta_evidence = (
            self._collect_meta(
                context,
                horizon,
            )
        )

        # --------------------------------------------------------------
        # 4. PRIMARY FINAL VOTING EVIDENCE
        # --------------------------------------------------------------

        final_evidence = (
            self._select_final_evidence(
                research_evidence,
                prediction_evidence,
                horizon,
            )
        )

        # --------------------------------------------------------------
        # 5. STORE STAGED OUTPUTS
        # --------------------------------------------------------------

        self._set_context_value(
            context,
            "research_evidence",
            research_evidence,
        )

        self._set_context_value(
            context,
            "prediction_evidence",
            prediction_evidence,
        )

        self._set_context_value(
            context,
            "meta_evidence",
            meta_evidence,
        )

        self._set_context_value(
            context,
            "final_evidence",
            final_evidence,
        )

        return final_evidence

    # ------------------------------------------------------------------
    # META OUTPUT HELPERS
    # ------------------------------------------------------------------

    @staticmethod
    def _find_meta(
        meta_evidence: Iterable[Any],
        engine_name: str,
    ):
        for item in meta_evidence:
            if not isinstance(
                item,
                Mapping,
            ):
                continue

            if (
                str(
                    item.get(
                        "engine",
                        "",
                    )
                ).strip()
                == engine_name
            ):
                return dict(item)

        return None

    # ------------------------------------------------------------------
    # HORIZON CONSISTENCY
    # ------------------------------------------------------------------

    @staticmethod
    def _validate_stage_horizons(
        evidence: Iterable[Any],
        horizon: int,
    ) -> list[str]:
        mismatches: list[str] = []

        for item in evidence:
            if not isinstance(
                item,
                Mapping,
            ):
                continue

            item_horizon = item.get(
                "horizon_minutes",
                horizon,
            )

            try:
                item_horizon = int(
                    item_horizon
                )
            except (
                TypeError,
                ValueError,
            ):
                mismatches.append(
                    str(
                        item.get(
                            "engine",
                            "unknown",
                        )
                    )
                )
                continue

            if item_horizon != horizon:
                mismatches.append(
                    str(
                        item.get(
                            "engine",
                            "unknown",
                        )
                    )
                )

        return mismatches

    # ------------------------------------------------------------------
    # FINAL EVALUATION
    # ------------------------------------------------------------------

    def evaluate(
        self,
        context,
    ) -> dict[str, Any]:
        """
        Execute the complete Master Brain pipeline for one horizon.

        The Orchestrator is responsible for creating separate contexts
        and calling this method separately for 5, 15, 30 and 60 minutes.
        """

        # --------------------------------------------------------------
        # 0. AUTHORITATIVE HORIZON
        # --------------------------------------------------------------

        horizon = self._get_horizon(
            context
        )

        # --------------------------------------------------------------
        # 1. COMPLETE PIPELINE
        # --------------------------------------------------------------

        evidence = self.collect_evidence(
            context
        )

        # --------------------------------------------------------------
        # 2. FINAL HORIZON SAFETY CHECK
        # --------------------------------------------------------------

        horizon_mismatches = (
            self._validate_stage_horizons(
                evidence,
                horizon,
            )
        )

        # --------------------------------------------------------------
        # 3. PRIMARY EVIDENCE FUSION
        # --------------------------------------------------------------

        fused = self.fusion.combine(
            evidence
        )

        self._set_context_value(
            context,
            "fused_evidence",
            fused,
        )

        # --------------------------------------------------------------
        # 4. MARKET DATA QUALITY
        # --------------------------------------------------------------

        market_data_quality = (
            self._get_context_value(
                context,
                "market_data_quality",
                {},
            )
        )

        if not isinstance(
            market_data_quality,
            Mapping,
        ):
            market_data_quality = {}

        # --------------------------------------------------------------
        # 5. FINAL DECISION
        # --------------------------------------------------------------
        #
        # SignalGate ownership remains with DecisionEngine if the
        # current DecisionEngine integrates it. Master Brain does not
        # duplicate the gate here.
        # --------------------------------------------------------------

        decision = self.decision.decide(
            fused,
            market_data_quality=dict(
                market_data_quality
            ),
        )

        # --------------------------------------------------------------
        # 6. STAGED OUTPUTS
        # --------------------------------------------------------------

        research_evidence = (
            self._get_context_value(
                context,
                "research_evidence",
                [],
            )
        )

        prediction_evidence = (
            self._get_context_value(
                context,
                "prediction_evidence",
                [],
            )
        )

        meta_evidence = (
            self._get_context_value(
                context,
                "meta_evidence",
                [],
            )
        )

        final_evidence = (
            self._get_context_value(
                context,
                "final_evidence",
                evidence,
            )
        )

        # --------------------------------------------------------------
        # 7. DERIVED OUTPUTS
        # --------------------------------------------------------------

        probability = self._find_meta(
            meta_evidence,
            "ProbabilityEngine",
        )

        ensemble = self._find_meta(
            meta_evidence,
            "EnsembleEngine",
        )

        ranking = self._find_meta(
            meta_evidence,
            "RankingEngine",
        )

        movement_path = self._find_meta(
            meta_evidence,
            "MovementPathEngine",
        )

        # --------------------------------------------------------------
        # 8. RESULT
        # --------------------------------------------------------------

        return {
            "horizon_minutes": horizon,

            "horizon_supported": (
                horizon in SUPPORTED_HORIZONS
            ),

            "horizon_consistency": {
                "valid": not bool(
                    horizon_mismatches
                ),
                "mismatched_engines": (
                    horizon_mismatches
                ),
            },

            "decision": decision,

            "research_evidence": (
                research_evidence
            ),

            "prediction_evidence": (
                prediction_evidence
            ),

            "meta_evidence": (
                meta_evidence
            ),

            "final_evidence": (
                final_evidence
            ),

            "fused_evidence": fused,

            "derived": {
                "probability": probability,
                "ensemble": ensemble,
                "ranking": ranking,
                "movement_path": movement_path,
            },
        }

    # ------------------------------------------------------------------
    # HEALTH
    # ------------------------------------------------------------------

    def health(self) -> dict[str, Any]:
        """Return orchestration readiness without claiming broker health."""

        return {
            "engine": self.name,
            "version": self.version,
            "registry_configured": self.registry is not None,
            "router_configured": self.router is not None,
            "supported_horizons": list(
                SUPPORTED_HORIZONS
            ),
            "meta_capabilities": sorted(
                self.META_CAPABILITIES
            ),
            "status": (
                "READY"
                if self.registry is not None
                else "NO_REGISTRY"
            ),
        }
