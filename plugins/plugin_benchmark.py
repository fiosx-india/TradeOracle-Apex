"""Contract/smoke benchmark before registration.

This stage verifies that an engine is executable and internally consistent.
It does not claim trading accuracy. Accuracy requires historical and
walk-forward validation.
"""

class PluginBenchmark:
    def benchmark(self, engine):
        errors = []

        try:
            self_test = getattr(engine, "self_test", None)
            if callable(self_test) and self_test() is False:
                errors.append("self_test returned False")

            method = getattr(engine, "analyze", None)
            if not callable(method):
                method = getattr(engine, "predict", None)

            if not callable(method):
                errors.append("no executable analyze/predict method")

        except Exception as exc:
            errors.append(f"{type(exc).__name__}: {exc}")

        return {
            "passed": not errors,
            "errors": errors,
            "mode": "CONTRACT_SMOKE_TEST",
        }
