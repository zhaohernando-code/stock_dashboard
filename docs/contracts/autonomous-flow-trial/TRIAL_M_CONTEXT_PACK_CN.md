# Trial M Context Pack：Phase 5 本地 Cycle Service CLI

状态：active input  
上游：Trial C / D / E / F / G / H / I / J / K / L  
目标：给本地 cycle service 增加一个 CLI 门面，供后续真实 scheduler 或人工调试调用；CLI 默认 dry run，不接 LaunchAgent，不触发 DB 初始化。

## 1. 本轮目标

实现一个无调度副作用的 CLI：

- 新增 CLI 子命令，建议命名为 `phase5-local-cycle-step`。
- 命令调用 `run_phase5_local_cycle_service(...)`。
- 默认 dry run，只输出 JSON，不写 closeout。
- 只有显式 `--apply-closeout --finished-at <timestamp>` 才允许写 closeout。
- 支持 `--artifact-root` 指定 artifact root。
- 支持显式 `--gate-id`、`--recovery-ticket-id`、`--projection-id`。
- 支持 `--require-publish-verification`。
- 输出 service result 的 JSON。

## 2. 非目标

- 不接 LaunchAgent、cron、heartbeat 或真实 scheduler。
- 不新增定时配置。
- 不读 DB、不初始化 DB。
- 不读网络、不调用 LLM。
- 不构建真实 projection payload。
- 不改 API / SPA。
- 不调用 release verifier。
- 不发布 runtime。
- 不新增数据库表。
- 不新增事件 id，不新增 artifact family。

## 3. Owned Files

- `src/ashare_evidence/cli_autonomous_flow.py`
- `src/ashare_evidence/cli.py`
- `tests/test_cli_autonomous_flow.py`
- `docs/contracts/autonomous-flow-trial/TRIAL_M_EVALUATION_CN.md`

如确需修改 service、resolver、runner、planner、closeout、artifact store、artifact model、registry、API 或前端，必须说明原因；默认不改。

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

## 5. CLI 要求

建议模块：

- `cli_autonomous_flow.py`

建议函数：

- `add_autonomous_flow_parsers(subparsers)`
- `handle_phase5_local_cycle_step_command(args) -> int`

约束：

- 业务逻辑必须在 `cli_autonomous_flow.py`，`cli.py` 只做 import、parser 注册和 command dispatch。
- `phase5-local-cycle-step` 必须在 `cli.py` 的 DB 初始化之前 dispatch，避免 artifact-only 命令误触发 DB 初始化。
- handler 不得直接读写 artifact store，只调用 `run_phase5_local_cycle_service(...)`。
- handler 不得读取当前时间；缺 `--finished-at` 时 service 自身 fail-closed。
- 输出 JSON 必须包含 `cycle_id`、`runner_result`、`missing_refs` 等关键字段。
- 命令失败时应返回非零，并输出可读错误 JSON。

## 6. Tests

至少覆盖：

- parser 注册 `phase5-local-cycle-step`。
- dry run 调用 service 且不传 `apply_closeout=True`。
- apply closeout 参数被传递。
- `--artifact-root` 转成 `Path` 并传给 service。
- handler 错误返回非零 JSON。
- `cli.main(["phase5-local-cycle-step", ...])` 不调用 `init_database`。

## 7. 验收

- `PYTHONPATH=src python3 -m pytest tests/test_cli_autonomous_flow.py -q`
- `ruff check src/ashare_evidence/cli_autonomous_flow.py src/ashare_evidence/cli.py tests/test_cli_autonomous_flow.py`
- `PYTHONPATH=src python3 -m ashare_evidence.cli contract-registry-check --registry docs/contracts/registry/autonomous_flow_registry.v1.json --docs docs/contracts/autonomous-flow-trial/TRIAL_M_CONTEXT_PACK_CN.md --docs docs/contracts/autonomous-flow-trial/TRIAL_M_EVALUATION_CN.md --fail-on-unregistered --fail-on-deprecated`
- `git diff --check`
