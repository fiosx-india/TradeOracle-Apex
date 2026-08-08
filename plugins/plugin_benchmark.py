"""Benchmark hook; real scores require historical timestamped data."""
class PluginBenchmark:
    def benchmark(self, engine, dataset=None):
        return {"engine": engine.name, "status": "PENDING_DATA"}
