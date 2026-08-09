"""Apex Master Brain.

The Master Brain is the final decision layer. It collects research evidence,
feeds that evidence into prediction engines, and fuses the primary prediction
outputs into one explainable directional decision.
"""

from .decision_engine import DecisionEngine
from .evidence_fusion import EvidenceFusion


class ApexMasterBrain:
    name = "ApexMasterBrain"
    capabilities = ["MASTER_DECISION"]

    def __init__(self, registry=None, router=None):
        self.registry = registry
        self.router = router
        self.fusion = EvidenceFusion()
        self.decision = DecisionEngine()

    def attach_registry(self, registry, router=None):
        self.registry = registry
        self.router = router

    @staticmethod
    def _capabilities(engine):
        value = getattr(engine, "capabilities", [])

        if isinstance(value, (list, tuple, set)):
            return {str(x).upper() for x in value}

        return set()

    @staticmethod
    def _set_context_value(context, key, value):
        if isinstance(context, dict):
            context[key] = value
        else:
            try:
                setattr(context, key, value)
            except Exception:
                pass

    def _run_engine(self, engine, context):
        try:
            analyze = getattr(engine, "analyze", None)
            predict = getattr(engine, "predict", None)

            if callable(analyze):
                result = analyze(context)

            elif callable(predict):
                result = predict(context)

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

            item.setdefault("weight", 1.0)
            item.setdefault("confidence", 1.0)

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
                "reason": f"engine_error:{type(exc).__name__}",
            }

    def _collect_stage(self, context, required_capability):
        if self.registry is None:
            return []

        evidence = []

        for engine in self.registry.all().values():

            capabilities = self._capabilities(engine)

            if required_capability not in capabilities:
                continue

            item = self._run_engine(
                engine,
                context,
            )

            if item is not None:
                evidence.append(item)

        return evidence

    def collect_evidence(self, context):
        """Collect final decision evidence through research -> prediction."""

        if self.registry is None:
            return []

        # ---------------------------------------------------------
        # STAGE 1: RESEARCH
        # ---------------------------------------------------------

        research_evidence = self._collect_stage(
            context,
            "RESEARCH",
        )

        self._set_context_value(
            context,
            "research_evidence",
            research_evidence,
        )

        # ---------------------------------------------------------
        # STAGE 2: PREDICTION
        # ---------------------------------------------------------

        prediction_evidence = self._collect_stage(
            context,
            "PREDICTION",
        )

        self._set_context_value(
            context,
            "prediction_evidence",
            prediction_evidence,
        )

        # ---------------------------------------------------------
        # FINAL DECISION EVIDENCE
        # ---------------------------------------------------------
        #
        # These are derived/meta engines. Their output should not become
        # another independent vote because that would double-count evidence.
        #

        meta_capabilities = {
            "ENSEMBLE",
            "PROBABILITY",
            "RANKING",
            "MOVEMENT_PATH",
        }

        final_prediction = []

        for item in prediction_evidence:

            engine = self.registry.get(
                item.get("engine")
            )

            capabilities = (
                self._capabilities(engine)
                if engine
                else set()
            )

            if capabilities.intersection(
                meta_capabilities
            ):
                continue

            final_prediction.append(item)

        # Prefer primary prediction evidence.
        #
        # If prediction engines are unavailable, fall back to research
        # evidence so the Master Brain remains functional.
        return (
            final_prediction
            or research_evidence
        )

    def evaluate(self, context):

        evidence = self.collect_evidence(
            context
        )

        fused = self.fusion.combine(
            evidence
        )

        decision = self.decision.decide(
            fused
        )

        if isinstance(context, dict):

            research_evidence = context.get(
                "research_evidence",
                [],
            )

            prediction_evidence = context.get(
                "prediction_evidence",
                [],
            )

            horizon_minutes = context.get(
                "horizon_minutes",
                60,
            )

        else:

            research_evidence = getattr(
                context,
                "research_evidence",
                [],
            )

            prediction_evidence = getattr(
                context,
                "prediction_evidence",
                [],
            )

            horizon_minutes = getattr(
                context,
                "horizon_minutes",
                60,
            )

        return {
            "horizon_minutes": horizon_minutes,

            "decision": decision,

            "research_evidence": research_evidence,

            "prediction_evidence": prediction_evidence,
        }
