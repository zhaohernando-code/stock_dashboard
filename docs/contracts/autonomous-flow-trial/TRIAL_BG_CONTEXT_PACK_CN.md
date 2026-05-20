# Trial BG 上下文包：Action Route Auto Apply CLI Smoke

目标：为 `phase5-local-cycle-step --output action-route-auto-apply` 补齐真实 artifact root 集成烟测，证明它不只在 mock handler 下顺序正确，也能在文件系统输入下稳定完成 skipped 或 route-selected durable write，并继续保持 fail-closed 与不触发数据库初始化。

## 1. 背景

Trial BF 已暴露 auto apply CLI：tick -> plan -> action -> route -> bind-and-apply。已有测试主要覆盖 handler 隔离与缺参阻断；本轮补真实 CLI 烟测，防止未来调度器接入时才发现 artifact root、生成 ID、写入结果或 exit code 口径不一致。

## 2. 本轮范围

必须做：

- 新增独立 smoke 测试文件，不扩写现有接近 warning 的大测试文件。
- 通过 `cli.main([...])` 调用真实 `phase5-local-cycle-step --output action-route-auto-apply`。
- 测试 happy path：已有完整 cycle/gate/projection fixture 时，`continue_tracking` route 应返回 skipped/no-op，不新增 scheduler diagnostic 或 execution ledger，并且不触发 DB 初始化。
- 测试 recovery path：缺失 cycle 时，CLI 应尊重真实 route contract。当前真实链路为 `open_recovery_ticket` follow-up，经 action preflight 后 route 到 `diagnostic_output`，auto apply 应写入 scheduler diagnostic；输出应包含生成的 `diagnostic_id`、`applied_output=diagnostic`，且 cycle event 不记录。
- 测试 fail-closed path：缺 `attempt_id` 或缺 `issued_at` 时不写 artifact，返回 blocked JSON。
- 验证输出不泄漏嵌套 service payload，例如 `plan_status`、`source_tick_status`、`input_bundle`、`runner_result`。
- 不修改 production code，除非测试暴露真实缺陷。

不得做：

- 不改变 `action-route-auto-apply` 语义。
- 不为了满足测试期望而改写 route；尤其不得解析或匹配 `reason` 自然语言文案来改变 route type。
- 不让 CLI 自动生成 `attempt_id` 或 `issued_at`。
- 不触发数据库初始化。
- 不新增对当前时间、随机数或网络的依赖。

BG1 复盘后的流程约束：真实 smoke 的职责是验证当前 contract 下的端到端行为，而不是把测试预设反向压到核心路由。若测试暴露“期望”和 contract 不一致，应先修正上下文包或新增结构化 contract，而不是用 reason 文案改道。

## 3. 子进程任务

| 子进程 | owned files | 目标 |
| --- | --- | --- |
| BG1 | auto apply smoke 测试、本评估文件 | 固化真实 CLI artifact root 烟测 |
| BG2 | auto apply smoke 测试、本评估文件 | 去除 reason 解析改道，按真实 route contract 重跑 |

子进程注意：本轮优先验证，不要主动改生产代码；如果发现必须改生产代码，先在评估文档里说明缺陷和修复理由。

## 4. 文件规模预算

- `tests/test_cli_autonomous_flow_action_route_auto_apply_smoke.py`：hard 220，warning 190。
- `tests/test_cli_autonomous_flow_action_route_auto_apply_output.py`：hard 220，warning 190，不建议修改。
- `tests/helpers_cli_autonomous_flow_smoke.py`：hard 260，warning 240，不建议修改。
- `src/ashare_evidence/cli_autonomous_flow_action_outputs.py`：hard 170，warning 150，不建议修改。
- `src/ashare_evidence/autonomous_flow_scheduler_action_route_auto_apply.py`：hard 170，warning 130，不建议修改。

如果达到 warning，必须拆分或压缩。

## 5. 验证命令

Focused tests：

```bash
PYTHONPATH=src python3 -m pytest tests/test_cli_autonomous_flow_action_route_auto_apply_smoke.py tests/test_cli_autonomous_flow_action_route_auto_apply_output.py tests/test_autonomous_flow_scheduler_action_route_auto_apply.py -q
```

Ruff：

```bash
ruff check tests/test_cli_autonomous_flow_action_route_auto_apply_smoke.py
```

Process hardening：

```bash
PYTHONPATH=src python3 -m ashare_evidence.cli process-hardening-check \
  --evaluation-doc docs/contracts/autonomous-flow-trial/TRIAL_BG_EVALUATION_CN.md \
  --line-budget tests/test_cli_autonomous_flow_action_route_auto_apply_smoke.py:220:190 \
  --line-budget tests/test_cli_autonomous_flow_action_route_auto_apply_output.py:220:190 \
  --line-budget tests/helpers_cli_autonomous_flow_smoke.py:260:240 \
  --line-budget src/ashare_evidence/cli_autonomous_flow_action_outputs.py:170:150 \
  --line-budget src/ashare_evidence/autonomous_flow_scheduler_action_route_auto_apply.py:170:130 \
  --required-evidence tests/test_cli_autonomous_flow_action_route_auto_apply_smoke.py:test_action_route_auto_apply_smoke_missing_cycle_records_diagnostic
```

Registry：

```bash
PYTHONPATH=src python3 -m ashare_evidence.cli contract-registry-check \
  --registry docs/contracts/registry/autonomous_flow_registry.v1.json \
  --docs docs/contracts/autonomous-flow-trial/TRIAL_BG_CONTEXT_PACK_CN.md \
  --docs docs/contracts/autonomous-flow-trial/TRIAL_BG_EVALUATION_CN.md \
  --fail-on-unregistered --fail-on-deprecated
```

Full regression：

```bash
PYTHONPATH=src python3 -m pytest -q
```
