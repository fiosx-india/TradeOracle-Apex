"""Apex Master Brain.

Pipeline:
RESEARCH
    ↓
PREDICTION
    ↓
DERIVED / META ANALYSIS
    ↓
EVIDENCE FUSION
    ↓
FINAL DECISION

The Master Brain is the sole orchestration layer for the
research/prediction/meta/decision pipeline.

Important multi-horizon rule:
    One MarketContext = One prediction horizon.

Supported horizons:
    5
    15
    30
    60

The Master Brain does NOT create four horizons itself.
The Orchestrator creates the appropriate MarketContext and
calls evaluate(context) once for each horizon.

Derived/meta engines are NOT counted as independent votes.
"""

from typing import Any

from .decision_engine import DecisionEngine
from .evidence_fusion import EvidenceFusion


# ----------------------------------------------------------------------
# SUPPORTED HORIZONS
# ----------------------------------------------------------------------

try:
    from config import PREDICTION_HORIZONS_MINUTES

    SUPPORTED_HORIZONS = tuple(
        sorted(
            int(value)
            for value in PREDICTION_HORIZONS_MINUTES
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
    """
    Central orchestration layer for Apex.

    The Master Brain runs the same pipeline independently for
    each MarketContext/horizon:

        Research
            ↓
        Base Prediction
            ↓
        Meta / Derived
            ↓
        Evidence Fusion
            ↓
        Final Decision

    The Master Brain does NOT mix evidence from different horizons.

    Example:

        context.horizon_minutes = 5
            → only 5-minute evidence

        context.horizon_minutes = 15
            → only 15-minute evidence

        context.horizon_minutes = 30
            → only 30-minute evidence

        context.horizon_minutes = 60
            → only 60-minute evidence
    """

    name = "ApexMasterBrain"
    version = "2.3.0"

    capabilities = [
        "MASTER_DECISION",
    ]

    # ------------------------------------------------------------------
    # META CAPABILITIES
    # ------------------------------------------------------------------
    #
    # These engines produce derived information.
    #
    # They MUST NOT become independent votes in EvidenceFusion.
    #
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
        """
        Return normalized engine capabilities.
        """

        if engine is None:
            return set()

        value = getattr(
            engine,
            "capabilities",
            [],
        )

        if isinstance(
            value,
            (list, tuple, set),
        ):
            return {
                str(item).upper()
                for item in value
            }

        return set()

    @staticmethod
    def _set_context_value(
        context,
        key: str,
        value: Any,
    ) -> None:
        """
        Store a value on either a dict context or object context.
        """

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
            pass

    @staticmethod
    def _get_context_value(
        context,
        key: str,
        default=None,
    ):
        """
        Read a value from either a dict context or object context.
        """

        if isinstance(context, dict):
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
        """
        Resolve the authoritative horizon from MarketContext.

        The context is authoritative.

        We deliberately do NOT default to 60 minutes anymore.
        """

        raw = cls._get_context_value(
            context,
            "horizon_minutes",
            5,
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
    # ENGINE EXECUTION
    # ------------------------------------------------------------------

    def _run_engine(
        self,
        engine,
        context,
        horizon: int,
    ):
        """
        Execute one engine safely.

        Every engine result is tagged with the current horizon.

        If an engine explicitly returns a different horizon,
        that is treated as a horizon mismatch and the evidence
        is disabled rather than silently mixing horizons.
        """

        engine_name = getattr(
            engine,
            "name",
            engine.__class__.__name__,
        )

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
                return None

            if not isinstance(
                result,
                dict,
            ):
                return None

            item = dict(result)

            item.setdefault(
                "engine",
                engine_name,
            )

            item.setdefault(
                "weight",
                1.0,
            )

            item.setdefault(
                "confidence",
                0.0,
            )

            # ----------------------------------------------------------
            # HORIZON CONSISTENCY
            # ----------------------------------------------------------

            returned_horizon = item.get(
                "horizon_minutes",
                None,
            )

            if returned_horizon is not None:

                try:
                    returned_horizon = int(
                        returned_horizon
                    )

                except (
                    TypeError,
                    ValueError,
                ):
                    returned_horizon = None

            # An engine that explicitly claims another horizon
            # must not be allowed into this horizon's evidence.
            if (
                returned_horizon is not None
                and returned_horizon != horizon
            ):
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

            # Context is authoritative.
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
    ):
        """
        Collect engines belonging to one capability stage.
        """

        if self.registry is None:
            return []

        evidence = []

        for engine in (
            self.registry.all().values()
        ):

            capabilities = self._capabilities(
                engine
            )

            if (
                required_capability
                not in capabilities
            ):
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
    ):
        """
        Run all RESEARCH engines.

        Research evidence is stored on the current context only.
        """

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
    ):
        """
        Run BASE prediction engines.

        Meta/derived engines are deliberately excluded here.

        This means:

            PredictionEngine
            SixtyMinuteEngine
            BreakoutEngine
            ReversalEngine
            EarlyMovementEngine
            etc.

        may contribute according to their capabilities,

        while:

            EnsembleEngine
            ProbabilityEngine
            RankingEngine
            MovementPathEngine

        are delayed until the meta stage.
        """

        prediction = []

        if self.registry is None:
            return prediction

        for engine in (
            self.registry.all().values()
        ):

            capabilities = self._capabilities(
                engine
            )

            if "PREDICTION" not in capabilities:
                continue

            # ----------------------------------------------------------
            # META ENGINES ARE NOT PRIMARY PREDICTION VOTES
            # ----------------------------------------------------------

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
    ):
        """
        Run derived/meta engines.

        Meta engines see the completed research and primary
        prediction evidence through the current MarketContext.

        Their results are stored for explanation and downstream
        consumers but are NOT independently fused as votes.
        """

        meta = []

        if self.registry is None:
            return meta

        for engine in (
            self.registry.all().values()
        ):

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
    # FINAL DECISION EVIDENCE
    # ------------------------------------------------------------------

    @staticmethod
    def _safe_weight(
        item,
    ) -> float:
        """
        Safely extract an evidence weight.
        """

        try:
            return max(
                0.0,
                float(
                    item.get(
                        "weight",
                        0.0,
                    )
                    or 0.0
                ),
            )

        except (
            TypeError,
            ValueError,
        ):
            return 0.0

    def _select_final_evidence(
        self,
        research_evidence,
        prediction_evidence,
    ):
        """
        Select primary voting evidence.

        Priority:
            1. usable prediction evidence
            2. research evidence as fallback

        Meta evidence is NEVER included here.
        """

        usable_prediction = [
            item
            for item in prediction_evidence
            if isinstance(
                item,
                dict,
            )
            and item.get(
                "horizon_consistent",
                True,
            )
            and self._safe_weight(
                item
            ) > 0.0
        ]

        if usable_prediction:
            return usable_prediction

        return [
            item
            for item in research_evidence
            if isinstance(
                item,
                dict,
            )
            and item.get(
                "horizon_consistent",
                True,
            )
            and self._safe_weight(
                item
            ) > 0.0
        ]

    # ------------------------------------------------------------------
    # PUBLIC EVIDENCE COLLECTION
    # ------------------------------------------------------------------

    def collect_evidence(
        self,
        context,
    ):
        """
        Execute the complete evidence pipeline for ONE horizon.

        This method must never combine evidence from another
        MarketContext/horizon.
        """

        if self.registry is None:
            return []

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
        # 2. BASE PREDICTION
        # --------------------------------------------------------------

        prediction_evidence = (
            self._collect_prediction(
                context,
                horizon,
            )
        )

        # --------------------------------------------------------------
        # 3. DERIVED / META ANALYSIS
        # --------------------------------------------------------------

        meta_evidence = (
            self._collect_meta(
                context,
                horizon,
            )
        )

        # --------------------------------------------------------------
        # 4. STORE COMPLETE STAGED CONTEXT
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

        # --------------------------------------------------------------
        # 5. PRIMARY FINAL VOTING EVIDENCE
        # --------------------------------------------------------------

        final_evidence = (
            self._select_final_evidence(
                research_evidence,
                prediction_evidence,
            )
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
        meta_evidence,
        engine_name: str,
    ):
        """
        Find one specific meta-engine result.
        """

        for item in meta_evidence:

            if not isinstance(
                item,
                dict,
            ):
                continue

            if (
                str(
                    item.get(
                        "engine",
                        "",
                    )
                )
                == engine_name
            ):
                return item

        return None

    # ------------------------------------------------------------------
    # HORIZON CONSISTENCY CHECK
    # ------------------------------------------------------------------

    @staticmethod
    def _validate_stage_horizons(
        evidence,
        horizon: int,
    ):
        """
        Verify that evidence belongs to the current horizon.

        This prevents accidental cross-horizon contamination.
        """

        mismatches = []

        for item in evidence:

            if not isinstance(
                item,
                dict,
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
                    item.get(
                        "engine",
                        "unknown",
                    )
                )
                continue

            if item_horizon != horizon:
                mismatches.append(
                    item.get(
                        "engine",
                        "unknown",
                    )
                )

        return mismatches

    # ------------------------------------------------------------------
    # FINAL EVALUATION
    # ------------------------------------------------------------------

    def evaluate(
        self,
        context,
    ):
        """
        Execute the complete Master Brain pipeline for ONE horizon.

        The Orchestrator should call this method separately for:

            5m
            15m
            30m
            60m

        using separate MarketContext objects.
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
        # 2. HORIZON SAFETY CHECK
        # --------------------------------------------------------------

        horizon_mismatches = (
            self._validate_stage_horizons(
                evidence,
                horizon,
            )
        )

        # --------------------------------------------------------------
        # 3. FUSE ONLY PRIMARY EVIDENCE
        # --------------------------------------------------------------
        #
        # Meta engines do not vote independently.
        # --------------------------------------------------------------

        fused = self.fusion.combine(
            evidence
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

        # --------------------------------------------------------------
        # 5. FINAL DECISION
        # --------------------------------------------------------------

        decision = self.decision.decide(
            fused,
            market_data_quality=(
                market_data_quality
            ),
        )

        # --------------------------------------------------------------
        # 6. READ STAGED OUTPUTS
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
        # 8. FINAL RESULT
        # --------------------------------------------------------------

        result = {
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

            "derived": {
                "probability": probability,
                "ensemble": ensemble,
                "ranking": ranking,
                "movement_path": movement_path,
            },
        }

        return result
