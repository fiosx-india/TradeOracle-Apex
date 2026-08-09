from pathlib import Path

src = Path("/mnt/data/apex_compare/orchestrator.py")
dst = Path("/mnt/data/orchestrator_fixed.py")

text = src.read_text(encoding="utf-8")

old = """        context = MarketContext(
            timestamp=latest_timestamp,
            symbol=symbol or "",
            sector=sector or "",
            horizon_minutes=int(horizon_minutes),
            data=data,
            evidence=[],
        )

        # Secondary feeds are optional. Their failure must be visible but
"""

new = """        context = MarketContext(
            timestamp=latest_timestamp,
            symbol=symbol or "",
            sector=sector or "",
            horizon_minutes=int(horizon_minutes),
            data=data,
            evidence=[],
        )

        # Market-data quality is part of the shared runtime contract.
        # Keep it in ``data`` for data/engine consumers, and expose the same
        # canonical object at the MarketContext top level because
        # ApexMasterBrain reads it from the shared context directly.
        #
        # This preserves backward compatibility with engines already using
        # context.data while fixing the MarketData -> MasterBrain -> SignalGate
        # contract.
        context.market_data_quality = quality
        context.market_data_source = fetched.get("source")

        # Secondary feeds are optional. Their failure must be visible but
"""

if old not in text:
    raise RuntimeError("Expected orchestrator block was not found; file was not modified.")

dst.write_text(text.replace(old, new, 1), encoding="utf-8")

print(f"Created: {dst}")
print("Applied only the MarketData quality propagation fix; the rest of orchestrator.py is unchanged.")
