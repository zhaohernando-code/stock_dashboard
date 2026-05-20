# Trial AZ 评估记录：CLI Action Route Preflight Output

状态：completed
输入：`TRIAL_AZ_CONTEXT_PACK_CN.md`
目标：评估 `phase5-local-cycle-step --output action-route-preflight` 是否能只读输出下一步 route 参数就绪状态，并保持无写入、无 ID 生成。

## 1. 子任务

| 子进程 | owned files | 目标 | 状态 |
| --- | --- | --- | --- |
| AZ1 | CLI action-route-preflight output、测试、本评估文件 | 暴露 route preflight CLI 输出 | completed |

## 2. 评分

| 维度 | 权重 |
| --- | ---: |
| CLI preflight 链路正确 | 35 |
| 参数名推导准确 | 25 |
| 副作用隔离 | 25 |
| 文件规模与门禁 | 15 |

自动重跑阈值：

- `action-route-preflight` 不走 `tick -> plan -> action -> route -> preflight`。
- CLI 参数到 provided argument names 的映射错误。
- blocked preflight 返回 0，或 ready preflight 返回非 0。
- 调用 diagnostic、execution ledger、full service 或 writer。
- 生成 ID/timestamp 或读取当前时间。
- 修改临界文件 `tests/test_cli_autonomous_flow_action_output.py`。
- focused tests、ruff、process hardening、registry 或 full regression 失败。

## 3. AZ1 结果

已完成。

- 新增 CLI 输出 `phase5-local-cycle-step --output action-route-preflight`。
- 执行链路为 `tick -> plan -> action -> route -> preflight`，输出 `Phase5SchedulerActionRoutePreflightResult` JSON。
- `provided_argument_names` 仅由已传 CLI 参数推导：`diagnostic_id`、`observed_at`、`execution_id`、`idempotency_key`、`created_at`。
- `status=ready` 返回 exit 0；`status=blocked` 返回 exit 4。
- 未调用 dry-run、diagnostic recorder、execution ledger recorder、full service；未生成 ID 或 timestamp。
- 未修改 `tests/test_cli_autonomous_flow_action_output.py`。

## 4. 主进程验证

AZ1 子进程验证记录：

- `PYTHONPATH=src python3 -m pytest tests/test_cli_autonomous_flow_action_route_preflight_output.py tests/test_cli_autonomous_flow_action_route_output.py tests/test_cli_autonomous_flow_action_output.py tests/test_cli_autonomous_flow_execution.py -q`：12 passed。
- `ruff check src/ashare_evidence/cli_autonomous_flow.py src/ashare_evidence/cli_autonomous_flow_outputs.py src/ashare_evidence/cli_autonomous_flow_action_outputs.py tests/test_cli_autonomous_flow_action_route_preflight_output.py`：passed。

主进程复核：

- `PYTHONPATH=src python3 -m pytest tests/test_cli_autonomous_flow_action_route_preflight_output.py tests/test_cli_autonomous_flow_action_route_output.py tests/test_cli_autonomous_flow_action_output.py tests/test_cli_autonomous_flow_execution.py -q`：12 passed。
- `ruff check src/ashare_evidence/cli_autonomous_flow.py src/ashare_evidence/cli_autonomous_flow_outputs.py src/ashare_evidence/cli_autonomous_flow_action_outputs.py tests/test_cli_autonomous_flow_action_route_preflight_output.py`：passed。
- `PYTHONPATH=src python3 -m ashare_evidence.cli process-hardening-check ...`：pass，行数预算与 required evidence 均通过。
- `PYTHONPATH=src python3 -m ashare_evidence.cli contract-registry-check ...`：pass。
- `git diff --check`：passed。
- `PYTHONPATH=src python3 -m pytest -q`：458 passed，147 deselected。

## 5. 重跑记录

无子进程自动重跑。一次 focused pytest 初跑发现新测试自身 helper 断言不适配 preflight `status` 字段，已收敛测试后通过。

## 6. 自评

通过 AZ1 目标。主进程复核未发现语义偏移；剩余流程风险是 `tests/test_cli_autonomous_flow_action_route_preflight_output.py` 与 `tests/test_cli_autonomous_flow_action_output.py` 均为 189 行，后续不能继续向这两个文件追加测试，应拆分新文件。
