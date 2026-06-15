# Run: 2026-06-15-W-002-shortpick-v2-paper-tracking-display

## Run ID

2026-06-15-W-002-shortpick-v2-paper-tracking-display

## Plan path

/Users/hernando_zhao/codex/worker-workspaces/stock_dashboard/20260615-shortpick-v2-paper-tracking-display/plans/active/plan-20260615-shortpick-v2-paper-tracking-display.md

## Hop ID

W-002

## Work item ID

W-002

## Goal

Rework the `试验田v2` paper-tracking frontend so the visible page uses the v1-like paper-tracking structure and Chinese-readable display fields supplied by W-001 instead of exposing backend config, contract, or row-field identifiers.

## Non-goals

- Do not change backend projection semantics in this run unless frontend build requires a type-only compatibility adjustment.
- Do not alter historical-replay strategy selection or introduce new strategy-search controls.
- Do not publish runtime or verify the served route in this run; W-003 owns final-main runtime verification.
- Do not add delayed-buy, retry-buy, or discretionary later-entry UI.

## Plan evidence

W-002 task: Rework the `试验田v2` paper tab to use the v1-style display structure and Chinese-readable labels, with no raw field-shaped visible content.

Deliverable: `frontend/src/components/ShortpickLabV2View.tsx`, types/helpers/styles/static tests.

Acceptance type: `test_pass`.

Acceptance spec: `cmd:python3 -m pytest -q tests/test_frontend_shortpick_static.py && cd frontend && npm run build`.

## Source coverage evidence

| Source ID | Source Requirement | W-002 Coverage |
|-----------|--------------------|----------------|
| SRC-002 | Stop presenting historical backtest/config data as the main paper-tracking display. | The paper tab will render `paper_display` display sections instead of raw `records`, `row_contract`, or config tables as its main content. |
| SRC-003 | Match v1 structure: latest simulated trade, strategy explanation, charts, and table. | The paper tab will render those four section types from `paper_display`. |
| SRC-004 | Add inclusive `signal_date >= 2026-05-08` data with `回放` tag. | The table will show backend-provided `tracking_tag` values and coverage summary cards, including visible `回放`. |
| SRC-005 | Ban field-shaped/raw unreadable UI content. | Visible paper-tab text will be Chinese-readable; static tests will reject known raw paper-tab strings and ensure the old `v2 Paper Ledger Rows` presentation is gone. |
| SRC-006 | Preserve H10 governance: replay rows are not true-forward, fixed90 diagnostic-only, no delayed buy. | Paper-tab explanation and chart subtitles will keep replay rows separate from true-forward records and state no delayed buy. |
| SRC-007 | Keep v2 limited to paper tracking and historical replay. | W-002 will preserve the two-tab set and not add modules. |
| SRC-009 | Keep API response compatible. | Frontend types will add optional `paper_display` fields without removing existing response properties. |

## Production path fidelity evidence

| Path ID | User / Production Path | W-002 Validation |
|---------|------------------------|------------------|
| PF-001 | User opens the real served dashboard route. | Deferred to W-003 after merge/publish; W-002 validates local source/build only. |
| PF-002 | `/shortpick-lab-v2/paper-tracking` returns data consumed by the v2 paper tab. | W-002 consumes the production response type and W-001 projection shape; W-003 later verifies the served API. |
| PF-004 | Frontend converts backend fields into readable Chinese. | Static tests and TypeScript build check the frontend source path. |

## Files expected to change

- `frontend/src/components/ShortpickLabV2View.tsx`
- `frontend/src/types/shortpick.ts`
- `tests/test_frontend_shortpick_static.py`
- Existing CSS only if the current utility classes are insufficient for simple chart bars.

## Implementation steps

1. Add TypeScript types for the additive `paper_display` projection.
2. Replace the current v2 paper tab content with display-layer rendering: latest simulated trade, strategy explanation, chart cards, display table, and coverage summary cards including `coverage_start`, `coverage_end`, `latest_source_signal_date`, replay count, and gap count where the backend provides them.
3. Keep the page header and paper-tab copy Chinese-readable and remove visible raw literals such as `research_observation`, `contract_ready`, `v2 Paper Ledger Rows`, `config_id`, and `decision_action`; static tests should also include a generic snake_case/key-shaped visible-text guard for the paper tab.
4. Preserve the existing two-tab v2 navigation and historical replay tab.
5. Update static tests to assert the new paper-tab structure and raw-field ban.
6. Run the W-002 acceptance command and fix any build/test failures.

## Acceptance criteria

- The v2 paper tab visibly includes `最新模拟交易`, `策略说明`, chart content, and a table.
- The paper tab shows `回放` tags when backend rows provide them.
- The paper tab exposes readable coverage summary values for the replay window, latest source signal date, replay rows, and data gaps.
- The paper tab does not use raw `records`, `row_contract`, or config tables as its main UI.
- Known raw visible strings from the old paper tab are absent.
- V2 still has only `纸面追踪` and `历史回放` tabs.
- Static tests and frontend build pass.

## Acceptance Type and Acceptance Spec

Acceptance Type: `test_pass`

Acceptance Spec: `cmd:python3 -m pytest -q tests/test_frontend_shortpick_static.py && cd frontend && npm run build`

## Planned Evidence

- MiMo run-plan review: pending.
- MiMo code review: pending.
- Static frontend tests: pending.
- Frontend build: pending.
- Plan validation after W-002 update: pending.

## Actual Evidence

- 2026-06-15T13:08:08Z: W-001 checkpoint commit `94deec4` exists; W-002 selected as next eligible work item.

## Risk and rollback notes

Primary rollback is to revert W-002 frontend/type/test changes while keeping W-001 backend projection. The main risk is a false raw-field ban that checks source literals rather than visible text; W-003 still must perform served browser verification for the real user-visible surface.

## Gate plan

- `python3 /Users/hernando_zhao/.codex/skills/reviewed-plan-generator/scripts/validate_plan.py plans/active/plan-20260615-shortpick-v2-paper-tracking-display.md`
- MiMo W-002 run-plan review.
- MiMo W-002 code review.
- `python3 -m pytest -q tests/test_frontend_shortpick_static.py`
- `cd frontend && npm run build`

## MiMo plan-review result

Passed with no blocker or major findings. Accepted and resolved two implementation-detail minors in this run plan: coverage summary cards now explicitly include replay window/latest-source/gap values, and static tests now explicitly require a generic snake_case/key-shaped visible-text guard for the paper tab. A CSS-scope note remains non-blocking and will be recorded after implementation depending on whether CSS changes are needed.

## Codex escalation plan-review result

Not required for W-002 by the approved plan; W-001 and W-003 carry required Codex escalation coverage.

## Implementation summary

Completed the frontend display-layer rewrite for `试验田v2 -> 纸面追踪`.

- Added additive TypeScript types for `paper_display`.
- Replaced the old paper tab raw/backtest-field presentation with four v1-like sections: `最新模拟交易`, `策略说明`, chart cards, and `模拟交易明细`.
- Added visible coverage summary cards for `真实前向记录`, `回放展示行`, `覆盖起点`, `覆盖终点`, `最新来源信号日`, and `数据缺口`.
- Preserved the `回放补齐不计入真实前向收益`, `不允许延迟买入`, and research-observation warnings in Chinese-readable copy.
- Converted config/status/action/reason fallbacks to Chinese-readable labels and avoided raw ids in table row keys.
- Added static frontend guards for paper-tab and replay-tab visible JSX text, including a generic snake_case/key-shaped guard.
- No CSS change was needed; existing panel/metric/table utility classes were sufficient.

## MiMo code-review result

Passed with no blocker. MiMo confirmed the paper tab uses `paper_display` rather than raw `records`/`row_contract`, and known raw identifiers have no visible rendering path. Accepted and applied its actionable recommendations: generated non-raw table row keys, expanded fallback paper-table columns to include reason/rank text, and added replay-tab visible-text guard coverage. Compatibility notes about `records` and `row_contract` remaining in the response type were retained because W-001/W-002 keep the API additive.

## Codex escalation code-review result

Not required for W-002 by the approved plan.

## Gate results

- Passed: `python3 -m pytest -q tests/test_frontend_shortpick_static.py` => 6 passed on 2026-06-15T13:24Z.
- Passed: `cd frontend && npm run build` => TypeScript and Vite build succeeded on 2026-06-15T13:24Z; Vite emitted only the existing large-chunk warning.
- Policy audit not required in W-002 because no weights, thresholds, windows, formulas, or Phase gates were changed.

## Plan update summary

Plan W-002 was marked done with evidence, revision history was updated, and the W-002 MiMo review outcomes were recorded in the external review log.

## Plan archive result

Not applicable until full-plan completion.

## Archive and merge result

W-002 is ready for archive and checkpoint commit. Merge, final-main push, publish, and served runtime verification remain owned by W-003.
