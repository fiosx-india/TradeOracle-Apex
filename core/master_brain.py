"""Apex Master Brain: executes registered engines and fuses their evidence."""

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

    def collect_evidence(self, context):
        if self.registry is None:
            return []

        evidence = []

        for engine in self.registry.all().values():
            try:
                analyze = getattr(engine, "analyze", None)
                predict = getattr(engine, "predict", None)

                if callable(analyze):
                    result = analyze(context)
                elif callable(predict):
                    result = predict(context)
                else:
                    continue

                if not isinstance(result, dict):
                    continue

                item = dict(result)
                item.setdefault("engine", engine.name)
                item.setdefault("weight", 1.0)
                item.setdefault("confidence", 1.0)
                evidence.append(item)

            except Exception as exc:
                # One bad engine cannot crash the Master Brain.
                evidence.append({
                    "engine": engine.name,
                    "score": 0.0,
                    "weight": 0.0,
                    "confidence": 0.0,
                    "reason": f"engine_error:{type(exc).__name__}",
                })

        return evidence

    def evaluate(self, context):
        evidence = self.collect_evidence(context)
        fused = self.fusion.combine(evidence)
        decision = self.decision.decide(fused)

        return {
            "horizon_minutes": getattr(
                context, "horizon_minutes", 60
            ),
            "decision": decision,
        }
