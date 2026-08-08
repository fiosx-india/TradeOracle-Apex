"""Only central runtime settings belong here."""
import os
APP_NAME = "TradeOracle Apex"
VERSION = "1.0.0"
PREDICTION_HORIZON_MINUTES = 60
DATA_MODE = os.getenv("APEX_DATA_MODE", "demo")
