"""Loads optional environment-based Apex settings."""
import os

def get_config():
    return {
        "app_name": "TradeOracle Apex",
        "version": "1.0.0",
        "horizon_minutes": int(os.getenv("APEX_HORIZON", "60")),
        "data_mode": os.getenv("APEX_DATA_MODE", "demo"),
    }
