# TradeOracle Apex — Actual ZIP Verification & Price Propagation Fix

## Source package
`TradeOracle-Apex-main (2).zip`

## Result
The uploaded project was inspected and the price-propagation defect was found in the actual source.

### Root cause
`core/orchestrator.py::_market_result()` returned market quality/status metadata but did not expose the latest price from `MarketContext.data`.

This caused the dashboard code, which already requests:
`market["last_price"]` -> `market["price"]`
to display `—`.

`MarketContext.data` already receives the latest `price` from `_records_to_data()`, and `data/market_data.py` normalizes provider LTP aliases into `price` and `close`.

## Applied changes

### 1. `core/orchestrator.py`
Added canonical propagation:
- `last_price` first
- `price` fallback
- `close` fallback

Also exposed the existing `price` field as a backward-compatible UI alias.

No price is calculated or synthesized.

### 2. `core/orchestrator_fixed.py`
Applied the same change so the fixed/reference orchestrator remains consistent with the active orchestrator.

### 3. `tests/test_runtime_contract.py`
Added tests for:
- canonical `last_price`
- `price` fallback
- `close` fallback

## Auto Buy verification

`trading/auto_buy.py` was NOT loosened or redesigned.

Focused runtime checks passed:
- stale data is rejected before history checks
- insufficient history is rejected
- SIDEWAYS is rejected
- confidence below 60% is rejected
- non-positive score is rejected
- a valid UP + fresh + sufficient-history + confidence >= 60% + positive-score + valid-price case is eligible

## Full source verification

- Python files scanned: 89
- Syntax errors: 0
- Existing runtime contract tests: 6/6 PASS
- Focused Auto Buy checks: 6/6 PASS

A Python startup environment emitted an unrelated spreadsheet-runtime warmup warning, but it did not affect the project tests; the tests completed successfully.

## Horizons / safety

No changes were made to:
- 5 / 15 / 30 / 60 minute horizon configuration
- SignalGate
- Apex prediction logic
- PAPER mode
- broker execution
- stale-data safety
- Auto Buy thresholds

## Expected UI result

After redeployment:
- GOLDM, NATURALGAS, CRUDEOILM, SILVERM should receive the actual latest price in `market_data`.
- The UI's existing `Live Price` rendering can then display that value instead of `—` when the snapshot contains a usable price.

## Important deployment note

This work modifies the uploaded project ZIP and verifies the source/tests locally in this session. It does not claim that the currently deployed Streamlit URL has been redeployed automatically.
