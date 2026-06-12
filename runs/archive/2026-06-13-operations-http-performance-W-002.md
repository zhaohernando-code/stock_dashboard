# Run ID

2026-06-13-operations-http-performance-W-002

## Plan path

/Users/hernando_zhao/codex/worker-workspaces/stock_dashboard/20260613-stabilize-operations-http-performance-c090a7/plans/active/plan-20260613-operations-http-performance.md

## Hop ID

W-002

## Work item ID

W-002

## Goal

Change release verification so operations API payloads fetched during warmup are reused for fingerprinting and audit, eliminating duplicate cold operations requests after successful warmup.

## Non-goals

- Do not change the release verifier's public purpose, canonical/local parity semantics, auth behavior, or endpoint list except as needed to reuse already fetched operations payloads.
- Do not implement the runtime performance probe script or publish the candidate in this hop.
- Do not broaden W-001 operations endpoint behavior.

## Plan evidence

W-002 depends on W-001 and addresses the verifier-specific source of repeated cold calls: operations endpoints are warmed, then fetched again for fingerprinting.

## Files expected to change

- `src/ashare_evidence/release_verifier.py`
- `tests/test_release_verifier.py`
- `tests/test_publish_script_static.py` only if static publish/verifier contract assertions need adjustment
- `plans/active/plan-20260613-operations-http-performance.md`
- `runs/archive/2026-06-13-operations-http-performance-W-002.md` after closeout

## Implementation steps

1. Inspect the current `warm_operations_api_endpoints` and fingerprint loop data flow.
2. Add an explicit in-memory warmup payload handoff for operations endpoints while keeping manifest warmup metadata compact.
3. Make fingerprinting consume the warmed local/canonical payloads when present.
4. When a warmed payload is unavailable for an operations endpoint, perform at most one bounded request per missing local/canonical side, and mark the fingerprint source per side as a warmup miss.
5. Preserve local/canonical snapshot artifacts from the exact payloads used for fingerprinting and audit.
6. Add tests proving successful warmup avoids a second operations fetch, warmup-miss fallback remains explicit, and mismatched warmed local/canonical payloads still fail parity verification.
7. Run the W-002 acceptance gate.

## Acceptance criteria

- Operations endpoints warmed successfully are not fetched a second time for fingerprinting.
- Fingerprints still compare local and canonical payloads.
- Missing warmup payloads take at most one bounded fallback fetch per missing side and surface `local_source` / `canonical_source` evidence.
- Warmed local/canonical payload mismatches still fail fingerprint parity.
- Snapshot artifacts are written from the exact payloads used for fingerprinting and audit.
- Existing release verifier tests continue to pass.

## Acceptance Type

test_pass

## Acceptance Spec

cmd:python3 -m pytest -q tests/test_release_verifier.py tests/test_publish_script_static.py

## Planned Evidence

- MiMo run-plan review result.
- Codex escalation plan-review result because this hop touches release/deployment verification behavior.
- MiMo code-review result.
- Codex escalation code-review result.
- Acceptance gate command and exit code.

## Actual Evidence

- Implemented in-memory operations warmup payload handoff without adding payload bodies to `api_warmups` manifest metadata.
- Fingerprint collection now consumes warmed operations payloads per local/canonical side and records `local_source` / `canonical_source` as `warmup`, `warmup_miss`, or `fetch`.
- Snapshot files are written from the exact payloads used for fingerprinting and audit.
- Added tests for no second fetch after warmup, local-missing/canonical-missing fallback source handling, and distinct warmed local/canonical payload mismatch through `_api_payload_pair_for_fingerprint` into `_record_api_fingerprint`.
- Acceptance gate passed: `python3 -m pytest -q tests/test_release_verifier.py tests/test_publish_script_static.py` exited 0 with `23 passed in 0.24s`.

## Risk and rollback notes

Primary risk is masking local/canonical mismatches by accidentally reusing the wrong side's payload. Mitigation is to carry local and canonical payloads separately, record payload source per side, keep writing snapshots from the exact payloads fingerprinted, and continue computing parity fingerprints from both. Rollback is reverting to the prior fetch-per-fingerprint path, accepting the known cold-call cost.

## Gate plan

Run `python3 -m pytest -q tests/test_release_verifier.py tests/test_publish_script_static.py`.

## MiMo plan-review result

Passed. MiMo found no blocking, material, or minor drift.

## Codex escalation plan-review result

Passed. Codex found no blocking or material issues. Minor guidance accepted into this run plan: side-specific warmup-miss source tracking, a negative warmed-payload parity test, and preserving snapshots from the exact payloads used for fingerprinting/audit.

## Implementation summary

`warm_operations_api_endpoints` accepts an optional in-memory `warmup_payloads` collector. `verify_release_parity` passes that collector into the fingerprint loop, where `_api_payload_pair_for_fingerprint` reuses warmed operations payloads by side or performs one bounded fallback request for a missing side. `_record_api_fingerprint` writes snapshots and fingerprint evidence from the selected payloads and still raises on local/canonical mismatch.

## MiMo code-review result

Passed. MiMo found no blocking or material issues in the W-002 implementation. After Codex identified a material test gap, MiMo's focused re-review confirmed the gap was closed.

## Codex escalation code-review result

Passed after one material test-coverage finding was fixed. Initial Codex review found that warmed mismatch coverage bypassed `_api_payload_pair_for_fingerprint`; the test now passes distinct warmed local/canonical payloads through the pair helper into `_record_api_fingerprint`, patches `_timed_request_json` to fail, and verifies mismatch plus exact snapshots. Focused Codex re-review found no blocking or material issues.

## Gate results

Passed: `python3 -m pytest -q tests/test_release_verifier.py tests/test_publish_script_static.py` exited 0 with `23 passed in 0.24s`.

## Plan update summary

W-002 completed and plan evidence updated.

## Plan archive result

Not applicable for W-002; the full plan remains active until all work items complete.

## Archive and merge result

Archived for later commit. The branch will not merge until W-004 passes because the plan is being executed in full-plan mode.
