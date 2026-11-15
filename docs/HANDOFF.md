# Handoff for new strategy work

Starting point for a new conversation working on a strategy separate from PORR. Read `CLAUDE.md` first.

## PORR (existing, keep unchanged unless asked)
- PORR (pre-open range reversal, MNQ) runs on paper: `strategies/porr.pine` v3.0 -> Render webhook bridge
  (`porr_bot/`) -> Webull paper futures account. Setup: `porr_bot/DEPLOYMENT.md`.
- All research results: `research/RESULTS.md`. Backtest code in `research/`:
  - `fastsim.py` 1-second trade simulator; `sys2.py` full PORR system simulator
  - `g2.py` / `g3.py` parallel batch runners; `grow.py` account-growth model
  - studies: `ff_*.py`, `bo_reach.py`, `open5.py`, `late5.py`, `reg*.py`
  - Some scripts still hold an old session's `/tmp/...` scratchpad paths; repoint them.

## Data (not in the repo; re-fetch)
- Databento `GLBX.MDP3`, schema `ohlcv-1s`, symbols `MNQ.FUT` (`stype_in` parent), two batch jobs:
  - `GLBX-20261109-SU399GCRLM`: Feb 2025 - Nov 2026
  - `GLBX-20261112-MMATYEGEWB`: Nov 1 2021 - Jul 31 2023
  - No data Aug 2023 - Jan 2025 (treated as no trading).
- Download already-paid files from the batch download URLs. The Databento key is a network credential in the
  environment (`curl -u dummy: ...`), never in the repo. Batch files expire (often ~30 days); ask before buying data.
- Pipeline: `research/db_filter.py`, `build_cache.py`, `build_cache2.py` turn the raw 1s CSV into RTH 1-second
  caches (`cache_1s.npz`) and 1-minute bars; `features.py` / `features2.py` build daily levels, EMA trends and
  day features. VIX daily closes (`ext/vix.csv`) came from CBOE's public history. Webull daily bars only go back
  5 years.

## Conventions
- 10 MNQ, $0.74/side commission, Central time.
- Test each idea separately on 2021-23 and 2025-26; only trust what holds in both.
- Keep explanations brief.
- Put the new strategy in its own folder, e.g. `strategies/<name>/`.
