"""Validates the Apex drop-in engine contract."""
class PluginValidator:
    def validate(self, engine):
        errors = []

        if not isinstance(getattr(engine, "name", None), str) or not engine.name.strip():
            errors.append("Engine must define a non-empty string: name")

        capabilities = getattr(engine, "capabilities", None)
        if not isinstance(capabilities, (list, tuple)) or not capabilities:
            errors.append("Engine must define non-empty list/tuple: capabilities")

        if not callable(getattr(engine, "analyze", None)) and not callable(
            getattr(engine, "predict", None)
        ):
            errors.append("Engine must implement analyze(context) or predict(context)")

        return {
            "valid": not errors,
            "errors": errors,
        }
