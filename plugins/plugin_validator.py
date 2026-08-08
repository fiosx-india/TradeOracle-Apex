"""Strict contract validation before an engine can be benchmarked."""

class PluginValidator:
    def validate(self, engine):
        errors = []

        name = getattr(engine, "name", None)
        if not isinstance(name, str) or not name.strip():
            errors.append("name must be a non-empty string")

        capabilities = getattr(engine, "capabilities", None)
        if not isinstance(capabilities, (list, tuple)) or not capabilities:
            errors.append("capabilities must be a non-empty list/tuple")

        analyze = getattr(engine, "analyze", None)
        predict = getattr(engine, "predict", None)

        if not callable(analyze) and not callable(predict):
            errors.append(
                "engine must implement analyze(context) or predict(context)"
            )

        return {
            "valid": not errors,
            "errors": errors,
        }
