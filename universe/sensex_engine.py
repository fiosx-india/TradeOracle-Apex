"""SENSEX universe adapter."""

from .index_engine import IndexEngine


class SensexEngine(IndexEngine):
    name = "SensexEngine"
    version = "2.0.0"
    capabilities = ["UNIVERSE", "INDEX", "SENSEX"]

    def __init__(self, constituents=None):
        super().__init__("SENSEX", constituents or [])

    def self_test(self):
        return True
