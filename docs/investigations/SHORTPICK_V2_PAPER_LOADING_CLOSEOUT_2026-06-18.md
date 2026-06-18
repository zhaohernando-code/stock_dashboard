# Shortpick v2 Paper Loading Closeout Investigation - 2026-06-18

## rawProblem

用户原始报告：`当前试验田v2卡死在数据获取界面`。

截图与 Appshot 指向真实页面：
`https://hernando-zhao.cn/projects/ashare-dashboard/?view=shortpick-v2&shortpickTab=paper-tracking&symbol=002028.SZ&shortpickV2Tab=paper-tracking`。

可见症状：试验田v2 `纸面追踪` 页面显示多个骨架屏，`刷新` 按钮处于 loading 状态，`最新模拟交易`、`策略说明`、`策略观察组`、`账户净值走势`、`图表`、`模拟交易明细` 未展示实际内容。

## normalizedProblem

试验田v2纸面追踪首屏依赖完整 `/shortpick-lab-v2/paper-tracking` 接口；当前真实前向记录只有 4 条且全为不买入，但完整接口仍在请求期重算账户曲线，导致页面长时间停留在数据获取状态。

## expectedBehavior

- 纸面追踪页面应在已有 ledger 数据时快速展示纸面追踪主视图。
- 真实前向全为 `skip` 时，不应重算无法改变结果的合并账户曲线。
- 运行时验证应覆盖真实页面使用的完整接口耗时，而不是只校验 ledger 记录存在。

## actualBehavior

- `GET /shortpick-lab-v2/paper-tracking/summary` 在本地运行服务上约 `0.013559s` 返回，状态 `active`，`record_count=4`，`true_forward=4`。
- `GET /shortpick-lab-v2/paper-tracking` 在同一服务上约 `35.280110s` 返回，`records=4`，展示表行 `60`，账户曲线 `2`。
- 页面首屏加载完整接口期间持续显示骨架屏。

## reproductionEvidence

真实用户路径：Chrome 公网页面 `试验田v2 -> 纸面追踪`，Appshot 显示骨架屏与 loading 刷新按钮。

本地服务接口证据：

```text
curl http://127.0.0.1:8000/shortpick-lab-v2/paper-tracking/summary
TOTAL:0.013559
summary: status=active, record_count=4, true_forward=4, has_display=True

curl http://127.0.0.1:8000/shortpick-lab-v2/paper-tracking
TOTAL:35.280110
summary: status=active, records=4, rows=60, curves=2
```

限制：截图来自用户浏览器已登录页面；自动化浏览器未复用用户登录态。后续验证需至少覆盖本地 served 页面和运行时完整 API。

## directCause

`src/ashare_evidence/shortpick_v2_read_model.py` 的 `_paper_tracking_display_projection` 在 `true_forward_rows` 非空时无条件调用 `_paper_display_account_curves_from_session(session, rows=[*replay_rows, *true_forward_rows])`。

当前 ledger 的真实前向记录全部是 `skip`，没有任何 `buy_primary` 或 `buy_fallback`，因此真实前向行不会改变账户曲线。无条件合并重算只增加行情加载和曲线重算成本，形成 35 秒级接口延迟。

前端 `frontend/src/components/ShortpickLabV2View.tsx` 的纸面追踪首屏直接等待 `api.getShortpickV2PaperTracking()`，因此后端完整接口延迟会直接表现为页面卡在骨架屏。

## rootCauseChain

1. 纸面追踪 ledger 刷新上线后，运行时数据已存在，但完整读模型仍按“有真实前向行”触发合并曲线重算。
2. 重算逻辑没有区分真实前向买入行和跳过行。
3. 之前收尾验证重点检查 ledger 数量、summary 可读性和生成脚本，没有把真实页面使用的完整接口耗时作为门禁。
4. 前端没有先用快速摘要接口解除首屏骨架屏，放大了后端慢路径的用户可见影响。

## missedInterceptors

- Runtime verification gap：`scripts/verify-shortpick-v2-paper-ledger-runtime.sh` 只验证记录存在与基本状态，没有验证完整 `/paper-tracking` API 的耗时。
- Browser fidelity gap：发布后没有以真实试验田v2纸面追踪页面验证骨架屏是否在合理时间内消失。
- Performance regression gap：测试没有覆盖“skip-only true-forward ledger 不应触发合并账户曲线重算”。

## downstreamImpactScan

已检查：

- `src/ashare_evidence/api.py`：完整纸面追踪接口使用 `include_records=True`，summary 接口使用 `include_records=False`。
- `frontend/src/components/ShortpickLabV2View.tsx`：纸面追踪首屏依赖完整接口，慢接口期间显示骨架屏。
- `src/ashare_evidence/shortpick_v2_read_model.py`：重算仅发生在纸面追踪展示投影；历史回放读模型不走该分支。
- `scripts/verify-shortpick-v2-paper-ledger-runtime.sh`：需要补充完整接口延迟验证。

未发现：

- summary 接口自身超时。
- ledger 记录缺失；当前 runtime ledger 已有 4 条记录。

边界：

- 若未来真实前向出现买入行，合并账户曲线仍需要估值；本次修复只消除 skip-only ledger 的无效重算，并增加当前完整接口耗时门禁。

## remediations

| Type | Status | Remediation | Evidence Required |
|------|--------|-------------|-------------------|
| known_defect | planned | skip-only true-forward ledger 复用回放账户曲线，不触发合并重算 | 单元测试；完整接口耗时复验；页面骨架屏解除 |
| process_gap | planned | 运行时验证脚本加入完整纸面追踪 API 延迟门禁 | 脚本输出包含 full_api_seconds 且低于阈值 |
| downstream_impact | planned | 检查 v2 页面与 API 路径，确认历史回放不受影响 | run 记录与验证输出 |

## confidence

高。summary 与完整接口耗时差异明显，代码中存在无条件重算分支，且当前 ledger 全为 skip 时该重算不会改变账户曲线。

## openQuestions

- 未来出现真实前向买入行后，是否需要为“回放+真实前向买入”账户曲线增加新的持久化缓存。本次修复先不扩大到该路径。
