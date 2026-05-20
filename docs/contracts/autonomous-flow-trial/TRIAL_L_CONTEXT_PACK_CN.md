# Trial L Context Pack：Phase 5 本地 Cycle Service

状态：active input  
上游：Trial C / D / E / F / G / H / I / J / K  
目标：组合 resolver 与 runner façade，提供一个后续 scheduler 可调用的本地 cycle service：按 `cycle_id` 解析 typed inputs，执行 planner，并可选应用 closeout。

## 1. 本轮目标

实现一个本地 service 入口：

- 输入 `cycle_id` 和可选 artifact ids。
- 调用 resolver 读取 typed input bundle。
- 调用 runner façade 得到 decision，并在 `apply_closeout=True` 时应用 closeout。
- 输出 typed service result，包含 input bundle、runner result 和 missing refs。
- dry run 默认不写 artifact。
- closeout 必须显式传入 `finished_at`。

## 2. 非目标

- 不接 LaunchAgent、cron、heartbeat 或真实 scheduler。
- 不决定运行频率、运行窗口或重试退避。
- 不启动 runner 子进程、LLM、DB、网络或发布脚本。
- 不构建真实 projection payload。
- 不改 API / SPA。
- 不调用 release verifier。
- 不发布 runtime。
- 不新增数据库表。
- 不新增事件 id，不新增 artifact family。

## 3. Owned Files

- `src/ashare_evidence/autonomous_flow_service.py`
- `tests/test_autonomous_flow_service.py`
- `docs/contracts/autonomous-flow-trial/TRIAL_L_EVALUATION_CN.md`

如确需修改 resolver、runner、planner、closeout、artifact store、artifact model、registry、API 或前端，必须说明原因；默认不改。

## 4. Registry IDs

本轮不新增事件或 artifact id。只允许引用：

- `phase5_cycle_ledger`
- `phase5_gate_readout`
- `phase5_recovery_ticket`
- `frontend_projection_manifest`
- `iface.scheduler.phase5-cycle-ledger.v1`
- `iface.gate.phase5-scheduler.v1`
- `iface.projection.publish-verifier.v1`
- `iface.recovery.scheduler-reviewer.v1`

## 5. Service 要求

建议对象和函数，不强制命名完全一致：

- `Phase5LocalCycleServiceResult`
- `run_phase5_local_cycle_service(...) -> Phase5LocalCycleServiceResult`

建议输入：

- `cycle_id: str`
- `gate_id: str | None = None`
- `recovery_ticket_id: str | None = None`
- `projection_id: str | None = None`
- `finished_at: str | None = None`
- `apply_closeout: bool = False`
- `require_publish_verification: bool = False`
- `root: Path | None = None`

建议输出字段：

- `cycle_id`
- `input_bundle`
- `runner_result`
- `missing_refs`

约束：

- service 可以只读 artifact store，并且只能通过 resolver 完成读取。
- service 不得直接调用 artifact store read/write 函数。
- service 不得绕过 runner façade 直接调用 planner 或 closeout。
- `apply_closeout=False` 默认 dry run，不写 artifact。
- `apply_closeout=True` 且 `finished_at` 缺失必须 fail-closed。
- resolver 缺 cycle / cycle mismatch 的错误必须透出，不吞掉。
- service 不读 DB、不读网络、不调用 LLM、不读取当前时间。

## 6. Tests

至少覆盖：

- dry run 从 artifact store 解析 bundle 并返回 runner decision，不写 closeout。
- apply closeout 通过 service 写回 cycle closeout。
- missing cycle 错误透出。
- missing gate/projection 进入 result missing refs，并让 runner decision 保守降级。
- explicit ids 覆盖 cycle refs。
- `apply_closeout=True` 缺 `finished_at` fail-closed。
- service 不绕过 resolver / runner，可用 monkeypatch 验证调用路径。

## 7. 验收

- `PYTHONPATH=src python3 -m pytest tests/test_autonomous_flow_service.py -q`
- `ruff check src/ashare_evidence/autonomous_flow_service.py tests/test_autonomous_flow_service.py`
- `PYTHONPATH=src python3 -m ashare_evidence.cli contract-registry-check --registry docs/contracts/registry/autonomous_flow_registry.v1.json --docs docs/contracts/autonomous-flow-trial/TRIAL_L_CONTEXT_PACK_CN.md --docs docs/contracts/autonomous-flow-trial/TRIAL_L_EVALUATION_CN.md --fail-on-unregistered --fail-on-deprecated`
- `git diff --check`
