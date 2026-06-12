# Short Pick Lab V2 Replay Design Run

Status: Completed and archived; pending branch merge closeout
Owner: stock_dashboard
Created: 2026-06-12
Source plan: `docs/contracts/SHORTPICK_LAB_V2_PLAN_2026-06-12.md`
Target phase: Phase 2 - Historical replay design

## Goal

Define the first machine-readable and human-readable replay design contract for `试验田v2`.

This run should complete the plan's Phase 2 outcome: define the v2 replay artifact contract and the limited rule-family matrix. It should not build the replay engine, generate replay results, add APIs, or add frontend tabs.

## Alignment Constraints

| Constraint | Run interpretation |
| --- | --- |
| Separate semantic domain | Add v2-specific contracts instead of extending v1 paper-tracking or replay response contracts. |
| Historical-first promotion | Define replay evidence fields before any user-visible strategy promotion. |
| No delayed entry | Exclude delayed buy from schema, rule families, action taxonomy, examples, and acceptance notes. |
| Bounded promoted set | Define a limited candidate matrix and a later promotion gate; do not expose a parameter search surface. |
| Efficiency boundary | Design for offline/precomputed artifacts that reuse fixed market/candidate inputs. |
| Research labeling | Keep artifact status and claim language in paper/research terms only. |

## Files To Change

| File | Action | Purpose |
| --- | --- | --- |
| `docs/contracts/SHORTPICK_LAB_V2_REPLAY_DESIGN_2026-06-12.md` | Add | Human-readable replay artifact and rule-family design contract. |
| `docs/contracts/registry/schemas/shortpick_v2_replay_artifact.schema.json` | Add | JSON Schema for the replay artifact envelope, config matrix, data scope, summaries, and decision samples. |
| `docs/contracts/SHORTPICK_LAB_V2_PLAN_2026-06-12.md` | Update at closeout | Mark Phase 2 as Done only after implementation, post-implementation MiMo review, and local validation pass; add references to the new design/schema. |
| `docs/contracts/SHORTPICK_LAB_V2_REPLAY_DESIGN_RUN_2026-06-12.md` | Move at closeout | Archive this run plan under `docs/archive/` after implementation and review. |

## Implementation Steps

1. Add the replay design contract document.
   - Define artifact family, version, intended producer/consumer, read-only UI/API expectation, and claim ceiling.
   - Define fixed input domains: candidate source projection, account profile, market bars, cost model, entry/exit assumptions, and leakage boundary.
   - Define output domains: artifact metadata, data scope, rule configurations, account-level summaries, signal-day decision samples, skip/fallback reasons, NAV/position summary references, and gate readouts.
   - Define explicitly that v2 account-path evidence must not be mixed with v1 candidate-level paper tracking.

2. Add the JSON Schema.
   - Use draft 2020-12.
   - Require fields for `artifact_family`, `schema_version`, `artifact_id`, `generated_at`, `status`, `claim_ceiling`, `source_plan_ref`, `data_scope`, `input_contracts`, `rule_matrix`, `results`, `promotion_gate`, `leakage_audit`, and `event_refs`.
   - Keep schema strict enough to prevent delayed-entry actions and live-facing production claims.
   - Allow future details through narrowly placed objects only where later producers need room for metrics.

3. Define the limited rule-family matrix in the design contract.
   - Include top1-or-skip, TopN fallback, fixed-notional lot rounding, capped utilization, and conservative cash reserve families.
   - Treat nominal-share-price effects only as board-lot capital utilization, not as selection alpha.
   - Require each rule to emit deterministic buy/fallback/skip reasons.

4. Run post-implementation review and local validation.
   - Ask MiMo to review code/contract risk and whether final changes drift from this run plan.
   - Validate JSON Schema syntax and schema structure locally.
   - Confirm the final diff is limited to intended contract/schema/doc files.

5. Update the main v2 plan.
   - Change Phase 2 from `Pending` to `Done` only after post-implementation review and local validation pass.
   - Add a short implementation reference to the new design and schema.
   - Leave later phases pending.

6. Archive this run document.
   - Move it to `docs/archive/SHORTPICK_LAB_V2_REPLAY_DESIGN_RUN_2026-06-12.md` only after implementation, MiMo review, and local validation pass.

## Validation Plan

| Check | Purpose |
| --- | --- |
| Read the final diff | Confirm only intended contract/schema/doc files changed. |
| Validate JSON Schema syntax with Python JSON parser | Catch malformed JSON; no runtime services required. |
| Search for delayed-entry leakage terms | Confirm the design does not introduce delayed buy as a valid action. |
| MiMo pre-implementation review | Confirm this run plan does not drift from the v2 plan. |
| MiMo post-implementation review | Confirm the final contract/schema/doc changes do not drift from this run plan and carry no obvious contract risk. |

## Out Of Scope

| Out-of-scope item | Reason |
| --- | --- |
| Python replay engine implementation | Belongs to Phase 3 replay artifact generation. |
| Runtime DB writes or data refresh | Phase 2 is contract design only. |
| API endpoint implementation | Belongs to Phase 6 backend read model. |
| Frontend `试验田v2` tab | Belongs to Phase 7 frontend tab. |
| Strategy promotion or parameter selection | Belongs to Phase 4 candidate rule selection after replay evidence exists. |
| Publish to runtime | No live-facing code changes in this phase. |

## Completion Criteria

| Criterion | Status |
| --- | --- |
| Run plan reviewed by MiMo with no blocking plan-drift issue | Done |
| Replay design contract added | Done |
| JSON Schema added and syntax-validated | Done |
| Main v2 plan Phase 2 updated to Done with references | Done |
| Post-implementation MiMo review has no blocking issue | Done |
| Run document archived | Done |
| Branch merged to `main` and pushed to `origin/main` | Pending final closeout |

## Local Validation Evidence

| Check | Status | Evidence |
| --- | --- | --- |
| JSON syntax | Done | `python3 -m json.tool docs/contracts/registry/schemas/shortpick_v2_replay_artifact.schema.json` returned `JSON_OK`. |
| JSON Schema structure | Done | `jsonschema.Draft202012Validator.check_schema(...)` returned `JSONSCHEMA_SCHEMA_OK`. |
| Sample artifact validation | Done | A bounded in-memory sample artifact validated with `JSONSCHEMA_SAMPLE_OK`. |
| Action taxonomy | Done | Schema action enums contain only `buy_primary`, `buy_fallback`, and `skip`. |
| MiMo post-implementation review | Done | Read-only review found no blocking drift from this run and no blocking contract/schema risk. |
