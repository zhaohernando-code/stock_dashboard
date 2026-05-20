# Trial O 评估记录：Phase 5 CLI Status Output

状态：进行中  
输入：`TRIAL_O_CONTEXT_PACK_CN.md`  
目标：评估 CLI 默认输出是否已经收敛为稳定 status projection 小 payload，并保留显式 full debug 模式。

## 1. 子任务

| 子进程 | owned files | 目标 |
| --- | --- | --- |
| O1 | `cli_autonomous_flow.py`、`test_cli_autonomous_flow.py`、本评估文件 | 将 CLI 成功默认输出切到 status projection，保留 `--output full` |

## 2. 评分

| 维度 | 权重 |
| --- | ---: |
| CLI 输出合同符合度 | 35 |
| 调试兼容与副作用隔离 | 25 |
| 测试覆盖 | 25 |
| 可运维错误输出 | 15 |

自动重跑阈值：

- 总分低于 85。
- 默认输出仍包含完整 `input_bundle`、`runner_result`、artifact payload、release manifest ref 或 digest。
- `--output full` 丢失 Trial M 的调试能力。
- CLI 触发 DB 初始化。
- handler 直接读写 artifact store、读 DB、读网络、调用 LLM 或读取当前时间。
- focused tests 失败。

## 3. O1 结果

已完成。

代码变更：

- `src/ashare_evidence/cli_autonomous_flow.py`
  - 为 `phase5-local-cycle-step` 增加 `--output status|full`。
  - 默认 `--output status`，成功输出改为 `project_phase5_local_cycle_status(result).model_dump(mode="json")`。
  - `--output full` 保留 Trial M 的完整 service result JSON，用于本地调试。
  - 错误路径保持结构化 JSON 与非零退出码。
- `tests/test_cli_autonomous_flow.py`
  - 覆盖 parser 默认 `output == "status"`。
  - 覆盖默认成功输出为 status projection 小 payload，且不包含 `input_bundle`、`runner_result`、release manifest ref 或 digest。
  - 覆盖 `--output full` 保留完整 service result。
  - 覆盖 service 调用参数不受 output mode 影响。
  - 保留错误路径与 `cli.main(["phase5-local-cycle-step", ...])` 不触发 DB 初始化的保护。

本轮未修改 service / resolver / runner / planner / status projection / artifact model / registry / API / frontend。

## 4. 主进程验证

主进程复核结论：通过。

已验证：

- `phase5-local-cycle-step` parser 默认 `output == "status"`。
- 成功默认输出路径调用 `project_phase5_local_cycle_status(result).model_dump(mode="json")`，不再直接输出完整 service result。
- `--output full` 保留 Trial M 的完整 service result JSON 调试能力，且不会调用 status projection。
- handler 仍只调用 local cycle service 与纯 status projection；没有直接读写 artifact store、读 DB、读网络、调用 LLM 或读取当前时间。
- 错误路径保持非零退出码与结构化 JSON。
- `cli.main(["phase5-local-cycle-step", ...])` 仍在 DB 初始化之前 dispatch。

跑偏检查：

- 本轮只修改 CLI 输出边界和对应测试；未修改 service / resolver / runner / planner / status projection / artifact model / registry / API / frontend。
- 默认输出黑名单覆盖 `input_bundle`、`runner_result`、`release_manifest_ref`、`digest`。
- 子进程采用 monkeypatch 验证 CLI 输出模式选择，真实 projection 字段完整性继续由 `tests/test_autonomous_flow_status.py` 覆盖；这个职责拆分合理，未把 CLI 测试膨胀成 service/projection 集成测试。

主进程门禁：

| 命令 | 结果 |
| --- | --- |
| `PYTHONPATH=src python3 -m pytest tests/test_cli_autonomous_flow.py tests/test_autonomous_flow_status.py -q` | 16 passed |
| `ruff check src/ashare_evidence/cli_autonomous_flow.py tests/test_cli_autonomous_flow.py` | pass |
| `PYTHONPATH=src python3 -m ashare_evidence.cli contract-registry-check --registry docs/contracts/registry/autonomous_flow_registry.v1.json --docs docs/contracts/autonomous-flow-trial/TRIAL_O_CONTEXT_PACK_CN.md --docs docs/contracts/autonomous-flow-trial/TRIAL_O_EVALUATION_CN.md --fail-on-unregistered --fail-on-deprecated` | status=pass, issue_count=0 |
| `PYTHONPATH=src python3 -m pytest tests/test_cli_autonomous_flow.py tests/test_autonomous_flow_service.py tests/test_autonomous_flow_resolver.py tests/test_autonomous_flow_runner.py tests/test_autonomous_flow_planner.py tests/test_autonomous_flow_status.py -q` | 48 passed |
| `PYTHONPATH=src python3 -m ashare_evidence.cli policy-audit --fail-on-new-unclassified --fail-on-direct-config-read --fail-on-formula-side-effects --fail-on-missing-config-lineage` | pass |
| `git diff --check` | pass |
| `PYTHONPATH=src python3 -m pytest -q` | 297 passed, 147 deselected |

运行时发布验证：本轮只改变本地 CLI 输出形态，不改变用户可见 Web/runtime 行为，因此不触发发布或浏览器验收。

## 5. 重跑记录

无需重跑子进程。

原因：

- O1 输出满足 Context Pack 的 owned files 与非目标边界。
- 未发现默认输出泄露内部嵌套结构、调试模式丢失、DB 初始化误触发或副作用越界。
- 后续真实 scheduler / LaunchAgent / API / SPA 接入继续留在后续轮次。

## 6. 自评

O1 自评：92 / 100。

- CLI 输出合同符合度：默认成功输出已收敛为 Trial N status projection 小 payload，显式 `--output full` 才暴露完整 service result。
- 调试兼容与副作用隔离：handler 仍只调用 service 与纯 projection，不新增 artifact store、DB、网络、LLM 或当前时间读取。
- 测试覆盖：focused CLI/status 测试覆盖默认、小 payload 黑名单、full debug、错误路径、DB 初始化隔离。
- 剩余风险：当前 CLI 测试通过 monkeypatch 隔离 projection，验证的是 CLI 选择输出视图的合同；真实 projection 字段完整性由 `tests/test_autonomous_flow_status.py` 承担。
