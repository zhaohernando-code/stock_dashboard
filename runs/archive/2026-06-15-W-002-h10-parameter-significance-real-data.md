# Run ID

2026-06-15-W-002-h10-parameter-significance-real-data

## Plan path

/Users/hernando_zhao/codex/worker-workspaces/20260614-shortpick-v2-robust-strategy-search-42e/20260615-h10-param-significance-adbc6f/plans/active/plan-20260615-h10-parameter-significance.md

## Hop ID

W-002

## Work item ID

W-002

## Goal

Run the real-data H10 parameter-significance artifact command against the runtime SQLite database and write the JSON artifact under `output/`.

## Non-goals

- Do not validate the generated artifact in this hop; W-003 owns that.
- Do not write to the runtime database or refresh market data.
- Do not publish runtime/frontend changes.
- Do not reinterpret or promote parameters beyond the command output.

## Plan evidence

W-002 acceptance is the exact real-data command:

`PYTHONPATH=src python3 -m ashare_evidence.cli shortpick-v2-h10-parameter-significance --database-url sqlite:////Users/hernando_zhao/codex/runtime/projects/ashare-dashboard/data/ashare_dashboard.db --horizon-days 10 --initial-cash 200000 --output output/shortpick-v2-h10-parameter-significance-artifact.json`

## Source coverage evidence

| Source ID | Run evidence |
|-----------|--------------|
| SRC-001 | This run continues the reviewed plan/run workflow after W-001 completed. |
| SRC-002 | The command passes `--horizon-days 10`; the builder rejects non-H10. |
| SRC-003 | The artifact command emits parameter rows for weekday, rank, pool-hot, fixed-notional, fallback/skip, and concentration/stability families. |
| SRC-004 | The generator uses the h10 quiet champion candidate batch around fixed85/fixed80 `quiet_breakout_rank2_poolhot10_mtw`. |
| SRC-005 | Parameter rows carry support labels and evidence basis. |
| SRC-006 | The artifact remains `claim_ceiling=research_observation` and recommendation status stays research-only. |

## Files expected to change

- `output/shortpick-v2-h10-parameter-significance-artifact.json`
- `plans/active/plan-20260615-h10-parameter-significance.md`
- `runs/archive/2026-06-15-W-002-h10-parameter-significance-real-data.md`

## Implementation steps

1. Run MiMo run-plan review.
2. Run the W-002 real-data artifact command exactly as specified.
3. Record exit code and output summary.
4. Mark W-002 done if the command exits 0 and the artifact file exists.

## Acceptance criteria

The W-002 command exits 0 and writes `output/shortpick-v2-h10-parameter-significance-artifact.json`.

## Acceptance Type

command_exit_0

## Acceptance Spec

cmd:PYTHONPATH=src python3 -m ashare_evidence.cli shortpick-v2-h10-parameter-significance --database-url sqlite:////Users/hernando_zhao/codex/runtime/projects/ashare-dashboard/data/ashare_dashboard.db --horizon-days 10 --initial-cash 200000 --output output/shortpick-v2-h10-parameter-significance-artifact.json

## Planned Evidence

- MiMo run-plan review has no blocking or major findings.
- Real-data command exits 0 and prints an artifact summary.
- The output JSON file exists.

## Actual Evidence

- MiMo run-plan review passed with no blocking or major findings.
- Command exited 0: `PYTHONPATH=src python3 -m ashare_evidence.cli shortpick-v2-h10-parameter-significance --database-url sqlite:////Users/hernando_zhao/codex/runtime/projects/ashare-dashboard/data/ashare_dashboard.db --horizon-days 10 --initial-cash 200000 --output output/shortpick-v2-h10-parameter-significance-artifact.json`.
- Wrote `output/shortpick-v2-h10-parameter-significance-artifact.json` (14KB).
- CLI summary: artifact id `shortpick_v2_h10_parameter_significance:2023-05-16:2026-05-08:20260615`, 7 parameter rows, support counts `supported=4`, `inconclusive=3`, recommendation `research_only_no_paper_tracking_promotion`.

## Risk and rollback notes

The command is read-only against runtime DB and writes only a local output artifact. Rollback is deleting the generated output file before commit if it is invalid or out of scope.

## Gate plan

- Plan validator before command execution.
- MiMo run-plan review before command execution.
- W-002 command exit 0.

## MiMo plan-review result

Passed with no blocking or major findings. MiMo confirmed W-002 is limited to real-data artifact generation and does not drift into W-003 validation or W-004 interpretation.

## Codex escalation plan-review result

Not required unless MiMo reports blocking/major issues.

## Implementation summary

Ran the real-data parameter-significance CLI against the runtime SQLite DB and generated the local output JSON artifact. The command used fixed `--horizon-days 10` and retained the current h10 quiet benchmark context.

## MiMo code-review result

Not applicable for W-002 unless command output reveals a code defect.

## Codex escalation code-review result

Not required.

## Gate results

- W-002 command: exit 0.
- Output file exists: `output/shortpick-v2-h10-parameter-significance-artifact.json`.

## Plan update summary

W-002 was updated from in_progress to done with command output evidence in the plan.

## Plan archive result

Not applicable until all work items complete.

## Archive and merge result

Archived to `runs/archive/2026-06-15-W-002-h10-parameter-significance-real-data.md` before the W-002 commit.
