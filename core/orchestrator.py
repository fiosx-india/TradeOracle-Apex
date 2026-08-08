"""Top-level Apex orchestration layer."""
from .master_brain import ApexMasterBrain
from .system_registry import SystemRegistry
from .capability_router import CapabilityRouter
from plugins.plugin_loader import PluginLoader
from plugins.plugin_validator import PluginValidator

class ApexOrchestrator:
    def __init__(self):
        self.registry = SystemRegistry()
        self.router = CapabilityRouter(self.registry)
        self.validator = PluginValidator()
        self.brain = ApexMasterBrain()

    def discover_plugins(self):
        loader = PluginLoader()
        for engine in loader.discover():
            result = self.validator.validate(engine)
            if result["valid"]:
                self.registry.register(engine)

    def run(self):
        self.discover_plugins()
        return {
            "status": "READY",
            "registered_engines": list(self.registry.all()),
        }
