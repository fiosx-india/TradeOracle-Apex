"""Provider loader for TradeOracle Apex."""

from __future__ import annotations

import importlib
from typing import Any, Optional

from config import DATA_MODE, DATA_PROVIDER


def load_market_provider(spec: Optional[str] = None) -> Any:
    """Load the configured market-data provider.

    Live mode defaults to the bundled Angel One provider. Demo mode remains
    provider-free unless an explicit provider is configured.
    """
    target = (spec if spec is not None else DATA_PROVIDER).strip()

    if not target and DATA_MODE == "live":
        target = "data.angelone_provider:AngelOneProvider"

    if not target:
        return None

    if ":" not in target:
        raise ValueError(
            "APEX_DATA_PROVIDER must use 'module.path:factory_or_class'"
        )

    module_name, attribute_name = target.split(":", 1)

    if not module_name or not attribute_name:
        raise ValueError(
            "APEX_DATA_PROVIDER must contain both module and factory/class"
        )

    module = importlib.import_module(module_name)
    factory = getattr(module, attribute_name)

    if not callable(factory):
        raise TypeError(
            f"Configured market provider '{target}' is not callable"
        )

    return factory()
