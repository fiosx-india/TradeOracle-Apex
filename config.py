"""Central, environment-driven Apex configuration.

TradeOracle Apex configuration contract.

Important:
- Prediction horizons are independent of Angel One candle intervals.
- Apex supports exactly 5, 15, 30 and 60 minute prediction horizons.
- Angel One market data remains on ONE_MINUTE candles.
- Live mode is the production default.
- This module contains configuration only; it does not create market data.
"""

from __future__ import annotations

import os


APP_NAME = "TradeOracle Apex"
VERSION = "2.2.0"


# ---------------------------------------------------------------------------
# SMALL CONFIGURATION HELPERS
# ---------------------------------------------------------------------------

def _env_str(
    name: str,
    default: str,
) -> str:
    return os.getenv(
        name,
        default,
    ).strip()


def _env_int(
    name: str,
    default: int,
    *,
    minimum: int | None = None,
) -> int:
    raw = os.getenv(
        name,
        str(default),
    ).strip()

    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(
            f"{name} must be an integer; got {raw!r}."
        ) from exc

    if minimum is not None and value < minimum:
        raise ValueError(
            f"{name} must be >= {minimum}; got {value}."
        )

    return value


def _env_float(
    name: str,
    default: float,
) -> float:
    raw = os.getenv(
        name,
        str(default),
    ).strip()

    try:
        value = float(raw)
    except ValueError as exc:
        raise ValueError(
            f"{name} must be a number; got {raw!r}."
        ) from exc

    if value != value or value in {
        float("inf"),
        float("-inf"),
    }:
        raise ValueError(
            f"{name} must be finite; got {raw!r}."
        )

    return value


def _env_bool(
    name: str,
    default: bool,
) -> bool:
    raw = os.getenv(
        name,
        "true" if default else "false",
    ).strip().lower()

    if raw in {
        "1",
        "true",
        "yes",
        "on",
    }:
        return True

    if raw in {
        "0",
        "false",
        "no",
        "off",
    }:
        return False

    raise ValueError(
        f"{name} must be one of "
        "true/false, yes/no, on/off, or 1/0."
    )


# ---------------------------------------------------------------------------
# PREDICTION HORIZONS
# ---------------------------------------------------------------------------
# These are prediction horizons, NOT Angel One candle intervals.
#
# Supported horizons:
#     5 minutes
#     15 minutes
#     30 minutes
#     60 minutes
#
# The same canonical market-data snapshot can be used by all four horizons.
# Angel One remains on ONE_MINUTE candles.
# ---------------------------------------------------------------------------

SUPPORTED_PREDICTION_HORIZONS_MINUTES = (
    5,
    15,
    30,
    60,
)

_configured_horizons_raw = _env_str(
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


if _configured_horizons != (
    SUPPORTED_PREDICTION_HORIZONS_MINUTES
):
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
# Existing modules such as the current Streamlit runner still import
# PREDICTION_HORIZON_MINUTES. Keep that name so the existing architecture
# does not break, but make 5 minutes the default fallback rather than 60.
#
# Multi-horizon execution must use PREDICTION_HORIZONS_MINUTES.
# ---------------------------------------------------------------------------

DEFAULT_PREDICTION_HORIZON_MINUTES = 5

PREDICTION_HORIZON_MINUTES = _env_int(
    "APEX_HORIZON_MINUTES",
    DEFAULT_PREDICTION_HORIZON_MINUTES,
    minimum=1,
)

if (
    PREDICTION_HORIZON_MINUTES
    not in PREDICTION_HORIZONS_MINUTES
):
    raise ValueError(
        "APEX_HORIZON_MINUTES must be one of "
        f"{PREDICTION_HORIZONS_MINUTES}; got "
        f"{PREDICTION_HORIZON_MINUTES}."
    )


# ---------------------------------------------------------------------------
# DATA MODE / PROVIDER
# ---------------------------------------------------------------------------

DATA_MODE = _env_str(
    "APEX_DATA_MODE",
    "live",
).lower()

if DATA_MODE not in {
    "live",
    "demo",
}:
    raise ValueError(
        "APEX_DATA_MODE must be 'live' or 'demo'."
    )

DATA_PROVIDER = _env_str(
    "APEX_DATA_PROVIDER",
    "",
)


# ---------------------------------------------------------------------------
# LIVE DATA
# ---------------------------------------------------------------------------

LIVE_DATA_MAX_AGE_SECONDS = _env_int(
    "APEX_LIVE_DATA_MAX_AGE_SECONDS",
    120,
    minimum=1,
)


# ---------------------------------------------------------------------------
# ANGEL ONE
# ---------------------------------------------------------------------------
# IMPORTANT:
# This is the MARKET-DATA candle interval.
# It is intentionally NOT tied to prediction horizons.
#
# Keep:
#     ONE_MINUTE
#
# Do NOT change this to 5/15/30/60 minute candles merely because Apex
# predicts those horizons.
# ---------------------------------------------------------------------------

ANGELONE_EXCHANGE = _env_str(
    "ANGELONE_EXCHANGE",
    "NSE",
).upper()

ANGELONE_SYMBOL = _env_str(
    "ANGELONE_SYMBOL",
    "NIFTY",
)

ANGELONE_SYMBOL_TOKEN = _env_str(
    "ANGELONE_SYMBOL_TOKEN",
    "",
)

ANGELONE_TRADINGSYMBOL = _env_str(
    "ANGELONE_TRADINGSYMBOL",
    "",
)

ANGELONE_INTERVAL = _env_str(
    "ANGELONE_INTERVAL",
    "ONE_MINUTE",
).upper()

if ANGELONE_INTERVAL != "ONE_MINUTE":
    raise ValueError(
        "ANGELONE_INTERVAL must remain ONE_MINUTE for the "
        "canonical Apex multi-horizon architecture."
    )

ANGELONE_HISTORY_BARS = _env_int(
    "ANGELONE_HISTORY_BARS",
    120,
    minimum=20,
)

ANGELONE_LOOKBACK_MINUTES = _env_int(
    "ANGELONE_LOOKBACK_MINUTES",
    240,
    minimum=30,
)


# ---------------------------------------------------------------------------
# RUNTIME
# ---------------------------------------------------------------------------

INCOMING_DIR = _env_str(
    "APEX_INCOMING_DIR",
    "incoming",
)


# ---------------------------------------------------------------------------
# DECISION THRESHOLDS
# ---------------------------------------------------------------------------

UP_THRESHOLD = _env_float(
    "APEX_UP_THRESHOLD",
    0.15,
)

DOWN_THRESHOLD = _env_float(
    "APEX_DOWN_THRESHOLD",
    -0.15,
)

if UP_THRESHOLD <= DOWN_THRESHOLD:
    raise ValueError(
        "APEX_UP_THRESHOLD must be greater than "
        "APEX_DOWN_THRESHOLD."
    )

MIN_CONFIDENCE_FOR_SIGNAL = _env_float(
    "APEX_MIN_CONFIDENCE",
    0.60,
)

if not 0.0 <= MIN_CONFIDENCE_FOR_SIGNAL <= 1.0:
    raise ValueError(
        "APEX_MIN_CONFIDENCE must be between 0.0 and 1.0."
    )

MIN_HISTORY_BARS = _env_int(
    "APEX_MIN_HISTORY_BARS",
    30,
    minimum=1,
)


# ---------------------------------------------------------------------------
# DATA SAFETY
# ---------------------------------------------------------------------------
# SignalGate uses this configuration to withhold directional output when
# live market data is not sufficiently fresh.
# ---------------------------------------------------------------------------

REQUIRE_FRESH_DATA_FOR_SIGNAL = _env_bool(
    "APEX_REQUIRE_FRESH_DATA_FOR_SIGNAL",
    True,
)

# ---------------------------------------------------------------------------
# AUTO BUY
# ---------------------------------------------------------------------------

AUTO_BUY_ENABLED = _env_bool(
    "APEX_AUTO_BUY_ENABLED",
    False,
)

# PAPER = test only; no broker order is submitted.
# LIVE  = reserved for explicit broker execution.
AUTO_BUY_MODE = _env_str(
    "APEX_AUTO_BUY_MODE",
    "PAPER",
).upper()

if AUTO_BUY_MODE not in {"PAPER", "LIVE"}:
    raise ValueError(
        "APEX_AUTO_BUY_MODE must be PAPER or LIVE."
    )

AUTO_BUY_MIN_CONFIDENCE = _env_float(
    "APEX_AUTO_BUY_MIN_CONFIDENCE",
    0.60,
)

AUTO_BUY_REQUIRE_FRESH = _env_bool(
    "APEX_AUTO_BUY_REQUIRE_FRESH",
    True,
)

AUTO_BUY_REQUIRE_POSITIVE_SCORE = _env_bool(
    "APEX_AUTO_BUY_REQUIRE_POSITIVE_SCORE",
    True,
)

AUTO_BUY_MIN_HISTORY = _env_int(
    "APEX_AUTO_BUY_MIN_HISTORY",
    30,
    minimum=1,
)

AUTO_BUY_MAX_QUANTITY = _env_int(
    "APEX_AUTO_BUY_MAX_QUANTITY",
    1,
    minimum=1,
)


# ---------------------------------------------------------------------------
# AUTO-BUY SETTINGS
# ---------------------------------------------------------------------------
# Auto-buy is controlled centrally from configuration.
# Keep the default disabled until the complete safety pipeline is validated.

AUTO_BUY_ENABLED = _env_bool(
    "APEX_AUTO_BUY_ENABLED",
    False,
)

AUTO_BUY_MODE = _env_str(
    "APEX_AUTO_BUY_MODE",
    "PAPER",
).upper()

if AUTO_BUY_MODE not in {
    "PAPER",
    "LIVE",
}:
    raise ValueError(
        "APEX_AUTO_BUY_MODE must be 'PAPER' or 'LIVE'."
    )

AUTO_BUY_MIN_CONFIDENCE = _env_float(
    "APEX_AUTO_BUY_MIN_CONFIDENCE",
    0.60,
)

if not 0.0 <= AUTO_BUY_MIN_CONFIDENCE <= 1.0:
    raise ValueError(
        "APEX_AUTO_BUY_MIN_CONFIDENCE must be between 0.0 and 1.0."
    )

AUTO_BUY_REQUIRE_FRESH_DATA = _env_bool(
    "APEX_AUTO_BUY_REQUIRE_FRESH_DATA",
    True,
)

AUTO_BUY_REQUIRE_UP_DIRECTION = _env_bool(
    "APEX_AUTO_BUY_REQUIRE_UP_DIRECTION",
    True,
)

AUTO_BUY_REQUIRE_POSITIVE_SCORE = _env_bool(
    "APEX_AUTO_BUY_REQUIRE_POSITIVE_SCORE",
    True,
)

AUTO_BUY_REQUIRE_RISK_GATE = _env_bool(
    "APEX_AUTO_BUY_REQUIRE_RISK_GATE",
    True,
)

AUTO_BUY_MAX_QUANTITY = _env_int(
    "APEX_AUTO_BUY_MAX_QUANTITY",
    1,
    minimum=1,
)

AUTO_BUY_STOP_LOSS_PERCENT = _env_float(
    "APEX_AUTO_BUY_STOP_LOSS_PERCENT",
    0.50,
)

AUTO_BUY_TARGET_PERCENT = _env_float(
    "APEX_AUTO_BUY_TARGET_PERCENT",
    1.00,
)

# ---------------------------------------------------------------------------
# NEWS
# ---------------------------------------------------------------------------

NEWS_LOOKBACK_HOURS = _env_int(
    "APEX_NEWS_LOOKBACK_HOURS",
    24,
    minimum=1,
)
