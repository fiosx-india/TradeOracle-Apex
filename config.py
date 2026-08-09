"""Central, environment-driven Apex configuration."""

import os


# ============================================================
# APPLICATION
# ============================================================

APP_NAME = "TradeOracle Apex"
VERSION = "2.2.0"


# ============================================================
# PREDICTION
# ============================================================

PREDICTION_HORIZON_MINUTES = int(
    os.getenv(
        "APEX_HORIZON_MINUTES",
        "60",
    )
)


# ============================================================
# DATA MODE
# ============================================================

# Live Angel One is the default.
#
# Use:
#   APEX_DATA_MODE=demo
#
# only for offline development/testing.
#
# The live provider itself must not generate synthetic
# market prices.
DATA_MODE = os.getenv(
    "APEX_DATA_MODE",
    "live",
).strip().lower()


DATA_PROVIDER = os.getenv(
    "APEX_DATA_PROVIDER",
    "",
).strip()


# ============================================================
# MARKET DATA FRESHNESS
# ============================================================

LIVE_DATA_MAX_AGE_SECONDS = int(
    os.getenv(
        "APEX_LIVE_DATA_MAX_AGE_SECONDS",
        "120",
    )
)


# ============================================================
# ANGEL ONE MARKET DATA
# ============================================================

ANGELONE_EXCHANGE = os.getenv(
    "ANGELONE_EXCHANGE",
    "NSE",
).strip().upper()


ANGELONE_SYMBOL = os.getenv(
    "ANGELONE_SYMBOL",
    "NIFTY",
).strip()


# Optional explicit token.
#
# Leave empty when the provider is responsible for resolving
# the instrument token.
ANGELONE_SYMBOL_TOKEN = os.getenv(
    "ANGELONE_SYMBOL_TOKEN",
    "",
).strip()


ANGELONE_INTERVAL = os.getenv(
    "ANGELONE_INTERVAL",
    "ONE_MINUTE",
).strip().upper()


ANGELONE_HISTORY_BARS = int(
    os.getenv(
        "ANGELONE_HISTORY_BARS",
        "120",
    )
)


ANGELONE_LOOKBACK_MINUTES = int(
    os.getenv(
        "ANGELONE_LOOKBACK_MINUTES",
        "240",
    )
)


# ============================================================
# PROJECT INPUT
# ============================================================

INCOMING_DIR = os.getenv(
    "APEX_INCOMING_DIR",
    "incoming",
)


# ============================================================
# DIRECTION THRESHOLDS
# ============================================================

UP_THRESHOLD = float(
    os.getenv(
        "APEX_UP_THRESHOLD",
        "0.15",
    )
)


DOWN_THRESHOLD = float(
    os.getenv(
        "APEX_DOWN_THRESHOLD",
        "-0.15",
    )
)


# ============================================================
# SIGNAL CONFIDENCE
# ============================================================

MIN_CONFIDENCE_FOR_SIGNAL = float(
    os.getenv(
        "APEX_MIN_CONFIDENCE",
        "0.60",
    )
)


# ============================================================
# SIGNAL DATA-QUALITY CONTROLS
# ============================================================

# Minimum number of historical bars required before a
# directional signal can become active.
#
# If fewer bars are available, SignalGate must withhold
# the directional signal.
MIN_HISTORY_BARS = int(
    os.getenv(
        "APEX_MIN_HISTORY_BARS",
        "30",
    )
)


# Require market data to be fresh before allowing an
# active directional signal.
#
# If enabled:
#
#     stale data
#         ↓
#     signal withheld
#
REQUIRE_FRESH_DATA_FOR_SIGNAL = os.getenv(
    "APEX_REQUIRE_FRESH_DATA_FOR_SIGNAL",
    "true",
).strip().lower() not in {
    "0",
    "false",
    "no",
    "off",
}


# ============================================================
# NEWS
# ============================================================

NEWS_LOOKBACK_HOURS = int(
    os.getenv(
        "APEX_NEWS_LOOKBACK_HOURS",
        "24",
    )
)
