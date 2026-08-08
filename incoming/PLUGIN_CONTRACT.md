# TradeOracle Apex Plugin Contract

Example:

class MyEngine:
    name = "MyEngine"
    version = "1.0.0"
    capabilities = ["RESEARCH"]

    def self_test(self):
        return True

    def analyze(self, context):
        return {
            "score": 0.0,
            "weight": 1.0,
            "reason": "..."
        }

PLUGIN_CLASS = MyEngine

Supported execution method:
- analyze(context)
OR
- predict(context)

The Auto-Fit system discovers PLUGIN_CLASS automatically.
