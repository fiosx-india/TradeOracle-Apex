"""Apex orchestration: Discover -> Validate -> Benchmark -> Register -> Master Brain."""
from .master_brain import ApexMasterBrain
from .system_registry import SystemRegistry
from .capability_router import CapabilityRouter
from plugins.plugin_loader import PluginLoader
from plugins.plugin_validator import PluginValidator
from plugins.plugin_benchmark import PluginBenchmark


class ApexOrchestrator:
    def __init__(self, incoming="incoming"):
        self.registry = SystemRegistry()
        self.router = CapabilityRouter(self.registry)
        self.validator = PluginValidator()
        self.benchmark = PluginBenchmark()
        self.brain = ApexMasterBrain()
        self.incoming = incoming

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
                    "name": getattr(engine, "name", item["file"]),
                    "stage": "VALIDATION",
                    "status": "REJECTED",
                    "errors": validation["errors"],
                    "file": item["file"],
                })
                continue

            benchmark = self.benchmark.benchmark(engine)
            if not benchmark["passed"]:
                report.append({
                    "name": engine.name,
                    "stage": "BENCHMARK",
                    "status": "REJECTED",
                    "errors": benchmark["errors"],
                    "file": item["file"],
                })
                continue

            self.registry.register(engine)
            report.append({
                "name": engine.name,
                "stage": "REGISTRATION",
                "status": "ACTIVE",
                "file": item["file"],
                "benchmark": benchmark,
            })

        self.brain.attach_registry(self.registry)
        return report

    def run(self):
        report = self.discover_validate_benchmark_register()
        return {
            "status": "READY",
            "pipeline": [
                "DISCOVER",
                "VALIDATE",
                "BENCHMARK",
                "REGISTER",
                "MASTER_BRAIN",
            ],
            "registered_engines": list(self.registry.all()),
            "report": report,
        }
