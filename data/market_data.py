"""Canonical market-data gateway for TradeOracle Apex.

Provider-agnostic market-data gateway.

Responsibilities:
- call the configured real market-data provider
- pass exchange/symbol/query parameters through unchanged
- normalize provider records
- validate timestamps and OHLC integrity
- validate market-data freshness
- expose latest/history/stream interfaces
- never generate synthetic/demo market prices

This module contains NO order-placement or GTT operations.
"""

from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any, Callable, Iterable, Optional


class MarketData:
    name = "MarketData"
    version = "2.2.0"
    capabilities = ["MARKET_DATA"]

    REQUIRED_FIELDS = (
        "symbol",
        "timestamp",
    )

    NUMERIC_FIELDS = (
        "open",
        "high",
        "low",
        "close",
        "price",
        "volume",
        "change",
        "change_pct",
        "volume_ratio",
    )

    def __init__(
        self,
        provider: Optional[Any] = None,
        max_age_seconds: int = 120,
    ) -> None:
        self.provider = provider
        self.max_age_seconds = max(
            1,
            int(max_age_seconds),
        )
        self.last_error: Optional[str] = None

    # ==================================================================
    # TIME
    # ==================================================================

    @staticmethod
    def utc_now() -> datetime:
        return datetime.now(timezone.utc)

    @classmethod
    def _timestamp(
        cls,
        value: Any,
    ) -> Optional[datetime]:

        if isinstance(value, datetime):
            dt = value

        elif isinstance(value, (int, float)) and not isinstance(value, bool):
            number = float(value)

            if not math.isfinite(number):
                return None

            # Unix milliseconds -> seconds.
            if number > 10_000_000_000:
                number /= 1000.0

            try:
                dt = datetime.fromtimestamp(
                    number,
                    tz=timezone.utc,
                )
            except (
                OverflowError,
                OSError,
                ValueError,
            ):
                return None

        elif isinstance(value, str):
            text = value.strip()

            if not text:
                return None

            text = text.replace(
                "Z",
                "+00:00",
            )

            try:
                dt = datetime.fromisoformat(text)
            except ValueError:
                return None

        else:
            return None

        if dt.tzinfo is None:
            dt = dt.replace(
                tzinfo=timezone.utc
            )

        return dt.astimezone(
            timezone.utc
        )

    # ==================================================================
    # NUMERIC NORMALIZATION
    # ==================================================================

    @staticmethod
    def _number(
        value: Any,
    ) -> Optional[float]:

        if value is None or isinstance(value, bool):
            return None

        try:
            number = float(value)
        except (
            TypeError,
            ValueError,
        ):
            return None

        if not math.isfinite(number):
            return None

        return number

    # ==================================================================
    # RECORD VALIDATION
    # ==================================================================

    @classmethod
    def _record_integrity_error(
        cls,
        row: dict[str, Any],
    ) -> Optional[str]:
        """Return an integrity reason without inventing missing values."""

        # Any supplied numeric field must be finite.
        for key in cls.NUMERIC_FIELDS:
            if key in row and row[key] is not None:
                if cls._number(row[key]) is None:
                    return f"invalid_numeric:{key}"

        price = cls._number(row.get("price"))
        close = cls._number(row.get("close"))
        open_price = cls._number(row.get("open"))
        high = cls._number(row.get("high"))
        low = cls._number(row.get("low"))
        volume = cls._number(row.get("volume"))

        # A supplied market price/close must be positive.
        if price is not None and price <= 0:
            return "non_positive_price"

        if close is not None and close <= 0:
            return "non_positive_close"

        if open_price is not None and open_price <= 0:
            return "non_positive_open"

        if high is not None and high <= 0:
            return "non_positive_high"

        if low is not None and low <= 0:
            return "non_positive_low"

        if volume is not None and volume < 0:
            return "negative_volume"

        # Validate OHLC relationships only when the required values exist.
        if (
            high is not None
            and low is not None
            and high < low
        ):
            return "high_below_low"

        if (
            open_price is not None
            and high is not None
            and low is not None
            and not low <= open_price <= high
        ):
            return "open_outside_range"

        if (
            close is not None
            and high is not None
            and low is not None
            and not low <= close <= high
        ):
            return "close_outside_range"

        return None

    # ==================================================================
    # RECORD NORMALIZATION
    # ==================================================================

    @classmethod
    def _normalize(
        cls,
        item: Any,
        symbol: Optional[str] = None,
    ) -> Optional[dict[str, Any]]:

        if not isinstance(item, dict):
            return None

        row = dict(item)

        resolved_symbol = (
            row.get("symbol")
            or row.get("ticker")
            or row.get("instrument")
            or symbol
        )

        if resolved_symbol is not None:
            row["symbol"] = str(
                resolved_symbol
            ).strip()

        timestamp = cls._timestamp(
            row.get("timestamp")
            or row.get("time")
            or row.get("datetime")
            or row.get("ts")
        )

        if (
            not row.get("symbol")
            or timestamp is None
        ):
            return None

        # --------------------------------------------------------------
        # COMMON PROVIDER ALIASES
        # --------------------------------------------------------------

        if row.get("price") is None:
            for key in (
                "last",
                "last_price",
                "ltp",
            ):
                if row.get(key) is not None:
                    row["price"] = row[key]
                    break

        # LTP records can legitimately use price as close.
        if (
            row.get("close") is None
            and row.get("price") is not None
        ):
            row["close"] = row["price"]

        if row.get("volume") is None:
            for key in (
                "vol",
                "trade_volume",
                "qty",
            ):
                if row.get(key) is not None:
                    row["volume"] = row[key]
                    break

        # --------------------------------------------------------------
        # NUMERIC NORMALIZATION
        # --------------------------------------------------------------

        for key in cls.NUMERIC_FIELDS:
            if key in row and row[key] is not None:
                number = cls._number(row[key])
                if number is None:
                    return None
                row[key] = number

        # --------------------------------------------------------------
        # CANONICAL METADATA
        # --------------------------------------------------------------

        row["timestamp"] = timestamp.isoformat()
        row["ingested_at"] = cls.utc_now().isoformat()

        row["data_type"] = str(
            row.get("data_type")
            or "market"
        )

        row["live"] = bool(
            row.get("live", False)
        )

        return row

    # ==================================================================
    # RECORD COLLECTION
    # ==================================================================

    @classmethod
    def _records(
        cls,
        raw: Any,
        symbol: Optional[str] = None,
    ) -> list[dict[str, Any]]:

        if raw is None:
            return []

        if (
            isinstance(raw, dict)
            and "records" in raw
        ):
            source_records = raw["records"]
        else:
            source_records = raw

        if isinstance(source_records, dict):
            source_records = [source_records]

        if not isinstance(source_records, Iterable):
            return []

        if isinstance(
            source_records,
            (str, bytes),
        ):
            return []

        normalized: list[dict[str, Any]] = []

        for item in source_records:
            row = cls._normalize(
                item,
                symbol,
            )

            if row is not None:
                normalized.append(row)

        normalized.sort(
            key=lambda x: (
                cls._timestamp(
                    x["timestamp"]
                )
                or datetime.min.replace(
                    tzinfo=timezone.utc
                )
            )
        )

        # Same symbol + timestamp is one market record.
        deduped: list[dict[str, Any]] = []
        seen: set[tuple[Any, Any]] = set()

        for row in normalized:
            key = (
                row.get("symbol"),
                row.get("timestamp"),
            )

            if key in seen:
                continue

            seen.add(key)
            deduped.append(row)

        return deduped

    # ==================================================================
    # PROVIDER CALL
    # ==================================================================

    def _call_provider(
        self,
        **kwargs: Any,
    ) -> Any:

        if self.provider is None:
            self.last_error = (
                "Market-data provider is not configured."
            )
            return None

        try:
            if callable(self.provider):
                return self.provider(**kwargs)

            fetch = getattr(
                self.provider,
                "fetch",
                None,
            )

            if callable(fetch):
                return fetch(**kwargs)

            self.last_error = (
                "Configured market-data provider "
                "does not expose a callable fetch() method."
            )
            return None

        except Exception as exc:
            self.last_error = (
                f"{type(exc).__name__}: {exc}"
            )
            return None

    # ==================================================================
    # FETCH
    # ==================================================================

    def fetch(
        self,
        symbol: Optional[str] = None,
        start: Any = None,
        end: Any = None,
        limit: Optional[int] = None,
        **kwargs: Any,
    ) -> dict[str, Any]:

        self.last_error = None

        raw = self._call_provider(
            symbol=symbol,
            start=start,
            end=end,
            limit=limit,
            **kwargs,
        )

        source = None

        if isinstance(raw, dict):
            source = raw.get("source")

        records = self._records(
            raw,
            symbol,
        )

        if source is None and records:
            source = records[-1].get("source")

        if limit:
            records = records[
                -max(
                    1,
                    int(limit),
                ):
            ]

        quality = self.quality(
            records
        )

        if self.last_error:
            quality["status"] = "ERROR"
            quality["fresh"] = False
            quality["error"] = self.last_error

        return {
            "records": records,
            "quality": quality,
            "source": (
                source
                or self._provider_name()
            ),
        }

    # ==================================================================
    # LATEST
    # ==================================================================

    def latest(
        self,
        symbol: Optional[str] = None,
        **kwargs: Any,
    ) -> dict[str, Any]:

        result = self.fetch(
            symbol=symbol,
            limit=1,
            **kwargs,
        )

        record = (
            result["records"][-1]
            if result["records"]
            else None
        )

        return {
            "record": record,
            "quality": result["quality"],
            "source": result["source"],
        }

    # ==================================================================
    # STREAM
    # ==================================================================

    def stream(
        self,
        symbol: Optional[str] = None,
        on_record: Optional[
            Callable[[dict[str, Any]], Any]
        ] = None,
        **kwargs: Any,
    ):
        """
        Normalize a provider-native stream when one exists.

        AngelOneProvider currently exposes stream_client() rather than
        a high-level stream() generator. This gateway therefore does not
        invent a streaming loop; callers that own SmartWebSocketV2 can
        normalize incoming records through normalize_record().
        """

        self.last_error = None

        if self.provider is None:
            return

        stream_fn = getattr(
            self.provider,
            "stream",
            None,
        )

        if not callable(stream_fn):
            return

        try:
            raw_stream = stream_fn(
                symbol=symbol,
                **kwargs,
            )

            for item in raw_stream or ():
                record = self._normalize(
                    item,
                    symbol,
                )

                if record is None:
                    continue

                quality = self.quality(
                    [record]
                )

                if not quality["fresh"]:
                    continue

                if on_record is not None:
                    on_record(record)

                yield record

        except Exception as exc:
            self.last_error = (
                f"{type(exc).__name__}: {exc}"
            )
            return

    @classmethod
    def normalize_record(
        cls,
        item: Any,
        symbol: Optional[str] = None,
    ) -> Optional[dict[str, Any]]:
        """Public normalization helper for WebSocket consumers."""
        return cls._normalize(
            item,
            symbol,
        )

    # ==================================================================
    # QUALITY VALIDATION
    # ==================================================================

    def quality(
        self,
        records: list[dict[str, Any]],
    ) -> dict[str, Any]:

        if not records:
            return {
                "status": "EMPTY",
                "count": 0,
                "fresh": False,
                "missing": list(
                    self.REQUIRED_FIELDS
                ),
                "invalid": [],
                "invalid_count": 0,
                "valid_count": 0,
                "age_seconds": None,
                "max_age_seconds": self.max_age_seconds,
            }

        now = self.utc_now()

        invalid: list[dict[str, Any]] = []
        ages: list[float] = []
        valid_count = 0

        for index, record in enumerate(records):

            missing = [
                field
                for field in self.REQUIRED_FIELDS
                if not record.get(field)
            ]

            if missing:
                invalid.append({
                    "index": index,
                    "missing": missing,
                })
                continue

            timestamp = self._timestamp(
                record.get("timestamp")
            )

            if timestamp is None:
                invalid.append({
                    "index": index,
                    "reason": "invalid_timestamp",
                })
                continue

            age = (
                now - timestamp
            ).total_seconds()

            if age < -5:
                invalid.append({
                    "index": index,
                    "reason": "future_timestamp",
                })
                continue

            integrity_error = (
                self._record_integrity_error(
                    record
                )
            )

            if integrity_error:
                invalid.append({
                    "index": index,
                    "reason": integrity_error,
                })
                continue

            ages.append(
                max(
                    0.0,
                    age,
                )
            )
            valid_count += 1

        # _records() sorts chronologically, so the last valid age is
        # the age of the newest valid record.
        latest_age = (
            ages[-1]
            if ages
            else None
        )

        has_invalid = bool(invalid)

        # IMPORTANT:
        # INVALID data is never considered fresh. This closes the
        # MarketData -> SignalGate safety gap present in the older version.
        fresh = (
            not has_invalid
            and latest_age is not None
            and latest_age <= self.max_age_seconds
        )

        if has_invalid:
            status = "INVALID"
        elif fresh:
            status = "OK"
        else:
            status = "STALE"

        return {
            "status": status,
            "count": len(records),
            "fresh": fresh,
            "missing": [],
            "invalid": invalid,
            "invalid_count": len(invalid),
            "valid_count": valid_count,
            "age_seconds": (
                round(
                    latest_age,
                    3,
                )
                if latest_age is not None
                else None
            ),
            "max_age_seconds": self.max_age_seconds,
        }

    # ==================================================================
    # PROVIDER NAME
    # ==================================================================

    def _provider_name(
        self,
    ) -> Optional[str]:

        if self.provider is None:
            return None

        if callable(self.provider):
            return getattr(
                self.provider,
                "__name__",
                str(self.provider),
            )

        return getattr(
            self.provider,
            "name",
            self.provider.__class__.__name__,
        )

    # ==================================================================
    # HEALTH
    # ==================================================================

    def health(
        self,
    ) -> dict[str, Any]:

        provider_health = None

        if self.provider is not None:
            health_fn = getattr(
                self.provider,
                "health",
                None,
            )

            if callable(health_fn):
                try:
                    provider_health = health_fn()
                except Exception as exc:
                    provider_health = {
                        "status": "ERROR",
                        "error": (
                            f"{type(exc).__name__}: "
                            f"{exc}"
                        ),
                    }

        return {
            "engine": self.name,
            "version": self.version,
            "provider_configured": (
                self.provider is not None
            ),
            "provider": self._provider_name(),
            "max_age_seconds": self.max_age_seconds,
            "last_error": self.last_error,
            "provider_health": provider_health,
        }
