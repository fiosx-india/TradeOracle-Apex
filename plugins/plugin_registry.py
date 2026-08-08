"""Runtime plugin registry."""
class PluginRegistry:
    def __init__(self):
        self._items = {}
    def add(self, engine):
        self._items[engine.name] = engine
    def all(self):
        return dict(self._items)
