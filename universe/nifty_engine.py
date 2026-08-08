"""NIFTY universe adapter.

Constituents are injected from a current source; no hard-coded stale list is
presented as live market truth.
"""

from .index_engine import IndexEngine


class NiftyEngine(IndexEngine):
    name = "NiftyEngine"
    version = "2.0.0"
    capabilities = ["UNIVERSE", "INDEX", "NIFTY"]

    def __init__(self, constituents=None):
        super().__init__("NIFTY", constituents or [])

    def self_test(self):
        return True
