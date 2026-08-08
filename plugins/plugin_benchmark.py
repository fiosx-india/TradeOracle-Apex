"""Fast safety/smoke benchmark before registration.

This is intentionally not an accuracy claim. Real predictive benchmarking requires
timestamped historical data and a proper backtest/walk-forward protocol.
"""
class PluginBenchmark:
    def benchmark(self, engine):
        errors = []

        try:
            if callable(getattr(engine, "self_test", None)):
                result = engine.self_test()
                if result is False:
                    errors.append("self_test returned False")

            # Contract-level smoke check only.
            if not callable(getattr(engine, "analyze", None)) and not callable(
                getattr(engine, "predict", None)
            ):
                errors.append("No executable engine method")

        except Exception as exc:
            errors.append(f"{type(exc).__name__}: {exc}")

        return {
            "passed": not errors,
            "errors": errors,
            "mode": "CONTRACT_SMOKE_TEST",
        }
