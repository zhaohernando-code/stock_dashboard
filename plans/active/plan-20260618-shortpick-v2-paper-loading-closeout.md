---
schema_version: 1
plan_id: "plan-20260618-shortpick-v2-paper-loading-closeout"
title: "Fix Shortpick v2 Paper Loading"
status: "executing"
created_at: "2026-06-18"
source_request: "用户报告试验田v2纸面追踪卡死在数据获取界面，要求按 problem-closeout-loop 标准流程定位并修复。"
target_repo: "/Users/hernando_zhao/codex/projects/stock_dashboard"
owner: "user"
review_rounds: 2
---

# Plan: Fix Shortpick v2 Paper Loading

## Compaction-Resistant Summary

Goal: 修复试验田v2纸面追踪首屏长时间骨架屏问题。
Scope: 后端 skip-only 真实前向行避免无效账户曲线重算，补运行时完整 API 延迟门禁，发布并验证真实 served 路径。
Out of scope: 不重新设计 v2 策略、不改变买卖规则、不解决未来真实买入行的长期缓存体系。
Key evidence: summary API 0.013s，完整 API 35.280s；根因在 read model 无条件合并重算。
Approval: MiMo plan review has no blocking finding; user has already required standard-flow implementation and no approval blocker.

## Goal

让试验田v2纸面追踪在当前 skip-only 真实前向 ledger 状态下快速返回完整展示数据，页面不再卡在数据获取骨架屏；同时补上能捕获该类回归的测试和运行时验收。

## Problem / Rationale

当前完整 `/shortpick-lab-v2/paper-tracking` 接口约 35 秒才返回，而用户页面首屏直接等待该接口，所以表现为“卡死在数据获取界面”。代码确认后端只要存在真实前向行就重算合并账户曲线，即使这些行全部是不买入，重算结果也不会改变账户曲线。这是无效计算与验收缺口共同导致的用户可见问题。

## Source Requirement Coverage

| Source ID | Source Requirement | Plan Coverage | Coverage Status | Scope Decision | Evidence Required |
|-----------|--------------------|---------------|-----------------|----------------|-------------------|
| SRC-001 | 修复“试验田v2卡死在数据获取界面”的用户可见缺陷 | W-001, W-003 | covered | - | 完整 API 耗时下降；页面验证不再长时间显示骨架屏 |
| SRC-002 | 使用 problem-closeout-loop，保留原始问题、根因、过程缺口和下游影响 | W-002, W-004 | covered | - | `docs/investigations/SHORTPICK_V2_PAPER_LOADING_CLOSEOUT_2026-06-18.md` 与 run 记录 |
| SRC-003 | 按标准流程实现，不因批准请求阻塞 | W-002, W-004 | covered | - | plan 通过 MiMo 审查后进入执行；User Review Notes 记录站立批准 |
| SRC-004 | live-facing 改动必须发布到 runtime 并验证真实 served 页面或 API | W-003, W-004 | covered | - | publish 命令成功；runtime 完整 API 与页面路径验证记录 |
| SRC-005 | 修复上游验收缺口，避免只验证 ledger 存在而漏掉完整接口慢路径 | W-001, W-003 | covered | - | 运行时验证脚本新增完整 API 延迟门禁并通过 |

## Production Path Fidelity

| Path ID | User / Production Path | Validation Path | Responsibility Owner | Test Setup / Bypass | Fidelity Status | Evidence Required |
|---------|------------------------|-----------------|----------------------|---------------------|-----------------|-------------------|
| PF-001 | 用户打开公网 `/projects/ashare-dashboard/?view=shortpick-v2&shortpickTab=paper-tracking&shortpickV2Tab=paper-tracking`，前端请求完整纸面追踪接口 | 发布后访问 runtime/public served 路径，并直接验证 runtime 完整 API | FastAPI read model + React v2 tab | none | matches_product_path | 页面或 served API 不再长时间等待 |
| PF-002 | `scripts/verify-shortpick-v2-paper-ledger-runtime.sh` 作为运行时验收脚本检查纸面 ledger | 脚本直接调用 runtime API 并校验完整接口耗时 | runtime verification script | none | matches_product_path | 脚本输出 full_api_seconds 且低于阈值 |
| PF-003 | 单元测试用 fixture 覆盖 skip-only ledger 读模型行为 | pytest monkeypatch 禁止调用 session 重算函数 | test harness | controlled simulation: fixture DB 和 monkeypatch 只用于证明 skip-only 分支不会触发昂贵重算；PF-001/PF-002 覆盖真实运行路径 | controlled_simulation | pytest 失败于旧逻辑、通过于新逻辑 |

## Scope

### In Scope

- 修改 v2 纸面追踪 read model：真实前向行全部为 skip/source_gap/not-entered 时，不重算合并账户曲线。
- 为 skip-only ledger 增加回归测试。
- 为运行时 v2 paper ledger 验证脚本增加完整 API 延迟门禁。
- 更新 investigation、plan、run 记录，发布 runtime 并验证。

### Out of Scope

- 不改变 H10 选股策略、金额参数、交易日期规则或 ledger 写入规则。
- 不改造前端为 summary-first 双阶段加载；若后端修复后仍有可见问题，再作为后续单独缺陷。
- 不为未来真实买入行设计新的持久化合并曲线缓存；本次只关闭当前 skip-only 卡顿缺陷。

## Assumptions and Dependencies

- 当前用户可见卡顿由完整接口慢路径导致，summary 接口与 ledger 写入不是直接故障点。
- 真实前向没有买入时，复用回放账户曲线在业务语义上正确，因为 skip 行不改变现金、仓位或净值。
- 运行时服务可通过现有发布脚本更新。

## Work Items

| ID | Status | Order | Depends On | Task | Deliverable | Acceptance Type | Acceptance Spec | Evidence |
|----|--------|-------|------------|------|-------------|-----------------|-----------------|----------|
| W-002 | done | 1 | - | 完成问题调查和 plan/run 审计记录，经过 MiMo 只读审查 | investigation + plan/run records | file_contains | path:docs/investigations/SHORTPICK_V2_PAPER_LOADING_CLOSEOUT_2026-06-18.md \| pattern:directCause | Investigation file created; MiMo plan review round 1 had no blocking findings and major findings were resolved in the plan. |
| W-001 | done | 2 | W-002 | 修复 skip-only 真实前向行触发无效账户曲线重算的问题，并补单元测试 | read model patch + pytest | test_pass | cmd:python3 -m pytest -q tests/test_shortpick_v2_paper_ledger.py tests/test_shortpick_v2_read_model_api.py | `35 passed in 9.20s`; MiMo code rereview approved with no blocking/major findings. |
| W-003 | pending | 3 | W-001 | 补运行时完整 paper-tracking API 延迟门禁，并执行必要专项验证 | runtime verifier update | command_exit_0 | cmd:bash scripts/verify-shortpick-v2-paper-ledger-runtime.sh |  |
| W-004 | pending | 4 | W-001,W-002,W-003 | 发布、验证、合入、推送并清理本任务临时状态 | merged main + pushed origin/main | manual | manual:main clean, origin/main updated, runtime published, served path/API verified, task worktree cleaned |  |

## Acceptance Criteria & Validation Gates

### Overall Acceptance Criteria

- 当前 skip-only v2 paper ledger 下，完整 `/shortpick-lab-v2/paper-tracking` 不再进行无效合并曲线重算。
- 单元测试覆盖旧缺陷路径。
- 运行时验证脚本能在完整接口慢于阈值时失败。
- runtime 发布后真实 served API/页面路径不再长时间停留在骨架屏。
- 变更合入 `main` 并 push 到 `origin/main`，临时 worktree 清理完成。

### Validation Gates

- `python3 -m pytest -q tests/test_shortpick_v2_paper_ledger.py tests/test_shortpick_v2_read_model_api.py`
- `bash scripts/verify-shortpick-v2-paper-ledger-runtime.sh`，默认要求完整 `/shortpick-lab-v2/paper-tracking` API 不超过 10 秒；可通过 `ASHARE_SHORTPICK_V2_PAPER_FULL_API_MAX_SECONDS` 覆盖。
- `ASHARE_PUBLISH_REFRESH_MODE=skip bash scripts/publish-local-runtime.sh`
- runtime API timing check for `/shortpick-lab-v2/paper-tracking`
- served route/browser check for `view=shortpick-v2&shortpickV2Tab=paper-tracking`

## Risks and Mitigations

- Risk: 未来真实前向出现买入行时完整接口仍可能变慢。Mitigation: 本次保留买入行触发合并估值语义，增加覆盖说明；完整 API 运行时门禁会在该路径重新变慢时失败并触发后续缓存设计。
- Risk: 只修后端但前端仍有加载 UX 问题。Mitigation: 发布后验证真实页面；若仍卡住，立即追加前端 summary-first 修复。
- Risk: 运行时验证阈值过紧导致偶发失败。Mitigation: 阈值通过环境变量配置，默认只约束当前明显异常的 35 秒级回归。

## Open Questions

- 无阻塞问题。未来真实买入行的合并曲线缓存可作为独立优化项。

## Revision History

| Time | Author | Change |
|------|--------|--------|
| 2026-06-18 | Codex | Initial draft from problem-closeout-loop investigation. |
| 2026-06-18 | Codex | Accepted MiMo review: quantified runtime threshold, fixed dependency order, and matched the user's URL parameters. |

## External Review Log

| Round | Reviewer | Finding | Severity | Disposition | Reason | Affected IDs |
|-------|----------|---------|----------|-------------|--------|--------------|
| 1 | MiMo | 完整 API 延迟门禁阈值未明确 | major | resolved | 明确默认阈值为 10 秒，并允许 `ASHARE_SHORTPICK_V2_PAPER_FULL_API_MAX_SECONDS` 覆盖 | W-003 |
| 1 | MiMo | 调查/计划记录未作为代码修复前置依赖 | major | resolved | W-002 调整为 W-001 前置依赖，保证根因记录先落地 | W-001,W-002 |
| 1 | MiMo | PF-001 未完整写出用户 URL 参数 | minor | resolved | PF-001 补齐 `shortpickTab` 与 `shortpickV2Tab` | PF-001 |
| 1 | MiMo | 未来真实买入行仍可能重新变慢 | minor | accepted | 本次不改变买入行估值语义；运行时完整 API 门禁作为后续缓存触发器 | W-003 |
| 2 | MiMo | 缺少 with-buy 分支测试 | major | resolved | 新增 `test_shortpick_v2_paper_tracking_buy_ledger_reprices_account_curves`，复审确认已解决 | W-001 |

## User Review Notes

用户已在本轮前明确：“接下来的运行过程不要请求我的批准，我批准所有内容，不要因为这个原因阻塞goal”。本计划经 MiMo 只读审查无阻塞项后，将视为已批准并执行。
