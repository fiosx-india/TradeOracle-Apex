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

The Master Brain is the orchestration layer.
Derived/meta engines are NOT counted as independent votes.
"""

from .decision_engine import DecisionEngine
from .evidence_fusion import EvidenceFusion


class ApexMasterBrain:
    name = "ApexMasterBrain"
    capabilities = ["MASTER_DECISION"]

    # These capabilities produce derived information.
    # They must not become independent votes in the final fusion.
    META_CAPABILITIES = {
        "ENSEMBLE",
        "PROBABILITY",
        "RANKING",
        "MOVEMENT_PATH",
    }

    def __init__(self, registry=None, router=None):
        self.registry = registry
        self.router = router

        self.fusion = EvidenceFusion()
        self.decision = DecisionEngine()

    # ------------------------------------------------------------------
    # REGISTRY
    # ------------------------------------------------------------------

    def attach_registry(self, registry, router=None):
        self.registry = registry
        self.router = router

    # ------------------------------------------------------------------
    # CONTEXT HELPERS
    # ------------------------------------------------------------------

    @staticmethod
    def _capabilities(engine):
        if engine is None:
            return set()

        value = getattr(engine, "capabilities", [])

        if isinstance(value, (list, tuple, set)):
            return {
                str(item).upper()
                for item in value
            }

        return set()

    @staticmethod
    def _set_context_value(context, key, value):
        if isinstance(context, dict):
            context[key] = value
            return

        try:
            setattr(context, key, value)
        except Exception:
            pass

    @staticmethod
    def _get_context_value(context, key, default=None):
        if isinstance(context, dict):
            return context.get(key, default)

        return getattr(
            context,
            key,
            default,
        )

    # ------------------------------------------------------------------
    # ENGINE EXECUTION
    # ------------------------------------------------------------------

    def _run_engine(self, engine, context):

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

            if not isinstance(result, dict):
                return None

            item = dict(result)

            item.setdefault(
                "engine",
                getattr(
                    engine,
                    "name",
                    engine.__class__.__name__,
                ),
            )

            item.setdefault(
                "weight",
                1.0,
            )

            item.setdefault(
                "confidence",
                1.0,
            )

            return item

        except Exception as exc:

            return {
                "engine": getattr(
                    engine,
                    "name",
                    engine.__class__.__name__,
                ),
                "score": 0.0,
                "weight": 0.0,
                "confidence": 0.0,
                "reason": (
                    "engine_error:"
                    f"{type(exc).__name__}"
                ),
            }

    # ------------------------------------------------------------------
    # CAPABILITY STAGE
    # ------------------------------------------------------------------

    def _collect_stage(
        self,
        context,
        required_capability,
    ):

        if self.registry is None:
            return []

        evidence = []

        for engine in self.registry.all().values():

            capabilities = self._capabilities(
                engine
            )

            if required_capability not in capabilities:
                continue

            item = self._run_engine(
                engine,
                context,
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
    ):

        research = self._collect_stage(
            context,
            "RESEARCH",
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
    ):

        prediction = []

        if self.registry is None:
            return prediction

        for engine in self.registry.all().values():

            capabilities = self._capabilities(
                engine
            )

            if "PREDICTION" not in capabilities:
                continue

            # ----------------------------------------------------------
            # META engines are deliberately delayed.
            # They must see the completed base prediction evidence.
            # ----------------------------------------------------------

            if capabilities.intersection(
                self.META_CAPABILITIES
            ):
                continue

            item = self._run_engine(
                engine,
                context,
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
    ):

        meta = []

        if self.registry is None:
            return meta

        for engine in self.registry.all().values():

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

    def _select_final_evidence(
        self,
        research_evidence,
        prediction_evidence,
    ):

        # Prediction engines are the preferred final evidence.
        #
        # Research engines are used only when no usable prediction
        # evidence exists.

        usable_prediction = [
            item
            for item in prediction_evidence
            if isinstance(item, dict)
            and (
                float(
                    item.get(
                        "weight",
                        0.0,
                    )
                ) > 0
            )
        ]

        if usable_prediction:
            return usable_prediction

        return research_evidence

    # ------------------------------------------------------------------
    # PUBLIC EVIDENCE COLLECTION
    # ------------------------------------------------------------------

    def collect_evidence(
        self,
        context,
    ):

        if self.registry is None:
            return []

        # --------------------------------------------------------------
        # 1. RESEARCH
        # --------------------------------------------------------------

        research_evidence = (
            self._collect_research(
                context
            )
        )

        # --------------------------------------------------------------
        # 2. BASE PREDICTION
        # --------------------------------------------------------------

        prediction_evidence = (
            self._collect_prediction(
                context
            )
        )

        # --------------------------------------------------------------
        # 3. DERIVED / META ANALYSIS
        # --------------------------------------------------------------

        meta_evidence = (
            self._collect_meta(
                context
            )
        )

        # Keep all three layers available to downstream consumers.
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
        # 4. FINAL VOTING EVIDENCE
        # --------------------------------------------------------------

        return self._select_final_evidence(
            research_evidence,
            prediction_evidence,
        )

    # ------------------------------------------------------------------
    # META OUTPUT HELPERS
    # ------------------------------------------------------------------

    @staticmethod
    def _find_meta(
        meta_evidence,
        engine_name,
    ):

        for item in meta_evidence:

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
    # FINAL EVALUATION
    # ------------------------------------------------------------------

    def evaluate(
        self,
        context,
    ):

        # --------------------------------------------------------------
        # Run complete pipeline.
        # --------------------------------------------------------------

        evidence = self.collect_evidence(
            context
        )

        # --------------------------------------------------------------
        # Fuse ONLY primary decision evidence.
        # Meta engines do not vote independently.
        # --------------------------------------------------------------

        fused = self.fusion.combine(
            evidence
        )

        market_data_quality = self._get_context_value(
            context,
            "market_data_quality",
            {},
        )

        decision = self.decision.decide(
            fused,
            market_data_quality=market_data_quality,
        )

        # --------------------------------------------------------------
        # Read staged outputs.
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

        horizon_minutes = (
            self._get_context_value(
                context,
                "horizon_minutes",
                60,
            )
        )

        # --------------------------------------------------------------
        # Extract derived outputs.
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
        # Final explainable result.
        # --------------------------------------------------------------

        result = {
            "horizon_minutes": horizon_minutes,

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

            "derived": {
                "probability": probability,
                "ensemble": ensemble,
                "ranking": ranking,
                "movement_path": movement_path,
            },
        }

        return result
