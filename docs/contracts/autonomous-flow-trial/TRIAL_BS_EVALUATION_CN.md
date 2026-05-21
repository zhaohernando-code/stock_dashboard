# Trial BS 评估记录：CLI Attempt Run Recording Opt-in

状态：verified
输入：`TRIAL_BS_CONTEXT_PACK_CN.md`
目标：评估 CLI 是否以显式 opt-in 方式接入 attempt/run artifact 记录，并保持默认兼容。

## 1. 子任务

| 子进程 | owned files | 目标 | 状态 |
| --- | --- | --- | --- |
| BS1 | CLI opt-in 接入、focused tests、本评估文件 | 显式开关下写 attempt/run artifact，默认保持兼容 | passed |

## 2. 评分

| 维度 | 权重 |
| --- | ---: |
| 默认兼容性 | 30 |
| opt-in 写入正确性 | 30 |
| blocked precondition 处理 | 20 |
| 副作用边界清晰 | 10 |
| 验证完整性 | 10 |

自动重跑阈值：

- 默认 `attempt-route-auto-apply` 输出 shape 改变或新增文件副作用。
- 未显式开关就写入 attempt/run artifact。
- record precondition 缺失时崩溃。
- 解析自然语言 reason。
- focused tests、ruff、process hardening、registry 或 full regression 失败。

## 3. BS1 结果

- `phase5-local-cycle-step` 增加 `--record-attempt-run` 显式开关和可选 `--attempt-run-id`。
- 默认 `attempt-route-auto-apply` 仍直接输出 apply result，focused test 覆盖未开关不调用 recorder、不写 artifact。
- 开关打开后输出 record envelope，包含 `apply_result`、`attempt_run_artifact`、`attempt_run_artifact_path`、`attempt_run_record_status`，并写入 BR attempt/run artifact。
- 缺 `issued_at` 或 `runner_id` 时返回 blocked record envelope，不调用 recorder、不写 artifact，exit code 仍来自 apply result blocked 语义。

## 4. 主进程验证

- Worker 本地验证：focused tests、ruff、process hardening、registry 均通过。
- 主进程复核：Boole 初版将较多测试装配加入既有 attempt-route helper，导致 helper 接近结构预算；主进程拆出 `helpers_cli_autonomous_flow_attempt_recording.py`，让通用 attempt-route helper 回到 45 行。
- `PYTHONPATH=src python3 -m pytest tests/test_cli_autonomous_flow_attempt_route_auto_apply_output.py tests/test_scheduler_attempt_run_recorder.py -q`：通过，10 passed。
- `ruff check ...`：通过。
- `PYTHONPATH=src python3 -m ashare_evidence.cli process-hardening-check ...`：通过，0 issues。
- `PYTHONPATH=src python3 -m ashare_evidence.cli contract-registry-check ...`：通过，0 issues。
- `PYTHONPATH=src python3 -m pytest -q`：通过，531 tests，147 deselected。

## 5. 重跑记录

- Worker 第一次 process hardening 失败原因：本文档仍含未完成标记；另测试文件触达 warning 线。已更新本文档并将长测试装配移入 helper，使目标测试文件降至 warning 线以下；重跑已通过。
- 主进程额外拆分 recording helper，避免既有 attempt-route helper 继续膨胀；focused tests 与 ruff 已重跑通过。
- 主进程补充 process hardening、registry、full regression 后均通过。

## 6. 自评

- 满足默认兼容、显式 opt-in 写入和缺 recorder 上下文 blocked envelope 的本轮要求。未改 `action-route-auto-apply`，未解析 reason，未使用 `datetime.now`、`uuid` 或 `random`，未修改 `process_hardening.py`。主进程发现并修正了 helper 膨胀问题，后续 CLI 测试应继续按领域拆 helper。
