"""Full Auto-Fit lifecycle:
Discover -> Validate -> Benchmark -> Register -> Master Brain.
"""

from .capability_router import CapabilityRouter
from .master_brain import ApexMasterBrain
from .system_registry import SystemRegistry
from plugins.plugin_benchmark import PluginBenchmark
from plugins.plugin_loader import PluginLoader
from plugins.plugin_validator import PluginValidator
from config import INCOMING_DIR


class ApexOrchestrator:
    def __init__(self, incoming=INCOMING_DIR):
        self.incoming = incoming
        self.registry = SystemRegistry()
        self.router = CapabilityRouter(self.registry)
        self.validator = PluginValidator()
        self.benchmark = PluginBenchmark()
        self.brain = ApexMasterBrain(
            registry=self.registry,
            router=self.router,
        )

    def discover_validate_benchmark_register(self):
        report = []
        loader = PluginLoader(self.incoming)

        for item in loader.discover():
            if not item["loaded"]:
                report.append(item)
                continue

            engine = item["engine"]

            validation = self.validator.validate(engine)
            if not validation["valid"]:
                report.append({
                    "stage": "VALIDATION",
                    "status": "REJECTED",
                    "name": getattr(engine, "name", item["file"]),
                    "file": item["file"],
                    "errors": validation["errors"],
                })
                continue

            benchmark = self.benchmark.benchmark(engine)
            if not benchmark["passed"]:
                report.append({
                    "stage": "BENCHMARK",
                    "status": "REJECTED",
                    "name": engine.name,
                    "file": item["file"],
                    "errors": benchmark["errors"],
                    "benchmark": benchmark,
                })
                continue

            self.registry.register(
                engine,
                benchmark=benchmark,
                source_file=item["file"],
            )

            report.append({
                "stage": "REGISTRATION",
                "status": "ACTIVE",
                "name": engine.name,
                "file": item["file"],
                "benchmark": benchmark,
            })

        self.brain.attach_registry(self.registry, self.router)
        return report

    def run(self, context=None):
        report = self.discover_validate_benchmark_register()

        result = {
            "status": "READY",
            "pipeline": [
                "DISCOVER",
                "VALIDATE",
                "BENCHMARK",
                "REGISTER",
                "MASTER_BRAIN",
            ],
            "registered_engines": list(self.registry.all()),
            "registry_report": self.registry.report(),
            "report": report,
        }

        if context is not None:
            result["master_brain"] = self.brain.evaluate(context)

        return result
