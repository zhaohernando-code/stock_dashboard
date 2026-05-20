# Trial AG Context Pack：Implementation Process Hardening Rules

状态：active input  
上游：Trial AC / AD / AE / AF  
目标：把近期实现试验暴露出的流程经验固化到自运行开发流程合同和试验记录，减少后续无人开发中重复踩坑。

## 1. 背景

近期几轮试验说明，子进程可以高效完成局部实现，但仍需要主进程把“可运行”提升为“可长期维护”：

- Trial AC 证明测试 fixture 和 smoke tests 需要主动拆分，不能等文件超线后再补救。
- Trial AE 证明 298 行测试文件虽未超过硬上限，但已经是后续劣化信号。
- Trial AF 证明子进程通过门禁后仍可能漏掉 legacy migration 边界，主进程必须做语义审查而不是只看 pytest。
- Reservation 这类基座能力不能只做扫描判断；必须有硬状态、原子边界和 crash replay 语义。

本轮只固化流程规则，不做业务功能。

## 2. 本轮目标

- 更新 `docs/contracts/AUTONOMOUS_DEVELOPMENT_FLOW_CN.md`。
- 更新 `docs/contracts/AUTONOMOUS_FLOW_TRIAL_2026-05-20_CN.md`。
- 新增本轮评估文档。
- 明确哪些规则进入 Context Pack 模板、子进程验收、主进程评估和重跑触发。

## 3. 非目标

- 不修改代码。
- 不修改 registry。
- 不改 API / SPA。
- 不运行 runtime publish。
- 不重写历史 Trial 文档。

## 4. Owned Files

默认允许修改：

- `docs/contracts/AUTONOMOUS_DEVELOPMENT_FLOW_CN.md`
- `docs/contracts/AUTONOMOUS_FLOW_TRIAL_2026-05-20_CN.md`
- `docs/contracts/autonomous-flow-trial/TRIAL_AG_EVALUATION_CN.md`

## 5. 必须固化的规则

### 文件规模治理

- Context Pack 必须声明关注文件的当前行数与目标上限。
- 子进程输出如果使测试文件接近 260 行，必须主动拆分；接近 300 行不得作为“通过即可合并”。
- 主进程评估中必须把“刚好低于上限”视为劣化信号。

### 子进程输出验收

- 子进程门禁通过不等于主进程接受。
- 主进程必须做至少一次语义 diff 审查，覆盖迁移、旧数据、crash replay、冲突分支、副作用边界。
- 如果主进程发现语义缺口，可在主进程修正小范围问题；如果缺口说明 Context Pack 方向错误，则必须重跑子进程。

### 基座能力规则

- 幂等、调度、artifact 写入、状态机等基座能力不得只靠“先查再写”的扫描逻辑。
- 需要硬状态时，必须设计可审计 artifact / reservation / ledger。
- 需要并发保护时，必须明确原子边界；如只支持本地文件系统原子语义，必须写入残余风险。

### Legacy migration 验收

- 新机制接入已有 artifact family 时，测试必须覆盖“旧数据存在、新索引不存在”的迁移路径。
- 新硬状态不得让旧数据绕过冲突检测或 claim gate。

### 文档与门禁

- 评估文档必须记录子进程结果、主进程修正、最终门禁和残余风险。
- 合同文档变更后必须至少执行 registry check 或说明不适用；本文档包含 registered ids 时必须执行 registry check。

## 6. 验收

- `PYTHONPATH=src python3 -m ashare_evidence.cli contract-registry-check --registry docs/contracts/registry/autonomous_flow_registry.v1.json --docs docs/contracts/AUTONOMOUS_DEVELOPMENT_FLOW_CN.md --docs docs/contracts/AUTONOMOUS_FLOW_TRIAL_2026-05-20_CN.md --docs docs/contracts/autonomous-flow-trial/TRIAL_AG_CONTEXT_PACK_CN.md --docs docs/contracts/autonomous-flow-trial/TRIAL_AG_EVALUATION_CN.md --fail-on-unregistered --fail-on-deprecated`
- `git diff --check`
- `wc -l docs/contracts/AUTONOMOUS_DEVELOPMENT_FLOW_CN.md docs/contracts/AUTONOMOUS_FLOW_TRIAL_2026-05-20_CN.md docs/contracts/autonomous-flow-trial/TRIAL_AG_EVALUATION_CN.md`
