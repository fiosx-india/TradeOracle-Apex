"""Validates the minimal plugin contract before registration."""
class PluginValidator:
    def validate(self, engine):
        missing = [x for x in ("name", "capabilities") if not hasattr(engine, x)]
        return {"valid": not missing, "missing": missing}
