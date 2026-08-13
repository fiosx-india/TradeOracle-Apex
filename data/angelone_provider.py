"""Angel One SmartAPI read-only market-data provider.

Responsibilities:
- authenticate with Angel One using Streamlit secrets/environment variables
- resolve NSE/NIFTY instruments
- resolve MCX/commodity instruments without confusing GOLD/GOLDM,
  SILVER/SILVERM, etc.
- fetch current LTP with provider timestamps
- fetch historical OHLCV candles using exchange-aware windows
- expose the official SmartWebSocketV2 client for streaming integration
- provide provider health information

This module contains NO order-placement or GTT operations.
"""

from __future__ import annotations

import os
import re
from datetime import date, datetime, timedelta, timezone
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
    version = "2.3.0"

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
            "ANGELONE_EXCHANGE", "NSE"
        ).strip().upper()

        self.symbol = self._secret(
            "ANGELONE_SYMBOL", "NIFTY"
        ).strip()

        self.symbol_token = self._secret(
            "ANGELONE_SYMBOL_TOKEN", ""
        ).strip()

        self.interval = self._secret(
            "ANGELONE_INTERVAL", "ONE_MINUTE"
        ).strip().upper()

        self.history_bars = max(
            20,
            self._safe_int(
                self._secret("ANGELONE_HISTORY_BARS", "120"),
                120,
            ),
        )

        self.lookback_minutes = max(
            30,
            self._safe_int(
                self._secret(
                    "ANGELONE_LOOKBACK_MINUTES", "240"
                ),
                240,
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

        self.client = SmartConnect(api_key=self.api_key)
        self.session: dict[str, Any] = {}
        self.feed_token = ""

        self._resolved_instruments: dict[
            str, tuple[str, str]
        ] = {}

        self._login()

    # ================================================================
    # HELPERS
    # ================================================================

    @staticmethod
    def _secret(name: str, default: str = "") -> str:
        try:
            import streamlit as st

            value = st.secrets.get(name)
            if value is not None:
                return str(value)
        except Exception:
            pass

        return os.getenv(name, default)

    @staticmethod
    def _safe_int(value: Any, default: int) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return int(default)

    @staticmethod
    def _float_or_none(value: Any) -> Optional[float]:
        try:
            if value is None:
                return None
            return float(value)
        except (TypeError, ValueError):
            return None

    # ================================================================
    # AUTHENTICATION
    # ================================================================

    def _login(self) -> None:
        totp = pyotp.TOTP(self.totp_secret).now()

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
                    "message", "Angel One login failed"
                )
                if isinstance(response, dict)
                else "Angel One login failed"
            )
            raise RuntimeError(message)

        self.session = response.get("data") or {}
        self.feed_token = self.client.getfeedToken()

        if not self.session.get("jwtToken"):
            raise RuntimeError(
                "Angel One login succeeded without jwtToken."
            )

        if not self.feed_token:
            raise RuntimeError(
                "Angel One login succeeded without feedToken."
            )

    # ================================================================
    # INSTRUMENT RESOLUTION
    # ================================================================

    def _resolve_instrument(
        self,
        symbol: Optional[str],
        exchange: Optional[str] = None,
    ) -> tuple[str, str]:
        """Resolve a symbol without silently crossing contracts."""

        requested = (symbol or self.symbol).strip()
        if not requested:
            raise RuntimeError("Angel One symbol is empty.")

        target_exchange = (
            exchange or self.exchange
        ).strip().upper()
        if not target_exchange:
            raise RuntimeError("Angel One exchange is empty.")

        cache_key = f"{target_exchange}:{requested.upper()}"

        cached = self._resolved_instruments.get(cache_key)
        if cached:
            return cached

        requested_upper = requested.upper()

        # Configured token is trusted only for the configured
        # exchange + symbol. ANGELONE_TRADINGSYMBOL may be supplied
        # when the configured token belongs to a derivative contract.
        configured_token = (
            self.symbol_token
            if (
                target_exchange == self.exchange
                and requested_upper == self.symbol.upper()
            )
            else ""
        )

        if configured_token:
            configured_tradingsymbol = self._secret(
                "ANGELONE_TRADINGSYMBOL",
                requested,
            ).strip() or requested

            result = (
                configured_tradingsymbol,
                configured_token,
            )
            self._resolved_instruments[cache_key] = result
            return result

        # NIFTY 50 index.
        if (
            target_exchange == "NSE"
            and requested_upper in {
                "NIFTY",
                "NIFTY 50",
                "NIFTY50",
            }
        ):
            result = ("NIFTY", "99926000")
            self._resolved_instruments[cache_key] = result
            return result

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
                f"Angel One returned no usable instrument "
                f"for '{requested}' on {target_exchange}."
            )

        # Exact tradingsymbol match always wins.
        exact = [
            row
            for row in candidates
            if str(row.get("tradingsymbol", "")).upper()
            == requested_upper
        ]

        if exact:
            chosen = self._choose_best_contract(exact)
            return self._store_resolution(
                cache_key, chosen
            )

        # NSE equity: SBIN -> SBIN-EQ.
        if target_exchange == "NSE":
            equity = [
                row
                for row in candidates
                if str(row.get("tradingsymbol", "")).upper()
                == f"{requested_upper}-EQ"
            ]

            if equity:
                chosen = self._choose_best_contract(equity)
                return self._store_resolution(
                    cache_key, chosen
                )

        # MCX must use an exact commodity root.
        if target_exchange == "MCX":
            chosen = self._resolve_mcx_contract(
                requested_upper,
                candidates,
            )
            return self._store_resolution(
                cache_key, chosen
            )

        # Other exchanges: never silently choose among unrelated
        # instruments.
        if len(candidates) == 1:
            return self._store_resolution(
                cache_key, candidates[0]
            )

        raise RuntimeError(
            f"Angel One returned multiple instruments for "
            f"'{requested}' on {target_exchange}, but no exact "
            "instrument match was found."
        )

    def _store_resolution(
        self,
        cache_key: str,
        row: dict[str, Any],
    ) -> tuple[str, str]:
        result = (
            str(row["tradingsymbol"]),
            str(row["symboltoken"]),
        )
        self._resolved_instruments[cache_key] = result
        return result

    # ================================================================
    # MCX CONTRACT RESOLUTION
    # ================================================================

    def _resolve_mcx_contract(
        self,
        requested: str,
        candidates: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """
        Resolve only the requested MCX commodity root.

        GOLD   -> GOLD futures
        GOLDM  -> GOLDM futures
        SILVER -> SILVER futures
        SILVERM -> SILVERM futures

        GOLD must NEVER silently resolve to GOLDM, GOLDPETAL,
        GOLDGUINEA, GOLDTEN, etc.
        """

        root_candidates = [
            row
            for row in candidates
            if self._commodity_root(
                str(row.get("tradingsymbol", ""))
            ) == requested
        ]

        if not root_candidates:
            available = sorted(
                str(row.get("tradingsymbol", ""))
                for row in candidates
            )

            preview = ", ".join(available[:12])

            raise RuntimeError(
                f"Angel One found MCX instruments for "
                f"'{requested}', but none belong to the exact "
                f"commodity root '{requested}'. "
                f"Candidates: {preview}"
            )

        futures = [
            row
            for row in root_candidates
            if self._is_futures_symbol(row)
        ]

        if futures:
            root_candidates = futures

        return self._choose_best_contract(
            root_candidates
        )

    @staticmethod
    def _commodity_root(
        trading_symbol: str,
    ) -> str:
        """
        Extract the alphabetic commodity root from a typical MCX
        futures symbol.

        GOLD31AUG26FUT      -> GOLD
        GOLDM31AUG26FUT     -> GOLDM
        GOLDPETAL31AUG26FUT -> GOLDPETAL
        SILVER05SEP26FUT    -> SILVER
        SILVERM05SEP26FUT   -> SILVERM
        """

        text = trading_symbol.upper().strip()

        match = re.match(
            r"^([A-Z]+?)(?:\d{1,2}[A-Z]{3}\d{2,4}|\d{4,8})",
            text,
        )

        if match:
            return match.group(1)

        alpha = re.match(r"^([A-Z]+)", text)
        return alpha.group(1) if alpha else text

    @staticmethod
    def _is_futures_symbol(
        row: dict[str, Any],
    ) -> bool:
        trading_symbol = str(
            row.get("tradingsymbol", "")
        ).upper()

        instrument_type = str(
            row.get("instrumenttype", "")
        ).upper()

        return (
            "FUT" in trading_symbol
            or "FUT" in instrument_type
            or bool(row.get("expiry"))
        )

    # ================================================================
    # BEST CONTRACT
    # ================================================================

    @staticmethod
    def _choose_best_contract(
        candidates: list[dict[str, Any]],
    ) -> dict[str, Any]:
        if not candidates:
            raise RuntimeError(
                "No Angel One instrument candidates."
            )

        today = datetime.now(IST).date()

        dated: list[
            tuple[date, dict[str, Any]]
        ] = []

        for row in candidates:
            expiry_value = row.get("expiry")
            if not expiry_value:
                continue

            parsed = AngelOneProvider._parse_expiry_date(
                str(expiry_value).strip()
            )

            if parsed is not None and parsed >= today:
                dated.append((parsed, row))

        if dated:
            dated.sort(key=lambda item: item[0])
            return dated[0][1]

        return candidates[0]

    @staticmethod
    def _parse_expiry_date(
        value: str,
    ) -> Optional[date]:
        formats = (
            "%d%b%Y",
            "%d-%b-%Y",
            "%d%b%y",
            "%d-%b-%y",
            "%Y-%m-%d",
            "%d/%m/%Y",
            "%d/%m/%y",
        )

        for fmt in formats:
            try:
                return datetime.strptime(
                    value.upper(), fmt
                ).date()
            except ValueError:
                continue

        return None

    # ================================================================
    # LTP
    # ================================================================

    def _fetch_ltp(
        self,
        symbol: Optional[str] = None,
        exchange: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        target_exchange = (
            exchange or self.exchange
        ).strip().upper()

        trading_symbol, token = self._resolve_instrument(
            symbol,
            target_exchange,
        )

        response = self.client.getMarketData(
            "FULL",
            {
                target_exchange: [
                    token
                ]
            },
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

        data = response.get("data") or {}

        fetched = (
            data.get(target_exchange, {})
            if isinstance(data, dict)
            else {}
        )

        if isinstance(fetched, dict):
            market_data = fetched.get(token) or {}
        else:
            market_data = {}

        price = self._float_or_none(
            market_data.get("ltp")
        )
        if price is None or price <= 0:
            raise RuntimeError(
                "Angel One returned no valid positive LTP value."
            )

        "open": self._float_or_none(
            market_data.get("open")
        ),
        "high": self._float_or_none(
            market_data.get("high")
        ),
        "low": self._float_or_none(
            market_data.get("low")
        ),
        "volume": self._float_or_none(
            market_data.get("tradeVolume")
        ),
        "change_pct": self._float_or_none(
            market_data.get("percentChange")
        ),

        return [
            {
                "symbol": trading_symbol,
                "timestamp": (
                    timestamp.isoformat()
                    if timestamp
                    else None
                ),
                "price": price,
                "close": price,
                "open": self._float_or_none(data.get("open")),
                "high": self._float_or_none(data.get("high")),
                "low": self._float_or_none(data.get("low")),
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
        ]

    # ================================================================
    # TIMESTAMP
    # ================================================================

    @staticmethod
    def _parse_exchange_timestamp(
        value: Any,
    ) -> Optional[datetime]:
        if not value:
            return None

        text = str(value).strip()

        formats = (
            "%d-%b-%Y %H:%M:%S",
            "%d-%b-%Y %H:%M",
            "%d-%b-%Y %H:%M:%S.%f",
        )

        for fmt in formats:
            try:
                return (
                    datetime.strptime(text, fmt)
                    .replace(tzinfo=IST)
                    .astimezone(timezone.utc)
                )
            except ValueError:
                continue

        try:
            dt = datetime.fromisoformat(
                text.replace("Z", "+00:00")
            )

            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=IST)

            return dt.astimezone(timezone.utc)
        except ValueError:
            return None

    # ================================================================
    # NSE SESSION
    # ================================================================

    @classmethod
    def _nse_session_bounds(
        cls,
        trading_date: date,
    ) -> tuple[datetime, datetime]:
        start = datetime(
            trading_date.year,
            trading_date.month,
            trading_date.day,
            cls.NSE_MARKET_OPEN_HOUR,
            cls.NSE_MARKET_OPEN_MINUTE,
            tzinfo=IST,
        )

        end = datetime(
            trading_date.year,
            trading_date.month,
            trading_date.day,
            cls.NSE_MARKET_CLOSE_HOUR,
            cls.NSE_MARKET_CLOSE_MINUTE,
            tzinfo=IST,
        )

        return start, end

    @classmethod
    def _is_nse_trading_day(
        cls,
        trading_date: date,
    ) -> bool:
        return trading_date.weekday() < 5

    @classmethod
    def _previous_nse_trading_day(
        cls,
        trading_date: date,
    ) -> date:
        current = trading_date - timedelta(days=1)

        while not cls._is_nse_trading_day(current):
            current -= timedelta(days=1)

        return current

    # ================================================================
    # HISTORICAL WINDOW
    # ================================================================

    def _session_aware_window(
        self,
        end_dt: datetime,
        bars: int,
        exchange: Optional[str] = None,
    ) -> tuple[datetime, datetime]:
        target_exchange = (
            exchange or self.exchange
        ).strip().upper()

        if target_exchange == "NSE":
            local_end = end_dt.astimezone(IST)

            session_open, session_close = (
                self._nse_session_bounds(
                    local_end.date()
                )
            )

            if (
                not self._is_nse_trading_day(local_end.date())
                or local_end < session_open
            ):
                previous_day = self._previous_nse_trading_day(
                    local_end.date()
                )
                session_open, session_close = (
                    self._nse_session_bounds(previous_day)
                )
                effective_end = session_close

            elif local_end > session_close:
                effective_end = session_close
            else:
                effective_end = local_end

            effective_start = (
                effective_end
                - timedelta(
                    minutes=max(
                        self.lookback_minutes,
                        bars * 2,
                    )
                )
            )

            if effective_start < session_open:
                effective_start = session_open

            return effective_start, effective_end

        # MCX / other exchanges do not use NSE hours.
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

    def _historical_window(
        self,
        start: Any = None,
        end: Any = None,
        limit: Optional[int] = None,
        exchange: Optional[str] = None,
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

            text = (
                str(value)
                .strip()
                .replace("Z", "+00:00")
            )

            try:
                dt = datetime.fromisoformat(text)
            except ValueError:
                return None

            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=IST)

            return dt.astimezone(IST)

        end_dt = parse(end) or now_ist
        start_dt = parse(start)

        target_exchange = (
            exchange or self.exchange
        ).strip().upper()

        if start_dt is None:
            bars = max(
                20,
                self._safe_int(
                    limit or self.history_bars,
                    self.history_bars,
                ),
            )

            start_dt, end_dt = self._session_aware_window(
                end_dt,
                bars,
                exchange=target_exchange,
            )

        if start_dt >= end_dt:
            start_dt = (
                end_dt
                - timedelta(
                    minutes=self.lookback_minutes
                )
            )

        return start_dt, end_dt

    # ================================================================
    # HISTORICAL CANDLES
    # ================================================================

    def _fetch_candles(
        self,
        symbol: Optional[str] = None,
        start: Any = None,
        end: Any = None,
        limit: Optional[int] = None,
        exchange: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        target_exchange = (
            exchange or self.exchange
        ).strip().upper()

        trading_symbol, token = self._resolve_instrument(
            symbol,
            target_exchange,
        )

        start_dt, end_dt = self._historical_window(
            start=start,
            end=end,
            limit=limit,
            exchange=target_exchange,
        )

        params = {
            "exchange": target_exchange,
            "symboltoken": token,
            "interval": self.interval,
            "fromdate": start_dt.strftime("%Y-%m-%d %H:%M"),
            "todate": end_dt.strftime("%Y-%m-%d %H:%M"),
        }

        response = self.client.getCandleData(params)

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

        rows = response.get("data") or []
        records: list[dict[str, Any]] = []

        for row in rows:
            if (
                not isinstance(row, (list, tuple))
                or len(row) < 6
            ):
                continue

            timestamp = self._parse_exchange_timestamp(row[0])
            if timestamp is None:
                continue

            try:
                open_price = float(row[1])
                high = float(row[2])
                low = float(row[3])
                close = float(row[4])
                volume = float(row[5])
            except (TypeError, ValueError):
                continue

            # Reject impossible candles before they reach MarketData
            # and the prediction pipeline.
            if (
                open_price <= 0
                or high <= 0
                or low <= 0
                or close <= 0
                or high < low
                or high < open_price
                or high < close
                or low > open_price
                or low > close
                or volume < 0
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
            key=lambda item: item["timestamp"]
        )

        if limit:
            records = records[
                -max(
                    1,
                    self._safe_int(limit, 1),
                ):
            ]

        return records

    # ================================================================
    # PUBLIC PROVIDER CONTRACT
    # ================================================================

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

        requested_limit = (
            self._safe_int(limit, 0)
            if limit is not None
            else 0
        )

        if (
            start is not None
            or end is not None
            or requested_limit > 1
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

    # ================================================================
    # LATEST
    # ================================================================

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

        record = records[-1] if records else None
        has_timestamp = bool(
            record and record.get("timestamp")
        )

        return {
            "record": record,
            "quality": {
                "status": (
                    "OK"
                    if record and has_timestamp
                    else "INVALID"
                    if record
                    else "EMPTY"
                ),
                "fresh": bool(record and has_timestamp),
                "count": len(records),
            },
            "source": "angelone_smartapi_ltp",
        }

    # ================================================================
    # OFFICIAL WEBSOCKET CLIENT
    # ================================================================

    def stream_client(self):
        """
        Return the official SmartWebSocketV2 client.

        This method creates the client but does not connect or
        subscribe. The caller owns the streaming lifecycle.
        """
        try:
            from SmartApi.smartWebSocketV2 import SmartWebSocketV2
        except ImportError as exc:
            raise RuntimeError(
                "SmartWebSocketV2 is unavailable. "
                "Install/upgrade smartapi-python."
            ) from exc

        jwt_token = self.session.get("jwtToken")

        if not jwt_token or not self.feed_token:
            raise RuntimeError(
                "Angel One session is not ready for WebSocket use."
            )

        return SmartWebSocketV2(
            jwt_token,
            self.api_key,
            self.client_id,
            self.feed_token,
        )

    # ================================================================
    # HEALTH
    # ================================================================

    def health(self) -> dict[str, Any]:
        return {
            "engine": self.name,
            "version": self.version,
            "provider": self.name,
            "exchange": self.exchange,
            "symbol": self.symbol,
            "interval": self.interval,
            "authenticated": bool(
                self.session.get("jwtToken")
            ),
            "feed_token": bool(self.feed_token),
            "stream_client_available": bool(
                self.session.get("jwtToken")
                and self.feed_token
            ),
            "order_capability": False,
        }
