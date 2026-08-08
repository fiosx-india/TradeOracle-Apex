"""Single runtime registry for validated and benchmarked engines."""

from datetime import datetime, timezone


class SystemRegistry:
    def __init__(self):
        self._items = {}
        self._metadata = {}

    def register(self, engine, benchmark=None, source_file=None):
        name = engine.name
        self._items[name] = engine
        self._metadata[name] = {
            "name": name,
            "version": getattr(engine, "version", "unknown"),
            "capabilities": list(getattr(engine, "capabilities", [])),
            "source_file": str(source_file) if source_file else None,
            "registered_at": datetime.now(timezone.utc).isoformat(),
            "benchmark": benchmark or {},
            "status": "ACTIVE",
        }

    def unregister(self, name):
        self._items.pop(name, None)
        self._metadata.pop(name, None)

    def get(self, name):
        return self._items.get(name)

    def metadata(self, name):
        return dict(self._metadata.get(name, {}))

    def all(self):
        return dict(self._items)

    def report(self):
        return {name: dict(meta) for name, meta in self._metadata.items()}
