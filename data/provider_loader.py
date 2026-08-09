"""Provider loader for TradeOracle Apex.

The loader is vendor-neutral. It never creates synthetic market data.

Configure a provider with:

    APEX_DATA_PROVIDER=module.path:factory_or_class

The target must be importable from the running application. The configured
factory/class may read provider credentials from environment variables or
its own configuration mechanism.
"""

from __future__ import annotations

import importlib
from typing import Any, Optional

from config import DATA_PROVIDER


def load_market_provider(spec: Optional[str] = None) -> Any:
    """Load and instantiate the configured market-data provider.

    Returns None when no provider is configured.
    """
    target = (spec if spec is not None else DATA_PROVIDER).strip()

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
