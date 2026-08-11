"""Central, environment-driven Apex configuration."""

import os


APP_NAME = "TradeOracle Apex"
VERSION = "2.2.0"


# ---------------------------------------------------------------------------
# PREDICTION HORIZONS
# ---------------------------------------------------------------------------
# Apex evaluates all supported forward horizons from the same canonical
# market-data snapshot.
#
# These are prediction horizons, NOT Angel One candle intervals.
#
# Supported horizons:
#     5 minutes
#     15 minutes
#     30 minutes
#     60 minutes
#
# Angel One remains on ONE_MINUTE candles.
# ---------------------------------------------------------------------------

SUPPORTED_PREDICTION_HORIZONS_MINUTES = (5, 15, 30, 60)

_configured_horizons_raw = os.getenv(
    "APEX_HORIZONS_MINUTES",
    "5,15,30,60",
)

try:
    _configured_horizons = tuple(
        sorted(
            {
                int(value.strip())
                for value in _configured_horizons_raw.split(",")
                if value.strip()
            }
        )
    )
except ValueError as exc:
    raise ValueError(
        "APEX_HORIZONS_MINUTES must contain only integers."
    ) from exc


if _configured_horizons != SUPPORTED_PREDICTION_HORIZONS_MINUTES:
    raise ValueError(
        "APEX_HORIZONS_MINUTES must contain exactly "
        "5,15,30,60."
    )


# Canonical public horizon configuration.
PREDICTION_HORIZONS_MINUTES = (
    SUPPORTED_PREDICTION_HORIZONS_MINUTES
)


# ---------------------------------------------------------------------------
# BACKWARD COMPATIBILITY
# ---------------------------------------------------------------------------
# Some existing modules still import PREDICTION_HORIZON_MINUTES.
# Keep it as a compatibility alias, but DO NOT use it for multi-horizon
# runtime execution.
#
# The default display/fallback horizon is now 5 minutes, not 60 minutes.
# ---------------------------------------------------------------------------

DEFAULT_PREDICTION_HORIZON_MINUTES = 5

PREDICTION_HORIZON_MINUTES = int(
    os.getenv(
        "APEX_HORIZON_MINUTES",
        str(DEFAULT_PREDICTION_HORIZON_MINUTES),
    )
)

if PREDICTION_HORIZON_MINUTES not in PREDICTION_HORIZONS_MINUTES:
    raise ValueError(
        "APEX_HORIZON_MINUTES must be one of "
        f"{PREDICTION_HORIZONS_MINUTES}."
    )


# ---------------------------------------------------------------------------
# DATA MODE
# ---------------------------------------------------------------------------

DATA_MODE = os.getenv(
    "APEX_DATA_MODE",
    "live",
).strip().lower()

DATA_PROVIDER = os.getenv(
    "APEX_DATA_PROVIDER",
    "",
).strip()


# ---------------------------------------------------------------------------
# LIVE DATA
# ---------------------------------------------------------------------------

LIVE_DATA_MAX_AGE_SECONDS = int(
    os.getenv(
        "APEX_LIVE_DATA_MAX_AGE_SECONDS",
        "120",
    )
)


# ---------------------------------------------------------------------------
# ANGEL ONE
# ---------------------------------------------------------------------------
# IMPORTANT:
# This is the MARKET-DATA interval.
# It is intentionally NOT tied to prediction horizons.
#
# Keep:
#     ONE_MINUTE
#
# Do NOT change this to 5/15/30/60 minute candles for this architecture.
# ---------------------------------------------------------------------------

ANGELONE_EXCHANGE = os.getenv(
    "ANGELONE_EXCHANGE",
    "NSE",
).strip().upper()

ANGELONE_SYMBOL = os.getenv(
    "ANGELONE_SYMBOL",
    "NIFTY",
).strip()

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


# ---------------------------------------------------------------------------
# RUNTIME
# ---------------------------------------------------------------------------

INCOMING_DIR = os.getenv(
    "APEX_INCOMING_DIR",
    "incoming",
)


# ---------------------------------------------------------------------------
# DECISION THRESHOLDS
# ---------------------------------------------------------------------------

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

MIN_CONFIDENCE_FOR_SIGNAL = float(
    os.getenv(
        "APEX_MIN_CONFIDENCE",
        "0.60",
    )
)

MIN_HISTORY_BARS = int(
    os.getenv(
        "APEX_MIN_HISTORY_BARS",
        "30",
    )
)


# ---------------------------------------------------------------------------
# DATA SAFETY
# ---------------------------------------------------------------------------

REQUIRE_FRESH_DATA_FOR_SIGNAL = os.getenv(
    "APEX_REQUIRE_FRESH_DATA_FOR_SIGNAL",
    "true",
).strip().lower() not in {
    "0",
    "false",
    "no",
    "off",
}


# ---------------------------------------------------------------------------
# NEWS
# ---------------------------------------------------------------------------

NEWS_LOOKBACK_HOURS = int(
    os.getenv(
        "APEX_NEWS_LOOKBACK_HOURS",
        "24",
    )
)
