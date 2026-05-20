# Trial BK 评估记录：Attempt Context CLI Output

状态：verified
输入：`TRIAL_BK_CONTEXT_PACK_CN.md`
目标：评估 CLI attempt context 输出是否能显式暴露稳定 `attempt_id` 生成能力，同时不改变执行路径的 fail-closed 语义。

## 1. 子任务

| 子进程 | owned files | 目标 | 状态 |
| --- | --- | --- | --- |
| BK1 | CLI attempt context 输出、测试、本评估文件 | 暴露显式 attempt context 输出 | passed |

## 2. 评分

| 维度 | 权重 |
| --- | ---: |
| 显式 CLI 契约 | 30 |
| 执行路径隔离 | 30 |
| 缺参 fail-closed | 20 |
| 文件规模与验证 | 20 |

自动重跑阈值：

- `attempt-context` 输出运行 tick、读写 artifact、调用 plan/action/route/apply/writer。
- CLI 读取当前时间、使用 random/uuid 或自动推导 `issued_at`。
- `action-route-auto-apply` 缺 `attempt_id` 不再 blocked。
- focused tests、ruff、process hardening、registry 或 full regression 失败。
- 既有 CLI helper 达到 warning 后仍继续堆叠。

## 3. BK1 结果

- `phase5-local-cycle-step --output attempt-context` 已新增，`--runner-id` 仅由该输出读取。
- attempt context 输出只调用 `build_phase5_scheduler_attempt_context(cycle_id=args.cycle_id, issued_at=args.issued_at, runner_id=args.runner_id)`，输出 typed result 的 `model_dump(mode="json")`。
- ready 返回 0；blocked 返回 4，沿用 blocked action exit code 口径。
- 新 helper `cli_autonomous_flow_attempt_outputs.py` 避免堆叠既有 CLI/action helper；未新增 artifact family 或 registry ID。
- `action-route-auto-apply` 缺 `attempt_id` 的 fail-closed 行为保持不变，由既有 focused test 覆盖。

## 4. 主进程验证

主进程复核隔离 worktree diff 后并入集成分支；验证结果：

- Focused tests：`9 passed in 0.52s`。
- Ruff：passed。
- Process hardening：status=pass，issue_count=0；`tests/test_cli_autonomous_flow_attempt_context_output.py` 154 行，低于 warning 160，但后续不应继续堆叠。
- Registry：status=pass，issue_count=0。
- Full regression：`506 passed, 147 deselected in 21.73s`。

主进程语义复核：

- `attempt-context` 分支在 tick 前返回，只调用 attempt context core，不读写 artifact，不调用 plan/action/route/apply/writer。
- `action-route-auto-apply` 未修改，缺 `attempt_id` fail-closed 仍由 focused test 覆盖。
- 新 helper 复制 blocked exit code 常量，避免从 action helper 导入私有实现细节；该取舍可接受。

## 5. 重跑记录

BK1 本地验证；主进程已复跑 focused gates：

- `PYTHONPATH=src python3 -m pytest tests/test_cli_autonomous_flow_attempt_context_output.py tests/test_cli_autonomous_flow_action_route_auto_apply_output.py -q`：9 passed。
- `ruff check src/ashare_evidence/cli_autonomous_flow.py src/ashare_evidence/cli_autonomous_flow_outputs.py src/ashare_evidence/cli_autonomous_flow_action_outputs.py src/ashare_evidence/cli_autonomous_flow_attempt_outputs.py tests/test_cli_autonomous_flow_attempt_context_output.py`：passed。
- `PYTHONPATH=src python3 -m ashare_evidence.cli process-hardening-check ...`：status=pass，issue_count=0。
- `PYTHONPATH=src python3 -m ashare_evidence.cli contract-registry-check ...`：status=pass，issue_count=0。
- `PYTHONPATH=src python3 -m pytest -q`：506 passed，147 deselected。

## 6. 自评

满足显式 CLI 契约、执行路径隔离、缺参 fail-closed 与文件规模要求。流程约束：临近 warning 的测试文件后续新增场景应拆分，不继续纵向堆叠。
