"""Auto-discovery of Python engines placed directly in incoming/."""
import importlib.util
from pathlib import Path


class PluginLoader:
    def __init__(self, incoming="incoming"):
        self.incoming = Path(incoming)

    def discover(self):
        self.incoming.mkdir(parents=True, exist_ok=True)
        results = []

        for path in sorted(self.incoming.glob("*.py")):
            if path.name.startswith("_"):
                continue

            try:
                module_name = f"apex_incoming_{path.stem}"
                spec = importlib.util.spec_from_file_location(module_name, path)
                if spec is None or spec.loader is None:
                    raise ImportError("Unable to create module loader")

                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)

                engine_cls = getattr(module, "PLUGIN_CLASS", None)
                if engine_cls is None:
                    results.append({
                        "file": str(path),
                        "loaded": False,
                        "stage": "DISCOVERY",
                        "status": "SKIPPED",
                        "reason": "PLUGIN_CLASS not found",
                    })
                    continue

                results.append({
                    "file": str(path),
                    "loaded": True,
                    "stage": "DISCOVERY",
                    "status": "FOUND",
                    "engine": engine_cls(),
                })

            except Exception as exc:
                results.append({
                    "file": str(path),
                    "loaded": False,
                    "stage": "DISCOVERY",
                    "status": "ERROR",
                    "reason": f"{type(exc).__name__}: {exc}",
                })

        return results
