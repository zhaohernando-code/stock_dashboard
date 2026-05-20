# Trial AP Context Pack：Scheduler Action Contract

状态：active input
上游：Trial W、AJ、AM、AO
目标：在真实 scheduler action 接入前，先建立每个 follow-up action 的结构化执行合同，让后续 executor 只能按合同扩展副作用，而不是在分支里临时写业务逻辑。

## 1. 背景

当前链路已有：

- follow-up plan：把 tick envelope 映射为 scheduler action。
- dry-run executor：把 action 映射为 planned effects，但映射仍是局部 helper。
- diagnostic 与 execution ledger：能记录诊断和安全 execution intent。
- idempotency reservation 与 clean closeout 门禁：为无人流程提供硬状态与收尾检查。

下一步不应直接执行真实 action。真实 action 前需要一个纯函数合同层，明确每类 action 的执行策略、允许副作用、必需输入和 durable output 边界。

## 2. 本轮目标

- 新增 scheduler action contract 模块，覆盖所有 `Phase5SchedulerAction`。
- 每个 action 至少声明：
  - action
  - execution strategy
  - planned effects
  - required inputs
  - allowed side effects
  - durable outputs
  - whether it may close cycle
- dry-run executor 复用该 contract 输出 planned effects，避免 action 语义分散。
- 合同层必须是无 IO、无 DB、无网络、无 artifact 写入的纯函数。

## 3. 非目标

- 不执行真实 scheduler action。
- 不写 recovery ticket。
- 不修改 cycle closeout。
- 不新增 CLI output。
- 不新增 artifact family 或 registry id。
- 不接 LaunchAgent、cron、heartbeat。

## 4. Owned Files

默认允许修改：

- `src/ashare_evidence/autonomous_flow_scheduler_action_contract.py`
- `src/ashare_evidence/autonomous_flow_scheduler_executor.py`
- `tests/test_autonomous_flow_scheduler_action_contract.py`
- `tests/test_autonomous_flow_scheduler_executor.py`
- `docs/contracts/autonomous-flow-trial/TRIAL_AP_EVALUATION_CN.md`

禁止修改：

- scheduler execution ledger / reservation store 语义文件。
- CLI output handler。
- frontend、stock research、runtime publish 文件。

## 5. 文件规模要求

- 新 action contract 模块 hard 180，warning 150。
- scheduler executor 当前约 177 行，hard 220，warning 200。
- 新 action contract 测试 hard 220，warning 190。
- scheduler executor 测试当前约 152 行，hard 220，warning 190。

## 6. 必测场景

- 所有 scheduler action 都有 contract。
- dry-run planned effects 来自 action contract，而不是重复局部映射。
- no-op / continue tracking 不允许 durable write。
- open recovery ticket / retry / rebuild / redesign / block cycle 均声明 required inputs 与 durable outputs。
- block cycle 明确 may close cycle，但仍不执行 closeout。
- contract 函数不创建 artifact root、不读取当前时间、不修改输入 plan。

## 7. 验收

- `PYTHONPATH=src python3 -m pytest tests/test_autonomous_flow_scheduler_action_contract.py tests/test_autonomous_flow_scheduler_executor.py -q`
- `ruff check src/ashare_evidence/autonomous_flow_scheduler_action_contract.py src/ashare_evidence/autonomous_flow_scheduler_executor.py tests/test_autonomous_flow_scheduler_action_contract.py tests/test_autonomous_flow_scheduler_executor.py`
- `PYTHONPATH=src python3 -m ashare_evidence.cli process-hardening-check --evaluation-doc docs/contracts/autonomous-flow-trial/TRIAL_AP_EVALUATION_CN.md --line-budget src/ashare_evidence/autonomous_flow_scheduler_action_contract.py:180:150 --line-budget src/ashare_evidence/autonomous_flow_scheduler_executor.py:220:200 --line-budget tests/test_autonomous_flow_scheduler_action_contract.py:220:190 --line-budget tests/test_autonomous_flow_scheduler_executor.py:220:190 --required-evidence tests/test_autonomous_flow_scheduler_action_contract.py:test_all_scheduler_actions_have_contracts`
- `PYTHONPATH=src python3 -m ashare_evidence.cli contract-registry-check --registry docs/contracts/registry/autonomous_flow_registry.v1.json --docs docs/contracts/autonomous-flow-trial/TRIAL_AP_CONTEXT_PACK_CN.md --docs docs/contracts/autonomous-flow-trial/TRIAL_AP_EVALUATION_CN.md --fail-on-unregistered --fail-on-deprecated`
- `git diff --check`
- `PYTHONPATH=src python3 -m pytest -q`
