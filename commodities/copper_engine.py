"""Copper analysis adapter."""

from .commodity_engine import CommodityEngine


class CopperEngine(CommodityEngine):
    name="CopperEngine"
    version="2.0.0"
    capabilities=["COMMODITY","COPPER"]

    def self_test(self): return True

    def analyze(self, observation=None, *args, **kwargs):
        result=super().analyze(observation or {}, *args, **kwargs)
        result["commodity"]="COPPER"
        return result
