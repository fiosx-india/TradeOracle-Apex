"""Canonical market-data gateway for TradeOracle Apex.

Provider-agnostic market-data gateway.
No synthetic/demo market prices are generated here.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable, Iterable, Optional


class MarketData:
    name = "MarketData"
    version = "2.1.0"
    capabilities = ["MARKET_DATA"]

    REQUIRED_FIELDS = ("symbol", "timestamp")

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
        provider: Optional[Callable] = None,
        max_age_seconds: int = 120,
    ):
        self.provider = provider
        self.max_age_seconds = max(1, int(max_age_seconds))
        self.last_error: Optional[str] = None

    @staticmethod
    def utc_now() -> datetime:
        return datetime.now(timezone.utc)

    @classmethod
    def _timestamp(cls, value: Any) -> Optional[datetime]:
        if isinstance(value, datetime):
            dt = value

        elif isinstance(value, (int, float)):
            number = float(value)

            # Unix milliseconds -> seconds
            if number > 10_000_000_000:
                number /= 1000.0

            try:
                dt = datetime.fromtimestamp(
                    number,
                    tz=timezone.utc,
                )
            except (OverflowError, OSError, ValueError):
                return None

        elif isinstance(value, str):
            text = value.strip()

            if not text:
                return None

            text = text.replace("Z", "+00:00")

            try:
                dt = datetime.fromisoformat(text)
            except ValueError:
                return None

        else:
            return None

        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)

        return dt.astimezone(timezone.utc)

    @staticmethod
    def _number(value: Any) -> Optional[float]:
        if value is None or isinstance(value, bool):
            return None

        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    @classmethod
    def _normalize(
        cls,
        item: Any,
        symbol: Optional[str] = None,
    ) -> Optional[dict]:

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
            row["symbol"] = str(resolved_symbol).strip()

        timestamp = cls._timestamp(
            row.get("timestamp")
            or row.get("time")
            or row.get("datetime")
            or row.get("ts")
        )

        if not row.get("symbol") or timestamp is None:
            return None

        # Common provider aliases.
        if row.get("price") is None:
            for key in ("last", "last_price", "ltp"):
                if row.get(key) is not None:
                    row["price"] = row[key]
                    break

        if row.get("close") is None and row.get("price") is not None:
            row["close"] = row["price"]

        if row.get("volume") is None:
            for key in ("vol", "trade_volume", "qty"):
                if row.get(key) is not None:
                    row["volume"] = row[key]
                    break

        # Validate numeric fields without inventing values.
        for key in cls.NUMERIC_FIELDS:
            if key in row and row[key] is not None:
                number = cls._number(row[key])

                if number is None:
                    return None

                row[key] = number

        row["timestamp"] = timestamp.isoformat()
        row["ingested_at"] = cls.utc_now().isoformat()
        row["data_type"] = str(
            row.get("data_type") or "market"
        )

        # Provider must explicitly identify live data.
        row["live"] = bool(row.get("live", False))

        return row

    @classmethod
    def _records(
        cls,
        raw: Any,
        symbol: Optional[str] = None,
    ) -> list[dict]:

        if raw is None:
            return []

        if isinstance(raw, dict) and "records" in raw:
            source_records = raw["records"]
        else:
            source_records = raw

        if isinstance(source_records, dict):
            source_records = [source_records]

        if not isinstance(source_records, Iterable):
            return []

        if isinstance(source_records, (str, bytes)):
            return []

        normalized = []

        for item in source_records:
            row = cls._normalize(item, symbol)

            if row is not None:
                normalized.append(row)

        normalized.sort(
            key=lambda x:
                cls._timestamp(x["timestamp"])
                or datetime.min.replace(tzinfo=timezone.utc)
        )

        # Remove duplicate symbol/timestamp records.
        deduped = []
        seen = set()

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

    def _call_provider(self, **kwargs):

        if self.provider is None:
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

            return None

        except Exception as exc:
            self.last_error = (
                f"{type(exc).__name__}: {exc}"
            )

            return None

    def fetch(
        self,
        symbol: Optional[str] = None,
        start: Any = None,
        end: Any = None,
        limit: Optional[int] = None,
        **kwargs,
    ) -> dict:

        """
        Fetch recent/historical market data.

        No demo/fallback records are generated.
        """

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

        if limit:
            records = records[
                -max(1, int(limit)):
            ]

        quality = self.quality(records)

        if self.last_error:
            quality["status"] = "ERROR"
            quality["error"] = self.last_error

        return {
            "records": records,
            "quality": quality,
            "source": (
                source
                or self._provider_name()
            ),
        }

    def latest(
        self,
        symbol: Optional[str] = None,
        **kwargs,
    ) -> dict:

        """Return the newest available market record."""

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

    def stream(
        self,
        symbol: Optional[str] = None,
        on_record: Optional[
            Callable[[dict], Any]
        ] = None,
        **kwargs,
    ):

        """
        Consume a real-time provider stream.

        The provider must expose:

            provider.stream(...)

        or support:

            provider(..., stream=True)

        No synthetic market records are generated.
        """

        self.last_error = None

        try:
            if self.provider is None:
                return

            stream_fn = getattr(
                self.provider,
                "stream",
                None,
            )

            if callable(stream_fn):
                raw_stream = stream_fn(
                    symbol=symbol,
                    **kwargs,
                )

            elif callable(self.provider):
                raw_stream = self.provider(
                    symbol=symbol,
                    stream=True,
                    **kwargs,
                )

            else:
                return

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

    def quality(
        self,
        records: list[dict],
    ) -> dict:

        """
        Validate freshness and basic market-data integrity.
        """

        if not records:
            return {
                "status": "EMPTY",
                "count": 0,
                "fresh": False,
                "missing": list(
                    self.REQUIRED_FIELDS
                ),
                "invalid": [],
                "age_seconds": None,
            }

        now = self.utc_now()

        invalid = []
        ages = []

        for index, record in enumerate(records):

            missing = [
                field
                for field in self.REQUIRED_FIELDS
                if not record.get(field)
            ]

            if missing:
                invalid.append(
                    {
                        "index": index,
                        "missing": missing,
                    }
                )
                continue

            timestamp = self._timestamp(
                record.get("timestamp")
            )

            if timestamp is None:
                invalid.append(
                    {
                        "index": index,
                        "reason": "invalid_timestamp",
                    }
                )
                continue

            age = (
                now - timestamp
            ).total_seconds()

            # Reject future-dated data.
            if age < -5:
                invalid.append(
                    {
                        "index": index,
                        "reason": "future_timestamp",
                    }
                )
                continue

            ages.append(
                max(0.0, age)
            )

            high = self._number(
                record.get("high")
            )

            low = self._number(
                record.get("low")
            )

            open_price = self._number(
                record.get("open")
            )

            close = self._number(
                record.get("close")
            )

            if (
                high is not None
                and low is not None
                and high < low
            ):
                invalid.append(
                    {
                        "index": index,
                        "reason": "high_below_low",
                    }
                )
                continue

            if (
                open_price is not None
                and high is not None
                and low is not None
                and not (
                    low
                    <= open_price
                    <= high
                )
            ):
                invalid.append(
                    {
                        "index": index,
                        "reason":
                            "open_outside_range",
                    }
                )
                continue

            if (
                close is not None
                and high is not None
                and low is not None
                and not (
                    low
                    <= close
                    <= high
                )
            ):
                invalid.append(
                    {
                        "index": index,
                        "reason":
                            "close_outside_range",
                    }
                )

        latest_age = (
            ages[-1]
            if ages
            else None
        )

        fresh = (
            latest_age is not None
            and latest_age
            <= self.max_age_seconds
        )

        if invalid:
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
            "age_seconds": (
                round(latest_age, 3)
                if latest_age is not None
                else None
            ),
            "max_age_seconds":
                self.max_age_seconds,
        }

    def _provider_name(self) -> Optional[str]:

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

    def health(self) -> dict:

        """
        Report gateway readiness.

        This does NOT claim that a real provider is connected.
        """

        return {
            "engine": self.name,
            "version": self.version,
            "provider_configured":
                self.provider is not None,
            "provider":
                self._provider_name(),
            "max_age_seconds":
                self.max_age_seconds,
            "last_error":
                self.last_error,
        }
