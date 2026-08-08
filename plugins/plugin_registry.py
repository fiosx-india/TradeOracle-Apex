"""Compatibility registry for plugin-level tooling.

Runtime activation is owned by core.SystemRegistry so there is only one
authoritative runtime registry.
"""

class PluginRegistry:
    def __init__(self):
        self._items = {}

    def add(self, engine):
        self._items[engine.name] = engine

    def get(self, name):
        return self._items.get(name)

    def all(self):
        return dict(self._items)
