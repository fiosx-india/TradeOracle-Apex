"""Apex Master Brain: combines evidence from registered engines."""
from .evidence_fusion import EvidenceFusion
from .decision_engine import DecisionEngine


class ApexMasterBrain:
    name = "ApexMasterBrain"
    capabilities = ["MASTER_DECISION"]

    def __init__(self):
        self.fusion = EvidenceFusion()
        self.decision = DecisionEngine()
        self.registry = None

    def attach_registry(self, registry):
        self.registry = registry

    def collect_evidence(self, context):
        evidence = []

        if self.registry is None:
            return evidence

        for engine in self.registry.all().values():
            try:
                if callable(getattr(engine, "analyze", None)):
                    result = engine.analyze(context)
                elif callable(getattr(engine, "predict", None)):
                    result = engine.predict(context)
                else:
                    continue

                if isinstance(result, dict):
                    result.setdefault("engine", engine.name)
                    evidence.append(result)
            except Exception as exc:
                # A failed plugin does not crash the whole brain.
                evidence.append({
                    "engine": engine.name,
                    "score": 0.0,
                    "weight": 0.0,
                    "reason": f"engine_error:{type(exc).__name__}",
                })

        return evidence

    def evaluate(self, context):
        evidence = self.collect_evidence(context)
        fused = self.fusion.combine(evidence)
        return self.decision.decide(fused)
