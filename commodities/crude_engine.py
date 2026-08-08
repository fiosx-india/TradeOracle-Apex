"""Crude oil analysis adapter."""

from .commodity_engine import CommodityEngine


class CrudeEngine(CommodityEngine):
    name="CrudeEngine"
    version="2.0.0"
    capabilities=["COMMODITY","CRUDE"]

    def self_test(self): return True

    def analyze(self, observation=None, *args, **kwargs):
        result=super().analyze(observation or {}, *args, **kwargs)
        result["commodity"]="CRUDE"
        return result
