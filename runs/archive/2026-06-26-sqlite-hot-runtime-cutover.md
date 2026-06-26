# Run: SQLite Hot Runtime Cutover

- Run ID: `2026-06-26-sqlite-hot-runtime-cutover`
- Plan path: `/Users/hernando_zhao/codex/worker-workspaces/stock_dashboard/20260626-sqlite-hot-cold-split/plans/archive/plan-20260626-sqlite-hot-cold-split.md`
- Branch: `codex/sqlite-hot-runtime-cutover`
- Base branch: `main`

## Goal
Complete the physical SQLite split that the first foundation run intentionally deferred: create a slim runtime hot DB, keep the original DB as rollback source, and cut the served runtime over to `ashare_hot.db`.

## Non-goals
- No PostgreSQL migration.
- No deletion or vacuum of the original `ashare_dashboard.db`.
- No real network data refresh during cutover validation.

## Plan Evidence
- The archived hot/cold split plan kept live hot paths and cold history separated but recorded physical hot cutover as out of scope for its first run.
- User explicitly asked whether DB splitting had actually been done, then asked to continue.
- Existing runtime scripts source the shared backend env file, so changing the runtime DB URL there affects the FastAPI process and scheduled refresh entrypoint consistently.

## Implementation Summary
- Extended `sqlite-hot-cold-split` with optional slim hot DB creation:
  - `--hot-database-url`
  - `--create-hot`
  - `--overwrite-hot`
  - `--hot-retain-days`
  - repeated `--hot-symbol`
- Slim hot DB generation copies the source DB, then deletes old non-hot `1d` market bars from the copy only.
- Hot-symbol retention includes active watchlist/follow symbols, portfolio/simulation benchmark symbols, default CSI benchmark aliases, and any explicit CLI symbols.
- Added regression coverage proving:
  - broad old non-hot `1d` rows are removed from the hot copy;
  - hot-symbol `1d` rows are retained;
  - `5min` rows are retained;
  - verify-only without `create_hot=True` does not create a hot DB;
  - cold `market_bar_history` still contains full archived `1d` rows.
- After MiMo review, fixed minor findings:
  - CLI success exit now includes hot DB creation status when `--create-hot` is used.
  - Hot DB creation result now includes `created_at`.

## Runtime Cutover Evidence
- Cold migration command completed successfully against runtime data:
  - `ashare_market_history.db`: `1d` rows copied: `2,325,997`, range `2022-11-21 15:00:00.000000` to `2026-06-26 15:00:00.000000`.
  - `ashare_research_archive.db`: archived `shortpick_experiment_runs` `262`, `shortpick_model_rounds` `692`, `shortpick_candidates` `8,208`, `shortpick_consensus_snapshots` `43`, `shortpick_validation_snapshots` `40,110`.
- Slim hot DB command completed successfully:
  - source: `/Users/hernando_zhao/codex/runtime/projects/ashare-dashboard/data/ashare_dashboard.db`
  - hot: `/Users/hernando_zhao/codex/runtime/projects/ashare-dashboard/data/ashare_hot.db`
  - retain window: `450` days, cutoff `2025-04-02 15:00:00.000000`
  - hot symbols: `000300.SH`, `000852.SH`, `000905.SH`, `002028.SZ`, `002270.SZ`, `600589.SH`
  - `market_bars` before/after: `2,333,334` -> `917,353`
  - `1d` before/after: `2,325,997` -> `910,016`
  - deleted old non-hot `1d`: `1,415,981`
  - retained hot-symbol `1d`: `5,114`
- Runtime DB sizes after checkpoint/optimization:
  - original `ashare_dashboard.db`: about `2.7G`
  - `ashare_hot.db`: about `1.2G`
  - `ashare_market_history.db`: about `2.0G`
  - `ashare_research_archive.db`: about `232M`
- Runtime backend env was backed up before cutover and updated to point to:
  - hot DB: `ashare_hot.db`
  - market-history DB: `ashare_market_history.db`
  - research archive DB: `ashare_research_archive.db`
- FastAPI LaunchAgent was restarted after env update.
- `/health` on the served runtime returned the hot DB URL.

## Served API Smoke
- Temporary pre-cutover server on port `8010` using hot/cold DB URLs:
  - `/health`: 200, `0.016s`
  - `/dashboard/shell`: 200, `0.083s`
  - `/dashboard/scheduled-refresh-status`: 200, `0.003s`
  - `/dashboard/operations`: 200 degraded cache miss, `0.003s`
  - `/dashboard/operations/summary`: 200, `0.005s`
  - `/dashboard/operations/details?section=portfolios`: 200 degraded cache miss, `0.003s`
  - `/dashboard/operations/details?section=replay`: 200 degraded cache miss, `0.002s`
  - `/stocks/002028.SZ/dashboard`: 200, `0.274s`
- Official runtime on port `8000` after LaunchAgent cutover:
  - `/health`: 200, `0.012s`
  - `/dashboard/shell`: 200, `0.274s`
  - `/dashboard/scheduled-refresh-status`: 200, `0.007s`
  - `/dashboard/operations?sample_symbol=600519.SH`: 200 degraded cache miss, `0.008s`
  - `/dashboard/operations/summary?sample_symbol=600519.SH`: 200, `0.014s`
  - `/dashboard/operations/details?section=portfolios&sample_symbol=600519.SH`: 200 degraded cache miss, `0.015s`
  - `/dashboard/operations/details?section=replay&sample_symbol=600519.SH`: 200 degraded cache miss, `0.008s`
  - `/stocks/002028.SZ/dashboard`: 200, `0.874s`

## Gate Plan
- `python3 -m pytest -q tests/test_sqlite_hot_cold_split.py -q`
- `python3 -m pytest -q`
- `PYTHONPATH=src python3 -m ashare_evidence.cli policy-audit --fail-on-new-unclassified --fail-on-direct-config-read --fail-on-formula-side-effects --fail-on-missing-config-lineage`
- MiMo read-only code-risk review for the hot DB creation path.
- Runtime publish with `ASHARE_PUBLISH_REFRESH_MODE=skip`, then served API smoke.

## Gate Results
- Targeted migration test: `... [100%]`.
- Compile check: `python3 -m compileall -q src/ashare_evidence/sqlite_hot_cold_split.py src/ashare_evidence/cli.py` passed.
- Full pytest: `973 passed, 173 deselected, 6 subtests passed in 35.73s`.
- Policy audit: pass; no direct config reads, formula side effects, missing config lineage, or new unclassified items.
- Runtime cold verify-only: pass; `1d` source/target counts both `2,325,997`, range `2022-11-21 15:00:00.000000` to `2026-06-26 15:00:00.000000`; research archive source/target counts match for all archived shortpick tables.
- MiMo code review: `NO_BLOCKING_CODE_REVIEW`; minor findings accepted and fixed before commit.
- Runtime publish after branch commit: pass.
  - Command: `ASHARE_PUBLISH_MAX_WAIT_SECONDS=600 ASHARE_PUBLISH_VERIFY_MODE=local ASHARE_PUBLISH_REFRESH_MODE=skip bash scripts/publish-local-runtime.sh`.
  - Published source commit: `7d16300aede71b72d41a33e504136d91b94b7d0b`.
  - Release parity manifest: `/Users/hernando_zhao/codex/runtime/projects/ashare-dashboard/output/releases/local-20260626T133130Z-7d16300.json`.
  - Backend health and frontend health passed.
  - Post-deploy real data refresh was skipped as intended; shortpick v2 paper cache prewarm completed.

## Post-Publish Served API Smoke
- `/health`: 200, `0.012s`, database URL `sqlite:////Users/hernando_zhao/codex/runtime/projects/ashare-dashboard/data/ashare_hot.db`.
- `/dashboard/shell`: 200, `0.224s`.
- `/dashboard/scheduled-refresh-status`: 200, `0.008s`.
- `/dashboard/operations?sample_symbol=600519.SH`: 200 degraded cache miss, `0.011s`.
- `/dashboard/operations/summary?sample_symbol=600519.SH`: 200, `0.025s`.
- `/dashboard/operations/details?section=portfolios&sample_symbol=600519.SH`: 200 degraded cache miss, `0.011s`.
- `/dashboard/operations/details?section=replay&sample_symbol=600519.SH`: 200 degraded cache miss, `0.010s`.
- `/stocks/002028.SZ/dashboard`: 200, `0.934s`.

## Risk And Rollback Notes
- Original runtime DB was not modified by hot slimming and remains the rollback DB.
- Rollback is a config switch back to the original `ashare_dashboard.db` plus FastAPI restart.
- If hot DB writes need to be reconciled back to the original DB later, `ashare_hot.db` must be treated as the newer live source for hot tables after cutover time.
- The cold DBs are append/copy artifacts; they can be regenerated from the original source DB and hot DB as needed.

## Archive And Merge Result
- Task branch pushed to `origin/codex/sqlite-hot-runtime-cutover`.
- `main` fast-forwarded from `04f16c8b533a23e692e37bddce9480c31b03cef8` to `324ca2f306335f02cfe04b6bd55b30e8f40629fd`.
- `origin/main` push succeeded after pre-push fast regression and policy audit passed.
