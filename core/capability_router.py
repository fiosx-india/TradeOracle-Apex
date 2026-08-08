"""Routes a market context only to engines that declare relevant capabilities."""

class CapabilityRouter:
    def __init__(self, registry):
        self.registry = registry

    def engines_for(self, capability):
        capability = str(capability).upper()
        return [
            engine
            for engine in self.registry.all().values()
            if capability in {
                str(item).upper()
                for item in getattr(engine, "capabilities", [])
            }
        ]

    def engines_for_any(self, capabilities):
        requested = {str(x).upper() for x in capabilities}
        return [
            engine
            for engine in self.registry.all().values()
            if requested.intersection(
                {str(x).upper() for x in getattr(engine, "capabilities", [])}
            )
        ]
