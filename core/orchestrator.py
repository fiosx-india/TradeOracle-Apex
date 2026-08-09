from pathlib import Path
import py_compile

outdir = Path("/mnt/data/TradeOracle-Apex-Orchestrator")
outdir.mkdir(parents=True, exist_ok=True)
path = outdir / "orchestrator.py"

content = '''"""TradeOracle Apex central runtime orchestrator.

Responsibilities
----------------
1. Discover and validate built-in engines.
2. Discover and validate user-supplied engines from ``incoming/``.
3. Register only engines that pass validation and benchmark checks.
4. Acquire market data through the canonical ``MarketData`` gateway.
5. Build the shared ``MarketContext``.
6. Optionally enrich that context with secondary data.
7. Pass the completed context to ``ApexMasterBrain``.
8. Return runtime/data-quality information for the UI and tests.

This file is orchestration only. It does not contain trading/order/GTT logic.
"""

from __future__ import annotations

import importlib
import inspect
import pkgutil
from datetime import datetime, timezone
from typing import Any, Callable, Optional

from config import INCOMING_DIR, LIVE_DATA_MAX_AGE_SECONDS

from .capability_router import CapabilityRouter
from .market_context import MarketContext
from .master_brain import ApexMasterBrain
from .system_registry import SystemRegistry

from data.market_data import MarketData

from plugins.plugin_benchmark import PluginBenchmark
from plugins.plugin_loader import PluginLoader
from plugins.plugin_validator import PluginValidator


# Optional secondary-context layer.
# The runtime still works when data/context_enricher.py has not yet been added.
try:
    from data.context_enricher import MarketContextEnricher
except ImportError:
    MarketContextEnricher = None


# First-party engine packages.
BUILTIN_PACKAGES = (
    "research",
    "prediction",
    "universe",
    "commodities",
)


class ApexOrchestrator:
    """Single orchestration layer for the complete Apex runtime."""

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
        self.router = CapabilityRouter(self.registry)

        self.validator = PluginValidator()
        self.benchmark = PluginBenchmark()

        self.market_data = market_data or MarketData(
            provider=market_provider,
            max_age_seconds=max_age_seconds,
        )

        self.brain = ApexMasterBrain(
            registry=self.registry,
            router=self.router,
        )

        if context_enricher is not None:
            self.context_enricher = context_enricher
        elif MarketContextEnricher is not None:
            self.context_enricher = MarketContextEnricher()
        else:
            self.context_enricher = None

    # ================================================================
    # ENGINE DISCOVERY
    # ================================================================

    @staticmethod
    def _looks_like_engine(obj: Any) -> bool:
        if not inspect.isclass(obj):
            return False

        if obj.__module__ == "builtins":
            return False

        name = getattr(obj, "name", None)
        capabilities = getattr(obj, "capabilities", None)

        return bool(
            isinstance(name, str)
            and name.strip()
            and isinstance(capabilities, (list, tuple, set))
            and capabilities
        )

    def _discover_builtin_engines(self) -> list[tuple[Any, str]]:
        """Discover first-party engines without hard-coding every filename."""
        discovered: list[tuple[Any, str]] = []
        seen: set[str] = set()

        for package_name in BUILTIN_PACKAGES:
            try:
                package = importlib.import_module(package_name)
            except Exception:
                continue

            package_path = getattr(package, "__path__", None)
            if not package_path:
                continue

            module_names = [package_name]

            for module_info in pkgutil.walk_packages(
                package_path,
                prefix=f"{package_name}.",
            ):
                if not module_info.ispkg:
                    module_names.append(module_info.name)

            for module_name in module_names:
                try:
                    module = importlib.import_module(module_name)
                except Exception:
                    continue

                for _, obj in inspect.getmembers(module, inspect.isclass):
                    if obj.__module__ != module.__name__:
                        continue

                    if not self._looks_like_engine(obj):
                        continue

                    key = f"{obj.__module__}.{obj.__name__}"

                    if key in seen:
                        continue

                    seen.add(key)

                    try:
                        discovered.append(
                            (
                                obj(),
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

    # ================================================================
    # VALIDATE / BENCHMARK / REGISTER
    # ================================================================

    def _register_engine(
        self,
        engine: Any,
        source_file: str,
    ) -> dict[str, Any]:
        try:
            validation = self.validator.validate(engine)
        except Exception as exc:
            return {
                "stage": "VALIDATION",
                "status": "ERROR",
                "name": getattr(engine, "name", source_file),
                "file": source_file,
                "errors": [
                    f"{type(exc).__name__}: {exc}",
                ],
            }

        if not validation.get("valid"):
            return {
                "stage": "VALIDATION",
                "status": "REJECTED",
                "name": getattr(engine, "name", source_file),
                "file": source_file,
                "errors": validation.get("errors", []),
            }

        try:
            benchmark = self.benchmark.benchmark(engine)
        except Exception as exc:
            return {
                "stage": "BENCHMARK",
                "status": "ERROR",
                "name": getattr(engine, "name", source_file),
                "file": source_file,
                "errors": [
                    f"{type(exc).__name__}: {exc}",
                ],
            }

        if not benchmark.get("passed"):
            return {
                "stage": "BENCHMARK",
                "status": "REJECTED",
                "name": getattr(engine, "name", source_file),
                "file": source_file,
                "errors": benchmark.get("errors", []),
                "benchmark": benchmark,
            }

        self.registry.register(
            engine,
            benchmark=benchmark,
            source_file=source_file,
        )

        return {
            "stage": "REGISTRATION",
            "status": "ACTIVE",
            "name": engine.name,
            "file": source_file,
            "benchmark": benchmark,
        }

    def discover_validate_benchmark_register(self) -> list[dict[str, Any]]:
        report: list[dict[str, Any]] = []

        # Register first-party engines.
        for engine, source_file in self._discover_builtin_engines():
            report.append(
                self._register_engine(
                    engine,
                    source_file,
                )
            )

        # Register user-supplied compatible engines.
        loader = PluginLoader(self.incoming)

        try:
            items = loader.discover()
        except Exception as exc:
            items = [{
                "loaded": False,
                "file": self.incoming,
                "errors": [
                    f"{type(exc).__name__}: {exc}",
                ],
            }]

        for item in items:
            if not item.get("loaded"):
                report.append(item)
                continue

            report.append(
                self._register_engine(
                    item["engine"],
                    item["file"],
                )
            )

        self.brain.attach_registry(
            self.registry,
            self.router,
        )

        return report

    # ================================================================
    # MARKET DATA -> SHARED CONTEXT
    # ================================================================

    @staticmethod
    def _records_to_data(
        records: list[dict[str, Any]],
    ) -> dict[str, Any]:
        if not records:
            return {}

        ordered = sorted(
            (
                dict(row)
                for row in records
                if isinstance(row, dict)
            ),
            key=lambda row: str(
                row.get("timestamp", "")
            ),
        )

        data: dict[str, Any] = {}

        aliases = {
            "open": ("open", "Open"),
            "high": ("high", "High"),
            "low": ("low", "Low"),
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
            values = []

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
                    values.append(float(value))
                except (TypeError, ValueError):
                    continue

            if values:
                data[target] = values

        timestamps = [
            row.get("timestamp")
            for row in ordered
            if row.get("timestamp")
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

    def build_market_context(
        self,
        symbol: str,
        *,
        sector: str = "",
        start: Any = None,
        end: Any = None,
        limit: int = 120,
        horizon_minutes: int = 60,
        **market_kwargs: Any,
    ) -> MarketContext:
        fetched = self.market_data.fetch(
            symbol=symbol,
            start=start,
            end=end,
            limit=limit,
            **market_kwargs,
        )

        # MarketData normally returns a canonical dict. The fallback also
        # prevents a raw provider list from crashing the orchestrator.
        if not isinstance(fetched, dict):
            fetched = {
                "records": (
                    fetched
                    if isinstance(fetched, list)
                    else []
                ),
                "quality": {},
                "source": None,
            }

        records = fetched.get("records") or []
        quality = fetched.get("quality") or {}

        data = self._records_to_data(records)
        data["market_data_quality"] = quality
        data["market_data_source"] = fetched.get("source")

        latest_timestamp = (
            records[-1].get("timestamp")
            if records
            and isinstance(records[-1], dict)
            else datetime.now(timezone.utc).isoformat()
        )

        context = MarketContext(
            timestamp=latest_timestamp,
            symbol=symbol or "",
            sector=sector or "",
            horizon_minutes=int(horizon_minutes),
            data=data,
            evidence=[],
        )

        # Secondary feeds are optional. Their failure must be visible but
        # must never silently replace or corrupt primary market data.
        if self.context_enricher is not None:
            try:
                self.context_enricher.enrich(context)
            except Exception as exc:
                data["context_enrichment_error"] = (
                    f"{type(exc).__name__}: {exc}"
                )

        return context

    # ================================================================
    # PUBLIC RUNTIME
    # ================================================================

    def run(
        self,
        context: Optional[MarketContext] = None,
        *,
        symbol: Optional[str] = None,
        sector: str = "",
        start: Any = None,
        end: Any = None,
        limit: int = 120,
        horizon_minutes: int = 60,
        **market_kwargs: Any,
    ) -> dict[str, Any]:
        report = self.discover_validate_benchmark_register()

        result: dict[str, Any] = {
            "status": "READY",
            "pipeline": [
                "DISCOVER",
                "VALIDATE",
                "BENCHMARK",
                "REGISTER",
                "MARKET_DATA",
                "MARKET_CONTEXT",
                "MASTER_BRAIN",
            ],
            "registered_engines": list(
                self.registry.all()
            ),
            "registry_report": self.registry.report(),
            "report": report,
            "market_data": {
                "provider_connected": (
                    self.market_data.provider is not None
                ),
                "max_age_seconds": (
                    self.market_data.max_age_seconds
                ),
            },
        }

        if context is None and symbol:
            context = self.build_market_context(
                symbol,
                sector=sector,
                start=start,
                end=end,
                limit=limit,
                horizon_minutes=horizon_minutes,
                **market_kwargs,
            )

        if context is None:
            result["status"] = "WAITING_FOR_CONTEXT"
            return result

        result["master_brain"] = self.brain.evaluate(context)

        context_data = getattr(
            context,
            "data",
            {},
        )

        quality = (
            context_data.get(
                "market_data_quality",
                {},
            )
            if isinstance(context_data, dict)
            else {}
        )

        result["market_data"].update({
            "quality": quality,
            "symbol": getattr(
                context,
                "symbol",
                "",
            ),
            "timestamp": getattr(
                context,
                "timestamp",
                None,
            ),
            "records": quality.get(
                "count",
                0,
            ),
            "fresh": quality.get(
                "fresh",
                False,
            ),
            "source": (
                context_data.get(
                    "market_data_source"
                )
                if isinstance(context_data, dict)
                else None
            ),
        })

        return result


class _FailedEngine:
    """Visible placeholder for a first-party engine that failed to instantiate."""

    capabilities: list[str] = []

    def __init__(
        self,
        name: str,
        error: Exception,
    ) -> None:
        self.name = name
        self.version = "unavailable"
        self.error = error
        self.capabilities = []

    def self_test(self) -> bool:
        return False
'''

path.write_text(content, encoding="utf-8")
py_compile.compile(str(path), doraise=True)
print("Created:", path)
print("Syntax validation: PASS")
