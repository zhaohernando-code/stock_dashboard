# Trial CD 评估记录：Intervention Run Artifact

状态：verified
输入：`TRIAL_CD_CONTEXT_PACK_CN.md`
目标：评估 intervention apply 是否具备可选硬存储能力且不改变默认行为。

## 1. 子任务

| 子进程 | owned files | 目标 | 状态 |
| --- | --- | --- | --- |
| CD1 | artifact、store、recorder、CLI envelope、tests、本评估文件 | 记录 intervention apply envelope | passed |

## 2. 评分

| 维度 | 权重 |
| --- | ---: |
| 硬存储完整性 | 35 |
| 默认行为兼容 | 25 |
| 记录前置条件 | 20 |
| 验证完整性 | 20 |

自动重跑阈值：

- 默认 apply 开始写 intervention run artifact。
- opt-in 记录缺少 runner_id/issued_at 时仍写 artifact。
- focused tests、ruff、process hardening 或 full regression 失败。

## 3. CD1 结果

- 新增 `phase5_scheduler_attempt_intervention_run` artifact family、schema、store 与 recorder。
- `attempt-run-intervention-apply` 默认行为不变；只有传入 `--record-intervention-run` 时才返回记录 envelope 并写 artifact。
- opt-in 记录要求 `issued_at` 与 `runner_id`；缺失时返回 blocked record envelope，不写 artifact。
- registry 新增 attempt intervention run event 与 artifact family，注册对象从 59 增至 61。

## 4. 主进程验证

- `PYTHONPATH=src python3 -m pytest tests/test_scheduler_attempt_run_intervention_recorder.py tests/test_cli_autonomous_flow_attempt_intervention_apply_output.py -q` 通过，6 passed。
- `ruff check ...` 通过。
- `PYTHONPATH=src python3 -m ashare_evidence.cli contract-registry-check ...` 通过，issue_count 0。
- `PYTHONPATH=src python3 -m pytest -q` 通过，562 passed，147 deselected。

## 5. 重跑记录

- 首轮实现只包含代码存储能力；主进程补充 registry event、artifact family 与 schema，避免硬存储成为未注册对象。

## 6. 自评

- 本轮补齐 intervention apply 结果硬存储，但保持 opt-in，避免破坏 CC 的默认 side effect 边界。
- 下一轮可以基于该 artifact 增加 readout/query，让看板和后续调度器不必扫描原始 JSON。
