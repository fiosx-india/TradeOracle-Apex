"""Central, environment-driven Apex configuration."""

import os

APP_NAME = "TradeOracle Apex"
VERSION = "2.1.0"

PREDICTION_HORIZON_MINUTES = int(
    os.getenv("APEX_HORIZON_MINUTES", "60")
)

# Set APEX_DATA_MODE=live after Angel One secrets are configured.
DATA_MODE = os.getenv("APEX_DATA_MODE", "demo").strip().lower()

# Optional override. In live mode, provider_loader falls back to the bundled
# Angel One provider when this is empty.
DATA_PROVIDER = os.getenv("APEX_DATA_PROVIDER", "").strip()

LIVE_DATA_MAX_AGE_SECONDS = int(
    os.getenv("APEX_LIVE_DATA_MAX_AGE_SECONDS", "120")
)

INCOMING_DIR = os.getenv("APEX_INCOMING_DIR", "incoming")

UP_THRESHOLD = float(os.getenv("APEX_UP_THRESHOLD", "0.15"))
DOWN_THRESHOLD = float(os.getenv("APEX_DOWN_THRESHOLD", "-0.15"))

MIN_CONFIDENCE_FOR_SIGNAL = float(
    os.getenv("APEX_MIN_CONFIDENCE", "0.60")
)
