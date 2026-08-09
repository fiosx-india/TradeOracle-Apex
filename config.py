"""Central, environment-driven Apex configuration."""
import os

APP_NAME = "TradeOracle Apex"
VERSION = "1.1.0"

PREDICTION_HORIZON_MINUTES = int(
    os.getenv("APEX_HORIZON_MINUTES", "60")
)

DATA_MODE = os.getenv("APEX_DATA_MODE", "demo")
INCOMING_DIR = os.getenv("APEX_INCOMING_DIR", "incoming")

# Direction thresholds are deliberately configurable.
UP_THRESHOLD = float(os.getenv("APEX_UP_THRESHOLD", "0.15"))
DOWN_THRESHOLD = float(os.getenv("APEX_DOWN_THRESHOLD", "-0.15"))

# Never present a model probability as certainty.
MIN_CONFIDENCE_FOR_SIGNAL = float(
    os.getenv("APEX_MIN_CONFIDENCE", "0.60")
)

