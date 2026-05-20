# Trial BF 上下文包：Action Route Auto Apply CLI

目标：新增一个 CLI 输出模式，把 tick -> plan -> action -> route -> bind-and-apply 串成单一可调用入口。该入口用于无人调度器后续触发一次安全的 route 自动应用，但参数绑定仍必须委托 Trial BE 的 core facade，不在 CLI 层重新实现生成规则。

## 1. 背景

Trial BE 已提供 `bind_and_apply_phase5_scheduler_action_route(...)`，它先执行 route argument binding，再调用 route apply core。本轮把该能力暴露到 `phase5-local-cycle-step` CLI，让调用方只需传入 `--attempt-id` 与可选 `--issued-at`，即可得到 typed apply result。

CLI 层必须继续保持薄：它负责串接既有 handlers、打印 JSON、返回 exit code；不读取当前时间、不生成随机数、不直接调用 diagnostic/execution writer。

## 2. 本轮范围

必须做：

- 新增 `--output action-route-auto-apply`。
- 新增 CLI 参数 `--attempt-id` 与 `--issued-at`，仅该输出模式消费。
- 在 handlers dataclass 中接入 `bind_and_apply_phase5_scheduler_action_route`，命名应表达 auto apply 语义。
- 新增 action output handler，执行顺序必须是 tick -> plan -> action -> route -> bind-and-apply。
- `bind-and-apply` 入参必须是 `plan`、`route_result`、`attempt_id=args.attempt_id`、`issued_at=args.issued_at`、`root=args.artifact_root`。
- handler 不能调用 dry-run、diagnostic recorder、execution recorder、preflight 或 legacy apply handler。
- 输出 JSON 为 apply result 的 `model_dump(mode="json")`。
- blocked 返回 exit code 4；applied/skipped 返回 0。
- 缺失 `issued_at` 时应通过 core facade fail closed，不写 artifact。
- 缺失 `attempt_id` 时也必须 fail closed，不能让底层生成含空 attempt 的 ID；该校验必须收敛到 core facade，CLI 不应自己构造 route apply result。

不得做：

- 不改变 `action-route-apply` 的显式参数模式。
- 不修改 route binding 生成规则。
- 不让 CLI 读取系统时间或自动补 `issued_at`。
- 不复用自然语言 reason 解析来决定参数。

## 3. 子进程任务

| 子进程 | owned files | 目标 |
| --- | --- | --- |
| BF1 | CLI parser/dispatcher/action handler、聚焦测试、本评估文件 | 暴露 auto apply CLI 并验证 fail-closed |

子进程注意：当前多个 CLI 测试文件接近 190 行 warning，不要继续扩写既有大测试文件；新增独立测试文件。

BF1 复盘后的流程约束：如果某个 fail-closed 规则对 CLI 和未来调度器都成立，应该放在核心层，不放在 CLI handler。CLI handler 只负责收集显式参数、调用核心能力、打印结果和映射 exit code。

## 4. 文件规模预算

- `src/ashare_evidence/cli_autonomous_flow.py`：hard 130，warning 110。
- `src/ashare_evidence/cli_autonomous_flow_outputs.py`：hard 180，warning 150。
- `src/ashare_evidence/cli_autonomous_flow_action_outputs.py`：hard 170，warning 150。
- `src/ashare_evidence/autonomous_flow_scheduler_action_route_auto_apply.py`：hard 170，warning 130。
- `tests/test_cli_autonomous_flow_action_route_auto_apply_output.py`：hard 220，warning 190。
- `tests/test_autonomous_flow_scheduler_action_route_auto_apply.py`：hard 240，warning 200。
- `tests/test_cli_autonomous_flow_action_route_apply_output.py`：hard 220，warning 190，不建议修改。

如果达到 warning，必须拆分或压缩。

## 5. 验证命令

Focused tests：

```bash
PYTHONPATH=src python3 -m pytest tests/test_cli_autonomous_flow_action_route_auto_apply_output.py tests/test_autonomous_flow_scheduler_action_route_auto_apply.py tests/test_cli_autonomous_flow_action_route_apply_output.py -q
```

Ruff：

```bash
ruff check src/ashare_evidence/cli_autonomous_flow.py src/ashare_evidence/cli_autonomous_flow_outputs.py src/ashare_evidence/cli_autonomous_flow_action_outputs.py tests/test_cli_autonomous_flow_action_route_auto_apply_output.py
```

Process hardening：

```bash
PYTHONPATH=src python3 -m ashare_evidence.cli process-hardening-check \
  --evaluation-doc docs/contracts/autonomous-flow-trial/TRIAL_BF_EVALUATION_CN.md \
  --line-budget src/ashare_evidence/cli_autonomous_flow.py:130:110 \
  --line-budget src/ashare_evidence/cli_autonomous_flow_outputs.py:180:150 \
  --line-budget src/ashare_evidence/cli_autonomous_flow_action_outputs.py:170:150 \
  --line-budget src/ashare_evidence/autonomous_flow_scheduler_action_route_auto_apply.py:170:130 \
  --line-budget tests/test_cli_autonomous_flow_action_route_auto_apply_output.py:220:190 \
  --line-budget tests/test_autonomous_flow_scheduler_action_route_auto_apply.py:240:200 \
  --line-budget tests/test_cli_autonomous_flow_action_route_apply_output.py:220:190 \
  --required-evidence tests/test_cli_autonomous_flow_action_route_auto_apply_output.py:test_action_route_auto_apply_output_calls_bind_and_apply_only
```

Registry：

```bash
PYTHONPATH=src python3 -m ashare_evidence.cli contract-registry-check \
  --registry docs/contracts/registry/autonomous_flow_registry.v1.json \
  --docs docs/contracts/autonomous-flow-trial/TRIAL_BF_CONTEXT_PACK_CN.md \
  --docs docs/contracts/autonomous-flow-trial/TRIAL_BF_EVALUATION_CN.md \
  --fail-on-unregistered --fail-on-deprecated
```

Full regression：

```bash
PYTHONPATH=src python3 -m pytest -q
```
