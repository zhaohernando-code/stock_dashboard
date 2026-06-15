# Run ID

2026-06-15-W-002-h10-rank-ablation-real-data

## Plan path

/Users/hernando_zhao/codex/worker-workspaces/stock_dashboard/20260615-h10-rank-ablation-140929/plans/active/plan-20260615-h10-rank-ablation.md

## Hop ID

W-002

## Work item ID

W-002

## Goal

Run the real-data H10 rank-ablation artifact command against the runtime SQLite database and write the JSON artifact under `output/`.

## Non-goals

- Do not validate the generated artifact in this hop; W-003 owns validation.
- Do not interpret, promote, or replace the benchmark in this hop; W-004 owns interpretation.
- Do not write to the runtime database or refresh market data.
- Do not publish runtime/frontend changes.

## Plan evidence

W-002 acceptance is the exact real-data command:

`PYTHONPATH=src python3 -m ashare_evidence.cli shortpick-v2-h10-rank-ablation --database-url sqlite:////Users/hernando_zhao/codex/runtime/projects/ashare-dashboard/data/ashare_dashboard.db --horizon-days 10 --initial-cash 200000 --output output/shortpick-v2-h10-rank-ablation-artifact.json`

## Source coverage evidence

| Source ID | Run evidence |
|-----------|--------------|
| SRC-001 | This run continues the reviewed plan/run workflow after W-001 completed. |
| SRC-002 | The command passes `--horizon-days 10`; the builder rejects non-H10. |
| SRC-003 | The artifact command emits same-gate rank rows for rank1/rank2/rank3 under MTW + poolhot10. |
| SRC-004 | The generator uses the h10 quiet champion candidate batch anchored on `quiet_breakout_rank2_poolhot10_mtw`. |
| SRC-005 | The artifact remains fallback-or-skip and introduces no delayed-buy action. |
| SRC-006 | The artifact keeps `claim_ceiling=research_observation` and recommendation status research-only. |

## Files expected to change

- `output/shortpick-v2-h10-rank-ablation-artifact.json`
- `plans/active/plan-20260615-h10-rank-ablation.md`
- `runs/archive/2026-06-15-W-002-h10-rank-ablation-real-data.md`

## Implementation steps

1. Run MiMo run-plan review.
2. Run the W-002 real-data artifact command exactly as specified.
3. Record exit code, output path, artifact id, rank2 status, and rank row count.
4. Update the plan's W-002 row and mark W-002 done if the command exits 0 and the artifact file exists.

## Acceptance criteria

The W-002 command exits 0 and writes `output/shortpick-v2-h10-rank-ablation-artifact.json`.

## Acceptance Type

command_exit_0

## Acceptance Spec

cmd:PYTHONPATH=src python3 -m ashare_evidence.cli shortpick-v2-h10-rank-ablation --database-url sqlite:////Users/hernando_zhao/codex/runtime/projects/ashare-dashboard/data/ashare_dashboard.db --horizon-days 10 --initial-cash 200000 --output output/shortpick-v2-h10-rank-ablation-artifact.json

## Planned Evidence

- MiMo run-plan review has no blocking or major findings.
- Real-data command exits 0 and prints an artifact summary.
- The output JSON file exists.

## Actual Evidence

- MiMo run-plan review passed with no blocking or major findings.
- Command exited 0: `PYTHONPATH=src python3 -m ashare_evidence.cli shortpick-v2-h10-rank-ablation --database-url sqlite:////Users/hernando_zhao/codex/runtime/projects/ashare-dashboard/data/ashare_dashboard.db --horizon-days 10 --initial-cash 200000 --output output/shortpick-v2-h10-rank-ablation-artifact.json`.
- Wrote `output/shortpick-v2-h10-rank-ablation-artifact.json` (14KB).
- CLI summary: artifact id `shortpick_v2_h10_rank_ablation:2023-05-16:2026-05-08:20260615`, `rank2_status=supported`, `rank_row_count=5`, recommendation `research_only_no_paper_tracking_promotion`.
- Artifact preview: fixed85 rank2 total return `+271.23%`, rank1 `+60.74%`, rank3 `+50.80%`; all mandatory rows have `sample_count >= 175` and `period_block_count=4`.

## Risk and rollback notes

The command is read-only against the runtime DB and writes only a local output artifact. Rollback is deleting the generated output file before W-003 if it is invalid or out of scope.

## Gate plan

- Plan validator before command execution.
- MiMo run-plan review before command execution.
- W-002 command exit 0.

## MiMo plan-review result

Passed with no blocking or major findings. MiMo reported one minor clarification: because the plan file is listed in expected changes, the run record should explicitly say W-002 writes back the plan row. This was accepted in the implementation steps.

## Codex escalation plan-review result

Not required unless MiMo reports blocking/major issues.

## Implementation summary

Ran the real-data rank-ablation CLI against the runtime SQLite DB and generated the local output JSON artifact. The command used fixed `--horizon-days 10` and retained the h10 quiet champion candidate batch.

## MiMo code-review result

Not applicable for W-002 unless command output reveals a code defect.

## Codex escalation code-review result

Not required.

## Gate results

- W-002 command: exit 0.
- Output file exists: `output/shortpick-v2-h10-rank-ablation-artifact.json`.

## Plan update summary

W-002 was updated from pending to in_progress after W-001 completion, then to done after the real-data command exited 0 and wrote the artifact.

## Plan archive result

Not applicable until all work items complete.

## Archive and merge result

Archived to `runs/archive/2026-06-15-W-002-h10-rank-ablation-real-data.md` before the W-002 commit.
