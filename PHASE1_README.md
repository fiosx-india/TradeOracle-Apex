# TradeOracle Apex — Phase 1 Patch

Prepared from the current `fiosx-india/TradeOracle-Apex` `main` branch.

## New files

- `data/news_data.py`
- `data/context_enricher.py`
- `core/signal_gate.py`
- `tests/test_runtime_contract.py`
- `docs/APEX_RUNTIME_AUDIT.md`

## Existing files to update

- `config.py`
- `core/orchestrator.py`
- `core/master_brain.py`
- `core/decision_engine.py`
- `research/volume_engine.py`
- `streamlit_app.py`

The included `apply_phase1_patch.py` performs these updates using exact anchors
and stops if the repository has diverged.

## Optional secret

`NEWSAPI_KEY = "..."`

Without this secret, news is reported as `UNCONFIGURED`; no synthetic news is
created.

## New controls

- `APEX_MIN_HISTORY_BARS` default `30`
- `APEX_REQUIRE_FRESH_DATA_FOR_SIGNAL` default `true`
- `APEX_NEWS_LOOKBACK_HOURS` default `24`

No order placement or GTT is introduced.
