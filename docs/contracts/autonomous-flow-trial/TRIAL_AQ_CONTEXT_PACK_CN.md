# Trial AQ Context Pack：Scheduler Action Preflight

状态：active input
上游：Trial AP
目标：把 scheduler action contract 从静态声明升级为可调用的纯 preflight 校验，让真实 action 接入前可以先判断输入、授权副作用和 durable output 边界是否满足。

## 1. 背景

Trial AP 已建立每个 scheduler action 的 execution strategy、required inputs、allowed side effects、durable outputs 和 may close cycle。当前缺口是这些规则还只是静态映射；真实 action 接入时仍可能绕过 required inputs 或写出 contract 未允许的副作用。

本轮做纯 preflight，不执行真实 action。

## 2. 本轮目标

- 在 action contract 模块中新增 typed preflight result。
- 提供纯函数，例如 `preflight_phase5_scheduler_action(...)`：
  - 输入 action。
  - 输入 provided input names。
  - 输入 requested side effects。
  - 返回 ready / blocked、missing inputs、unauthorized side effects、durable outputs、may close cycle、reason。
- preflight 不读取文件、不写 artifact、不读当前时间、不访问 DB/网络。
- 为后续真实 action executor 提供统一前置校验入口。

## 3. 非目标

- 不执行真实 scheduler action。
- 不写 recovery ticket、projection、cycle closeout、scheduler execution ledger。
- 不新增 CLI output。
- 不修改 ledger / reservation 语义。
- 不接 LaunchAgent、cron、heartbeat。

## 4. Owned Files

默认允许修改：

- `src/ashare_evidence/autonomous_flow_scheduler_action_contract.py`
- `tests/test_autonomous_flow_scheduler_action_contract.py`
- `tests/test_autonomous_flow_scheduler_action_preflight.py`
- `docs/contracts/autonomous-flow-trial/TRIAL_AQ_EVALUATION_CN.md`

禁止修改：

- CLI output handler。
- scheduler execution ledger / reservation store。
- `autonomous_flow.py` 里的 artifact 写入原语。
- frontend、stock research、runtime publish 文件。

## 5. 文件规模要求

- action contract 模块当前 113 行，hard 220，warning 180。
- action contract 测试当前 92 行，hard 180，warning 150。
- action preflight 测试如新增，hard 180，warning 150。
- 评估文档 hard 140，warning 110。

## 6. 必测场景

- all required inputs + allowed side effects -> ready。
- missing required inputs -> blocked，列出 missing inputs。
- requested side effect 不在 allowed side effects -> blocked。
- action with `allowed_side_effects=("none",)` only accepts no side effects or explicit `none`。
- result includes durable outputs and may close cycle from contract。
- preflight 不修改输入集合，不触碰 IO/DB/network/time。

## 7. 验收

- `PYTHONPATH=src python3 -m pytest tests/test_autonomous_flow_scheduler_action_contract.py tests/test_autonomous_flow_scheduler_action_preflight.py -q`
- `ruff check src/ashare_evidence/autonomous_flow_scheduler_action_contract.py tests/test_autonomous_flow_scheduler_action_contract.py tests/test_autonomous_flow_scheduler_action_preflight.py`
- `PYTHONPATH=src python3 -m ashare_evidence.cli process-hardening-check --evaluation-doc docs/contracts/autonomous-flow-trial/TRIAL_AQ_EVALUATION_CN.md --line-budget src/ashare_evidence/autonomous_flow_scheduler_action_contract.py:220:180 --line-budget tests/test_autonomous_flow_scheduler_action_contract.py:180:150 --line-budget tests/test_autonomous_flow_scheduler_action_preflight.py:180:150 --required-evidence tests/test_autonomous_flow_scheduler_action_preflight.py:test_action_preflight_blocks_missing_required_inputs`
- `PYTHONPATH=src python3 -m ashare_evidence.cli contract-registry-check --registry docs/contracts/registry/autonomous_flow_registry.v1.json --docs docs/contracts/autonomous-flow-trial/TRIAL_AQ_CONTEXT_PACK_CN.md --docs docs/contracts/autonomous-flow-trial/TRIAL_AQ_EVALUATION_CN.md --fail-on-unregistered --fail-on-deprecated`
- `git diff --check`
- `PYTHONPATH=src python3 -m pytest -q`
