"""Silver analysis adapter."""

from .commodity_engine import CommodityEngine


class SilverEngine(CommodityEngine):
    name="SilverEngine"
    version="2.0.0"
    capabilities=["COMMODITY","SILVER"]

    def self_test(self): return True

    def analyze(self, observation=None, *args, **kwargs):
        result=super().analyze(observation or {}, *args, **kwargs)
        result["commodity"]="SILVER"
        return result
