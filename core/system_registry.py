"""Central registry for discovered engines."""
class SystemRegistry:
    def __init__(self):
        self._items = {}

    def register(self, engine):
        self._items[engine.name] = engine

    def get(self, name):
        return self._items.get(name)

    def all(self):
        return dict(self._items)
