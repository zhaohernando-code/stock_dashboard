# Trial AB Context Pack：CLI Diagnostic Output

状态：active input  
上游：Trial X / AA  
目标：给 `phase5-local-cycle-step` 增加 `--output diagnostic`，执行 tick -> follow-up plan -> scheduler diagnostic recorder，把 scheduler 诊断事实写入 artifact store，并输出小型 diagnostic record result。

## 1. 背景

Trial AA 已提供执行前 diagnostic recorder，但当前只有内部函数入口。为了让后续本地 scheduler、cron/heartbeat 包装器或人工调试都能通过统一 CLI 触发“只记录、不执行”的硬存储路径，需要把它接入 `phase5-local-cycle-step`。

## 2. 本轮目标

扩展 CLI 输出形态：

- `status`、`plan`、`dry-run`、`full` 语义保持不变。
- 新增 `--output diagnostic`。
- `diagnostic` 路径调用 tick、follow-up plan、scheduler diagnostic recorder。
- `diagnostic` 输出 diagnostic record result JSON。
- `diagnostic` 返回 0。
- `diagnostic` 需要调用方显式传入 `--diagnostic-id` 与 `--observed-at`，函数内部不读取当前时间。

## 3. 非目标

- 不执行真实 scheduler action。
- 不写 recovery ticket。
- 不创建 follow-up cycle。
- 不修改 tick、plan、dry-run executor、diagnostic recorder 行为。
- 不改 registry/schema。
- 不改 API / SPA。
- 不发布 runtime。

## 4. Owned Files

默认只允许修改：

- `src/ashare_evidence/cli_autonomous_flow.py`
- `tests/test_cli_autonomous_flow.py`
- `tests/test_cli_autonomous_flow_outputs.py`
- `tests/test_cli_autonomous_flow_diagnostics.py`
- `tests/helpers_cli_autonomous_flow.py`
- `docs/contracts/autonomous-flow-trial/TRIAL_AB_EVALUATION_CN.md`

不要向 `tests/test_cli_autonomous_flow_smoke.py` 继续追加测试；该文件已接近 300 行。

## 5. CLI 合同

Parser：

- `--output` choices 扩展为 `status|plan|dry-run|diagnostic|full`。
- 增加 `--diagnostic-id`，默认 None。
- 增加 `--observed-at`，默认 None。

Diagnostic 路径：

- 如果缺少 `--diagnostic-id` 或 `--observed-at`，输出小错误 JSON，返回 2。
- 调用 tick，参数完整透传。
- 调用 follow-up planner。
- 调用 scheduler diagnostic recorder。
- 输出 diagnostic record result JSON。
- 返回 0。
- 不调用 service。
- 不调用 dry-run executor。

输出安全：

- 不包含完整 tick payload、status projection、plan payload、input bundle、runner result、release manifest ref、digest、traceback。

## 6. Tests

至少覆盖：

- parser 接受 `--output diagnostic`、`--diagnostic-id`、`--observed-at`。
- 缺少 diagnostic 参数时返回 2 且不调用 tick/service。
- diagnostic 路径调用 tick、plan、diagnostic recorder，不调用 service/dry-run。
- diagnostic 路径参数完整透传给 tick，并把 diagnostic id、observed_at、root 传给 recorder。
- error tick 仍返回 0 并输出 diagnostic record result。
- 真实 artifact root happy path：写 diagnostic artifact 且 cycle event 被追加。
- 真实 artifact root missing cycle：仍写 diagnostic artifact，cycle event 未追加，exit code 0。
- 新增或修改的 CLI 测试文件均低于 300 行。

## 7. 验收

- `PYTHONPATH=src python3 -m pytest tests/test_cli_autonomous_flow.py tests/test_cli_autonomous_flow_outputs.py tests/test_cli_autonomous_flow_diagnostics.py tests/test_autonomous_flow_scheduler_diagnostics.py -q`
- `ruff check src/ashare_evidence/cli_autonomous_flow.py tests/test_cli_autonomous_flow.py tests/test_cli_autonomous_flow_outputs.py tests/test_cli_autonomous_flow_diagnostics.py tests/helpers_cli_autonomous_flow.py`
- `wc -l tests/test_cli_autonomous_flow.py tests/test_cli_autonomous_flow_outputs.py tests/test_cli_autonomous_flow_diagnostics.py tests/test_cli_autonomous_flow_smoke.py tests/helpers_cli_autonomous_flow.py`
- `PYTHONPATH=src python3 -m ashare_evidence.cli contract-registry-check --registry docs/contracts/registry/autonomous_flow_registry.v1.json --docs docs/contracts/autonomous-flow-trial/TRIAL_AB_CONTEXT_PACK_CN.md --docs docs/contracts/autonomous-flow-trial/TRIAL_AB_EVALUATION_CN.md --fail-on-unregistered --fail-on-deprecated`
- `git diff --check`
