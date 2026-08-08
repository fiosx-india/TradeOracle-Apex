"""Discovers compatible Python engines from incoming/."""
import importlib.util
from pathlib import Path

class PluginLoader:
    def __init__(self, incoming="incoming"):
        self.incoming = Path(incoming)

    def discover(self):
        engines = []
        self.incoming.mkdir(parents=True, exist_ok=True)
        for path in self.incoming.glob("*.py"):
            if path.name.startswith("_"):
                continue
            spec = importlib.util.spec_from_file_location(path.stem, path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            cls = getattr(module, "PLUGIN_CLASS", None)
            if cls:
                engines.append(cls())
        return engines
