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

from datetime import datetime, timezone
from typing import Any, Callable, Iterable, Optional


class MarketData:
    name = "MarketData"
    version = "2.1.0"
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
        provider: Optional[Callable] = None,
        max_age_seconds: int = 120,
    ):
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
        return datetime.now(
            timezone.utc
        )

    @classmethod
    def _timestamp(
        cls,
        value: Any,
    ) -> Optional[datetime]:

        if isinstance(
            value,
            datetime,
        ):

            dt = value

        elif isinstance(
            value,
            (int, float),
        ):

            number = float(
                value
            )

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

        elif isinstance(
            value,
            str,
        ):

            text = value.strip()

            if not text:
                return None

            text = text.replace(
                "Z",
                "+00:00",
            )

            try:

                dt = datetime.fromisoformat(
                    text
                )

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

        if value is None:
            return None

        if isinstance(
            value,
            bool,
        ):
            return None

        try:

            return float(
                value
            )

        except (
            TypeError,
            ValueError,
        ):

            return None

    # ==================================================================
    # RECORD NORMALIZATION
    # ==================================================================

    @classmethod
    def _normalize(
        cls,
        item: Any,
        symbol: Optional[str] = None,
    ) -> Optional[dict]:

        if not isinstance(
            item,
            dict,
        ):
            return None

        row = dict(
            item
        )

        # --------------------------------------------------------------
        # SYMBOL
        # --------------------------------------------------------------

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

        # --------------------------------------------------------------
        # TIMESTAMP
        # --------------------------------------------------------------

        timestamp = cls._timestamp(
            row.get("timestamp")
            or row.get("time")
            or row.get("datetime")
            or row.get("ts")
        )

        # Both symbol and timestamp are mandatory.
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

                    row["price"] = (
                        row[key]
                    )

                    break

        # LTP records can legitimately use price as close.
        if (
            row.get("close") is None
            and row.get("price") is not None
        ):

            row["close"] = (
                row["price"]
            )

        if row.get("volume") is None:

            for key in (
                "vol",
                "trade_volume",
                "qty",
            ):

                if row.get(key) is not None:

                    row["volume"] = (
                        row[key]
                    )

                    break

        # --------------------------------------------------------------
        # NUMERIC VALIDATION
        #
        # Never manufacture numeric values.
        # --------------------------------------------------------------

        for key in cls.NUMERIC_FIELDS:

            if (
                key in row
                and row[key] is not None
            ):

                number = cls._number(
                    row[key]
                )

                if number is None:
                    return None

                row[key] = number

        # --------------------------------------------------------------
        # CANONICAL METADATA
        # --------------------------------------------------------------

        row["timestamp"] = (
            timestamp.isoformat()
        )

        row["ingested_at"] = (
            cls.utc_now().isoformat()
        )

        row["data_type"] = str(
            row.get(
                "data_type"
            )
            or "market"
        )

        # Provider must explicitly identify live data.
        row["live"] = bool(
            row.get(
                "live",
                False,
            )
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
    ) -> list[dict]:

        if raw is None:
            return []

        # --------------------------------------------------------------
        # Provider may return:
        #
        # {
        #     "records": [...]
        # }
        #
        # or directly:
        #
        # [...]
        # --------------------------------------------------------------

        if (
            isinstance(raw, dict)
            and "records" in raw
        ):

            source_records = raw[
                "records"
            ]

        else:

            source_records = raw

        if isinstance(
            source_records,
            dict,
        ):

            source_records = [
                source_records
            ]

        if not isinstance(
            source_records,
            Iterable,
        ):

            return []

        if isinstance(
            source_records,
            (str, bytes),
        ):

            return []

        normalized: list[
            dict
        ] = []

        for item in source_records:

            row = cls._normalize(
                item,
                symbol,
            )

            if row is not None:

                normalized.append(
                    row
                )

        # --------------------------------------------------------------
        # CHRONOLOGICAL ORDER
        # --------------------------------------------------------------

        normalized.sort(
            key=lambda x:
            cls._timestamp(
                x["timestamp"]
            )
            or datetime.min.replace(
                tzinfo=timezone.utc
            )
        )

        # --------------------------------------------------------------
        # DEDUPLICATION
        #
        # Same symbol + same timestamp = same market record.
        # --------------------------------------------------------------

        deduped: list[
            dict
        ] = []

        seen = set()

        for row in normalized:

            key = (
                row.get("symbol"),
                row.get("timestamp"),
            )

            if key in seen:
                continue

            seen.add(
                key
            )

            deduped.append(
                row
            )

        return deduped

    # ==================================================================
    # PROVIDER CALL
    # ==================================================================

    def _call_provider(
        self,
        **kwargs,
    ):

        if self.provider is None:

            self.last_error = (
                "Market-data provider is not configured."
            )

            return None

        try:

            # ----------------------------------------------------------
            # Callable provider
            # ----------------------------------------------------------

            if callable(
                self.provider
            ):

                return self.provider(
                    **kwargs
                )

            # ----------------------------------------------------------
            # Standard provider contract
            # ----------------------------------------------------------

            fetch = getattr(
                self.provider,
                "fetch",
                None,
            )

            if callable(
                fetch
            ):

                return fetch(
                    **kwargs
                )

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
        **kwargs,
    ) -> dict:

        """
        Fetch live or historical market data.

        Important:
        All additional keyword arguments are passed unchanged
        to the provider.

        This allows:

            exchange="NSE"

        or:

            exchange="MCX"

        to reach the Angel One provider without the gateway
        hard-coding an exchange.
        """

        self.last_error = None

        # --------------------------------------------------------------
        # PROVIDER CALL
        # --------------------------------------------------------------

        raw = self._call_provider(
            symbol=symbol,
            start=start,
            end=end,
            limit=limit,
            **kwargs,
        )

        # --------------------------------------------------------------
        # SOURCE
        # --------------------------------------------------------------

        source = None

        if isinstance(
            raw,
            dict,
        ):

            source = raw.get(
                "source"
            )

        # --------------------------------------------------------------
        # NORMALIZE
        # --------------------------------------------------------------

        records = self._records(
            raw,
            symbol,
        )

        # --------------------------------------------------------------
        # LIMIT
        #
        # The provider may already apply the limit.
        # Applying it again here is safe.
        # --------------------------------------------------------------

        if limit:

            records = records[
                -max(
                    1,
                    int(limit),
                ):
            ]

        # --------------------------------------------------------------
        # QUALITY
        # --------------------------------------------------------------

        quality = self.quality(
            records
        )

        # --------------------------------------------------------------
        # PROVIDER ERROR
        # --------------------------------------------------------------

        if self.last_error:

            quality["status"] = (
                "ERROR"
            )

            quality["error"] = (
                self.last_error
            )

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
        **kwargs,
    ) -> dict:

        """
        Return the newest available market record.

        The provider decides whether this represents
        LTP/live data or another supported latest record.
        """

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

            "quality": result[
                "quality"
            ],

            "source": result[
                "source"
            ],
        }

    # ==================================================================
    # STREAM
    # ==================================================================

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

            # ----------------------------------------------------------
            # Native provider stream
            # ----------------------------------------------------------

            stream_fn = getattr(
                self.provider,
                "stream",
                None,
            )

            if callable(
                stream_fn
            ):

                raw_stream = stream_fn(
                    symbol=symbol,
                    **kwargs,
                )

            # ----------------------------------------------------------
            # Callable provider stream
            # ----------------------------------------------------------

            elif callable(
                self.provider
            ):

                raw_stream = self.provider(
                    symbol=symbol,
                    stream=True,
                    **kwargs,
                )

            else:

                return

            # ----------------------------------------------------------
            # NORMALIZE STREAM RECORDS
            # ----------------------------------------------------------

            for item in (
                raw_stream or ()
            ):

                record = self._normalize(
                    item,
                    symbol,
                )

                if record is None:
                    continue

                quality = self.quality(
                    [record]
                )

                if not quality[
                    "fresh"
                ]:

                    continue

                if on_record is not None:

                    on_record(
                        record
                    )

                yield record

        except Exception as exc:

            self.last_error = (
                f"{type(exc).__name__}: {exc}"
            )

            return

    # ==================================================================
    # QUALITY VALIDATION
    # ==================================================================

    def quality(
        self,
        records: list[dict],
    ) -> dict:

        """
        Validate freshness and basic market-data integrity.

        This method does not create or repair market values.
        """

        # --------------------------------------------------------------
        # EMPTY
        # --------------------------------------------------------------

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

                "max_age_seconds":
                    self.max_age_seconds,
            }

        now = self.utc_now()

        invalid: list[
            dict
        ] = []

        ages: list[
            float
        ] = []

        # --------------------------------------------------------------
        # RECORD VALIDATION
        # --------------------------------------------------------------

        for index, record in enumerate(
            records
        ):

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
                record.get(
                    "timestamp"
                )
            )

            if timestamp is None:

                invalid.append(
                    {
                        "index": index,
                        "reason":
                            "invalid_timestamp",
                    }
                )

                continue

            age = (
                now - timestamp
            ).total_seconds()

            # ----------------------------------------------------------
            # FUTURE DATA
            # ----------------------------------------------------------

            if age < -5:

                invalid.append(
                    {
                        "index": index,
                        "reason":
                            "future_timestamp",
                    }
                )

                continue

            ages.append(
                max(
                    0.0,
                    age,
                )
            )

            # ----------------------------------------------------------
            # OHLC VALIDATION
            # ----------------------------------------------------------

            high = self._number(
                record.get(
                    "high"
                )
            )

            low = self._number(
                record.get(
                    "low"
                )
            )

            open_price = self._number(
                record.get(
                    "open"
                )
            )

            close = self._number(
                record.get(
                    "close"
                )
            )

            # high >= low
            if (
                high is not None
                and low is not None
                and high < low
            ):

                invalid.append(
                    {
                        "index": index,
                        "reason":
                            "high_below_low",
                    }
                )

                continue

            # low <= open <= high
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

            # low <= close <= high
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

                continue

        # --------------------------------------------------------------
        # LATEST AGE
        # --------------------------------------------------------------

        latest_age = (
            max(ages)
            if False
            else (
                ages[-1]
                if ages
                else None
            )
        )

        # Records are already chronologically sorted
        # by _records(). Therefore ages[-1] corresponds
        # to the newest valid record.
        fresh = (
            latest_age is not None
            and latest_age
            <= self.max_age_seconds
        )

        # --------------------------------------------------------------
        # STATUS
        # --------------------------------------------------------------

        if invalid:

            status = "INVALID"

        elif fresh:

            status = "OK"

        else:

            status = "STALE"

        return {
            "status": status,

            "count": len(
                records
            ),

            "fresh": fresh,

            "missing": [],

            "invalid": invalid,

            "age_seconds": (
                round(
                    latest_age,
                    3,
                )
                if latest_age is not None
                else None
            ),

            "max_age_seconds":
                self.max_age_seconds,
        }

    # ==================================================================
    # PROVIDER NAME
    # ==================================================================

    def _provider_name(
        self,
    ) -> Optional[str]:

        if self.provider is None:

            return None

        if callable(
            self.provider
        ):

            return getattr(
                self.provider,
                "__name__",
                str(
                    self.provider
                ),
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
    ) -> dict:

        """
        Report gateway readiness.

        This method does not claim that the broker
        connection is currently healthy.

        Actual provider health is exposed separately
        when the provider implements health().
        """

        provider_health = None

        if self.provider is not None:

            health_fn = getattr(
                self.provider,
                "health",
                None,
            )

            if callable(
                health_fn
            ):

                try:

                    provider_health = (
                        health_fn()
                    )

                except Exception as exc:

                    provider_health = {
                        "status": "ERROR",
                        "error":
                            (
                                f"{type(exc).__name__}: "
                                f"{exc}"
                            ),
                    }

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

            "provider_health":
                provider_health,
            }
