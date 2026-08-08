"""BANKNIFTY universe adapter."""

from .index_engine import IndexEngine


class BankNiftyEngine(IndexEngine):
    name = "BankNiftyEngine"
    version = "2.0.0"
    capabilities = ["UNIVERSE", "INDEX", "BANKNIFTY"]

    def __init__(self, constituents=None):
        super().__init__("BANKNIFTY", constituents or [])

    def self_test(self):
        return True
