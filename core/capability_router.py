"""Routes context to engines by declared capability."""
class CapabilityRouter:
    def __init__(self, registry):
        self.registry = registry

    def engines_for(self, capability):
        return [
            e for e in self.registry.all().values()
            if capability in getattr(e, "capabilities", [])
        ]
