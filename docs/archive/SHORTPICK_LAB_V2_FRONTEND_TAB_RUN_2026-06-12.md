# Short Pick Lab V2 Frontend Tab Run

Status: Complete; published runtime served UI/API verified
Owner: stock_dashboard
Created: 2026-06-12
Source plan: `docs/contracts/SHORTPICK_LAB_V2_PLAN_2026-06-12.md`

## Objective

Implement Phase 7 of the Short Pick Lab V2 plan: add a user-facing `试验田v2` tab that reads the Phase 6 backend read APIs and exposes only the two approved modules.

| Module | Frontend scope |
| --- | --- |
| 纸面追踪 | Show v2 paper-tracking status, selected/baseline configs, `2026-05-08` start anchor, allowed actions, and ledger rows when present. If no ledger exists, show the contract-ready empty state. |
| 历史回放 | Show the precomputed Phase 3/4 replay readout: selected configs, baseline/holdout/rejected configs, summary metrics, bounded decision samples, and artifact/research labels. |

## Scope

| Area | Planned change |
| --- | --- |
| App navigation | Add a separate `view=shortpick-v2` view/card labeled `试验田v2`, distinct from v1 `view=shortpick`. |
| Mobile navigation | Add the same v2 view to the mobile shell without replacing v1 `试验田`. |
| API client/types | Add typed frontend client calls for `/shortpick-lab-v2/paper-tracking` and `/shortpick-lab-v2/historical-replay`. |
| Component | Add a standalone `ShortpickLabV2View` component with two tabs only: `纸面追踪` and `历史回放`. |
| Tests | Add static/type tests that prove the v2 tab uses v2 routes and does not expose v1-only modules. |
| Publish/verification | Build, publish to runtime, and verify the served UI/API after merge. |

## Non-Scope

| Non-scope | Boundary |
| --- | --- |
| v1 Short Pick Lab redesign | Do not refactor the existing `ShortpickLabView` beyond routing/import wiring. |
| Backend changes | Phase 6 APIs are already implemented; do not add new backend behavior unless a compile-only type mismatch requires a narrow fix. |
| Paper writer | Do not create or backfill v2 paper ledger rows. |
| Dynamic replay | Do not trigger replay generation, market refresh, model calls, or parameter sweeps from the UI. |
| Parameter grid | Do not expose strategy parameters as interactive controls. |
| Extra modules | Do not add LLM validation, model feedback, today batch, settings, or candidate-management modules to v2. |

## Intended UI Contract

| Screen area | Requirement |
| --- | --- |
| Header | Make `试验田v2` the primary page signal and label it as paper/research account-path evidence. |
| Tabs | Exactly `纸面追踪` and `历史回放`. |
| Paper empty state | Show contract-ready status with selected configs and no v1-derived rows. |
| Replay summary | Show selected promoted configs first, baseline separately, holdout/rejected as non-active reference. |
| Research labeling | Keep `claim_ceiling=research_observation`, evidence basis, and no investment-advice language visible. |
| Actions | Only refresh/read actions; no write, run, validate, retry, parameter edit, or market refresh buttons. |

## Acceptance

| Rule | Status | Evidence target |
| --- | --- | --- |
| Separate frontend domain | Done | `ShortpickLabV2View` uses v2 API client calls and a separate `view=shortpick-v2` route. |
| Two modules only | Done | UI exposes only `纸面追踪` and `历史回放`. |
| v1 data boundary | Done | V2 view does not call `/shortpick-lab/paper-tracking`, v1 replay APIs, v1 validation, or v1 feedback; static tests assert the separation. |
| No dynamic replay/write actions | Done | UI has no run/replay/validate/write/parameter controls. |
| Paper contract-ready state | Done | Missing ledger state from `docs/contracts/SHORTPICK_LAB_V2_PAPER_TRACKING_CONTRACT_2026-06-12.md` is displayed as contract-ready empty paper tracking, not as failure or implicit buy. |
| Research labeling | Done | UI shows research/evidence labels and avoids production/investment claims. |
| Focused tests pass | Done | `python3 -m pytest -q tests/test_frontend_shortpick_static.py tests/test_frontend_mobile_static.py` passed. |
| Required gates pass | Done | `npm run build`, default `pytest`, and policy audit passed before merge. |
| Runtime verification | Done | Published runtime served page/API verified after merge. |

## Implementation Evidence

| Evidence | Result |
| --- | --- |
| MiMo run-plan drift review | PASS; no blocking issues before implementation. |
| MiMo implementation review | PASS; no blocking v1 mixing, module creep, write action, or overclaiming issue. |
| MiMo popstate follow-up review | PASS after adding browser back/forward sync for `shortpickV2Tab`. |
| Focused frontend static tests | `7 passed in 0.06s`. |
| Frontend build/typecheck | `npm run build` passed; only the existing Vite chunk-size warning remains. |
| Default Python regression | `808 passed, 171 deselected, 6 subtests passed in 30.11s`. |
| Policy audit | PASS. |
| Runtime publish | `publish-local-runtime.sh` built and synced `b62f2a9`; script timed out at backend health wait, then manual health checks confirmed backend/frontend recovered. |
| Served API verification | `GET /health` returned 200; `GET /shortpick-lab-v2/paper-tracking` returned `contract_ready`; `GET /shortpick-lab-v2/historical-replay?sample_limit=1` returned `ready`. |
| Served UI verification | Browser opened `http://127.0.0.1:5173/?view=shortpick-v2`; verified v2 header, `纸面追踪`, `历史回放`, `contract_ready`, `2026-05-08`, no v1 module labels, tab switch, browser back sync, and no console errors. |

## Review Plan

MiMo should review this run plan before implementation for drift against:

- `docs/contracts/SHORTPICK_LAB_V2_PLAN_2026-06-12.md`
- `docs/archive/SHORTPICK_LAB_V2_BACKEND_READ_MODEL_RUN_2026-06-12.md`
- Phase 5 paper contract

After implementation, MiMo should review the frontend for semantic mixing, hidden write actions, module creep, and overclaiming.
