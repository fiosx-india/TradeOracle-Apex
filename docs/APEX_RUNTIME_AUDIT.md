# TradeOracle Apex — Phase 1 Runtime Audit

## Verified from the current `main` branch

- Angel One SmartAPI is the default live market provider.
- `streamlit_app.py` performs an LTP connection check and then historical-candle analysis.
- `MarketData` validates timestamps and freshness.
- `ApexOrchestrator` owns the shared `MarketContext`; `ApexMasterBrain` is the final orchestration layer.
- Research engines already exist for technicals, momentum, volume, news, sentiment, events, fundamentals, global impact, and correlation.
- Prediction engines already exist for base prediction, breakout, early movement, reversal, and 60-minute analysis.
- Derived engines are separated from primary voting.

## Problems found

### 1. Freshness did not gate the final signal
The UI could show a directional assessment even when `MarketData` reported `STALE`.

**Phase 1 fix:** `SignalGate` is applied after fusion. Directional output becomes `SIDEWAYS` with `decision_status=WITHHELD` when history is too short, data is stale, or confidence is below the configured threshold.

### 2. Secondary gateways existed but were not connected to `MarketContext`
`EventData`, `MacroData`, `GlobalData`, and `CurrencyData` existed, but the orchestrator only populated price/candle fields.

**Phase 1 fix:** `MarketContextEnricher` attaches normalized secondary data and quality metadata. It remains provider-agnostic.

### 3. News intelligence had no concrete news gateway
`NewsIntelligence` expected normalized news, but there was no `data/news_data.py` provider.

**Phase 1 fix:** `NewsData` was added with optional NewsAPI integration. It is read-only. Heuristic sentiment/event labels are explicitly tagged.

### 4. Index volume semantics were unsafe
Angel One historical data can legitimately report zero volume for index instruments. The existing `VolumeEngine` treated zero-volume input as if a normal relative-volume baseline existed.

**Phase 1 fix:** all-zero volume is now treated as unavailable; the engine falls back to price-only confirmation with lower weight/confidence.

### 5. Contract smoke tests were too shallow
The existing plugin benchmark checks `self_test()` and method presence but does not validate final decision gating.

**Phase 1 fix:** a standard-library `unittest` contract suite is added.

## Operational rule

Deployment reachability does not prove Angel One authentication and fresh market data. The Streamlit runtime should show:

- Authentication = CONNECTED
- LTP present
- Fresh = YES
- Gateway = OK

When the market is closed, `Fresh=NO` is expected. The new gate withholds a directional signal instead of treating the last traded price as current.

## Phase 2 candidates

1. Real corporate-event provider and event-confidence calibration.
2. Global index / FX / macro providers with timestamps and freshness contracts.
3. Historical walk-forward validation and probability calibration.
4. Per-engine performance tracking instead of fixed confidence assumptions.
5. WebSocket tick ingestion if continuous tick-level analysis is required.
6. BUY/SELL presentation only after directional output is validated.

This phase does not add order placement or GTT.
