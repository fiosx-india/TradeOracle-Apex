"""Reference drop-in engine for the TradeOracle Apex Auto-Fit pipeline."""

class ExampleEngine:
    name = "ExampleEngine"
    version = "1.0.0"
    capabilities = ["RESEARCH"]

    def self_test(self):
        return True

    def analyze(self, context):
        return {
            "score": 0.0,
            "weight": 1.0,
            "reason": "Reference engine only."
        }


PLUGIN_CLASS = ExampleEngine
