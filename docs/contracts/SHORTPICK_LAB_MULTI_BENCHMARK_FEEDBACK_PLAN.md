# Short Pick Lab Multi-Benchmark Feedback Plan

## Purpose

短投试验田的收益反馈不能只用一个默认市场基准表达。后续实现必须把候选的后验收益拆成三条可切换、可审计的 benchmark 维度，让运营能同时观察“跑赢大盘、跑赢小盘/中证风格、跑赢同板块”的差异。

## Approved Scope

首期只覆盖短投试验田的后验验证与历史验证工作台，不接入主推荐评分、主候选池、模拟盘自动调仓、生产权重或 Phase 5 promotion gate。

必须支持的三维口径：

- `hs300`: 沪深300，沿用当前官方短投默认基准。
- `csi1000`: 中证1000，沿用当前短投研究基准，用于观察小盘/中证风格相对表现。
- `sector_equal_weight`: 同板块等权基准，按候选标的的主要行业/板块归属，使用可得同行日线构造等权收益。

## Product Contract

- 历史验证表、研究池候选表和模型反馈表的收益列应支持在表头切换 benchmark 维度。
- 表头切换只改变展示的 `benchmark_return / excess_return / benchmark_label`，不得改变候选排序、验证状态或原始模型输出。
- 默认展示仍为 `hs300`，以兼容现有“沪深300超额”用户认知。
- 当某一维度缺基准行情、缺同板块同行样本或样本不足时，该维度显示 `待基准数据` 或 `待板块样本`，不能回退成个股绝对收益或用沪深300代替。
- 同一 candidate-horizon 行必须保留所有可用维度的原始数值，前端切换不得重新请求单行明细或丢失其他维度。

## Backend Contract

- `shortpick_validation_snapshots.validation_payload` 必须写入多维 benchmark map，至少包含每个维度的 `benchmark_id / label / symbol_or_scope / benchmark_return / excess_return / status / reason`。
- 兼容字段 `benchmark_return` 与 `excess_return` 暂时继续代表默认 `hs300` 口径，避免破坏现有 API/前端。
- run summary、candidate summary、validation queue 和 model feedback 聚合都要接受 selected benchmark 维度，或在响应中同时返回可切换维度聚合。
- 同板块等权基准必须使用 point-in-time 可得的 `SectorMembership` 和日线收盘构造；若板块内可用同行少于实现阶段锁定的最小样本数，状态为 `pending_sector_peer_baseline`。
- 日更 `phase5-daily-refresh` 与 `shortpick-lab-validate-recent` 必须能补算近期旧批次的多维 benchmark，不要求用户手动打开页面触发。

## Frontend Contract

- `ShortpickLabView` 的收益反馈列使用表头内 segmented control 或等价控件切换 `沪深300 / 中证1000 / 同板块`。
- 研究池候选、历史验证队列、模型反馈聚合的标签和数值必须跟随同一个选中 benchmark 维度。
- 空值和 pending 状态要显示原因，不允许只显示 `--` 而不说明是缺行情、缺板块映射还是同行样本不足。
- 文案统一使用“超额收益”，并在旁边显示当前 benchmark label，避免用户把不同口径混读。

## Acceptance

- 后端测试覆盖三维 benchmark 都有数据、同板块样本不足、缺中证行情、默认兼容字段仍为沪深300四类路径。
- 前端静态/组件测试覆盖表头切换后收益列、模型反馈聚合和 pending 文案变化。
- 发布后必须在真实 served 页面验证：切换 `沪深300 / 中证1000 / 同板块` 时，同一历史验证行的 benchmark label 和超额收益随之变化；缺数据维度显示待补原因。
- 发布验收不得只看 API 或单元测试；这是用户可见的试验田工作台能力，必须完成 runtime 发布和浏览器验证。

## Closeout

2026-05-07 已落地并发布验收：

- Runtime 发布 manifest：`/Users/hernando_zhao/codex/runtime/projects/ashare-dashboard/output/releases/20260507T111724Z-211dc0291542/manifest.json`，deploy verifier `19 passed, 0 failed`。
- 运行态补跑近期验证后，2026-05-05 批次已有 `10` 条 completed 验证快照。
- API 验证确认 `/shortpick-lab/validation-queue` 和 `/shortpick-lab/model-feedback` 都返回 `hs300 / csi1000 / sector_equal_weight` 三维数据。
- 真实 served 页面 `http://127.0.0.1:5173/?verify=shortpick-multibenchmark` 已验证历史验证表头切换：同一条 `2026-05-05 · 002384.SZ · 1日 · 已完成` 行在 `沪深300 / 中证1000 / 同板块` 三个维度下分别显示不同 benchmark label 与超额收益。

## Non-Goals

- 不把短投试验田收益反馈写回主 `Recommendation`。
- 不基于三维短投表现自动调整生产权重或买卖方向。
- 不把同板块基准作为 Phase 5 主研究 benchmark 的替代，除非另有决策记录批准。
