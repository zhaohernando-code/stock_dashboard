# Shortpick Deep Research End-State Design

Date: 2026-07-03

Status: active design contract

Owner: stock_dashboard / Short Pick research governance

## Purpose

本文件定义 Short Pick 深度研究验证体系的完整终局设计。它不是 P0 简化方案，也不是只为当前 patch 服务的临时说明。

后续实现可以分 P0/P1/P2/P3/P4/P5 逐步交付，但设计边界必须一次性固定：任何阶段切片都不得把终局范围缩小成当前已经实现的能力，也不得把临时诊断路径包装成可推广生产路径。

## Completion Status / 完成状态

| Item | Status | Evidence / note |
|---|---|---|
| End-state design contract | completed | 本合同已落地，commit `a4303d6`；本次修订补充完成状态、量化门禁、制品字段合同和实现映射。 |
| P0 validation artifact boundary | implemented | commit `3621f2d`；`factor_ic_study` / `weight_sweep_study` 写入独立 `research_validation` artifact namespace。 |
| runtime DB read-only input boundary | implemented/partial | 当前只在 factor validation / weight sweep 路径落地；runtime DB 作为只读输入源，验证结果写 artifact，不写业务表。其他研究路径仍需逐步迁移到同一边界。 |
| research input snapshot | implemented | Factor validation / weight sweep path now creates an addressable `research_input_snapshot` artifact under `research_validation/input_snapshots`; it freezes runtime DB read-only inputs before validation and remains non-promotional. |
| PIT feature store | implemented | Factor validation / weight sweep path now builds a research-only `pit_feature_store` artifact from the frozen input snapshot, with independent price, liquidity, risk/trading, valuation, news/text, regime, crowding and placeholder availability groups. Legacy `recommendation_payload.factor_breakdown` remains diagnostic-only and is not used to compute PIT features. |
| objective frozen universe | implemented | Factor validation / weight sweep path now freezes a pre-validation `objective_frozen_universe` artifact from DB stocks with 1d market-bar coverage, records recommendation/watchlist rows only as a coverage subset, and keeps promotion blocked by legacy factor source, OOS and governance gates. |
| walk-forward / purge / embargo | implemented | Factor validation / weight sweep path now writes a `walk_forward_purge_embargo` protocol artifact with anchored splits, purge days and embargo days. Current data may still have zero ready splits and remain blocked from promotion. |
| PBO / DSR / multiple comparison | not_started | 尚未实现 PBO、Deflated Sharpe Ratio、多重比较校正；weight sweep 标记 `multiple_testing_status=not_corrected`。 |
| OOS artifacts | not_started | 尚无 out-of-sample validation artifact；任何 promotion 仍 blocked。 |
| governance promotion state machine | not_started | 当前只有 blocked gate readout；尚无状态机、审批、回滚、retirement / unretirement 协议实现。 |
| dashboard approved projection registry | not_started | 当前 operations/dashboard 只透传 gate/lineage/promotion summary；尚无 materialized approved projection artifact registry。 |
| runtime publish / served verification | P0 factor_observation verified; full publish parity blocked | P0 `factor_observation` served API 已验证返回 diagnostic-only、lineage、gate 和 `blocked_from_production`；完整 publish parity 被无关 `portfolios` detail endpoint timeout 阻断。 |

## Background

Short Pick v1 和后续纸面/回放证据曾出现过高收益表现，但收益高度依赖少数标的，尤其是生益科技这类单一大赢家贡献。该现象说明当前策略不能被视为稳定 alpha，也不能把某一轮回放收益直接解释为可复用、可生产化的选股能力。

现有 `recommendation_payload.factor_breakdown` 来源于生产 recommendation 输出。它可以帮助诊断“旧系统给出的解释分数与后验收益是否有关系”，但它不是独立、点时、可复现实验特征。若直接用它反推因子权重，会把生产模型输出再喂回研究验证路径，形成自证循环。

因此，Short Pick 后续研究必须从业务库与生产输出中隔离验证结果：runtime DB 只能作为只读事实来源；研究验证结果必须写入独立 artifact store；生产推广必须通过治理 gate 和审定 projection，而不能由 raw validation artifact 或 in-sample weight sweep 自动驱动。

## Core Principles

1. 设计不阶段化，实施阶段化。
   P0/P1/P2/P3/P4/P5 只是完整终局设计的交付切片，不是不同版本的设计边界。任何阶段都必须承认完整终局数据流、存储边界和 promotion 规则。

2. 研究证据不能回写生产事实。
   runtime DB / 业务库提供只读输入。研究验证、实验权重、诊断行、OOS 结果和 promotion gate 结果必须落在独立 artifact/projection 层，不得混入业务事实表。

3. raw validation artifact 不能直接驱动看板结论。
   看板只能消费审定 projection。projection 必须带 `lineage`、`gate_readout`、`claim_ceiling` 和 `promotion_status`，并隐藏或压缩 raw rows。

4. legacy diagnostic 不等于 alpha 证明。
   从 `recommendation_payload.factor_breakdown` 反取的分数必须标记为 diagnostic-only。它不能用于生产权重、horizon approval、自动 promotion 或模拟盘毕业。

5. benchmark 缺失时 fail closed。
   缺主 benchmark 的验证不能用 active universe 等权收益继续计算 IC。active universe proxy 可以作为历史兼容或诊断上下文，但不能在 benchmark 缺失时替代正式 excess-return label。

6. 样本不足时默认阻断。
   小样本 IC、少窗口 weight sweep、单一赢家驱动、watchlist 污染或缺少 OOS artifact 时，系统必须输出 blocked / diagnostic-only，而不是输出精确权重建议。

## End-State Data Flow

终局数据流固定为：

```text
runtime DB (read-only source)
  -> research input snapshot
  -> PIT feature store
  -> validation store
  -> governance / promotion gate
  -> dashboard projection
```

### 1. Runtime DB (read-only source)

职责：

- 提供生产和运行时事实：行情、基准、股票信息、watchlist、recommendation、paper tracking、验证快照等。
- 作为研究输入的只读源。

禁止：

- 写入 raw validation rows。
- 写入 weight sweep 结果。
- 写入 research gate 的中间状态。
- 由研究验证过程直接修改 recommendation、生产权重、policy config 或 paper tracking 状态。

### 2. Research Input Snapshot

职责：

- 从 runtime DB 读取必要输入，冻结成可复现的研究快照。
- 记录 `source_db_snapshot_id`、时间范围、universe 定义、benchmark 可用性、数据缺口。
- 把 watchlist、候选池、市场基准和标签窗口固化，避免请求时漂移。

终局要求：

- snapshot 必须可寻址、可审计、可重放。
- snapshot 本身不是 promotion 证据，只是研究输入边界。

### 3. PIT Feature Store

职责：

- 生成独立 point-in-time 特征，避免读取生产 recommendation 输出作为特征。
- 每个特征必须有 `feature_version`、计算代码版本、输入时间戳、数据许可/来源和缺失规则。

终局要求：

- 特征计算只使用 signal time 当时或更早的数据。
- 不得使用 forward return、验证结果、后验排序或生产输出解释作为特征。
- legacy recommendation payload 只能作为 diagnostic feature source，并在 gate 中阻断 promotion。

### 4. Validation Store

职责：

- 保存 IC、bucket return、portfolio replay、OOS、PBO/DSR、execution constraint 等验证制品。
- 保存 raw validation rows 但不直接暴露给看板。
- 保持独立于 runtime DB / 业务库。

终局要求：

- artifact 必须带 schema version、artifact id、validation run id、lineage、gate readout、claim ceiling。
- artifact store 可以位于 runtime 项目的 data/artifacts 下，但必须是独立 research/validation namespace，不能写入 SQLite 业务表。

### 5. Governance / Promotion Gate

职责：

- 读取 validation artifacts 和 OOS artifacts，做 machine-checkable promotion 判定。
- 管理状态机：`diagnostic_only -> research_candidate -> oos_candidate -> paper_tracking_candidate -> production_eligible`。
- 输出审定 projection，而不是把 raw artifact 原样传给前端。

终局要求：

- gate 必须检查独立特征、objective frozen universe、benchmark、样本数、窗口数、walk-forward、purge/embargo、PBO/DSR、多重比较、执行约束和 OOS。
- 任一关键 gate blocked 时，promotion status 必须保持 blocked。

### 6. Dashboard Projection

职责：

- 面向看板提供经过审定、降维、可读的 projection。
- 只展示 summary、gate、lineage、claim ceiling、benchmark context、必要指标和用户可理解解释。

禁止：

- 直接消费 raw validation artifact。
- 展示未过 gate 的生产权重建议。
- 把 diagnostic rows 表达为策略有效性证明。

## Storage Boundary

### Runtime DB

权限：

- Production: read/write 自身业务事实。
- Research: read-only。
- Validation: read-only input source。
- Governance: read-only source，可读取 production 状态做 gate，但不得直接写 validation rows。

禁止：

- raw validation rows 写入 runtime DB。
- research weight sweep 写入 policy config。
- legacy diagnostic result 写入 recommendation payload 形成闭环。

### Research / Validation Artifact Store

权限：

- Research: write research input snapshots and PIT feature artifacts。
- Validation: write IC、sweep、OOS、replay、PBO/DSR artifacts。
- Governance: read validation artifacts, write gate/projection artifacts。
- Production: read only approved governance projection，不读 raw validation rows。

路径约束：

- P0 使用 `research_validation/factor_ic_studies` 和 `research_validation/weight_sweep_studies`。
- 后续 PIT feature、input snapshot、OOS、governance projection 可以扩展同一独立 namespace。

## Layer Responsibilities And Permissions

| Layer | Primary responsibility | Runtime DB | Artifact store | Production effect |
|---|---|---:|---:|---|
| Research | define universe, snapshots, PIT features, hypotheses | read-only | write research inputs/features | none |
| Validation | compute labels, IC, sweeps, OOS, execution diagnostics | read-only | write validation artifacts | none |
| Governance | evaluate promotion gates and claim ceiling | read-only | read validation, write approved projection | controls allowed claims |
| Production | serve dashboard and paper/simulation workflows | read/write business facts | read approved projection only | no direct raw research mutation |

## Factor Design End State

以下全部属于终局设计范围，即使实施分阶段完成。

### Price / Volume

- return momentum and reversal across multiple horizons
- gap / breakout / consolidation features
- volatility-adjusted trend strength
- volume expansion / contraction
- turnover and abnormal volume

### Liquidity

- turnover depth
- average transaction amount
- limit-up / limit-down fillability risk
- board-lot efficiency under account size
- suspension and stale quote risk

### Risk And Execution Constraints

- T+1 sell availability
- price-limit unfillable entry/exit
- ST / delisting risk / board eligibility
- concentration, repeated exposure, and cooldown
- slippage / fee / stamp tax assumptions
- capacity and capital deployment efficiency

### Fundamentals

- profitability and margin quality
- growth and revision direction
- balance sheet risk
- cash flow quality
- report freshness and restatement risk

### Valuation

- PE / PB / PS / EV-style relative valuation when available
- industry-relative z-scores
- growth-adjusted valuation
- valuation regime interaction

### Announcements / News / Text

- exchange/company disclosure events
- designated disclosure media
- mainstream financial media
- vertical industry media
- broker research / PDF
- community/forum and aggregator noise flags
- source authority and thesis support
- event dedupe, hierarchy, timestamp alignment, and decay

### Industry Diffusion

- same-industry momentum diffusion
- upstream/downstream theme propagation
- peer confirmation and divergence
- sector breadth and concentration

### Regime

- market trend / volatility / breadth regime
- size style regime
- liquidity regime
- policy/event risk regime
- benchmark-relative regime

### Crowding

- crowded winners and one-stock dependency
- turnover crowding
- theme overheat
- concentration in symbol / industry / date / model source

### Dynamic Weights

- dynamic weighting is a governed output, not an in-sample convenience.
- weight updates require sufficient independent windows, sufficient samples, positive OOS evidence, and governance approval.
- rolling IC adjustment must be bounded, slow-moving, and blocked under small samples.

## Quantitative Gates / 具体技术门禁

这些数值是当前合同门槛，不是 UI 文案。实现可以在后续治理决策中提高门槛，但不得为了让当前样本显得可推广而降低门槛。

### P0 Constants

| Constant | Value | Contract meaning |
|---|---:|---|
| `MIN_SYMBOLS_PER_SNAPSHOT` | 20 | 单个 as-of 截面少于 20 只股票时，不生成该截面的 IC / bucket 证据。 |
| `MIN_SNAPSHOT_COUNT` | 10 | 少于 10 个有效 as-of 截面时，整体 status 保持 `insufficient_sample`。 |
| `MIN_UNIQUE_SYMBOLS_FOR_WEIGHTING` | 50 | 少于 50 个 unique symbols 时，`research_universe_width` gate blocked。 |
| `MIN_TOTAL_SAMPLES_FOR_WEIGHTING` | 600 | 少于 600 条截面观察行时，因子 weighting eligibility blocked。 |
| `MIN_WINDOWS_FOR_WEIGHTING` | 20 | 少于 20 个独立时间窗口时，因子 weighting eligibility blocked。 |

### Rolling IC Dynamic Weight Gates

| Parameter | Value | Contract meaning |
|---|---:|---|
| `min_periods_for_adjustment` | 60 | 少于 60 个 rolling IC 观测期时，不允许动态调整权重。 |
| `sensitivity` | `<= 0.3` | 动态权重响应强度上限为 0.3。 |
| multiplier clip | `[0.5, 1.5]` | 单因子动态权重乘数必须裁剪在 0.5 到 1.5 之间。 |

### Research Candidate Target Gates

这些是进入 `research_candidate` 的目标门槛；达不到时只能保持 diagnostic / observe-only。

| Gate | Threshold |
|---|---:|
| OOS Rank IC | `> 0.02` |
| ICIR | `> 0.35` |
| Positive IC months | `>= 55%` |
| Top quantile net excess | positive after costs |
| Quantile shape | roughly monotonic from low-score to high-score buckets |

### Promotion / Paper / Live Candidate Gates

这些是从 research candidate 继续进入 paper/live 候选前的最低门槛；任一未达标时 promotion remains blocked。

| Gate | Threshold |
|---|---:|
| Net Sharpe | `>= 1.0` |
| Deflated Sharpe confidence | `>= 95%` |
| PBO | `<= 10%` |
| Alpha t-stat or multiple-testing equivalent | `>= 3.0` |
| Cost stress | Still positive under `2x` costs |

### Execution Gates

进入 promotion 前，验证和回放必须包含以下执行约束，不允许只看理论收益：

- T+1 sell availability.
- Suspension / stale quote exclusion.
- Limit-up buyability.
- Limit-down sellability.
- Fee, slippage, and sell stamp tax.
- ADV / capacity / fill-rate constraints.
- Board eligibility, lot size, cash deployment, and position concentration.

## Required Artifact Contract / 制品字段合同

任何进入 validation store、governance gate 或 dashboard approved projection 的 artifact 至少必须包含以下字段。缺任一关键字段时，不得进入 dashboard approved projection，也不得参与 promotion。

| Field | Required | Meaning |
|---|---:|---|
| `schema_version` | yes | Artifact schema version. |
| `artifact_id` | yes | Stable artifact identifier. |
| `validation_run_id` | yes | Concrete run id for reproducibility. |
| `generated_at` | yes | Generation timestamp. |
| `source_db_snapshot_id` | yes | Source runtime DB snapshot/hash identifier. |
| `source_data_time_range` | yes | Input and label time coverage. |
| `feature_version` | yes | Feature generation version; legacy payload features must be marked diagnostic. |
| `label_version` | yes | Label and benchmark construction version. |
| `code_version` | yes | Code commit or explicit unresolved local checkout marker. |
| `config_version` | yes | Validation/gate/config protocol version. |
| `validation_protocol` | yes | Storage boundary, feature source, walk-forward, execution and promotion policy. |
| `gate_readout` | yes | Machine-readable pass/block checks and blocking gate ids. |
| `claim_ceiling` | yes | Highest allowed user-facing claim. |
| `promotion_status` | yes | `blocked_from_production` unless all governance gates pass. |

P0 `factor_ic_study` currently carries these fields partly nested under `lineage`: `source_db_snapshot_id`, `source_data_time_range`, `feature_version`, `label_version`, `code_version`, and `config_version`. P0 carries `claim_ceiling` inside `gate_readout`, which is acceptable only for the current diagnostic summary path. A future approved projection registry must keep all required fields machine-addressable and stable for validators before any stronger dashboard claim or promotion.

## Overfitting Protections

End-state promotion requires all of the following classes of protection:

- Independent feature computation: features cannot be reverse-engineered from recommendation output.
- Objective frozen universe: universe must be fixed before validation and not selected by post-hoc winners.
- Point-in-time labels: labels use only executable entry/exit definitions with benchmark availability.
- Walk-forward validation: training/tuning windows precede validation windows.
- Purge / embargo: overlapping label leakage must be removed.
- PBO / DSR: probability of backtest overfitting and deflated Sharpe-style corrections for multiple tests.
- Multiple comparison control: parameter sweeps and strategy grids must report tested count and correction status.
- OOS artifact: any promotion beyond research candidate requires out-of-sample artifact.
- Execution constraints: board, lot, liquidity, price-limit, T+1, costs, and cash deployment must be included.
- Winner dependency checks: remove top symbol/day/month and re-evaluate.
- Benchmark integrity: benchmark must be external or formally approved; missing benchmark blocks official IC/excess-return rows.

## P0 Implementation Slice Contract

P0 is only the first implementation slice of this full design. It must not be interpreted as shrinking the end-state scope.

P0 must deliver:

- independent `research_validation` artifact store for factor IC and weight sweep outputs.
- legacy `recommendation_payload.factor_breakdown` path explicitly marked diagnostic-only.
- validation artifacts carry schema version, artifact id, validation run id, lineage, validation protocol, gate readout, and blocked promotion status.
- dashboard-facing projection exposes gate/lineage/promotion readout but not raw validation rows.
- benchmark fallback is blocked: missing primary benchmark bars must skip IC rows rather than use active universe equal-weight return.
- small-sample gates block factor weighting and research claims.
- rolling IC dynamic weight adjustment requires a long enough independent history and bounded multipliers.
- weight sweep remains diagnostic-only and cannot auto-promote into production.

Original P0 did not deliver:

- independent PIT factor feature store.
- objective full-market or frozen research universe.
- walk-forward / purged CV / PBO / DSR.
- OOS promotion artifact.
- production weight state machine.
- final dashboard projection artifact registry.

Those gaps were expected for P0. Later slices may close individual items only by implementing the full contract for that item and keeping remaining blocked gates visible.

## Implementation Mapping / 当前实现映射

| Contract area | Current files | Implemented behavior |
|---|---|---|
| research validation artifact folders | `src/ashare_evidence/artifact_store_core.py` | Adds `research_validation/objective_universes`, `research_validation/input_snapshots`, `research_validation/pit_feature_store`, `research_validation/walk_forward_protocols`, `research_validation/factor_ic_studies`, and `research_validation/weight_sweep_studies`. |
| research validation artifact writer | `src/ashare_evidence/research_artifact_store.py` | Adds `write_research_validation_artifact(...)` with artifact type whitelist and repo-write guard, including `objective_frozen_universe`, `research_input_snapshot`, `pit_feature_store` and `walk_forward_purge_embargo`. |
| objective frozen universe | `src/ashare_evidence/objective_universe.py` | Freezes a deterministic pre-validation universe from runtime DB stocks with 1d market-bar coverage; recommendation/watchlist symbols are measured only as a coverage subset, not as the research universe. |
| research input snapshot | `src/ashare_evidence/factor_observation.py` | Builds a non-promotional `research_input_snapshot` artifact that freezes symbols, recommendation as-of dates, source data ranges, horizons, benchmark context, validation protocol, and snapshot gates before IC/weight validation. |
| PIT feature store | `src/ashare_evidence/pit_feature_store.py` | Builds non-promotional `pit_feature_store` artifacts from the frozen snapshot only; feature rows include independent price, liquidity, risk/trading, valuation, news/text, regime, crowding, fundamental availability, industry diffusion availability and dynamic-weight context groups. |
| walk-forward / purge / embargo | `src/ashare_evidence/walk_forward_protocol.py` | Builds non-promotional anchored walk-forward protocol artifacts from observation dates, with purge and embargo days equal to the maximum validation horizon. |
| legacy diagnostic-only factor path | `src/ashare_evidence/factor_observation.py` | Reads `recommendation_payload.factor_breakdown` only as `legacy_diagnostic_only`; writes validation protocol and feature lineage linked to the input snapshot. |
| benchmark fail-closed | `src/ashare_evidence/factor_observation.py` | Missing primary benchmark bars skip IC rows; artifact records `fallback_policy=block_ic_rows_when_primary_benchmark_unavailable`. |
| gate / lineage / promotion readout | `src/ashare_evidence/factor_observation.py` | Emits `lineage`, `gate_readout` with `claim_ceiling`, `promotion_status=blocked_from_production`, and diagnostic notes. |
| factor eligibility and rolling IC bounds | `src/ashare_evidence/phase2/factor_ic.py` | Requires 20 windows and 600 samples for weighting eligibility; rolling weight adjustment requires 60 periods and clips multiplier to `[0.5, 1.5]`. |
| operations projection summary | `src/ashare_evidence/operations.py` | Exposes schema/artifact id, input snapshot, PIT feature store, validation protocol, lineage, gate readout and promotion summary; does not expose raw `observation_rows` or raw PIT feature rows. |
| stock dashboard factor validation | `src/ashare_evidence/dashboard.py` | Exposes factor validation protocol, input snapshot, PIT feature store, lineage, gate readout and promotion summary in product-facing payload. |
| artifact store tests | `tests/test_research_artifact_store.py` | Verifies isolated `research_validation` paths for input snapshots, PIT feature store, factor IC and weight sweep artifacts; rejects unsupported artifact types. |
| factor IC tests | `tests/test_factor_ic.py` | Verifies small-sample weighting block and rolling IC adjustment gate. |
| P0 product contract tests | `tests/test_professionalization_plan.py` | Verifies diagnostic-only, benchmark fallback block, lineage, gate and promotion summary in study/sweep/API payloads. |

## Non-Goals / Still Blocked

The following blocked states are intentional completion status, not omissions. P0 must keep them visible until later slices implement and verify them.

- Full upstream coverage for PIT fundamental statement availability and frozen industry membership is still source-limited; the PIT feature store records those groups with explicit availability status instead of synthesizing unavailable data.
- Full-market breadth is still limited by whatever runtime DB stocks and market bars are available locally; the objective universe artifact records that coverage explicitly, while active watchlist remains only the recommendation sample source.
- Walk-forward promotion is still blocked until the protocol artifact has enough ready splits; the split/purge/embargo machinery itself is implemented.
- PBO / DSR / multiple-comparison correction is still blocked.
- OOS validation artifacts are still blocked.
- Governance promotion state machine is still blocked; P0 only emits blocked gate readout.
- Approved dashboard projection registry is still blocked; current API is summary projection, not final materialized governance projection.
- Production weight update is still blocked; weight sweep cannot change policy config or recommendation generation.
- Paper/live candidate promotion is still blocked until research, OOS, execution, PBO/DSR and governance gates pass.

## Review / Verification Log

| Time | Reviewer / process | Result | Evidence |
|---|---|---|---|
| 2026-07-03 | Main Codex local requirement check | passed | Checked required section names, status rows, numeric gates, artifact fields, implementation mappings, and blocked-state language against this document. |
| 2026-07-03 | Independent subagent review `019f26ab-ff4c-7842-961d-997d0dc3aead` | PASS | Reviewer reported no required fixes; confirmed completion status, quantitative gates, artifact field contract, P0 implementation/test mapping, Non-Goals/Still Blocked, and `DECISIONS.md` coverage. |
| 2026-07-03 | `git diff --check` | passed | No whitespace or patch formatting errors. |
| 2026-07-03 | Research input snapshot slice local verification | passed | `ruff check` passed for changed Python/tests; `pytest -q tests/test_research_artifact_store.py tests/test_professionalization_plan.py` passed with 18 tests. |

## DS / MiMo Review Summary

The external review themes that shaped this contract:

- Circular dependency: validating `recommendation_payload.factor_breakdown` as if it were independent factor data creates a self-referential loop.
- Watchlist pollution: active watchlist is an operational universe, not an objective frozen research universe.
- Small-sample IC: sparse symbols/windows can create unstable IC and false precision.
- Benchmark self-reference: active universe equal-weight fallback can become a self-benchmark and hide market-relative weakness.
- Dynamic weight second-order overfitting: using in-sample rolling IC to tune weights can overfit the validation layer itself unless constrained by OOS and governance gates.

## Future Implementation Slices

### P1 - Independent Factor Feature Store

- Status: implemented for the factor validation / weight sweep path through `pit_feature_store.v1`.
- Extend research input snapshots beyond this path where needed.
- Add richer upstream source coverage for currently unavailable fundamental statement timing and frozen industry membership inputs.
- Keep legacy payload path as diagnostic-only comparator.

### P2 - Objective Universe And PIT Labels

- Status: objective frozen universe implemented for the factor validation / weight sweep path through `objective_frozen_universe.v1`.
- Generate PIT label artifacts with executable entry/exit definitions.
- Require benchmark bars before official excess-return labels.
- Add winner-dependency and universe-width reporting.

### P3 - Walk-Forward / Purged CV / PBO

- Status: walk-forward split / purge / embargo protocol artifacts implemented for the factor validation / weight sweep path through `walk_forward_purge_embargo.v1`.
- Add PBO / DSR / multiple-comparison reporting.
- Produce OOS validation artifacts before any promotion candidate.

### P4 - Governance Promotion State Machine

- Implement machine-checkable state transitions.
- Add promotion blockers, approvals, retirements, and rollback.
- Forbid automatic promotion from weight sweep or single validation artifact.

### P5 - Dashboard Projection

- Materialize approved governance projection artifacts.
- Frontend and operations APIs read projection, not raw validation artifacts.
- User-facing copy follows `claim_ceiling` and abstains when gates block.

## Explicit Prohibitions

- Do not use scores reverse-extracted from `recommendation_payload.factor_breakdown` for production weights.
- Do not compute official IC with active universe equal-weight return when primary benchmark data is missing.
- Do not let weight sweep automatically enter production config, policy config, simulation policy, or recommendation generation.
- Do not write raw validation rows into runtime DB or business tables.
- Do not let dashboard or frontend consume raw validation rows directly.
- Do not treat watchlist-only IC as objective universe evidence.
- Do not present P0 diagnostic artifacts as end-state research validation.
- Do not weaken sample/window/gate thresholds to make current data appear promotable.

## Current Alignment Statement

Commit `3621f2d` implements the P0 slice only. It aligns with the P0 contract by isolating `factor_ic_study` and `weight_sweep_study` under `research_validation`, marking legacy factor payloads diagnostic-only, blocking benchmark fallback, carrying lineage/gate/promotion readouts, and tightening small-sample/dynamic-weight gates.

Subsequent commits add the objective frozen universe, research input snapshot, PIT feature store, and walk-forward/purge/embargo protocol slices for the factor validation / weight sweep path. The remaining end-state items are PBO/DSR/multiple-comparison reporting, OOS artifacts, promotion state machine, and materialized dashboard projection registry. Those are intentional next slices, not removed design scope, and implemented protocol artifacts do not imply promotion readiness.
