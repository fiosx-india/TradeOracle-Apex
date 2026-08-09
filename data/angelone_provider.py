"""Angel One SmartAPI live market-data provider for TradeOracle Apex.

This module is read-only for the first live-data test:
- logs in to SmartAPI using Streamlit secrets
- fetches the latest LTP through Angel One's market-data API
- optionally exposes a WebSocket streaming client for future continuous feeds

No order-placement code is included.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any, Optional

try:
    import pyotp
    from SmartApi import SmartConnect
except ImportError:  # pragma: no cover
    pyotp = None
    SmartConnect = None


def _secret(name: str, default: str = "") -> str:
    """Read a credential from Streamlit secrets first, then environment."""
    try:
        import streamlit as st
        value = st.secrets.get(name)
        if value is not None:
            return str(value)
    except Exception:
        pass
    return os.getenv(name, default)


class AngelOneProvider:
    """Read-only Angel One SmartAPI provider.

    Required secrets:
        ANGELONE_API_KEY
        ANGELONE_CLIENT_ID
        ANGELONE_PIN
        ANGELONE_TOTP_SECRET

    Market-data defaults:
        ANGELONE_EXCHANGE
        ANGELONE_SYMBOL
        ANGELONE_SYMBOL_TOKEN
    """

    name = "AngelOneSmartAPI"
    version = "1.0.0"

    def __init__(self) -> None:
        if SmartConnect is None or pyotp is None:
            raise RuntimeError(
                "Angel One dependencies are missing. Install smartapi-python and pyotp."
            )

        self.api_key = _secret("ANGELONE_API_KEY")
        self.client_id = _secret("ANGELONE_CLIENT_ID")
        self.pin = _secret("ANGELONE_PIN")
        self.totp_secret = _secret("ANGELONE_TOTP_SECRET")

        self.exchange = _secret("ANGELONE_EXCHANGE", "NSE")
        self.symbol = _secret("ANGELONE_SYMBOL", "NIFTY")
        self.symbol_token = _secret("ANGELONE_SYMBOL_TOKEN")

        missing = [
            key
            for key, value in {
                "ANGELONE_API_KEY": self.api_key,
                "ANGELONE_CLIENT_ID": self.client_id,
                "ANGELONE_PIN": self.pin,
                "ANGELONE_TOTP_SECRET": self.totp_secret,
                "ANGELONE_SYMBOL_TOKEN": self.symbol_token,
            }.items()
            if not value
        ]
        if missing:
            raise RuntimeError(
                "Missing Angel One secret(s): " + ", ".join(missing)
            )

        self.client = SmartConnect(api_key=self.api_key)
        self.session = None
        self._login()

    def _login(self) -> None:
        totp = pyotp.TOTP(self.totp_secret).now()
        response = self.client.generateSession(
            self.client_id,
            self.pin,
            totp,
        )

        if not isinstance(response, dict) or not response.get("status"):
            message = (
                response.get("message", "Angel One login failed")
                if isinstance(response, dict)
                else "Angel One login failed"
            )
            raise RuntimeError(message)

        self.session = response.get("data") or {}
        self.feed_token = self.client.getfeedToken()

    def fetch(
        self,
        symbol: Optional[str] = None,
        start: Any = None,
        end: Any = None,
        limit: Optional[int] = None,
        **kwargs: Any,
    ) -> list[dict[str, Any]]:
        """Return the latest Angel One LTP as one normalized record."""
        requested_symbol = symbol or self.symbol

        response = self.client.ltpData(
            self.exchange,
            requested_symbol,
            self.symbol_token,
        )

        if not isinstance(response, dict) or not response.get("status"):
            message = (
                response.get("message", "Angel One LTP request failed")
                if isinstance(response, dict)
                else "Angel One LTP request failed"
            )
            raise RuntimeError(message)

        data = response.get("data") or {}
        price = data.get("ltp")

        if price is None:
            raise RuntimeError("Angel One returned no LTP value.")

        now = datetime.now(timezone.utc).isoformat()

        return [{
            "symbol": requested_symbol,
            "timestamp": now,
            "price": float(price),
            "close": float(price),
            "exchange": self.exchange,
            "symbol_token": self.symbol_token,
            "source": "angelone_smartapi_ltp",
        }]

    def stream_client(self):
        """Create the official SmartWebSocketV2 client.

        This method does not start the socket. It is intentionally separate so
        the current readiness test can use the stable LTP endpoint first.
        """
        from SmartApi.smartWebSocketV2 import SmartWebSocketV2

        return SmartWebSocketV2(
            self.session["jwtToken"],
            self.api_key,
            self.client_id,
            self.feed_token,
        )
