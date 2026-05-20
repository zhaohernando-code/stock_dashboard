# Trial X 评估记录：Phase 5 CLI Dry-run Output

状态：主进程复核通过  
输入：`TRIAL_X_CONTEXT_PACK_CN.md`  
目标：评估 CLI 是否能显式输出 scheduler dry-run result，同时保持 status / plan / full 路径稳定。

## 1. 子任务

| 子进程 | owned files | 目标 |
| --- | --- | --- |
| X1 | CLI、CLI tests、smoke tests、本评估文件 | 增加 `--output dry-run` |

## 2. 评分

| 维度 | 权重 |
| --- | ---: |
| CLI dry-run 合同符合度 | 35 |
| 兼容性 | 25 |
| 输出泄露保护 | 20 |
| 测试覆盖与文件规模 | 20 |

自动重跑阈值：

- 总分低于 85。
- 默认 `status`、`plan` 或 `full` 语义被改变。
- `--output dry-run` 直接调用 service 或 status projection。
- `--output dry-run` 返回 tick error code，而不是 0。
- dry-run 输出泄露 nested tick/plan payload、release manifest ref 或 digest。
- 修改后任一 CLI 测试文件超过 300 行。
- focused tests 失败。

## 3. X1 结果

结论：通过。`phase5-local-cycle-step` 已新增 `--output dry-run`，按 tick -> follow-up plan -> scheduler dry-run executor 的无副作用链路生成 dry-run result，并返回 0。

变更范围：

- `src/ashare_evidence/cli_autonomous_flow.py`：新增 `dry-run` output choice；抽取 `_run_tick_from_args`，保证 `status` / `plan` / `dry-run` 的 tick 参数透传一致；`full` 仍走 service。
- `tests/test_cli_autonomous_flow.py`：补充 parser 支持 `dry-run` 且默认仍为 `status`。
- `tests/test_cli_autonomous_flow_outputs.py`：补充 dry-run 调用链、参数透传、error tick 返回 0、禁止 service 调用、输出不泄露嵌套 payload 的单元覆盖。
- `tests/test_cli_autonomous_flow_smoke.py`：补充真实 artifact root 的 happy path 与 missing cycle dry-run smoke 覆盖。
- `tests/helpers_cli_autonomous_flow.py`：补充 fake dry-run result、tick 参数断言和输出泄露断言 helper。

关键合同检查：

- `status`：仍输出 tick envelope，并返回 tick exit code。
- `plan`：仍输出 follow-up plan，并返回 0。
- `dry-run`：调用 tick、plan、dry-run executor；不调用 service；输出 dry-run result；返回 0。
- `full`：仍输出 service result；不调用 tick 或 plan。
- dry-run 输出不包含完整 tick status/error、plan payload、input bundle、runner result、release manifest ref、digest 或 traceback。

## 4. 主进程验证

独立修正：

- 初始实现可用，但 `tests/test_cli_autonomous_flow_outputs.py` 为 303 行、`tests/test_cli_autonomous_flow_smoke.py` 为 313 行，违反单文件 <300 行约束。
- 将 rich tick 参数断言下沉到 `tests/helpers_cli_autonomous_flow.py`，避免 output tests 继续膨胀。
- 将两个 dry-run smoke 场景合并为参数化测试，保留 happy path 与 missing cycle 两个真实 artifact-root 覆盖。
- 校正 smoke 泄露断言边界：`plan` 输出允许 `plan_status` / `source_tick_status`，`dry-run` 输出禁止 nested scheduler payload。

指定门禁结果：

- `PYTHONPATH=src python3 -m pytest tests/test_cli_autonomous_flow.py tests/test_cli_autonomous_flow_outputs.py tests/test_cli_autonomous_flow_smoke.py tests/test_autonomous_flow_scheduler_executor.py -q`：通过，30 passed。
- `PYTHONPATH=src python3 -m pytest tests/test_cli_autonomous_flow.py tests/test_cli_autonomous_flow_outputs.py tests/test_cli_autonomous_flow_smoke.py tests/test_autonomous_flow_scheduler_executor.py tests/test_autonomous_flow_scheduler_plan.py tests/test_autonomous_flow_tick.py -q`：通过，51 passed。
- `ruff check src/ashare_evidence/cli_autonomous_flow.py tests/test_cli_autonomous_flow.py tests/test_cli_autonomous_flow_outputs.py tests/test_cli_autonomous_flow_smoke.py tests/helpers_cli_autonomous_flow.py`：通过。
- `wc -l tests/test_cli_autonomous_flow.py tests/test_cli_autonomous_flow_outputs.py tests/test_cli_autonomous_flow_smoke.py tests/helpers_cli_autonomous_flow.py`：182 / 284 / 298 / 205，全部低于 300 行。
- `PYTHONPATH=src python3 -m ashare_evidence.cli policy-audit --fail-on-new-unclassified --fail-on-direct-config-read --fail-on-formula-side-effects --fail-on-missing-config-lineage`：通过。
- `PYTHONPATH=src python3 -m ashare_evidence.cli contract-registry-check --registry docs/contracts/registry/autonomous_flow_registry.v1.json --docs docs/contracts/autonomous-flow-trial/TRIAL_X_CONTEXT_PACK_CN.md --docs docs/contracts/autonomous-flow-trial/TRIAL_X_EVALUATION_CN.md --fail-on-unregistered --fail-on-deprecated`：通过，issue_count=0。
- `git diff --check`：通过。
- `PYTHONPATH=src python3 -m pytest -q`：通过，341 passed，147 deselected。

## 5. 重跑记录

- 第一次 focused tests 失败：plan smoke 复用了 dry-run 的 nested scheduler payload 禁止断言，导致合法的 `plan_status` 被误判。
- 修正后按指定门禁完整重跑，全部通过。

## 6. 自评

自评分：92 / 100。

扣分点：

- 本轮为了保持测试文件低于 300 行，引入了若干测试 helper；覆盖仍清晰，但 smoke 文件已接近上限，后续若继续扩展 CLI output，应优先拆分新的测试文件。
- dry-run 当前只生成 execution intent，不落 durable event；这符合本轮非目标，但下一轮真实 scheduler 介入前需要重新定义持久化边界。
- `full` debug 输出按兼容性要求继续保留 service payload，不能作为默认自动化状态通道使用。
