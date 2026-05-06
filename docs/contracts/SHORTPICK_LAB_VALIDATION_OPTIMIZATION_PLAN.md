# Short Pick Lab Validation Optimization Plan

Status: p0_p3_completed_p4_gate_scaffold_published
Owner: codex
Created: 2026-05-07
Scope: shortpick_lab validation, feedback aggregation, source/search robustness, and theme normalization
Last updated: 2026-05-07

## Purpose

This plan turns the first Short Pick Lab observations into a tracked implementation backlog. The goal is not to make trial candidates look better; it is to make the lab's statistics executable, auditable, and hard to misuse.

Current runtime evidence shows the pipeline is working, but the first completed validation rows are not yet valid proof of model selection ability. The main reasons are:

- The existing entry logic can use the previous trading-day close for a recommendation generated after that close.
- A-share T+1 means a next-day buy cannot realize same-day gains, so next-day limit-up behavior must not be counted as sellable first-day performance.
- Shortpick candidates currently have reliable `1d` coverage, while `5min` coverage is limited to a small set of watchlist / simulation symbols.
- Model feedback currently aggregates candidate-horizon rows, which overweights duplicate symbols and long horizon rows.
- Theme feedback is based on raw model theme strings, so semantically similar themes such as rare earth pricing or low-altitude economy split into unrelated buckets.

## Non-Negotiable Constraints

- The lab remains isolated. No Short Pick Lab output may write into `Recommendation`, `ModelResult`, watchlist membership, main candidate pool, simulation auto-model weights, or production scoring.
- This is a pure AI/system project. No plan step may require the operator to manually label source quality, theme classes, candidate truth, or tradeability.
- Search-required executors must fail closed. If DeepSeek/SearXNG cannot produce enough usable public sources after bounded repair attempts, the round fails and stays in diagnostics. It must not degrade into pure reasoning output.
- Validation must distinguish information availability from executable trade availability.
- All public performance claims must name the validation mode and sample basis. Legacy or diagnostic rows must not be mixed into official capability metrics.

## Target Validation Contract

### Official Mode

Name: `after_close_t_plus_1_close_entry_v1`

This is the default official validation mode for Short Pick Lab until stable all-candidate intraday coverage exists.

Definitions:

- `signal_available_at`: the model round completion time, not just `run_date`.
- `signal_trade_day`: the trading day whose information was available when the signal was produced.
- `entry_trade_day`: the first trading day after `signal_available_at` for which a completed daily close exists and the symbol is tradeable.
- `entry_price`: `entry_trade_day` close.
- `exit_trade_day(horizon=N)`: the N-th trading day after `entry_trade_day`.
- `exit_price`: `exit_trade_day` close.
- `stock_return`: `exit_price / entry_price - 1`.
- `benchmark_return`: benchmark close-to-close return from `entry_trade_day` to `exit_trade_day`.
- `excess_return`: `stock_return - benchmark_return`.

Important implication:

- A recommendation generated after close on day D cannot enter at day D close.
- A recommendation generated during a holiday cannot enter at the last pre-holiday close.
- The `1d` horizon means the first close where a T+1 buyer can evaluate sellable performance, not the same close used for entry.

### Diagnostic Modes

Diagnostic modes are allowed for research visibility, but are excluded from official model feedback unless explicitly selected.

- `signal_reaction_close_to_close`: previous available close to next available close. This measures market reaction to the information window, not executable return.
- `next_open_nominal`: next trading-day open entry. This remains unavailable for official aggregation until all-candidate open price and limit-up fillability checks are stable.
- `legacy_previous_close_entry`: current historical behavior, retained only to explain old rows and migration.

## Tradeability Contract

Every validation snapshot must carry a `tradeability_status`.

Initial statuses:

- `tradeable`: entry close can be used in official aggregation.
- `entry_unfillable_limit_up`: the symbol appears impossible or highly unrealistic to buy at the planned entry point because of one-price limit-up or equivalent constraints.
- `suspended_or_no_current_bar`: daily bars are stale or the symbol has no current tradeable bar.
- `pending_market_data`: the entry or exit bar has not landed yet.
- `pending_benchmark_data`: stock bars are available but benchmark bars are missing.
- `invalid_execution_assumption`: legacy rows where entry precedes signal availability.

System-only detection, no human labels:

- Use OHLC daily bars to flag one-price limit-up candidates when open, high, low, and close are effectively identical and the daily return is near the applicable limit threshold.
- Use stale latest bar dates to flag suspension or unresolved market-data gaps.
- Use exchange/board metadata where available to infer 10%, 20%, or special treatment limit bands. If the band is unknown, mark as `tradeability_uncertain` and exclude from official aggregation until inferred.
- Persist raw detection evidence in `validation_payload`, including prior close, entry open/high/low/close, inferred limit band, and reason.

## Aggregation Contract

Model feedback must expose separate sample bases:

- `candidate_row_count`: raw candidate rows.
- `candidate_horizon_row_count`: validation rows across horizons.
- `unique_symbol_run_count`: unique `(run_id, symbol)` rows.
- `official_sample_count`: rows included in official aggregation after validation mode and tradeability filters.
- `completed_official_sample_count`: completed official rows with return metrics.

Official model performance must aggregate primarily on unique symbol-run rows. Candidate-row and candidate-horizon metrics can remain visible as behavior diagnostics, but they must not be the default model-quality headline.

Duplicate handling:

- Same model repeats same symbol in one run: keep both candidate rows, but official performance counts the symbol once for that model/run/horizon.
- Cross-model same symbol: count once in overall symbol-run performance, and separately count as cross-model consensus evidence.
- Multiple themes for the same symbol: retain raw themes, but normalize them into system-generated topic clusters.

## Consensus Contract

The current linear priority score is not a good fit for `2 models x 5 rounds` open discovery. Replace it with explicit AI/system-derived categories:

- `cross_model_same_symbol`: at least two providers independently choose the same symbol in the same run.
- `same_model_repeat_symbol`: one provider repeats the same symbol in the same run.
- `cross_model_same_topic`: different providers choose different symbols that normalize into the same topic cluster.
- `single_model_high_conviction`: single-provider candidate with high confidence, high source quality, and no tradeability red flag.
- `divergent_novel`: valid external candidate that does not converge by symbol or topic.
- `watch_only`: internal/system-known candidate or weak validation/source status.
- `failed_or_unusable`: parse failed, source failed, or tradeability invalid.

These categories are research priorities only. They do not imply verified advice.

## AI-Led Topic Normalization

Raw theme strings are insufficient. The lab needs a structured topic layer generated by AI, with deterministic code used only for guardrails, caching, and non-semantic normalization. Hard keyword logic must not be the primary clustering mechanism because it cannot reliably distinguish overlapping A-share themes, event chains, and weakly related narratives.

### Topic Schema

Each parsed candidate should have:

- `topic_cluster_id`: stable slug, such as `rare_earth_price_security`, `low_altitude_economy`, `ai_compute_hardware`, `commercial_space`, `grid_equipment`.
- `topic_labels`: readable Chinese labels.
- `topic_keywords`: extracted core keywords.
- `topic_drivers`: structured drivers such as `policy`, `price_change`, `earnings`, `contract_order`, `market_hotspot`, `industry_chain`.
- `topic_confidence`: model/system confidence.
- `topic_evidence_refs`: source URLs or source indexes that support the topic.
- `normalization_method`: `rules_v1`, `llm_structured_v1`, or `hybrid_v1`.

### Normalization Pipeline

The default path is AI-led:

1. Build a compact candidate packet from `theme`, `thesis`, catalysts, risks, source titles, source domains, and model metadata.
2. Ask an LLM to assign one or more topic clusters using a strict JSON schema.
3. The LLM must either map to an existing topic, split a broad topic into a child topic, or propose a new topic with evidence and a confidence score.
4. A second lightweight verifier pass checks whether the assigned topic is actually supported by the candidate packet and sources.
5. Deterministic code validates schema, normalizes slugs, deduplicates near-identical labels, stores artifacts, and prevents unstable labels from becoming canonical too early.
6. If AI classification fails after bounded repair, keep raw theme and mark `topic_cluster_id=unclassified`; do not request manual labeling.

Deterministic rules are allowed only for:

- Exact alias normalization after the AI has identified the semantic cluster.
- Slug stability, for example converting "稀土价格/战略资源" into `rare_earth_price_security`.
- Merging labels that the AI already judged equivalent across multiple runs.
- Blocking obviously invalid clusters such as a source-domain name or a single company name when the task is topic classification.

Deterministic rules must not be the primary decision engine for whether `低空经济`, `商业航天`, `算力硬件`, `稀土价格`, or any future theme belongs together.

### AI Topic Classifier Contract

The classifier output must include:

```json
{
  "primary_topic": {
    "topic_cluster_id": "rare_earth_price_security",
    "label_zh": "稀土价格与战略资源安全",
    "confidence": 0.0,
    "reason": "为什么这个候选属于该题材",
    "supporting_evidence_refs": [0, 2],
    "driver_types": ["price_change", "resource_security", "industry_policy"]
  },
  "secondary_topics": [],
  "new_topic_proposal": null,
  "not_topic_reason": null
}
```

The verifier output must include:

```json
{
  "verdict": "supported",
  "confidence": 0.0,
  "unsupported_claims": [],
  "suggested_topic_cluster_id": null
}
```

If classifier and verifier disagree materially, mark the topic as `topic_uncertain` and exclude it from topic-level performance aggregation until a later automated reclassification pass resolves it.

### Topic Registry

Maintain an AI-generated topic registry as an artifact, not as hand-authored labels.

Registry fields:

- `topic_cluster_id`
- `label_zh`
- `description`
- `known_aliases`
- `positive_examples`
- `negative_examples`
- `created_by_run_id`
- `last_confirmed_at`
- `evidence_count`
- `status`: `candidate`, `active`, `deprecated`, or `merged`

Promotion rules:

- New topics start as `candidate`.
- A topic becomes `active` only after repeated AI classifications across separate runs or cross-provider agreement.
- A topic can be `merged` when later AI passes judge two topics semantically equivalent.
- All promotions/merges are system decisions with artifact evidence; no manual labeling is required.

### Topic Performance

Topic feedback must show:

- Topic-level official sample count.
- Symbol count and provider count per topic.
- Dispersion inside the topic, because the same theme can contain both strong and weak picks.
- Best/worst symbol contribution, with outlier-excluded mean.
- Cross-model topic agreement separate from same-symbol agreement.

This directly addresses cases where low-altitude economy or rare earth themes split across raw strings and where same-theme candidates perform very differently.

## Source And Search Robustness

### DeepSeek/SearXNG Fail-Closed Repair

Allowed repair attempts:

- Search-plan JSON repair: one deterministic JSON-only repair attempt.
- Search query retry: up to 2 attempts per query when the backend errors.
- Query expansion: one system-generated expansion pass if total usable results are below threshold.
- Final-answer JSON repair: one JSON-only repair pass against the raw answer.
- Source integrity retry: recheck transient URL failures once before classifying.

Required failure behavior:

- If usable public sources remain below threshold, mark the round failed.
- Do not create a normal candidate.
- Persist `failure_stage`, `attempt_count`, search queries, result counts, source statuses, raw error, and artifact id.

### Source Authority Without Human Labels

Add system-derived source scoring:

- `exchange_or_company_disclosure`
- `designated_disclosure_media`
- `mainstream_financial_media`
- `vertical_industry_media`
- `broker_research_or_pdf`
- `community_or_forum`
- `aggregator_or_unknown`

Initial classification can be domain-rule based and then refined by AI extraction from title/URL/content snippets. No manual labels required.

Source scoring should affect research quality indicators, not official return math.

## Baseline And Go/No-Go Plan

No model capability judgment is allowed until P0 validation mode is implemented and old rows are migrated or excluded.

Minimum evaluation checkpoints after P0:

- Checkpoint A: 30 unique symbol-run rows with completed `3d` official validation.
- Checkpoint B: 50 unique symbol-run rows with completed `5d` official validation.
- Checkpoint C: 100 unique symbol-run rows with completed `5d` official validation across multiple market regimes.

Required baselines:

- `random_same_market_cap_bucket`
- `momentum_volume_baseline`
- `topic_peer_baseline`

Initial go/no-go gates:

- `5d` official mean excess return is positive after outlier trimming.
- `5d` official positive excess rate is above baseline by a meaningful margin.
- Performance remains positive after removing the single best symbol and the single best day.
- Cross-model same-symbol and cross-model same-topic buckets outperform divergent buckets, or the consensus layer is not useful.
- Search/source failure rows remain excluded from official samples.

## Implementation Phases

### P0 - Truthful Executable Validation

Status: completed

Tasks:

- [x] Add validation mode fields to shortpick validation payloads and API schemas.
- [x] Implement `after_close_t_plus_1_close_entry_v1` entry/exit resolver.
- [x] Detect and exclude legacy invalid execution assumptions from official aggregation.
- [x] Add tradeability status and evidence payload.
- [x] Recompute or mark existing Run 1 rows as diagnostic-only.
- [x] Update model feedback to default to official samples only.
- [x] Add regression tests for holiday-generated runs, after-close runs, and T+1 `1d` exit semantics.

Acceptance:

- A 2026-05-05 holiday run no longer enters at 2026-04-30 close.
- `1d` official exit is the first sellable close after entry, not the entry day close.
- Stale symbols such as missing-current-bar candidates do not appear as normal pending forward windows.
- Frontend labels distinguish official and diagnostic validation modes.

### P1 - Feedback Aggregation And Consensus Repair

Status: completed

Tasks:

- [x] Split candidate-row, candidate-horizon, unique-symbol-run, and official sample metrics.
- [x] Replace run-level linear priority score with explicit consensus categories.
- [x] Count same-model repeat and cross-model agreement separately.
- [x] Add outlier-excluded aggregate metrics.
- [x] Update frontend model feedback labels so `sample_count` is not ambiguous.

Acceptance:

- Duplicate symbols do not overweight official performance.
- Cross-model same-symbol candidates are visible even when raw discovery remains diverse.
- Run-level priority no longer depends on an unreachable `7/10 same symbol` style threshold.

### P2 - AI-Led Topic Normalization

Status: completed

Tasks:

- [x] Add topic normalization fields to candidate payload / serialized API.
- [x] Implement AI topic classifier with strict JSON schema.
- [x] Implement AI verifier pass for classifier/source support.
- [x] Add deterministic schema validation, slug stabilization, and registry artifact storage.
- [x] Store topic normalization artifacts and failure states.
- [x] Add topic-level feedback grouped by normalized topic, not raw theme string.
- [x] Add topic registry with `candidate / active / deprecated / merged` states.
- [x] Add tests for rare earth, low-altitude economy, AI compute hardware, commercial space, and grid equipment clustering.

Acceptance:

- `稀土价格上行`, `战略资源`, and `央企稀土整合` cluster together.
- `低空经济`, `通航`, and `航空运营` cluster together while still showing dispersion by symbol.
- Topic feedback exposes both topic-level performance and within-topic best/worst spread.
- No manual labeling path is required.
- Hard keyword matching is not sufficient to pass acceptance; tests must exercise AI classifier/verifier behavior through deterministic fixtures or mocked model outputs.

### P3 - Source/Search Hardening

Status: completed

Tasks:

- [x] Add staged retry metadata to DeepSeek/SearXNG execution.
- [x] Add bounded repair attempts for search plan, search result scarcity, final JSON, and transient source checks.
- [x] Keep pure reasoning fallback disabled.
- [x] Add source authority classifier.
- [x] Add source support checks that compare source title/snippet/domain with candidate thesis.
- [x] Surface search/source failure reasons in diagnostics without polluting normal candidates.

Acceptance:

- Search failures are retryable but fail closed after the configured attempt budget.
- A round with no adequate public source cannot enter the normal research pool.
- Source quality shows authority classes, not only HTTP reachability.

### P4 - Baselines And Evaluation Gates

Status: in_progress

Tasks:

- [ ] Implement random same-market-cap bucket baseline.
- [ ] Implement momentum/volume baseline.
- [ ] Implement topic peer baseline.
- [x] Add baseline readiness status to model feedback.
- [x] Add checkpoint artifacts for 30/50/100 unique-symbol official samples.
- [x] Add go/no-go gate rendering that remains research-only.

Acceptance:

- Model performance is always shown against at least one non-LLM baseline.
- The lab cannot claim model capability before P0 validation and checkpoint sample thresholds.
- Go/no-go results do not write to main recommendation or simulation policy.

## Tracking Checklist

- [x] P0 complete: official executable validation exists and legacy rows are excluded or marked.
- [x] P1 complete: aggregation and consensus semantics are repaired.
- [x] P2 complete: AI-only normalized topic feedback is available.
- [x] P3 complete: DeepSeek/SearXNG repair is bounded and fail-closed.
- [ ] P4 complete: baselines and go/no-go gates exist.
- [x] Runtime DB refreshed under new validation contract.
- [x] Localhost browser verified.
- [ ] Canonical browser verified if any frontend/runtime behavior changes are shipped.

## Notes For Future Implementers

- Do not add manual review queues or operator labeling requirements to this plan.
- Do not make old diagnostic returns disappear; keep them explainable, but exclude them from official aggregates.
- Do not treat `high_convergence` as advice. It is only a research priority.
- Do not use intraday data as official entry unless coverage is proven for the full Short Pick Lab universe.
- Any live-facing implementation derived from this plan must be published through `scripts/publish-local-runtime.sh` and verified in a real browser before being called complete.
