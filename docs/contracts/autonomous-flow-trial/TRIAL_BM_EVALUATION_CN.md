# Trial BM 评估记录：Attempt Route Auto Apply CLI Output

状态：verified
输入：`TRIAL_BM_CONTEXT_PACK_CN.md`
目标：评估显式 attempt route auto apply CLI 输出是否能作为无人调度入口，同时不破坏旧输出语义。

## 1. 子任务

| 子进程 | owned files | 目标 | 状态 |
| --- | --- | --- | --- |
| BM1 | CLI attempt-route-auto-apply 输出、测试、本评估文件 | 暴露显式组合输出 | passed |

## 2. 评分

| 维度 | 权重 |
| --- | ---: |
| CLI 显式组合契约 | 30 |
| 旧输出隔离 | 25 |
| 缺参 fail-closed | 25 |
| 文件规模与验证 | 20 |

自动重跑阈值：

- 缺 `issued_at` 或 `runner_id` 时进入 core apply 或写 artifact。
- CLI 读取当前时间、使用 random/uuid、自动生成 `issued_at` 或解析 reason。
- 旧 `action-route-auto-apply` 缺 `attempt_id` 不再 blocked。
- focused tests、ruff、process hardening、registry 或 full regression 失败。
- 新场景把临界测试文件推到 warning 以上。

## 3. BM1 结果

- `phase5-local-cycle-step --output` 新增 `attempt-route-auto-apply`。
- 新输出按 tick -> plan -> action -> route -> `build_attempt_context_and_apply_phase5_scheduler_action_route(...)` 顺序执行。
- `issued_at` 与 `runner_id` 仅从 CLI 显式参数透传；缺参时由 BL core typed result 返回 blocked，CLI 不补值、不读取当前时间。
- 输出为组合 result 的 `model_dump(mode="json")`，blocked exit code 沿用 action blocked 口径 4；ready/applied/skipped 返回 0。
- 既有 `action-route-auto-apply` 未改语义，缺 `attempt_id` 仍由原路径 blocked。
- 分发层只增加 handler 注入与一个 output 分支；组合逻辑放在 `cli_autonomous_flow_attempt_outputs.py`，避免继续扩写主 outputs 文件。

## 4. 主进程验证

主进程复核隔离 worktree diff 后并入集成分支；BM1 本地验证与主进程 focused gates 均通过：

- Focused tests：BM1 `9 passed in 0.59s`；main `9 passed in 0.60s`。
- Ruff：passed。
- Process hardening：status=pass，issue_count=0。
- Registry：status=pass，issue_count=0。
- Full regression：BM1 `513 passed, 147 deselected in 23.16s`；main `513 passed, 147 deselected in 22.31s`。

主进程语义复核：

- 新输出复用 BL core，CLI 只透传显式 `issued_at` 与 `runner_id`，不自行生成 blocked result 或时间值。
- 旧 `action-route-auto-apply` 未改语义，缺 `attempt_id` 仍由旧 focused test 覆盖。
- 文件规模风险：`cli_autonomous_flow_outputs.py` 150 行接近 warning 160，新 BM 测试 178 行接近 warning 180；后续 CLI 输出必须拆新 helper / 新测试文件，不继续扩写这两个文件。

## 5. 重跑记录

- `PYTHONPATH=src python3 -m pytest tests/test_cli_autonomous_flow_attempt_route_auto_apply_output.py tests/test_cli_autonomous_flow_action_route_auto_apply_output.py -q`：9 passed in 0.59s。
- `ruff check src/ashare_evidence/cli_autonomous_flow.py src/ashare_evidence/cli_autonomous_flow_outputs.py src/ashare_evidence/cli_autonomous_flow_action_outputs.py src/ashare_evidence/cli_autonomous_flow_attempt_outputs.py tests/test_cli_autonomous_flow_attempt_route_auto_apply_output.py`：passed。
- `PYTHONPATH=src python3 -m ashare_evidence.cli process-hardening-check ...`：status=pass，issue_count=0。
- `PYTHONPATH=src python3 -m ashare_evidence.cli contract-registry-check ...`：status=pass，issue_count=0。
- `PYTHONPATH=src python3 -m pytest -q`：513 passed，147 deselected in 23.16s。

## 6. 自评

实现保持显式上下文边界，不把旧 auto-apply 改成自动生成 attempt id；缺上下文的真实 CLI 测试同时断言无 artifact 写入和 bind/apply 未进入。流程约束：接近 warning 的 CLI dispatcher 与 BM 测试文件后续只允许拆分，不允许继续堆叠。
