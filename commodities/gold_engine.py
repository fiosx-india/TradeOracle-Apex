"""Gold analysis adapter."""

from .commodity_engine import CommodityEngine


class GoldEngine(CommodityEngine):
    name="GoldEngine"
    version="2.0.0"
    capabilities=["COMMODITY","GOLD"]

    def self_test(self): return True

    def analyze(self, observation=None, *args, **kwargs):
        result=super().analyze(observation or {}, *args, **kwargs)
        result["commodity"]="GOLD"
        return result
