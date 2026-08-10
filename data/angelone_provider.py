"""Angel One SmartAPI read-only market-data provider.

Responsibilities:
- authenticate with Angel One using Streamlit secrets/environment variables
- fetch current LTP
- fetch historical OHLCV candles
- optionally expose the official SmartWebSocketV2 client for a later streaming layer

This module intentionally contains NO order-placement or GTT operations.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from zoneinfo import ZoneInfo

try:
    import pyotp
    from SmartApi import SmartConnect
except ImportError:  # pragma: no cover
    pyotp = None
    SmartConnect = None


IST = ZoneInfo("Asia/Kolkata")


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
    name = "AngelOneSmartAPI"
    version = "2.0.0"

    def __init__(self) -> None:
        if SmartConnect is None or pyotp is None:
            raise RuntimeError(
                "Angel One dependencies are missing. Install smartapi-python and pyotp."
            )

        self.api_key = _secret("ANGELONE_API_KEY")
        self.client_id = _secret("ANGELONE_CLIENT_ID")
        self.pin = _secret("ANGELONE_PIN")
        self.totp_secret = _secret("ANGELONE_TOTP_SECRET")

        self.exchange = _secret("ANGELONE_EXCHANGE", "NSE").strip().upper()
        self.symbol = _secret("ANGELONE_SYMBOL", "NIFTY").strip()
        self.symbol_token = _secret("ANGELONE_SYMBOL_TOKEN").strip()

        self.interval = _secret("ANGELONE_INTERVAL", "ONE_MINUTE").strip().upper()
        self.history_bars = max(
            20, int(_secret("ANGELONE_HISTORY_BARS", "120"))
        )
        self.lookback_minutes = max(
            30, int(_secret("ANGELONE_LOOKBACK_MINUTES", "240"))
        )

        missing = [
            key
            for key, value in {
                "ANGELONE_API_KEY": self.api_key,
                "ANGELONE_CLIENT_ID": self.client_id,
                "ANGELONE_PIN": self.pin,
                "ANGELONE_TOTP_SECRET": self.totp_secret,
            }.items()
            if not value
        ]
        if missing:
            raise RuntimeError(
                "Missing Angel One secret(s): " + ", ".join(missing)
            )

        self.client = SmartConnect(api_key=self.api_key)
        self.session: dict[str, Any] = {}
        self.feed_token = ""
        self._resolved_instruments: dict[str, tuple[str, str]] = {}
        self._login()

    # ------------------------------------------------------------------
    # AUTHENTICATION
    # ------------------------------------------------------------------

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

        if not self.session.get("jwtToken"):
            raise RuntimeError("Angel One login succeeded without jwtToken.")
        if not self.feed_token:
            raise RuntimeError("Angel One login succeeded without feedToken.")

    # ------------------------------------------------------------------
    # INSTRUMENT RESOLUTION
    # ------------------------------------------------------------------

    def _resolve_instrument(self, symbol: Optional[str]) -> tuple[str, str]:
        """Resolve a user symbol to (trading_symbol, token).

        A configured token is preferred. Otherwise Angel One's authenticated
        Search Scrip API is used. For the NIFTY index we retain the standard
        Angel One token as a safe default.
        """
        requested = (symbol or self.symbol).strip()
        if not requested:
            raise RuntimeError("Angel One symbol is empty.")

        cache_key = f"{self.exchange}:{requested.upper()}"
        if cache_key in self._resolved_instruments:
            return self._resolved_instruments[cache_key]

        configured_token = self.symbol_token if requested.upper() == self.symbol.upper() else ""
        if configured_token:
            result = (requested, configured_token)
            self._resolved_instruments[cache_key] = result
            return result

        # Standard Angel One token for NIFTY 50 index.
        if self.exchange == "NSE" and requested.upper() in {
            "NIFTY", "NIFTY 50", "NIFTY50"
        }:
            result = ("NIFTY", "99926000")
            self._resolved_instruments[cache_key] = result
            return result

        response = self.client.searchScrip(
            self.exchange,
            requested,
        )
        if not isinstance(response, dict) or not response.get("status"):
            message = (
                response.get("message", "Angel One symbol lookup failed")
                if isinstance(response, dict)
                else "Angel One symbol lookup failed"
            )
            raise RuntimeError(message)

        rows = response.get("data") or []
        if not rows:
            raise RuntimeError(
                f"Angel One could not find symbol '{requested}' on {self.exchange}."
            )

        candidates = [
            row for row in rows
            if isinstance(row, dict)
            and row.get("symboltoken")
            and row.get("tradingsymbol")
        ]
        if not candidates:
            raise RuntimeError(
                f"Angel One returned no usable instrument for '{requested}'."
            )

        exact = [
            row for row in candidates
            if str(row.get("tradingsymbol", "")).upper()
            == requested.upper()
        ]
        equity = [
            row for row in candidates
            if str(row.get("tradingsymbol", "")).upper()
            == f"{requested.upper()}-EQ"
        ]

        chosen = (exact or equity or candidates)[0]
        trading_symbol = str(chosen["tradingsymbol"])
        token = str(chosen["symboltoken"])

        result = (trading_symbol, token)
        self._resolved_instruments[cache_key] = result
        return result

    # ------------------------------------------------------------------
    # LTP
    # ------------------------------------------------------------------

    def _fetch_ltp(self, symbol: Optional[str] = None) -> list[dict[str, Any]]:
        trading_symbol, token = self._resolve_instrument(symbol)

        response = self.client.ltpData(
            self.exchange,
            trading_symbol,
            token,
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

        timestamp = self._parse_exchange_timestamp(
            data.get("exchTradeTime")
            or data.get("exchFeedTime")
        ) or datetime.now(timezone.utc)

        return [{
            "symbol": trading_symbol,
            "timestamp": timestamp.isoformat(),
            "price": float(price),
            "close": float(price),
            "open": self._float_or_none(data.get("open")),
            "high": self._float_or_none(data.get("high")),
            "low": self._float_or_none(data.get("low")),
            "volume": self._float_or_none(data.get("tradeVolume")),
            "change_pct": self._float_or_none(data.get("percentChange")),
            "exchange": self.exchange,
            "symbol_token": token,
            "source": "angelone_smartapi_ltp",
            "live": True,
            "data_type": "ltp",
        }]

    # ------------------------------------------------------------------
    # HISTORICAL CANDLES
    # ------------------------------------------------------------------

    @staticmethod
    def _float_or_none(value: Any) -> Optional[float]:
        try:
            return None if value is None else float(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _parse_exchange_timestamp(value: Any) -> Optional[datetime]:
        if not value:
            return None

        text = str(value).strip()
        for fmt in (
            "%d-%b-%Y %H:%M:%S",
            "%d-%b-%Y %H:%M",
        ):
            try:
                return datetime.strptime(text, fmt).replace(tzinfo=IST).astimezone(timezone.utc)
            except ValueError:
                continue

        try:
            return datetime.fromisoformat(text.replace("Z", "+00:00")).astimezone(timezone.utc)
        except ValueError:
            return None

    def _historical_window(
        self,
        start: Any = None,
        end: Any = None,
        limit: Optional[int] = None,
    ) -> tuple[datetime, datetime]:
        now_ist = datetime.now(IST)

        def parse(value: Any) -> Optional[datetime]:
            if value is None:
                return None
            if isinstance(value, datetime):
                dt = value
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=IST)
                return dt.astimezone(IST)
            text = str(value).strip().replace("Z", "+00:00")
            try:
                dt = datetime.fromisoformat(text)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=IST)
                return dt.astimezone(IST)
            except ValueError:
                return None

        end_dt = parse(end) or now_ist
        start_dt = parse(start)

        if start_dt is None:
            bars = max(20, int(limit or self.history_bars))
            # Add a cushion because weekends/holidays and market closures can
            # make a simple bars*interval window shorter than requested.
            start_dt = end_dt - timedelta(
                minutes=max(self.lookback_minutes, bars * 2)
            )

        if start_dt >= end_dt:
            start_dt = end_dt - timedelta(minutes=self.lookback_minutes)

        return start_dt, end_dt

    def _fetch_candles(
        self,
        symbol: Optional[str] = None,
        start: Any = None,
        end: Any = None,
        limit: Optional[int] = None,
    ) -> list[dict[str, Any]]:
        trading_symbol, token = self._resolve_instrument(symbol)
        start_dt, end_dt = self._historical_window(start, end, limit)

        params = {
            "exchange": self.exchange,
            "symboltoken": token,
            "interval": self.interval,
            "fromdate": start_dt.strftime("%Y-%m-%d %H:%M"),
            "todate": end_dt.strftime("%Y-%m-%d %H:%M"),
        }

        response = self.client.getCandleData(params)

        if not isinstance(response, dict) or not response.get("status"):
            message = (
                response.get("message", "Angel One historical candle request failed")
                if isinstance(response, dict)
                else "Angel One historical candle request failed"
            )
            raise RuntimeError(message)

        rows = response.get("data") or []
        records: list[dict[str, Any]] = []

        for row in rows:
            if not isinstance(row, (list, tuple)) or len(row) < 6:
                continue

            timestamp = self._parse_exchange_timestamp(row[0])
            if timestamp is None:
                try:
                    timestamp = datetime.fromisoformat(
                        str(row[0]).replace("Z", "+00:00")
                    ).astimezone(timezone.utc)
                except ValueError:
                    continue

            records.append({
                "symbol": trading_symbol,
                "timestamp": timestamp.isoformat(),
                "open": float(row[1]),
                "high": float(row[2]),
                "low": float(row[3]),
                "close": float(row[4]),
                "volume": float(row[5]),
                "exchange": self.exchange,
                "symbol_token": token,
                "source": "angelone_smartapi_candles",
                "live": False,
                "data_type": "candle",
            })

        records.sort(key=lambda item: item["timestamp"])
        if limit:
            records = records[-max(1, int(limit)):]
        return records

    # ------------------------------------------------------------------
    # PUBLIC GATEWAY CONTRACT
    # ------------------------------------------------------------------

    def fetch(
        self,
        symbol: Optional[str] = None,
        start: Any = None,
        end: Any = None,
        limit: Optional[int] = None,
        **kwargs: Any,
    ) -> list[dict[str, Any]]:
        """Fetch LTP for limit<=1 without an explicit range; otherwise candles."""
        if start is not None or end is not None or (limit is not None and int(limit) > 1):
            return self._fetch_candles(symbol, start, end, limit)

        return self._fetch_ltp(symbol)

    def latest(self, symbol: Optional[str] = None, **kwargs: Any) -> dict[str, Any]:
        records = self._fetch_ltp(symbol)
        return {
            "record": records[-1] if records else None,
            "quality": {"status": "OK" if records else "EMPTY", "fresh": bool(records), "count": len(records)},
            "source": "angelone_smartapi_ltp",
        }

    def stream_client(self):
        """Return the official SmartWebSocketV2 client without starting it."""
        from SmartApi.smartWebSocketV2 import SmartWebSocketV2

        return SmartWebSocketV2(
            self.session["jwtToken"],
            self.api_key,
            self.client_id,
            self.feed_token,
        )

    def health(self) -> dict[str, Any]:
        return {
            "engine": self.name,
            "version": self.version,
            "provider": self.name,
            "exchange": self.exchange,
            "symbol": self.symbol,
            "authenticated": bool(self.session.get("jwtToken")),
            "feed_token": bool(self.feed_token),
            "order_capability": False,
        }
