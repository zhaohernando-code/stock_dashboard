# Trial S 评估记录：Phase 5 CLI Tick Smoke Tests

状态：进行中  
输入：`TRIAL_S_CONTEXT_PACK_CN.md`  
目标：评估默认 CLI tick envelope 是否在真实 artifact root 下通过集成烟测，而不是只靠 monkeypatch 单元测试。

## 1. 子任务

| 子进程 | owned files | 目标 |
| --- | --- | --- |
| S1 | `test_cli_autonomous_flow_smoke.py`、本评估文件 | 增加 CLI tick 集成烟测 |

## 2. 评分

| 维度 | 权重 |
| --- | ---: |
| 集成烟测有效性 | 40 |
| 输出泄露保护 | 25 |
| 副作用隔离 | 20 |
| 测试维护性 | 15 |

自动重跑阈值：

- 总分低于 85。
- 测试只 monkeypatch，没有真实 artifact root。
- 默认 CLI 输出不是 tick envelope。
- 缺失 cycle 没有映射为 degraded artifact-missing。
- 测试触发 DB 初始化。
- focused tests 失败。

## 3. S1 结果

完成。

改动文件：

- `tests/test_cli_autonomous_flow_smoke.py`
- `docs/contracts/autonomous-flow-trial/TRIAL_S_EVALUATION_CN.md`

实现内容：

- 新增真实 `tmp_path / artifacts` artifact root 烟测，不依赖 monkeypatch tick/service。
- happy path 写入 cycle ledger、gate readout、frontend projection manifest fixture，然后通过 `cli.main(["phase5-local-cycle-step", ...])` 调默认 CLI。
- missing cycle path 不写 cycle ledger，同样通过 `cli.main(...)` 调默认 CLI。
- 两条路径都 monkeypatch `ashare_evidence.cli.init_database` 为失败函数，并断言没有调用记录，证明默认 tick CLI 不触发 DB 初始化。
- happy path 验证默认输出是 tick envelope：`tick_status=ok`、`exit_code=0`、`status.summary_status=completed`、`publish_verification_status=present`。
- missing cycle path 验证默认输出是 tick error envelope：`tick_status=error`、`exit_code=1`、`error.failure_class=artifact-missing`、`summary_status=degraded`。
- 两条路径都序列化检查不泄露 `input_bundle`、`runner_result`、`release-manifest:`、`sha256:`。
- 未修改 CLI / tick / resolver / service / runner / planner / status projection 生产代码。

子进程验证：

- `PYTHONPATH=src python3 -m pytest tests/test_cli_autonomous_flow.py tests/test_cli_autonomous_flow_smoke.py tests/test_autonomous_flow_tick.py -q`：18 passed
- `ruff check tests/test_cli_autonomous_flow_smoke.py`：passed
- `PYTHONPATH=src python3 -m ashare_evidence.cli contract-registry-check --registry docs/contracts/registry/autonomous_flow_registry.v1.json --docs docs/contracts/autonomous-flow-trial/TRIAL_S_CONTEXT_PACK_CN.md --docs docs/contracts/autonomous-flow-trial/TRIAL_S_EVALUATION_CN.md --fail-on-unregistered --fail-on-deprecated`：passed，`issue_count=0`
- `git diff --check`：passed

## 4. 主进程验证

主进程复核结论：通过。

已验证：

- 新测试通过真实 `tmp_path / artifacts` 写入 cycle ledger、gate readout、frontend projection manifest，再调用 `cli.main(...)` 默认路径。
- happy path 输出为 tick envelope，`tick_status=ok`、`exit_code=0`、`status.summary_status=completed`、`publish_verification_status=present`。
- missing cycle path 输出为 tick error envelope，`tick_status=error`、`exit_code=1`、`error.failure_class=artifact-missing`、`summary_status=degraded`。
- 两条路径都 monkeypatch `init_database` 为失败函数并断言未调用，证明 artifact-only CLI 不触发 DB 初始化。
- 两条路径均检查 JSON 字符串不包含 `input_bundle`、`runner_result`、`release-manifest:`、`sha256:`。
- 本轮未修改任何生产代码。

跑偏检查：

- 测试没有 monkeypatch tick/service/projection，确实覆盖真实 CLI 默认入口到 artifact store/resolver/service/tick/status projection 的链路。
- 没有接入 scheduler、LaunchAgent、cron 或 heartbeat。
- 没有写 repo artifact；所有 artifact fixture 都在临时目录。
- helper 自包含，避免跨测试文件 import 私有 helper；少量重复可接受。

主进程门禁：

| 命令 | 结果 |
| --- | --- |
| `PYTHONPATH=src python3 -m pytest tests/test_cli_autonomous_flow.py tests/test_cli_autonomous_flow_smoke.py tests/test_autonomous_flow_tick.py -q` | 18 passed |
| `ruff check tests/test_cli_autonomous_flow_smoke.py` | pass |
| `PYTHONPATH=src python3 -m ashare_evidence.cli contract-registry-check --registry docs/contracts/registry/autonomous_flow_registry.v1.json --docs docs/contracts/autonomous-flow-trial/TRIAL_S_CONTEXT_PACK_CN.md --docs docs/contracts/autonomous-flow-trial/TRIAL_S_EVALUATION_CN.md --fail-on-unregistered --fail-on-deprecated` | status=pass, issue_count=0 |
| `PYTHONPATH=src python3 -m pytest tests/test_cli_autonomous_flow.py tests/test_cli_autonomous_flow_smoke.py tests/test_autonomous_flow_service.py tests/test_autonomous_flow_resolver.py tests/test_autonomous_flow_runner.py tests/test_autonomous_flow_planner.py tests/test_autonomous_flow_status.py tests/test_autonomous_flow_tick.py -q` | 59 passed |
| `PYTHONPATH=src python3 -m ashare_evidence.cli policy-audit --fail-on-new-unclassified --fail-on-direct-config-read --fail-on-formula-side-effects --fail-on-missing-config-lineage` | pass |
| `git diff --check` | pass |
| `PYTHONPATH=src python3 -m pytest -q` | 308 passed, 147 deselected |

运行时发布验证：本轮只新增测试，不改变用户可见 Web/runtime 行为，因此不触发发布或浏览器验收。

## 5. 重跑记录

无需重跑子进程。

原因：

- S1 输出满足 Context Pack 的 owned files 与非目标边界。
- 未发现测试退化为 monkeypatch-only、DB 初始化误触发、输出泄露或生产代码越界。

## 6. 自评

评分：94 / 100。

- 集成烟测有效性：39 / 40。测试走真实 artifact root 与真实 CLI 默认路径，覆盖成功和缺失 cycle；未覆盖 explicit gate/projection id，因为本轮目标聚焦默认 envelope。
- 输出泄露保护：25 / 25。对完整 JSON 字符串做敏感字段和 ref/digest 级别断言。
- 副作用隔离：20 / 20。使用 tmp artifact root，不读 DB、不写 repo artifact、不触发 DB 初始化。
- 测试维护性：10 / 15。fixture helper 在新文件内自包含，清晰但与 resolver/status 测试存在轻微重复；这是为了遵守不跨测试文件 import 私有 helper 的约束。

剩余风险：

- 当前 smoke test 验证 CLI 输出合同与真实 artifact 读取链路，不验证 scheduler/LaunchAgent。
- 输出泄露断言是字符串级黑名单；如果后续新增敏感字段类型，需要同步扩展 denylist 或沉淀为共用测试 helper。
