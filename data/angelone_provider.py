"""Angel One SmartAPI read-only market-data provider.

Responsibilities:
- authenticate with Angel One using Streamlit secrets/environment variables
- resolve NIFTY instruments
- fetch current LTP with provider timestamps
- fetch historical OHLCV candles using market-session-aware windows
- expose the official SmartWebSocketV2 client for future streaming use

This module contains NO order-placement or GTT operations.
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


class AngelOneProvider:
    name = "AngelOneSmartAPI"
    version = "2.1.0"

    # NSE index/equity regular market session.
    NSE_MARKET_OPEN_HOUR = 9
    NSE_MARKET_OPEN_MINUTE = 15
    NSE_MARKET_CLOSE_HOUR = 15
    NSE_MARKET_CLOSE_MINUTE = 30

    def __init__(self) -> None:
        if SmartConnect is None or pyotp is None:
            raise RuntimeError(
                "Angel One dependencies are missing. "
                "Install smartapi-python and pyotp."
            )

        self.api_key = self._secret("ANGELONE_API_KEY")
        self.client_id = self._secret("ANGELONE_CLIENT_ID")
        self.pin = self._secret("ANGELONE_PIN")
        self.totp_secret = self._secret("ANGELONE_TOTP_SECRET")

        self.exchange = self._secret(
            "ANGELONE_EXCHANGE",
            "NSE",
        ).strip().upper()

        self.symbol = self._secret(
            "ANGELONE_SYMBOL",
            "NIFTY",
        ).strip()

        self.symbol_token = self._secret(
            "ANGELONE_SYMBOL_TOKEN",
        ).strip()

        self.interval = self._secret(
            "ANGELONE_INTERVAL",
            "ONE_MINUTE",
        ).strip().upper()

        self.history_bars = max(
            20,
            int(
                self._secret(
                    "ANGELONE_HISTORY_BARS",
                    "120",
                )
            ),
        )

        self.lookback_minutes = max(
            30,
            int(
                self._secret(
                    "ANGELONE_LOOKBACK_MINUTES",
                    "240",
                )
            ),
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
                "Missing Angel One secret(s): "
                + ", ".join(missing)
            )

        self.client = SmartConnect(
            api_key=self.api_key
        )

        self.session: dict[str, Any] = {}
        self.feed_token = ""

        self._resolved_instruments: dict[
            str,
            tuple[str, str],
        ] = {}

        self._login()

    # ------------------------------------------------------------------
    # SECRET ACCESS
    # ------------------------------------------------------------------

    @staticmethod
    def _secret(
        name: str,
        default: str = "",
    ) -> str:
        try:
            import streamlit as st

            value = st.secrets.get(name)

            if value is not None:
                return str(value)

        except Exception:
            pass

        return os.getenv(
            name,
            default,
        )

    # ------------------------------------------------------------------
    # AUTHENTICATION
    # ------------------------------------------------------------------

    def _login(self) -> None:
        totp = pyotp.TOTP(
            self.totp_secret
        ).now()

        response = self.client.generateSession(
            self.client_id,
            self.pin,
            totp,
        )

        if (
            not isinstance(response, dict)
            or not response.get("status")
        ):
            message = (
                response.get(
                    "message",
                    "Angel One login failed",
                )
                if isinstance(response, dict)
                else "Angel One login failed"
            )

            raise RuntimeError(message)

        self.session = (
            response.get("data") or {}
        )

        self.feed_token = (
            self.client.getfeedToken()
        )

        if not self.session.get(
            "jwtToken"
        ):
            raise RuntimeError(
                "Angel One login succeeded "
                "without jwtToken."
            )

        if not self.feed_token:
            raise RuntimeError(
                "Angel One login succeeded "
                "without feedToken."
            )

    # ------------------------------------------------------------------
    # INSTRUMENT RESOLUTION
    # ------------------------------------------------------------------

    def _resolve_instrument(
            self,
            symbol: Optional[str],
            exchange: Optional[str] = None,
        ) -> tuple[str, str]:

            requested = (
                symbol or self.symbol
            ).strip()

            if not requested:
                raise RuntimeError(
                    "Angel One symbol is empty."
                )

            target_exchange = (
                exchange
                or self.exchange
            ).strip().upper()

            cache_key = (
                f"{target_exchange}:"
                f"{requested.upper()}"
            )

            if cache_key in self._resolved_instruments:
                return self._resolved_instruments[cache_key]

            configured_token = (
                self.symbol_token
                if (
                    target_exchange == self.exchange
                    and requested.upper() == self.symbol.upper()
                )
                else ""
            )

            if configured_token:
                result = (
                    requested,
                    configured_token,
                )

                self._resolved_instruments[cache_key] = result
                return result

            # NIFTY standard token.
            if (
                target_exchange == "NSE"
                and requested.upper()
                in {
                    "NIFTY",
                    "NIFTY 50",
                    "NIFTY50",
                }
            ):
                result = (
                    "NIFTY",
                    "99926000",
                )

                self._resolved_instruments[cache_key] = result
                return result

            # MCX and all other instruments:
            # resolve through Angel One Search Scrip.
            response = self.client.searchScrip(
                target_exchange,
                requested,
            )

            if (
                not isinstance(response, dict)
                or not response.get("status")
            ):
                message = (
                    response.get(
                        "message",
                        "Angel One symbol lookup failed",
                    )
                    if isinstance(response, dict)
                    else "Angel One symbol lookup failed"
                )

                raise RuntimeError(message)

            rows = response.get("data") or []

            if not rows:
                raise RuntimeError(
                    f"Angel One could not find "
                    f"symbol '{requested}' "
                    f"on {target_exchange}."
                )

            candidates = [
                row
                for row in rows
                if (
                    isinstance(row, dict)
                    and row.get("symboltoken")
                    and row.get("tradingsymbol")
                )
            ]

            if not candidates:
                raise RuntimeError(
                    f"Angel One returned no usable "
                    f"instrument for '{requested}'."
                )

            exact = [
                row
                for row in candidates
                if str(
                    row.get("tradingsymbol", "")
                ).upper()
                == requested.upper()
            ]

            chosen = (
                exact or candidates
            )[0]

            result = (
                str(chosen["tradingsymbol"]),
                str(chosen["symboltoken"]),
            )

            self._resolved_instruments[cache_key] = result

            return result
    # ------------------------------------------------------------------
    # LTP
    # ------------------------------------------------------------------

    def _fetch_ltp(
        self,
        symbol: Optional[str] = None,
        exchange: Optional[str] = None,
    ) -> list[dict[str, Any]]:

        target_exchange = (
            exchange or target_exchange
        ).strip().upper()

        trading_symbol, token = (
            self._resolve_instrument(
                symbol,
                target_exchange,
            )
        )
        
        response = self.client.ltpData(
            target_exchange,
            trading_symbol,
            token,
        )

        if (
            not isinstance(response, dict)
            or not response.get("status")
        ):
            message = (
                response.get(
                    "message",
                    "Angel One LTP request failed",
                )
                if isinstance(response, dict)
                else "Angel One LTP request failed"
            )

            raise RuntimeError(message)

        data = (
            response.get("data") or {}
        )

        price = data.get("ltp")

        if price is None:
            raise RuntimeError(
                "Angel One returned no LTP value."
            )

        # IMPORTANT:
        # Do NOT manufacture a live timestamp.
        # If Angel One does not provide a usable
        # exchange timestamp, mark the record
        # as timestamp-unavailable instead.
        timestamp = (
            self._parse_exchange_timestamp(
                data.get("exchTradeTime")
                or data.get("exchFeedTime")
            )
        )

        record = {
            "symbol": trading_symbol,
            "timestamp": (
                timestamp.isoformat()
                if timestamp
                else None
            ),
            "price": float(price),
            "close": float(price),
            "open": self._float_or_none(
                data.get("open")
            ),
            "high": self._float_or_none(
                data.get("high")
            ),
            "low": self._float_or_none(
                data.get("low")
            ),
            "volume": self._float_or_none(
                data.get("tradeVolume")
            ),
            "change_pct": self._float_or_none(
                data.get("percentChange")
            ),
            "exchange": target_exchange,
            "symbol_token": token,
            "source": "angelone_smartapi_ltp",
            "live": True,
            "data_type": "ltp",
            "timestamp_source": (
                "angelone_exchange"
                if timestamp
                else "unavailable"
            ),
        }

        return [record]

    # ------------------------------------------------------------------
    # NUMERIC / TIMESTAMP HELPERS
    # ------------------------------------------------------------------

    @staticmethod
    def _float_or_none(
        value: Any,
    ) -> Optional[float]:

        try:
            return (
                None
                if value is None
                else float(value)
            )

        except (
            TypeError,
            ValueError,
        ):
            return None

    @staticmethod
    def _parse_exchange_timestamp(
        value: Any,
    ) -> Optional[datetime]:

        if not value:
            return None

        text = str(value).strip()

        for fmt in (
            "%d-%b-%Y %H:%M:%S",
            "%d-%b-%Y %H:%M",
        ):
            try:
                return (
                    datetime.strptime(
                        text,
                        fmt,
                    )
                    .replace(
                        tzinfo=IST
                    )
                    .astimezone(
                        timezone.utc
                    )
                )

            except ValueError:
                continue

        try:
            dt = datetime.fromisoformat(
                text.replace(
                    "Z",
                    "+00:00",
                )
            )

            if dt.tzinfo is None:
                dt = dt.replace(
                    tzinfo=IST
                )

            return dt.astimezone(
                timezone.utc
            )

        except ValueError:
            return None

    # ------------------------------------------------------------------
    # MARKET SESSION HELPERS
    # ------------------------------------------------------------------

    @classmethod
    def _nse_session_bounds(
        cls,
        date,
    ) -> tuple[datetime, datetime]:

        start = datetime(
            date.year,
            date.month,
            date.day,
            cls.NSE_MARKET_OPEN_HOUR,
            cls.NSE_MARKET_OPEN_MINUTE,
            tzinfo=IST,
        )

        end = datetime(
            date.year,
            date.month,
            date.day,
            cls.NSE_MARKET_CLOSE_HOUR,
            cls.NSE_MARKET_CLOSE_MINUTE,
            tzinfo=IST,
        )

        return start, end

    @classmethod
    def _is_nse_trading_day(
        cls,
        date,
    ) -> bool:
        return date.weekday() < 5

    @classmethod
    def _previous_nse_trading_day(
        cls,
        date,
    ):
        current = date - timedelta(
            days=1
        )

        while not cls._is_nse_trading_day(
            current
        ):
            current -= timedelta(
                days=1
            )

        return current

    def _session_aware_window(
        self,
        end_dt: datetime,
        bars: int,
        exchange: Optional[str] = None,
    ) -> tuple[
        datetime,
        datetime,
    ]:
        """Build an exchange-aware historical data window."""

        target_exchange = (
            exchange or self.exchange
        ).strip().upper()

        # NSE/NIFTY session-aware handling.
        # MCX and other exchanges currently use
        # the generic lookback window.
        if target_exchange != "NSE":
            return (
                end_dt
                - timedelta(
                    minutes=max(
                        self.lookback_minutes,
                        bars * 2,
                    )
                ),
                end_dt,
            )

        local_end = end_dt.astimezone(
            IST
        )

        session_open, session_close = (
            self._nse_session_bounds(
                local_end.date()
            )
        )

        if (
            not self._is_nse_trading_day(
                local_end.date()
            )
            or local_end < session_open
        ):
            previous_day = (
                self._previous_nse_trading_day(
                    local_end.date()
                )
            )

            session_open, session_close = (
                self._nse_session_bounds(
                    previous_day
                )
            )

            effective_end = session_close

        elif local_end > session_close:
            effective_end = session_close

        else:
            effective_end = local_end

        # Keep enough calendar time to obtain
        # the requested number of one-minute bars.
        effective_start = (
            effective_end
            - timedelta(
                minutes=max(
                    self.lookback_minutes,
                    bars * 2,
                )
            )
        )

        # Never start before the NSE session opening
        # when requesting a same-session window.
        if effective_start < session_open:
            effective_start = session_open

        return (
            effective_start,
            effective_end,
    )

    # ------------------------------------------------------------------
    # HISTORICAL WINDOW
    # ------------------------------------------------------------------

    def _historical_window(
        self,
        start: Any = None,
        end: Any = None,
        limit: Optional[int] = None,
        exchange: Optional[str] = None,
    ) -> tuple[
        datetime,
        datetime,
    ]:

        now_ist = datetime.now(IST)

        def parse(
            value: Any,
        ) -> Optional[datetime]:

            if value is None:
                return None

            if isinstance(
                value,
                datetime,
            ):
                dt = value

                if dt.tzinfo is None:
                    dt = dt.replace(
                        tzinfo=IST
                    )

                return dt.astimezone(
                    IST
                )

            text = str(
                value
            ).strip().replace(
                "Z",
                "+00:00",
            )

            try:
                dt = datetime.fromisoformat(
                    text
                )

                if dt.tzinfo is None:
                    dt = dt.replace(
                        tzinfo=IST
                    )

                return dt.astimezone(
                    IST
                )

            except ValueError:
                return None

        end_dt = (
            parse(end)
            or now_ist
        )

        start_dt = parse(start)

        target_exchange = (
            exchange
            or self.exchange
        ).strip().upper()

        if start_dt is None:
            bars = max(
                20,
                int(
                    limit
                    or self.history_bars
                ),
            )

            start_dt, end_dt = (
                self._session_aware_window(
                    end_dt,
                    bars,
                    exchange=target_exchange,
                )
            )

        if start_dt >= end_dt:
            start_dt = (
                end_dt
                - timedelta(
                    minutes=self.lookback_minutes
                )
            )

        return (
            start_dt,
            end_dt,
        )

    # ------------------------------------------------------------------
    # HISTORICAL CANDLES
    # ------------------------------------------------------------------

    def _fetch_candles(
        self,
        symbol: Optional[str] = None,
        start: Any = None,
        end: Any = None,
        limit: Optional[int] = None,
        exchange: Optional[str] = None,
    ) -> list[dict[str, Any]]:

        target_exchange = (
            exchange or target_exchange,
        ).strip().upper()

        trading_symbol, token = (
            self._resolve_instrument(
                symbol,
                target_exchange,
            )
        )

        start_dt, end_dt = (
            self._historical_window(
                start,
                end,
                limit,
            )
        )

        params = {
            "exchange": target_exchange,
            "symboltoken": token,
            "interval": self.interval,
            "fromdate": start_dt.strftime(
                "%Y-%m-%d %H:%M"
            ),
            "todate": end_dt.strftime(
                "%Y-%m-%d %H:%M"
            ),
        }

        response = (
            self.client.getCandleData(
                params
            )
        )

        if (
            not isinstance(response, dict)
            or not response.get("status")
        ):
            message = (
                response.get(
                    "message",
                    "Angel One historical candle request failed",
                )
                if isinstance(response, dict)
                else "Angel One historical candle request failed"
            )

            raise RuntimeError(message)

        rows = (
            response.get("data") or []
        )

        records: list[
            dict[str, Any]
        ] = []

        for row in rows:

            if (
                not isinstance(
                    row,
                    (list, tuple),
                )
                or len(row) < 6
            ):
                continue

            timestamp = (
                self._parse_exchange_timestamp(
                    row[0]
                )
            )

            if timestamp is None:
                try:
                    timestamp = (
                        datetime.fromisoformat(
                            str(
                                row[0]
                            ).replace(
                                "Z",
                                "+00:00",
                            )
                        ).astimezone(
                            timezone.utc
                        )
                    )

                except ValueError:
                    continue

            try:
                open_price = float(
                    row[1]
                )
                high = float(
                    row[2]
                )
                low = float(
                    row[3]
                )
                close = float(
                    row[4]
                )
                volume = float(
                    row[5]
                )
            except (
                TypeError,
                ValueError,
            ):
                continue

            records.append(
                {
                    "symbol": trading_symbol,
                    "timestamp": timestamp.isoformat(),
                    "open": open_price,
                    "high": high,
                    "low": low,
                    "close": close,
                    "volume": volume,
                    "exchange": target_exchange,
                    "symbol_token": token,
                    "source": "angelone_smartapi_candles",
                    "live": False,
                    "data_type": "candle",
                }
            )

        records.sort(
            key=lambda item:
            item["timestamp"]
        )

        if limit:
            records = records[
                -max(
                    1,
                    int(limit),
                ):
            ]

        return records

    # ------------------------------------------------------------------
    # PUBLIC PROVIDER CONTRACT
    # ------------------------------------------------------------------

    def fetch(
        self,
        symbol: Optional[str] = None,
        start: Any = None,
        end: Any = None,
        limit: Optional[int] = None,
        **kwargs: Any,
    ) -> list[dict[str, Any]]:

        target_exchange = (
            kwargs.get("exchange")
            or self.exchange
        ).strip().upper()

        if (
            start is not None
            or end is not None
            or (
                limit is not None
                and int(limit) > 1
            )
        ):
            return self._fetch_candles(
                symbol=symbol,
                start=start,
                end=end,
                limit=limit,
                exchange=target_exchange,
            )

        return self._fetch_ltp(
            symbol=symbol,
            exchange=target_exchange,
        )

    def latest(
        self,
        symbol: Optional[str] = None,
        **kwargs: Any,
    ) -> dict[str, Any]:

        target_exchange = (
            kwargs.get("exchange")
            or self.exchange
        ).strip().upper()

        records = self._fetch_ltp(
            symbol=symbol,
            exchange=target_exchange,
        )

        has_timestamp = bool(
            records
            and records[-1].get(
                "timestamp"
            )
        )

        return {
            "record": (
                records[-1]
                if records
                else None
            ),
            "quality": {
                "status": (
                    "OK"
                    if records
                    else "EMPTY"
                ),
                "fresh": (
                    bool(records)
                    and has_timestamp
                ),
                "count": len(records),
            },
            "source":
                "angelone_smartapi_ltp",
        }

    # ------------------------------------------------------------------
    # OFFICIAL WEBSOCKET CLIENT
    # ------------------------------------------------------------------

    def stream_client(self):
        """Return SmartWebSocketV2 without starting it."""

        from SmartApi.smartWebSocketV2 import (
            SmartWebSocketV2,
        )

        return SmartWebSocketV2(
            self.session["jwtToken"],
            self.api_key,
            self.client_id,
            self.feed_token,
        )

    # ------------------------------------------------------------------
    # HEALTH
    # ------------------------------------------------------------------

    def health(
        self,
    ) -> dict[str, Any]:

        return {
            "engine": self.name,
            "version": self.version,
            "provider": self.name,
            "exchange": self.exchange,
            "symbol": self.symbol,
            "authenticated": bool(
                self.session.get(
                    "jwtToken"
                )
            ),
            "feed_token": bool(
                self.feed_token
            ),
            "order_capability": False,
            }
