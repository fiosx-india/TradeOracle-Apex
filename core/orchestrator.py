"""TradeOracle Apex central runtime orchestrator.

Responsibilities
----------------
1. Discover first-party and incoming engines.
2. Validate and contract-test engines before registration.
3. Acquire canonical market data through MarketData.
4. Build one shared, horizon-neutral base MarketContext.
5. Optionally enrich the base context once with secondary data.
6. Create independent contexts for the configured prediction horizons.
7. Evaluate each horizon independently through ApexMasterBrain.
8. Return per-horizon results without fabricating market data.

Architecture rules
------------------
- Prediction horizons are 5, 15, 30 and 60 minutes.
- One MarketContext represents one prediction horizon during evaluation.
- Angel One candle interval is independent of prediction horizons.
- Market data is fetched once for a multi-horizon run.
- No synthetic/current timestamp is created when market data is empty.
- Signal gating remains owned by DecisionEngine -> SignalGate.
- This file contains no order-placement or GTT logic.
"""

from __future__ import annotations

import copy
import importlib
import inspect
import pkgutil

from typing import Any, Callable, Iterable, Optional

try:
    from config import (
        INCOMING_DIR,
        LIVE_DATA_MAX_AGE_SECONDS,
        PREDICTION_HORIZONS_MINUTES,
    )
except ImportError:
    INCOMING_DIR = "incoming"
    LIVE_DATA_MAX_AGE_SECONDS = 120
    PREDICTION_HORIZONS_MINUTES = (
        5,
        15,
        30,
        60,
    )

from .capability_router import CapabilityRouter
from .market_context import MarketContext
from .master_brain import ApexMasterBrain
from .system_registry import SystemRegistry

from data.market_data import MarketData

from plugins.plugin_benchmark import PluginBenchmark
from plugins.plugin_loader import PluginLoader
from plugins.plugin_validator import PluginValidator


# ---------------------------------------------------------------------------
# OPTIONAL CONTEXT ENRICHMENT
# ---------------------------------------------------------------------------

try:
    from data.context_enricher import MarketContextEnricher
except ImportError:
    MarketContextEnricher = None


# ---------------------------------------------------------------------------
# CANONICAL HORIZONS
# ---------------------------------------------------------------------------
#
# config.py is authoritative for runtime configuration, but this orchestrator
# deliberately protects the architecture from accidental horizon expansion.
# ---------------------------------------------------------------------------

SUPPORTED_HORIZONS = (
    5,
    15,
    30,
    60,
)

try:
    _configured_horizons = tuple(
        sorted(
            {
                int(value)
                for value in PREDICTION_HORIZONS_MINUTES
            }
        )
    )
except (
    TypeError,
    ValueError,
):
    _configured_horizons = SUPPORTED_HORIZONS

if _configured_horizons != SUPPORTED_HORIZONS:
    raise ValueError(
        "TradeOracle Apex requires exactly these prediction horizons: "
        "5, 15, 30 and 60 minutes."
    )


# ---------------------------------------------------------------------------
# FIRST-PARTY ENGINE PACKAGES
# ---------------------------------------------------------------------------

BUILTIN_PACKAGES = (
    "research",
    "prediction",
    "universe",
    "commodities",
)


# ---------------------------------------------------------------------------
# FAILED ENGINE WRAPPER
# ---------------------------------------------------------------------------

class _FailedEngine:
    """Represent an engine that failed during construction."""

    def __init__(
        self,
        name: str,
        error: Exception,
    ) -> None:
        self.name = name
        self.error = error
        self.capabilities = ["FAILED"]

    def self_test(self) -> bool:
        return False

    def analyze(
        self,
        context: Any,
    ) -> dict[str, Any]:
        raise RuntimeError(
            "Engine initialization failed: "
            f"{type(self.error).__name__}: "
            f"{self.error}"
        )


# ---------------------------------------------------------------------------
# ORCHESTRATOR
# ---------------------------------------------------------------------------

class ApexOrchestrator:
    """Single orchestration layer for the complete Apex runtime."""

    name = "ApexOrchestrator"
    version = "2.4.0"

    def __init__(
        self,
        incoming: str = INCOMING_DIR,
        market_data: Optional[MarketData] = None,
        market_provider: Optional[Callable[..., Any]] = None,
        max_age_seconds: int = LIVE_DATA_MAX_AGE_SECONDS,
        context_enricher: Optional[Any] = None,
    ) -> None:
        self.incoming = incoming

        self.registry = SystemRegistry()

        self.router = CapabilityRouter(
            self.registry
        )

        self.validator = PluginValidator()
        self.benchmark = PluginBenchmark()

        self.market_data = (
            market_data
            if market_data is not None
            else MarketData(
                provider=market_provider,
                max_age_seconds=max_age_seconds,
            )
        )

        self.brain = ApexMasterBrain(
            registry=self.registry,
            router=self.router,
        )

        # Optional secondary context layer.
        if context_enricher is not None:
            self.context_enricher = context_enricher

        elif MarketContextEnricher is not None:
            try:
                self.context_enricher = (
                    MarketContextEnricher()
                )
            except Exception:
                self.context_enricher = None

        else:
            self.context_enricher = None

    # ==================================================================
    # HORIZON HELPERS
    # ==================================================================

    @staticmethod
    def _normalize_horizons(
        horizon_minutes: Optional[int] = None,
        horizons_minutes: Optional[Any] = None,
    ) -> tuple[int, ...]:
        """
        Resolve requested prediction horizons.

        Priority:
            1. horizons_minutes
            2. horizon_minutes
            3. config.PREDICTION_HORIZONS_MINUTES

        Examples:
            horizon_minutes=15
            horizons_minutes=(5, 15, 30, 60)
        """

        if horizons_minutes is not None:

            if isinstance(
                horizons_minutes,
                bool,
            ):
                raise ValueError(
                    "horizons_minutes must be an integer "
                    "or iterable of integers."
                )

            if isinstance(
                horizons_minutes,
                int,
            ):
                values = [
                    horizons_minutes
                ]
            else:
                try:
                    values = list(
                        horizons_minutes
                    )
                except TypeError as exc:
                    raise ValueError(
                        "horizons_minutes must be an integer "
                        "or iterable of integers."
                    ) from exc

        elif horizon_minutes is not None:

            if isinstance(
                horizon_minutes,
                bool,
            ):
                raise ValueError(
                    "horizon_minutes must be an integer."
                )

            values = [
                horizon_minutes
            ]

        else:
            values = list(
                PREDICTION_HORIZONS_MINUTES
            )

        normalized: list[int] = []

        for value in values:

            if isinstance(
                value,
                bool,
            ):
                raise ValueError(
                    "Prediction horizon must be an integer."
                )

            try:
                horizon = int(
                    value
                )
            except (
                TypeError,
                ValueError,
            ) as exc:
                raise ValueError(
                    "Prediction horizon must be an integer."
                ) from exc

            if horizon not in SUPPORTED_HORIZONS:
                raise ValueError(
                    "Unsupported prediction horizon: "
                    f"{horizon}. Supported horizons: "
                    f"{SUPPORTED_HORIZONS}"
                )

            if horizon not in normalized:
                normalized.append(
                    horizon
                )

        if not normalized:
            raise ValueError(
                "At least one prediction horizon is required."
            )

        return tuple(
            sorted(
                normalized
            )
        )

    # ==================================================================
    # ENGINE DISCOVERY
    # ==================================================================

    @staticmethod
    def _looks_like_engine(
        obj: Any,
    ) -> bool:
        if not inspect.isclass(obj):
            return False

        if obj.__module__ == "builtins":
            return False

        name = getattr(
            obj,
            "name",
            None,
        )

        capabilities = getattr(
            obj,
            "capabilities",
            None,
        )

        return bool(
            isinstance(
                name,
                str,
            )
            and name.strip()
            and isinstance(
                capabilities,
                (
                    list,
                    tuple,
                    set,
                    frozenset,
                ),
            )
            and capabilities
        )

    def _discover_builtin_engines(
        self,
    ) -> list[tuple[Any, str]]:
        """Discover first-party engine classes without hard-coding filenames."""

        discovered: list[
            tuple[Any, str]
        ] = []

        seen: set[str] = set()

        for package_name in BUILTIN_PACKAGES:

            try:
                package = importlib.import_module(
                    package_name
                )
            except Exception:
                continue

            package_path = getattr(
                package,
                "__path__",
                None,
            )

            if not package_path:
                continue

            module_names = [
                package_name
            ]

            try:
                package_modules = (
                    pkgutil.walk_packages(
                        package_path,
                        prefix=(
                            f"{package_name}."
                        ),
                    )
                )

                for module_info in package_modules:

                    if not module_info.ispkg:
                        module_names.append(
                            module_info.name
                        )

            except Exception:
                pass

            for module_name in module_names:

                try:
                    module = importlib.import_module(
                        module_name
                    )
                except Exception:
                    continue

                for _, obj in inspect.getmembers(
                    module,
                    inspect.isclass,
                ):

                    # Only classes actually defined in the module.
                    if (
                        obj.__module__
                        != module.__name__
                    ):
                        continue

                    if not self._looks_like_engine(
                        obj
                    ):
                        continue

                    key = (
                        f"{obj.__module__}."
                        f"{obj.__name__}"
                    )

                    if key in seen:
                        continue

                    seen.add(
                        key
                    )

                    try:
                        engine = obj()

                        discovered.append(
                            (
                                engine,
                                f"builtin:{key}",
                            )
                        )

                    except Exception as exc:

                        discovered.append(
                            (
                                _FailedEngine(
                                    name=getattr(
                                        obj,
                                        "name",
                                        obj.__name__,
                                    ),
                                    error=exc,
                                ),
                                f"builtin:{key}",
                            )
                        )

        return discovered

    # ==================================================================
    # VALIDATE / BENCHMARK / REGISTER
    # ==================================================================

    @staticmethod
    def _benchmark_passed(
        benchmark: Any,
    ) -> bool:
        """
        Normalize benchmark implementations.

        Current production contract returns:
            {"passed": bool, ...}

        Older benchmark implementations may return only status/pending data.
        They are not treated as passed unless they explicitly say so.
        """

        if not isinstance(
            benchmark,
            dict,
        ):
            return False

        return bool(
            benchmark.get(
                "passed",
                False,
            )
        )

    def _register_engine(
        self,
        engine: Any,
        source_file: str,
    ) -> dict[str, Any]:

        name = getattr(
            engine,
            "name",
            source_file,
        )

        # --------------------------------------------------------------
        # VALIDATION
        # --------------------------------------------------------------

        try:
            validation = (
                self.validator.validate(
                    engine
                )
            )

        except Exception as exc:
            return {
                "stage": "VALIDATION",
                "status": "ERROR",
                "name": name,
                "file": source_file,
                "errors": [
                    f"{type(exc).__name__}: {exc}"
                ],
            }

        if not isinstance(
            validation,
            dict,
        ):
            return {
                "stage": "VALIDATION",
                "status": "ERROR",
                "name": name,
                "file": source_file,
                "errors": [
                    "PluginValidator returned a non-dict result."
                ],
            }

        if not validation.get(
            "valid",
            False,
        ):
            return {
                "stage": "VALIDATION",
                "status": "REJECTED",
                "name": name,
                "file": source_file,
                "errors": validation.get(
                    "errors",
                    [],
                ),
                "warnings": validation.get(
                    "warnings",
                    [],
                ),
            }

        # --------------------------------------------------------------
        # BENCHMARK
        # --------------------------------------------------------------

        try:
            benchmark = (
                self.benchmark.benchmark(
                    engine
                )
            )

        except Exception as exc:
            return {
                "stage": "BENCHMARK",
                "status": "ERROR",
                "name": name,
                "file": source_file,
                "errors": [
                    f"{type(exc).__name__}: {exc}"
                ],
            }

        if not self._benchmark_passed(
            benchmark
        ):
            errors = []

            if isinstance(
                benchmark,
                dict,
            ):
                errors = benchmark.get(
                    "errors",
                    [],
                )

            return {
                "stage": "BENCHMARK",
                "status": "REJECTED",
                "name": name,
                "file": source_file,
                "errors": errors,
                "benchmark": benchmark,
            }

        # --------------------------------------------------------------
        # REGISTRATION
        # --------------------------------------------------------------

        try:
            self.registry.register(
                engine,
                benchmark=benchmark,
                source_file=source_file,
            )

        except TypeError:
            # Backward-compatible fallback for an older registry that
            # still exposes register(engine) only.
            try:
                self.registry.register(
                    engine
                )
            except Exception as exc:
                return {
                    "stage": "REGISTRATION",
                    "status": "ERROR",
                    "name": name,
                    "file": source_file,
                    "errors": [
                        f"{type(exc).__name__}: {exc}"
                    ],
                    "benchmark": benchmark,
                }

        except Exception as exc:
            return {
                "stage": "REGISTRATION",
                "status": "ERROR",
                "name": name,
                "file": source_file,
                "errors": [
                    f"{type(exc).__name__}: {exc}"
                ],
                "benchmark": benchmark,
            }

        return {
            "stage": "REGISTRATION",
            "status": "ACTIVE",
            "name": name,
            "file": source_file,
            "benchmark": benchmark,
        }

    def discover_validate_benchmark_register(
        self,
    ) -> list[dict[str, Any]]:

        report: list[
            dict[str, Any]
        ] = []

        # --------------------------------------------------------------
        # FIRST-PARTY ENGINES
        # --------------------------------------------------------------

        for (
            engine,
            source_file,
        ) in self._discover_builtin_engines():

            report.append(
                self._register_engine(
                    engine,
                    source_file,
                )
            )

        # --------------------------------------------------------------
        # USER-SUPPLIED ENGINES
        # --------------------------------------------------------------

        loader = PluginLoader(
            self.incoming
        )

        try:
            items = loader.discover()
        except Exception as exc:
            items = [
                {
                    "loaded": False,
                    "file": self.incoming,
                    "errors": [
                        (
                            f"{type(exc).__name__}: "
                            f"{exc}"
                        )
                    ],
                }
            ]

        for item in items:

            if not isinstance(
                item,
                dict,
            ):
                report.append(
                    {
                        "stage": "LOADER",
                        "status": "ERROR",
                        "file": self.incoming,
                        "errors": [
                            "Plugin loader returned a non-dict item."
                        ],
                    }
                )
                continue

            if not item.get(
                "loaded",
                False,
            ):
                report.append(
                    item
                )
                continue

            engine = item.get(
                "engine"
            )

            if engine is None:
                report.append(
                    {
                        "stage": "LOADER",
                        "status": "ERROR",
                        "file": item.get(
                            "file",
                            self.incoming,
                        ),
                        "errors": [
                            (
                                "Plugin loader returned "
                                "loaded=True without an engine."
                            )
                        ],
                    }
                )
                continue

            report.append(
                self._register_engine(
                    engine,
                    item.get(
                        "file",
                        self.incoming,
                    ),
                )
            )

        self.brain.attach_registry(
            self.registry,
            self.router,
        )

        return report

    # ==================================================================
    # MARKET DATA NORMALIZATION
    # ==================================================================

    @staticmethod
    def _records_to_data(
        records: Iterable[
            dict[str, Any]
        ],
    ) -> dict[str, Any]:
        """
        Convert canonical MarketData records into the series-oriented
        structure expected by existing engines.

        Unknown provider fields are not fabricated.
        """

        if not records:
            return {}

        ordered = sorted(
            [
                dict(row)
                for row in records
                if isinstance(
                    row,
                    dict,
                )
            ],
            key=lambda row: str(
                row.get(
                    "timestamp",
                    "",
                )
            ),
        )

        if not ordered:
            return {}

        data: dict[
            str,
            Any,
        ] = {}

        aliases = {
            "open": (
                "open",
                "Open",
            ),
            "high": (
                "high",
                "High",
            ),
            "low": (
                "low",
                "Low",
            ),
            "close": (
                "close",
                "Close",
                "price",
                "last_price",
            ),
            "volume": (
                "volume",
                "Volume",
                "trade_volume",
            ),
        }

        for target, names in aliases.items():

            values: list[
                float
            ] = []

            for row in ordered:

                value = next(
                    (
                        row.get(name)
                        for name in names
                        if row.get(name) is not None
                    ),
                    None,
                )

                try:
                    number = float(
                        value
                    )
                except (
                    TypeError,
                    ValueError,
                ):
                    continue

                if number != number:
                    continue

                values.append(
                    number
                )

            if values:
                data[target] = values

        timestamps = [
            row.get(
                "timestamp"
            )
            for row in ordered
            if row.get(
                "timestamp"
            )
        ]

        if timestamps:
            data["timestamps"] = timestamps

        latest = ordered[-1]

        for key in (
            "symbol",
            "price",
            "change",
            "change_pct",
            "exchange",
            "symbol_token",
            "source",
            "live",
            "data_type",
            "ingested_at",
        ):
            if key in latest:
                data[key] = latest[key]

        return data

    # ==================================================================
    # BASE MARKET CONTEXT
    # ==================================================================

    def build_market_context(
        self,
        symbol: str,
        *,
        sector: str = "",
        start: Any = None,
        end: Any = None,
        limit: int = 120,
        horizon_minutes: int = 5,
        **market_kwargs: Any,
    ) -> MarketContext:
        """
        Fetch canonical market data once and build the shared,
        horizon-neutral base MarketContext.

        The horizon argument is retained for backward compatibility.
        Multi-horizon runtime evaluation replaces it with independent
        cloned contexts before ApexMasterBrain.evaluate().
        """

        fetched = self.market_data.fetch(
            symbol=symbol,
            start=start,
            end=end,
            limit=limit,
            **market_kwargs,
        )

        if not isinstance(
            fetched,
            dict,
        ):
            fetched = {
                "records": (
                    fetched
                    if isinstance(
                        fetched,
                        list,
                    )
                    else []
                ),
                "quality": {},
                "source": None,
            }

        records = (
            fetched.get(
                "records"
            )
            or []
        )

        quality = (
            fetched.get(
                "quality"
            )
            or {}
        )

        if not isinstance(
            quality,
            dict,
        ):
            quality = {}

        data = self._records_to_data(
            records
        )

        # Keep quality in both locations:
        # - data: backward compatibility for existing engines
        # - context attribute: canonical MasterBrain -> SignalGate contract
        data[
            "market_data_quality"
        ] = copy.deepcopy(
            quality
        )

        data[
            "market_data_source"
        ] = fetched.get(
            "source"
        )

        # --------------------------------------------------------------
        # NO SYNTHETIC MARKET TIMESTAMP
        # --------------------------------------------------------------

        latest_timestamp = None

        if records:

            latest = records[-1]

            if isinstance(
                latest,
                dict,
            ):
                latest_timestamp = latest.get(
                    "timestamp"
                )

        # MarketContext requires a string. An empty value is explicit:
        # no market record exists, therefore no market timestamp exists.
        context_timestamp = (
            str(
                latest_timestamp
            )
            if latest_timestamp
            else ""
        )

        context = MarketContext(
            timestamp=context_timestamp,
            symbol=symbol or "",
            sector=sector or "",
            horizon_minutes=int(
                horizon_minutes
            ),
            data=data,
            evidence=[],
        )

        context.market_data_quality = (
            copy.deepcopy(
                quality
            )
        )

        context.market_data_source = (
            fetched.get(
                "source"
            )
        )

        # --------------------------------------------------------------
        # OPTIONAL SECONDARY ENRICHMENT
        # --------------------------------------------------------------

        if (
            self.context_enricher is not None
            and records
        ):
            try:
                self.context_enricher.enrich(
                    context
                )
            except Exception as exc:
                data[
                    "context_enrichment_error"
                ] = (
                    f"{type(exc).__name__}: "
                    f"{exc}"
                )

        return context

    # ==================================================================
    # HORIZON CONTEXT CLONING
    # ==================================================================

    @staticmethod
    def _clone_for_horizon(
        base_context: MarketContext,
        horizon: int,
    ) -> MarketContext:
        """
        Create a completely independent context for one horizon.

        Shared:
            canonical market snapshot

        Independent:
            data structure
            evidence
            horizon
            staged MasterBrain outputs
        """

        context = MarketContext(
            timestamp=(
                getattr(
                    base_context,
                    "timestamp",
                    "",
                )
            ),
            symbol=(
                getattr(
                    base_context,
                    "symbol",
                    "",
                )
            ),
            sector=(
                getattr(
                    base_context,
                    "sector",
                    "",
                )
            ),
            horizon_minutes=int(
                horizon
            ),
            data=copy.deepcopy(
                getattr(
                    base_context,
                    "data",
                    {},
                )
            ),
            evidence=[],
        )

        context.market_data_quality = (
            copy.deepcopy(
                getattr(
                    base_context,
                    "market_data_quality",
                    {},
                )
            )
        )

        context.market_data_source = (
            getattr(
                base_context,
                "market_data_source",
                None,
            )
        )

        return context

    # ==================================================================
    # MARKET RESULT
    # ==================================================================

    @staticmethod
    def _market_result(
        context: MarketContext,
    ) -> dict[str, Any]:

        context_data = getattr(
            context,
            "data",
            {},
        )

        if not isinstance(
            context_data,
            dict,
        ):
            context_data = {}

        quality = getattr(
            context,
            "market_data_quality",
            None,
        )

        if not isinstance(
            quality,
            dict,
        ):
            quality = context_data.get(
                "market_data_quality",
                {},
            )

        if not isinstance(
            quality,
            dict,
        ):
            quality = {}

        return {
            "quality": copy.deepcopy(
                quality
            ),

            "symbol": getattr(
                context,
                "symbol",
                "",
            ),

            "timestamp": getattr(
                context,
                "timestamp",
                "",
            ),

            "records": quality.get(
                "count",
                0,
            ),

            "fresh": bool(
                quality.get(
                    "fresh",
                    False,
                )
            ),

            "status": quality.get(
                "status",
                "UNKNOWN",
            ),

            "source": (
                getattr(
                    context,
                    "market_data_source",
                    None,
                )
                or context_data.get(
                    "market_data_source"
                )
            ),
        }

    # ==================================================================
    # PUBLIC RUNTIME
    # ==================================================================

    def run(
        self,
        context: Optional[
            MarketContext
        ] = None,
        *,
        symbol: Optional[str] = None,
        sector: str = "",
        start: Any = None,
        end: Any = None,
        limit: int = 120,
        horizon_minutes: Optional[int] = None,
        horizons_minutes: Optional[Any] = None,
        **market_kwargs: Any,
    ) -> dict[str, Any]:
        """
        Run Apex.

        Single horizon:
            run(
                symbol="NIFTY",
                horizon_minutes=15,
            )

        Multi-horizon:
            run(
                symbol="NIFTY",
                horizons_minutes=(5, 15, 30, 60),
            )

        Market data is fetched once.
        Each horizon gets an independent MarketContext.
        """

        # --------------------------------------------------------------
        # 1. RESOLVE HORIZONS
        # --------------------------------------------------------------

        horizons = self._normalize_horizons(
            horizon_minutes=horizon_minutes,
            horizons_minutes=horizons_minutes,
        )

        # --------------------------------------------------------------
        # 2. DISCOVER / VALIDATE / BENCHMARK / REGISTER
        # --------------------------------------------------------------

        report = (
            self.discover_validate_benchmark_register()
        )

        try:
            registered_engines = list(
                self.registry.all()
            )
        except Exception:
            registered_engines = []

        try:
            registry_report = (
                self.registry.report()
            )
        except Exception as exc:
            registry_report = {
                "status": "ERROR",
                "error": (
                    f"{type(exc).__name__}: "
                    f"{exc}"
                ),
            }

        result: dict[
            str,
            Any,
        ] = {
            "status": "READY",

            "pipeline": [
                "DISCOVER",
                "VALIDATE",
                "BENCHMARK",
                "REGISTER",
                "MARKET_DATA",
                "MARKET_CONTEXT",
                "MULTI_HORIZON",
                "MASTER_BRAIN",
            ],

            "supported_horizons": (
                SUPPORTED_HORIZONS
            ),

            "requested_horizons": (
                horizons
            ),

            "registered_engines": (
                registered_engines
            ),

            "registry_report": (
                registry_report
            ),

            "report": report,

            "market_data": {
                "provider_connected": (
                    self.market_data.provider
                    is not None
                ),

                "max_age_seconds": (
                    self.market_data.max_age_seconds
                ),
            },
        }

        # --------------------------------------------------------------
        # 3. BASE CONTEXT
        # --------------------------------------------------------------

        if context is None:

            if not symbol:

                result[
                    "status"
                ] = "WAITING_FOR_CONTEXT"

                return result

            base_context = (
                self.build_market_context(
                    symbol,
                    sector=sector,
                    start=start,
                    end=end,
                    limit=limit,
                    # Compatibility only. This value is replaced during
                    # per-horizon cloning below.
                    horizon_minutes=horizons[0],
                    **market_kwargs,
                )
            )

        else:
            base_context = context

        # --------------------------------------------------------------
        # 4. EVALUATE EACH HORIZON INDEPENDENTLY
        # --------------------------------------------------------------

        horizon_results: dict[
            str,
            dict[str, Any],
        ] = {}

        for horizon in horizons:

            horizon_context = (
                self._clone_for_horizon(
                    base_context,
                    horizon,
                )
            )

            try:

                brain_result = (
                    self.brain.evaluate(
                        horizon_context
                    )
                )

                horizon_results[
                    str(horizon)
                ] = {
                    "horizon_minutes": (
                        horizon
                    ),

                    "master_brain": (
                        brain_result
                    ),

                    "market_data": (
                        self._market_result(
                            horizon_context
                        )
                    ),

                    "status": "EVALUATED",
                }

            except Exception as exc:

                horizon_results[
                    str(horizon)
                ] = {
                    "horizon_minutes": (
                        horizon
                    ),

                    "status": "ERROR",

                    "error": (
                        f"{type(exc).__name__}: "
                        f"{exc}"
                    ),
                }

        # --------------------------------------------------------------
        # 5. MULTI-HORIZON OUTPUT
        # --------------------------------------------------------------

        result[
            "horizons"
        ] = horizon_results

        # --------------------------------------------------------------
        # 6. BACKWARD COMPATIBILITY
        # --------------------------------------------------------------

        primary_horizon = horizons[0]

        primary_result = (
            horizon_results.get(
                str(
                    primary_horizon
                )
            )
        )

        if primary_result is not None:

            result[
                "master_brain"
            ] = primary_result.get(
                "master_brain"
            )

            result[
                "market_data"
            ].update(
                primary_result.get(
                    "market_data",
                    {},
                )
            )

        # --------------------------------------------------------------
        # 7. CONVENIENCE SUMMARY
        # --------------------------------------------------------------

        summary: dict[
            str,
            Any,
        ] = {}

        for (
            horizon,
            payload,
        ) in horizon_results.items():

            brain = payload.get(
                "master_brain",
                {},
            )

            if not isinstance(
                brain,
                dict,
            ):
                continue

            decision = brain.get(
                "decision",
                {},
            )

            if not isinstance(
                decision,
                dict,
            ):
                decision = {}

            summary[horizon] = {
                "horizon_minutes": int(
                    horizon
                ),

                "direction": (
                    decision.get(
                        "direction",
                        "UNKNOWN",
                    )
                ),

                "score": (
                    decision.get(
                        "score",
                        0.0,
                    )
                ),

                "confidence": (
                    decision.get(
                        "confidence",
                        0.0,
                    )
                ),

                "decision_status": (
                    decision.get(
                        "decision_status",
                        "UNKNOWN",
                    )
                ),
            }

        result[
            "horizon_summary"
        ] = summary

        # --------------------------------------------------------------
        # 8. OVERALL STATUS
        # --------------------------------------------------------------

        evaluated_count = sum(
            1
            for item in horizon_results.values()
            if item.get(
                "status"
            ) == "EVALUATED"
        )

        if evaluated_count == 0:
            result["status"] = "ERROR"

        elif evaluated_count < len(
            horizon_results
        ):
            result["status"] = "PARTIAL"

        else:
            result["status"] = "EVALUATED"

        return result

    # ==================================================================
    # HEALTH
    # ==================================================================

    def health(self) -> dict[str, Any]:
        """Report orchestration readiness without claiming broker health."""

        provider_health = None

        health_fn = getattr(
            self.market_data,
            "health",
            None,
        )

        if callable(
            health_fn
        ):
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
            "supported_horizons": list(
                SUPPORTED_HORIZONS
            ),
            "incoming": self.incoming,
            "registry_configured": (
                self.registry is not None
            ),
            "market_data_configured": (
                self.market_data is not None
            ),
            "provider_connected": (
                self.market_data.provider
                is not None
            ),
            "provider_health": provider_health,
            "status": (
                "READY"
                if self.registry is not None
                and self.market_data is not None
                else "NOT_READY"
            ),
        }
