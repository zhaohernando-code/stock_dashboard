# Run: 2026-06-16-W-001-paper-divergence-attribution

## Run ID

2026-06-16-W-001-paper-divergence-attribution

## Plan path

`/Users/hernando_zhao/codex/worker-workspaces/stock_dashboard/20260616-shortpick-paper-divergence-attribution/plans/active/plan-20260616-shortpick-paper-divergence-attribution.md`

## Hop ID

W-001

## Work item ID

W-001

## Goal

Implement the research-only attribution module, CLI commands, schema, and focused tests for the v1/v2 paper-window divergence question.

## Non-goals

- Do not change frontend or served dashboard routes.
- Do not promote, retire, or reorder strategies.
- Do not mutate existing v1/v2 paper ledgers.
- Do not refresh market data.

## Plan evidence

The approved plan requires a separate research artifact that compares the `2026-05-08` onward paper window on an account basis, while treating v1 raw paper records as candidate observations and deriving a separate 20w control.

## Source coverage evidence

- SRC-001: Durable brainstorm record exists at `docs/archive/SHORTPICK_PAPER_DIVERGENCE_BRAINSTORM_2026-06-16.md`.
- SRC-002/SRC-003: W-001 creates the attribution machinery needed to explain the v2/v1 current-window divergence.
- SRC-004/SRC-005: W-001 must keep v1 raw observations separate from a derived account simulation and enforce 20w, 100-share lots, skip-if-unaffordable, and no delayed buy.
- SRC-006/SRC-007: W-001 is research-only and does not change strategy promotion or UI.

## Production path fidelity evidence

- PF-001/PF-002: CLI and module are the production research path.
- PF-003: v1 control is a controlled simulation owned by the new attribution module.
- PF-004: No UI/API display path is in scope.

## Files expected to change

- `src/ashare_evidence/shortpick_paper_divergence_attribution.py`
- `src/ashare_evidence/cli.py`
- `docs/contracts/registry/schemas/shortpick_paper_divergence_attribution.schema.json`
- `tests/test_shortpick_paper_divergence_attribution.py`
- Plan/run documentation.

## Implementation steps

1. Inspect existing v1/v2 data adapters and CLI patterns.
2. Add a dedicated attribution builder with pure functions for account simulation and classification.
3. Add CLI commands for build and validate.
4. Add schema and focused tests.
5. Run the W-001 focused pytest gate.

## Acceptance criteria

`PYTHONPATH=src python3 -m pytest -q tests/test_shortpick_paper_divergence_attribution.py` exits 0 and covers schema validation, v2 H10 account rules, v1 20w top1-or-skip, board lots, skip-if-unaffordable, and no delayed buy.

## Acceptance Type and Spec

test_pass: `cmd:PYTHONPATH=src python3 -m pytest -q tests/test_shortpick_paper_divergence_attribution.py`

## Planned Evidence

- Focused pytest pass.
- Git diff contains no frontend/API display route changes.
- MiMo and DeepSeek implementation reviews have no unresolved blocker.

## Actual Evidence

- `PYTHONPATH=src python3 -m pytest -q tests/test_shortpick_paper_divergence_attribution.py` initially passed `4 passed`.
- MiMo implementation review: no blocker/major; minor notes on v2 label matching and unresolved/open position valuation.
- DeepSeek implementation review: no blocker/major; requested a rank1 happy-path test and less misleading v2 cash/lot rejection metadata.
- Applied minor fixes, including matured-exit final settlement discovered by the new happy-path test.
- Final W-001 gate: `5 passed in 0.56s`.

## Risk and rollback notes

The main risk is confusing v1 candidate observations with account NAV. Rollback is to remove the new research-only module/CLI/schema/tests and plan/run docs from the task branch.

## Gate plan

- MiMo read-only run-plan/code review.
- DeepSeek read-only implementation review.
- Focused pytest for the new attribution module.

## MiMo plan-review result

Passed after minor clarifications were applied.

## Codex escalation plan-review result

Not required.

## Implementation summary

Implemented `shortpick_paper_divergence_attribution` with a dedicated research-only artifact, v1 raw/derived separation, v2 read-model account-curve ingestion, schema validation, CLI build/validate commands, and focused tests.

## MiMo code-review result

Passed with no blocker/major. Minor notes were accepted or addressed.

## Codex escalation code-review result

Not required.

## Gate results

- W-001 focused pytest passed: `5 passed in 0.56s`.
- W-002 generated `output/shortpick-paper-divergence-attribution-20260616.json` and `docs/archive/SHORTPICK_PAPER_DIVERGENCE_ATTRIBUTION_2026-06-16.md` from runtime SQLite.
- W-002 validate passed: `failed_check_count=0`.

## Plan update summary

W-001 and W-002 marked done; W-003 closeout started in the plan.

## Plan archive result

Plan status set to archived and prepared for move from `plans/active/plan-20260616-shortpick-paper-divergence-attribution.md` to `plans/archive/plan-20260616-shortpick-paper-divergence-attribution.md`.

## Archive and merge result

Run record prepared for archive at `runs/archive/2026-06-16-W-001-paper-divergence-attribution.md`. Final task-branch push, main merge, origin/main push, lock cleanup, and temporary worktree cleanup are performed after this run record is committed and are reported in the final closeout response.
