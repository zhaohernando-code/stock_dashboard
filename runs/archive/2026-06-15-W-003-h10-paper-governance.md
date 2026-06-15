# Run ID

2026-06-15-W-003-h10-paper-governance

## Plan Path

`/Users/hernando_zhao/codex/worker-workspaces/stock_dashboard/20260615-h10-paper-governance-150154/plans/active/plan-20260615-h10-paper-governance.md`

## Hop ID

W-003

## Work Item ID

W-003

## Goal

Generate real H10 paper-governance evidence from the runtime database and regenerated H10 artifacts, publish the durable governance artifact copy under `docs/archive/`, and update the durable champion run document with the required future-true-forward/no-fixed90 marker.

## Non-Goals

- Do not publish the runtime app or verify served routes in this hop; W-004 owns runtime publish and served verification.
- Do not create or backfill true-forward paper ledger rows.
- Do not promote fixed90 or allow delayed-entry actions.
- Do not reopen broad strategy search or change H10 parameter choices.
- Do not commit ignored `output/` artifacts as durable source files.

## Plan Evidence

W-003 deliverable: `output/shortpick-v2-h10-paper-governance-artifact.json`, `docs/archive/SHORTPICK_LAB_V2_H10_PAPER_GOVERNANCE_ARTIFACT_2026-06-15.json`, and archive doc update.

Acceptance: `bash scripts/run-shortpick-v2-h10-paper-governance.sh`.

## Source Coverage Evidence

- SRC-001: continues reviewed-plan-generator + plan-run-loop execution with W-001/W-002 archived and W-003 active.
- SRC-002: durable H10 memory must preserve fixed85 as primary and fixed80 as capital shadow in the generated governance artifact and durable doc.
- SRC-003: generated governance artifact must say historical replay is not true-forward paper tracking and must not write paper rows.
- SRC-004: generated artifact must preserve no-delayed-buy policy.
- SRC-005: generated artifact validation must enforce market outperformance and at least 30% annualized return for future-observation candidates.
- SRC-006: fixed90 must remain diagnostic-only in generated artifact and docs.
- SRC-007: no new UI or broad search direction is added.
- SRC-008: generated artifact must stay `research_observation` and historical governance evidence only.
- SRC-009: MiMo and Codex escalation run-plan/code reviews are required because W-003 lands durable governance artifacts and decisions.

## Production Path Fidelity Evidence

- PF-001: run the actual generation script, which invokes the CLI generation path against the runtime SQLite DB and regenerated H10 source artifacts, then validates the generated and published governance artifacts.
- PF-002: W-003 does not create paper ledger rows; W-002 schema/read-model gates already proved future row acceptance/rejection.
- PF-003: W-003 produces the docs/archive governance artifact consumed by the W-002 artifact resolver; served verification remains deferred to W-004.
- PF-004: runtime publish and served checks are explicitly deferred to W-004.

## Files Expected To Change

- `docs/archive/SHORTPICK_LAB_V2_H10_QUIET_CHAMPION_RUN_2026-06-15.md`
- `docs/archive/SHORTPICK_LAB_V2_H10_PAPER_GOVERNANCE_ARTIFACT_2026-06-15.json`
- `plans/active/plan-20260615-h10-paper-governance.md`
- `runs/active/2026-06-15-W-003-h10-paper-governance.md`

Ignored local evidence expected:

- `output/shortpick-v2-h10-paper-governance-artifact.json`
- regenerated prerequisite H10 artifacts under `output/`

## Implementation Steps

1. Add the exact durable marker `H10 paper governance; future true-forward only; fixed90 diagnostic only` to the champion run archive document with a concise governance disposition.
2. Run `bash scripts/run-shortpick-v2-h10-paper-governance.sh` against the runtime DB using the script defaults.
3. Inspect the command result and generated/published artifact summary for ready status, fixed85/fixed80 candidates, fixed90 diagnostic-only state, zero true-forward record count, and research-only labels.
4. If generation fails because the marker or source artifacts are inconsistent, fix only the W-003 scoped durable docs/script/artifact contract issue and rerun the W-003 acceptance command.
5. Record W-003 evidence in this run document and the plan, then validate the plan and archive this run document.

## Acceptance Criteria

The W-003 generation script exits 0, regenerates prerequisite H10 artifacts from the runtime DB, writes and validates both the ignored `output/` paper-governance artifact and the committed `docs/archive/` copy, and verifies the durable champion run marker.

## Acceptance Type

command_exit_0

## Acceptance Spec

`cmd:bash scripts/run-shortpick-v2-h10-paper-governance.sh`

## Planned Evidence

- MiMo run-plan review: passed, no blocker/major.
- Codex escalation run-plan review: passed, no blocker/major/minor.
- Acceptance command output: passed.
- Artifact summary inspection: passed.
- MiMo code/artifact review: passed, no blocker/major; one marker punctuation minor fixed.
- Codex escalation code/artifact review: passed, no blocker/major; doc wording minor fixed.

## Actual Evidence

- `bash scripts/run-shortpick-v2-h10-paper-governance.sh` exited 0. It regenerated replay, selection, parameter-significance, rank-ablation, benchmark robustness, and execution-decomposition artifacts from the runtime DB; validated robustness/execution with 25 checks and 0 failures; built `output/shortpick-v2-h10-paper-governance-artifact.json`; wrote `docs/archive/SHORTPICK_LAB_V2_H10_PAPER_GOVERNANCE_ARTIFACT_2026-06-15.json`; validated both governance artifacts with 32 checks and 0 failures; and verified the durable doc marker.
- Generated artifact summary: `status=ready`, `claim_ceiling=research_observation`, `recommendation.status=forward_observation_ready_with_open_risks`, `recommendation.paper_tracking_status=not_started_no_true_forward_rows`, candidate configs exactly fixed85/fixed80, fixed90 diagnostic-only and paper-tracking-ineligible, ledger policy `future_true_forward_only_no_historical_backfill`, entry policy `declared_entry_date_only_fallback_or_skip_no_delayed_entry`, `record_backfill_allowed=false`, `current_true_forward_record_count=0`, and leakage audit passed.
- Marker check passed after removing the trailing punctuation from the marker line: `H10 paper governance; future true-forward only; fixed90 diagnostic only`.

## Risk And Rollback Notes

Risk: the generation script could create a ready artifact while the durable doc still implies paper-tracking promotion. Mitigation: the marker and new doc text must explicitly say future true-forward only and fixed90 diagnostic only.

Risk: ignored `output/` artifacts could be mistaken for committed source state. Mitigation: only the `docs/archive/` artifact copy is durable source; `output/` is local evidence regenerated by the script.

Risk: runtime DB/artifact generation is slower and more fragile than unit tests. Mitigation: use the single reviewed generation script as the acceptance boundary and record explicit failure context if it fails.

Rollback: remove the W-003 doc marker/update and published docs/archive governance artifact, then rerun the plan from W-003 after correcting the source issue.

## Gate Plan

- MiMo run-plan review before W-003 edits/generation.
- Codex escalation run-plan review before W-003 edits/generation.
- W-003 acceptance command after marker update.
- MiMo code/artifact review after generation.
- Codex escalation code/artifact review after generation.
- Plan validator after updating W-003 evidence.

## MiMo Plan-Review Result

Passed. MiMo found no blocker or major issue. It confirmed W-003 stays inside the approved SRC/PF boundaries: no historical paper-ledger backfill, fixed85/fixed80 future-observation candidates only, fixed90 diagnostic-only, no delayed buy, PF-004 deferred to W-004, and `bash scripts/run-shortpick-v2-h10-paper-governance.sh` is sufficient PF-001 acceptance. Minor notes were to keep the durable marker exactly aligned with the script default and record prerequisite artifact generation failures clearly if they occur.

## Codex Escalation Plan-Review Result

Passed. Codex subagent review was read-only and found no blocker, major, or minor issue. It confirmed the run plan does not drift from the approved plan, the generation script covers runtime DB source generation, artifact validation, docs/archive publication, and marker verification, and W-003 should execute in the run-plan order by adding the marker before running acceptance.

## Implementation Summary

Added the exact H10 paper-governance marker to the durable champion run document and generated the published H10 paper-governance artifact under `docs/archive/`. The generated artifact keeps fixed85/fixed80 as future true-forward observation candidates only, keeps fixed90 diagnostic-only, preserves the prior robustness `not_ready_for_paper_tracking` disposition and open high-risk flags, and does not create or imply historical paper-tracking rows.

## MiMo Code-Review Result

Passed. MiMo found no blocker or major issue in the generated governance artifact, champion doc marker, or run document. It confirmed fixed85/fixed80 are future-observation-only candidates, fixed90 is diagnostic-only, true-forward row count is zero, backfill and delayed buys are blocked, and the claim ceiling remains `research_observation`. Minor marker punctuation was accepted and fixed by removing the trailing period from the marker line.

## Codex Escalation Code-Review Result

Passed. Codex subagent review found no blocker or major issue. It confirmed the artifact and marker satisfy W-003. Minor accepted and fixed: the champion document no longer says "W-003 and W-004 reran the robustness path" before W-004 runtime publish/served verification has occurred.

## Gate Results

- Passed: `bash scripts/run-shortpick-v2-h10-paper-governance.sh`
- Passed: local marker check for `H10 paper governance; future true-forward only; fixed90 diagnostic only`

## Plan Update Summary

Paused before plan update/archive at user request on 2026-06-15T09:48:48Z. Resumed on 2026-06-15T11:11:18Z and fixed the Codex doc wording minor. Updated W-003 to `done` in the schema-v1 plan with acceptance evidence and review dispositions. Plan validator passed: `Plan is valid.`

## Plan Archive Result

Not applicable for W-003 unless the remaining plan completes in the same run.

## Archive And Merge Result

W-003 run document is ready to archive under `runs/archive/2026-06-15-W-003-h10-paper-governance.md`. Full-plan execution continues to W-004; no commit, push, merge, runtime publish, or served verification has been performed yet.
