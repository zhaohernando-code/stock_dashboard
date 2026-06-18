---
schema_version: 1
plan_id: "plan-20260618-shortpick-v2-industry-theme-experiment"
title: "试验田 v2 行业主线实验"
status: "archived"
created_at: "2026-06-18"
source_request: "按标准流程试验行业风口/行业主线方向，但研究结果不直接进入试验田 v2 候选。"
target_repo: "/Users/hernando_zhao/codex/worker-workspaces/stock_dashboard/20260618-shortpick-v2-industry-theme-experiment"
owner: "user"
review_rounds: 2
---

# Plan: 试验田 v2 行业主线实验

## Compaction-Resistant Summary

Goal: research whether industry/theme leadership signals can explain or improve shortpick v2 ranking under the existing H10/20w/fixed85 frame.
Hard boundary: no strategy promotion, no paper-tracking candidate change, no live-facing UI/API change.
Dependencies: existing local DB, v2 replay helpers, archived stage/theme diagnostics, Xiaomi MiMo read-only review.
Major risks: current paper window is short, theme labels can leak future outcomes, simple industry heat was already weak.
Approval state: archived; implementation, experiment artifact, reviews, and gates completed.

## Goal

Run a research-only experiment for industry/theme leadership signals in shortpick v2, with enough evidence to decide whether this direction deserves future candidate work. The output must clearly distinguish diagnostic findings from promotable strategy candidates.

## Problem / Rationale

Recent diagnostics show v2 missed the June 2026 strong-stock cohort even though most winners were in the eligible observation universe. The visible pattern was industry concentration and possible mainline/theme leadership, but a previous simple industry-heat ranking did not beat the current v2 baseline over holdout/full history. We need a bounded experiment that tests richer industry/theme signals without allowing one-month overfit or accidental candidate promotion.

## Source Requirement Coverage

| Source ID | Source Requirement | Plan Coverage | Coverage Status | Scope Decision | Evidence Required |
|-----------|--------------------|---------------|-----------------|----------------|-------------------|
| SRC-001 | Follow the established reviewed plan/run flow for the experiment. | W-001, W-002, W-005 | covered | - | Plan file, MiMo review log, run archive, validation evidence. |
| SRC-002 | Experiment with industry wind/theme leadership directions. | W-003, W-004 | covered | - | Research artifact with industry/theme variant definitions and replay/diagnostic result rows. |
| SRC-003 | Do not directly enter any result into candidates. | W-003, W-004, W-005 | covered | - | Artifact and markdown show research-only promotion status; no paper-governance or frontend candidate files changed. |
| SRC-004 | Preserve prior hard-won findings and avoid repeating known dead ends. | W-001, W-003, W-004 | covered | - | Summary references stage summary, theme diagnostics, and previous weak simple industry-heat ranking. |

## Production Path Fidelity

| Path ID | User / Production Path | Validation Path | Responsibility Owner | Test Setup / Bypass | Fidelity Status | Evidence Required |
|---------|------------------------|-----------------|----------------------|---------------------|-----------------|-------------------|
| PF-001 | Future strategy research uses offline v2 replay helpers and archived artifacts before any paper-candidate governance step. | Run the new research CLI/module against the local database and validate the emitted JSON/markdown. | shortpick v2 research CLI | none | matches_product_path | CLI exits 0, validation exits 0, output declares research-only and no promotion. |
| PF-002 | Paper tracking candidates are controlled by governance artifacts and UI/API read models. | Git diff confirms no paper-governance, paper-ledger, frontend candidate, or runtime display path is changed. | shortpick v2 paper governance | none | matches_product_path | `git diff --name-only` evidence excludes candidate promotion paths. |
| PF-003 | Existing historical diagnostics remain durable references for later work. | Archive a compact report under docs/archive and link relevant prior artifacts. | repository documentation | none | matches_product_path | Markdown report exists with links/references and concise conclusion. |

## Scope

### In Scope

- Add or extend a research-only shortpick v2 experiment for industry/theme leadership signals.
- Compare against the current v2 baseline and the already-failed simple industry-heat variants.
- Measure at minimum historical all, holdout, and paper-window behavior.
- Include current-month strong-stock capture diagnostics so we know whether theme logic actually reaches the stocks v2 missed.
- Archive the JSON artifact and human-readable markdown report.
- Run focused tests/validators and repository policy gates appropriate to code/document changes.

### Out of Scope

- Promoting any variant into paper tracking, candidate groups, frontend cards, scheduled refresh, or live runtime cache.
- Changing v2 buy/sell execution rules, account constraints, H10 horizon, fixed85 baseline, or paper ledger behavior.
- Triggering real daily refresh, LLM calls, market data refresh, or model search.
- Claiming an investable strategy from one paper month or a post-hoc June winner profile.

## Experiment Design

The run must keep the current baseline frame fixed: H10, 20 万初始资金, fixed85 target notional, MTW weekday gate, Rank2 primary with same-day fallback. The experiment changes only the ranking source.

In-scope research variants:

- `theme_breadth_pullback_rank2_mtw`: industry breadth and diffusion first, then pullback setup and liquidity. This tests whether hot industries with multiple advancing members plus non-chasing individual position can improve Top5 entry.
- `theme_leader_rotation_rank2_mtw`: industry leadership plus individual relative strength moderation. This tests whether avoiding the most overheated member while staying inside a hot industry improves paper and holdout behavior.
- `theme_breakout_cluster_rank2_mtw`: industry cluster breakout count plus liquidity. This tests whether several industry peers near short-term highs carry useful mainline information.
- `theme_position_guard_rank2_mtw`: existing quiet Rank2 base with an industry/position guard as a soft ranking modifier, not a hard filter. This tests whether the old baseline can be nudged toward current mainline stocks without destroying historical strength.

Required comparison variants:

- `baseline_quiet_rank2_mtw`: current v2 baseline.
- Previously weak simple ranking replacements, at least `industry_heat_pullback_rank2_mtw`, `industry_heat_amount_rank2_mtw`, and `pullback_low_chase_rank2_mtw`, either rerun or explicitly referenced from the prior artifact.

Out-of-scope known dead ends:

- Simple industry 10 日均值 heat alone as a candidate direction.
- Winner-label-driven ranking using June outcomes.
- Hard industry-only buying or replacing the account execution frame.

Promotion/tie-breaking rule: no variant can be described as candidate-ready in this run. A variant may only be described as "future research worthy" if it beats the baseline on holdout total return by at least 10 percentage points, does not worsen holdout max drawdown by more than 5 percentage points, improves paper-window total return, and improves current-month strong-stock Top5 capture. Anything below that threshold is recorded as a dead end or inconclusive diagnostic.

## Assumptions and Dependencies

- The local database contains enough history through at least 2026-06-17 for current paper-window diagnostics.
- The existing v2 replay helpers are the source of truth for account constraints and H10 execution behavior.
- Industry names already present in daily context are sufficient for this experiment; no new external industry taxonomy is introduced.
- Xiaomi MiMo review is available through the existing local launcher; if it times out repeatedly, the run records the failure and proceeds only when the main agent can bound the risk.

## Work Items

| ID | Status | Order | Depends On | Task | Deliverable | Acceptance Type | Acceptance Spec | Evidence |
|----|--------|-------|------------|------|-------------|-----------------|-----------------|----------|
| W-001 | done | 1 | - | Inventory prior v2 artifacts and define the exact industry/theme experiment family without repeating the failed simple industry-heat direction. | Plan/run evidence and experiment design notes. | file_contains | path:runs/archive/2026-06-18-shortpick-v2-industry-theme-experiment.md \| pattern:Prior evidence inventory: stage summary #11 and #15 | Run document contains the required prior evidence inventory. |
| W-002 | done | 2 | W-001 | Create reviewed execution run record and get MiMo plan/run drift review. | Active then archived run document with MiMo plan-review result. | file_contains | path:runs/archive/2026-06-18-shortpick-v2-industry-theme-experiment.md \| pattern:MiMo plan-review result | MiMo run-plan review found no blocking or major issues; minor notes accepted in run doc. |
| W-003 | done | 3 | W-002 | Implement or extend the research-only industry/theme experiment CLI/module and validation contract. | Research code and tests. | test_pass | cmd:python3 -m pytest -q tests/test_shortpick_v2_industry_theme_experiment.py tests/test_shortpick_v2_ranking_backtest.py | Passed: 7 tests. |
| W-004 | done | 4 | W-003 | Run the experiment against local data and archive the JSON/markdown outputs. | JSON artifact and docs/archive markdown report. | command_exit_0 | cmd:PYTHONPATH=src python3 -m ashare_evidence.cli shortpick-v2-industry-theme-experiment --paper-end-date 2026-06-17 --output output/shortpick-v2-industry-theme-experiment-20260618.json --summary-output docs/archive/SHORTPICK_V2_INDUSTRY_THEME_EXPERIMENT_2026-06-18.md && PYTHONPATH=src python3 -m ashare_evidence.cli shortpick-v2-industry-theme-experiment-validate --artifact output/shortpick-v2-industry-theme-experiment-20260618.json | Generated artifact/report using runtime DB through 2026-06-17; validator passed; no future-research variants. |
| W-005 | done | 5 | W-004 | Close out with MiMo code/result review, gates, plan evidence update, push, merge to main, base push, and cleanup. | Archived run record, archived/done plan handling, merged and pushed branch. | command_exit_0 | cmd:python3 -c 'import subprocess, sys; allowed=("plans/","runs/","docs/archive/","output/","src/ashare_evidence/","tests/"); paths=subprocess.check_output(["git","diff","--name-only","HEAD"], text=True).splitlines(); bad=[p for p in paths if not p.startswith(allowed)]; print("\\n".join(bad)); sys.exit(1 if bad else 0)' && git status --short | MiMo code/result review passed; policy audit passed; default pytest passed. Merge evidence pending final git closeout. |

## Acceptance Criteria & Validation Gates

### Overall Acceptance Criteria

- The experiment outputs a research-only artifact and readable Chinese report.
- The artifact explicitly states no strategy promotion and no paper-candidate change.
- The report explains whether industry/theme signals improved historical, holdout, paper-window, and winner-capture diagnostics versus baseline.
- Known weak directions are labeled as prior failures and are not reintroduced as candidates.
- Any variant below the explicit promotion/tie-breaking threshold is called dead-end or inconclusive, never "candidate-ready".
- The final diff contains no live-facing paper-candidate or scheduled-refresh change.
- The task branch is pushed, merged into main, main is pushed, and temporary worktree state is cleaned unless a recorded blocker prevents merge.

### Validation Gates

- `python3 $CODEX_HOME/skills/reviewed-plan-generator/scripts/validate_plan.py plans/active/plan-20260618-shortpick-v2-industry-theme-experiment.md`
- MiMo read-only plan review.
- `python3 -m pytest -q tests/test_shortpick_v2_industry_theme_experiment.py tests/test_shortpick_v2_ranking_backtest.py`
- `PYTHONPATH=src python3 -m ashare_evidence.cli shortpick-v2-industry-theme-experiment --paper-end-date 2026-06-17 --output output/shortpick-v2-industry-theme-experiment-20260618.json --summary-output docs/archive/SHORTPICK_V2_INDUSTRY_THEME_EXPERIMENT_2026-06-18.md`
- `PYTHONPATH=src python3 -m ashare_evidence.cli shortpick-v2-industry-theme-experiment-validate --artifact output/shortpick-v2-industry-theme-experiment-20260618.json`
- `PYTHONPATH=src python3 -m ashare_evidence.cli policy-audit --fail-on-new-unclassified --fail-on-direct-config-read --fail-on-formula-side-effects --fail-on-missing-config-lineage`
- MiMo read-only code/result review, including a conclusion-language check that fails the run if the report suggests candidate promotion or investable readiness.

## Risks and Mitigations

- Risk: June winner labels create leakage. Mitigation: use winner capture only as post-hoc diagnostic; simulated rankings only use signal-day-or-earlier context.
- Risk: industry signal overfits a short paper window. Mitigation: require historical all and holdout comparison before any future candidate discussion.
- Risk: repeating already-failed simple industry heat. Mitigation: explicitly compare against prior failed variants and test richer breadth/diffusion/position-shape signals.
- Risk: performance cost from full replay. Mitigation: reuse loaded daily series and existing replay helpers inside one artifact build.
- Risk: accidental promotion. Mitigation: no governance/frontend/paper-ledger path changes; artifact validator checks research-only promotion status.

## Open Questions

- None for execution. If all variants fail, the deliverable is still a useful dead-end map rather than a candidate proposal.

## Revision History

| Round | Date | Change |
|-------|------|--------|
| 0 | 2026-06-18 | Initial draft plan for research-only industry/theme experiment. |
| 1 | 2026-06-18 | Accepted MiMo feedback: added explicit variant list, prior-failure boundaries, quantitative future-research threshold, conclusion-language check, and stronger forbidden-path closeout check. |
| 2 | 2026-06-18 | MiMo focused rereview found no blocking or major findings; user instruction treated as approval to execute. |
| 3 | 2026-06-18 | Completed implementation, generated research artifact/report, passed MiMo code/result review and gates, and marked work items done. |
| 4 | 2026-06-18 | Archived completed plan and run record for merge closeout. |

## External Review Log

| Round | Reviewer | Finding | Severity | Disposition | Reason | Affected IDs |
|-------|----------|---------|----------|-------------|--------|--------------|
| 1 | MiMo | Experiment variants were too vague, so execution could drift or repeat known failed directions. | major | accepted | Added `Experiment Design` with in-scope variants, required comparisons, and out-of-scope dead ends. | W-001, W-003, W-004 |
| 1 | MiMo | Missing quantitative threshold could allow marginal results to be softly promoted. | major | accepted | Added explicit holdout/drawdown/paper/capture threshold and required below-threshold wording as dead-end or inconclusive. | W-004, W-005 |
| 1 | MiMo | Hard-coded paper end date could become stale if execution is delayed. | minor | accepted | Kept 2026-06-17 for this immediate run because the latest fixed data requirement was 2026-06-17; W-004 report must record actual cutoff. | W-004 |
| 1 | MiMo | Result review should check conclusion language for overclaiming. | minor | accepted | Added MiMo conclusion-language gate. | W-005 |
| 1 | MiMo | Prior evidence inventory should explicitly cite the old weak ranking and theme diagnostic. | minor | accepted | Tightened W-001 acceptance pattern to stage summary #11 and #15. | W-001 |
| 1 | MiMo | `git status --short` alone is too broad for no-promotion path proof. | note | accepted | Replaced W-005 command with forbidden-path diff check plus status output. | W-005 |
| 2 | MiMo | Rereview found the variant list and no-promotion threshold sufficient; no blocking or major issues remain. | note | resolved | Proceeding with execution. Minor implementation notes will be handled in validator/report wording. | W-003, W-004, W-005 |

## User Review Notes

- User requested standard flow execution and explicitly said the tested directions should not directly enter candidates.
