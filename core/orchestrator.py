"""Full Auto-Fit lifecycle:

Discover -> Validate -> Benchmark -> Register -> Master Brain.
"""

from .builtin_engines import BUILTIN_ENGINE_CLASSES
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

        self.router = CapabilityRouter(
            self.registry
        )

        self.validator = PluginValidator()

        self.benchmark = PluginBenchmark()

        self.brain = ApexMasterBrain(
            registry=self.registry,
            router=self.router,
        )

    def _register_engine(
        self,
        engine,
        source_file,
        report,
    ):

        # ---------------------------------------------------------
        # VALIDATION
        # ---------------------------------------------------------

        validation = self.validator.validate(
            engine
        )

        if not validation["valid"]:

            report.append({
                "stage": "VALIDATION",
                "status": "REJECTED",
                "name": getattr(
                    engine,
                    "name",
                    str(engine),
                ),
                "file": str(source_file),
                "errors": validation["errors"],
            })

            return

        # ---------------------------------------------------------
        # BENCHMARK
        # ---------------------------------------------------------

        benchmark = self.benchmark.benchmark(
            engine
        )

        if not benchmark["passed"]:

            report.append({
                "stage": "BENCHMARK",
                "status": "REJECTED",
                "name": getattr(
                    engine,
                    "name",
                    str(engine),
                ),
                "file": str(source_file),
                "errors": benchmark["errors"],
                "benchmark": benchmark,
            })

            return

        # ---------------------------------------------------------
        # REGISTRATION
        # ---------------------------------------------------------

        self.registry.register(
            engine,
            benchmark=benchmark,
            source_file=source_file,
        )

        report.append({
            "stage": "REGISTRATION",
            "status": "ACTIVE",
            "name": engine.name,
            "file": str(source_file),
            "benchmark": benchmark,
        })

    def _register_builtins(self, report):

        for engine_cls in BUILTIN_ENGINE_CLASSES:

            try:

                engine = engine_cls()

                self._register_engine(
                    engine,
                    (
                        "builtin:"
                        f"{engine_cls.__module__}."
                        f"{engine_cls.__name__}"
                    ),
                    report,
                )

            except Exception as exc:

                report.append({
                    "stage": "BUILTIN_DISCOVERY",
                    "status": "ERROR",
                    "name": getattr(
                        engine_cls,
                        "__name__",
                        str(engine_cls),
                    ),
                    "file": (
                        "builtin:"
                        f"{getattr(engine_cls, '__module__', '')}"
                    ),
                    "errors": [
                        f"{type(exc).__name__}: {exc}"
                    ],
                })

    def discover_validate_benchmark_register(self):

        report = []

        # ---------------------------------------------------------
        # REGISTER BUILT-IN ENGINES
        # ---------------------------------------------------------

        self._register_builtins(
            report
        )

        # ---------------------------------------------------------
        # DISCOVER INCOMING PLUGINS
        # ---------------------------------------------------------

        loader = PluginLoader(
            self.incoming
        )

        for item in loader.discover():

            if not item["loaded"]:

                report.append(item)

                continue

            self._register_engine(
                item["engine"],
                item["file"],
                report,
            )

        # ---------------------------------------------------------
        # RE-ATTACH CURRENT REGISTRY
        # ---------------------------------------------------------

        self.brain.attach_registry(
            self.registry,
            self.router,
        )

        return report

    def run(self, context=None):

        report = (
            self
            .discover_validate_benchmark_register()
        )

        result = {

            "status": "READY",

            "pipeline": [
                "DISCOVER",
                "VALIDATE",
                "BENCHMARK",
                "REGISTER",
                "MASTER_BRAIN",
            ],

            "registered_engines": list(
                self.registry.all()
            ),

            "registry_report": (
                self.registry.report()
            ),

            "report": report,
        }

        # Master Brain only runs when a real MarketContext
        # is supplied.
        if context is not None:

            result["master_brain"] = (
                self.brain.evaluate(
                    context
                )
            )

        return result
