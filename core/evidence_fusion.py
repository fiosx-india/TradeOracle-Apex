"""Combines independent evidence without treating duplicate signals as independent."""
class EvidenceFusion:
    def combine(self, evidence):
        valid = [e for e in evidence if isinstance(e, dict)]
        if not valid:
            return {"score": 0.0, "confidence": 0.0, "reasons": []}
        weighted = []
        reasons = []
        for e in valid:
            score = float(e.get("score", 0.0))
            weight = float(e.get("weight", 1.0))
            weighted.append((score, max(0.0, weight)))
            if e.get("reason"):
                reasons.append(e["reason"])
        denom = sum(w for _, w in weighted)
        score = sum(s*w for s, w in weighted) / denom if denom else 0.0
        return {"score": score, "confidence": min(1.0, abs(score)), "reasons": reasons}
