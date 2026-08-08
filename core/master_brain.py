"""Apex Master Brain: final evidence-fusion and decision layer."""
from .evidence_fusion import EvidenceFusion
from .decision_engine import DecisionEngine

class ApexMasterBrain:
    name = "ApexMasterBrain"
    capabilities = ["MASTER_DECISION"]

    def __init__(self):
        self.fusion = EvidenceFusion()
        self.decision = DecisionEngine()

    def evaluate(self, evidence):
        return self.decision.decide(self.fusion.combine(evidence))
