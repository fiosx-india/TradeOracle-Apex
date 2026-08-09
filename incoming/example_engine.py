"""Reference drop-in plugin for the TradeOracle Apex Auto-Fit pipeline.

This plugin is intentionally neutral. It validates the plugin contract but is
not part of Master Brain research/prediction evidence.
"""


class ExampleEngine:

    name = "ExampleEngine"
    version = "1.0.0"

    # IMPORTANT:
    # This is only a reference plugin.
    # Do not classify it as RESEARCH because it has no real market evidence.
    capabilities = ["REFERENCE"]

    def self_test(self):
        return True

    def analyze(self, context):

        return {
            "score": 0.0,
            "weight": 0.0,
            "confidence": 0.0,
            "reason": (
                "Reference plugin; "
                "excluded from decision evidence."
            ),
        }


PLUGIN_CLASS = ExampleEngine
