# Trial AQ 评估记录：Scheduler Action Preflight

状态：completed, main verification passed
输入：`TRIAL_AQ_CONTEXT_PACK_CN.md`
目标：评估 scheduler action preflight 是否能在真实 action 执行前校验输入和副作用边界。

## 1. 子任务

| 子进程 | owned files | 目标 |
| --- | --- | --- |
| AQ1 | action contract preflight、测试、本评估文件 | 增加纯 preflight 校验 |

## 2. 评分

| 维度 | 权重 |
| --- | ---: |
| required inputs 校验 | 30 |
| side effect 授权校验 | 30 |
| contract 字段继承 | 20 |
| 文件规模与门禁 | 20 |

自动重跑阈值：

- missing required inputs 不会 block。
- unauthorized side effect 不会 block。
- preflight 执行 IO、DB、网络、artifact 写入或当前时间读取。
- 修改 CLI、ledger/reservation、artifact 写入原语或真实 action。
- focused tests、ruff、process hardening、registry 或 full regression 失败。

## 3. AQ1 结果

结论：通过。AQ1 已在 action contract 模块增加纯 `preflight_phase5_scheduler_action(...)` 和冻结的 typed result。

覆盖结果：

- required inputs：缺少 `failure_class` 时返回 `blocked`，并列入 `missing_inputs`。
- side effects：请求 contract 未授权的 `write_recovery_ticket` 时返回 `blocked`，并列入 `unauthorized_side_effects`。
- `allowed_side_effects=("none",)`：允许空请求或显式 `none`，拒绝任何真实写入意图。
- contract 字段继承：preflight result 继承 `durable_outputs` 和 `may_close_cycle`，`block_cycle` 保留 `phase5_cycle_ledger` 与 `may_close_cycle=True`。
- 纯函数边界：实现只读取静态 contract 并复制调用方传入集合；不执行真实 scheduler action，不写 recovery ticket、projection、cycle closeout 或 scheduler execution ledger，不读 IO/DB/network/time。

AQ1 本地验证：

- `PYTHONPATH=src python3 -m pytest tests/test_autonomous_flow_scheduler_action_contract.py -q`：13 passed。
- `ruff check src/ashare_evidence/autonomous_flow_scheduler_action_contract.py tests/test_autonomous_flow_scheduler_action_contract.py`：passed。
- `PYTHONPATH=src python3 -m ashare_evidence.cli process-hardening-check ...`：passed，0 issues；contract 176/220 行，测试 188/240 行。
- `PYTHONPATH=src python3 -m ashare_evidence.cli contract-registry-check ...`：passed，0 issues。
- `git diff --check`：passed。
- `PYTHONPATH=src python3 -m pytest -q`：427 passed, 147 deselected。

## 4. 主进程验证

主进程语义审查：

- preflight 只读取静态 action contract 和调用方传入的集合，不触达 CLI、ledger/reservation、artifact store、cycle closeout 或真实 action。
- ready / blocked、missing inputs、unauthorized side effects、durable outputs、may close cycle 均来自同一 contract 源。
- 主进程补充 combined blockers 覆盖：同时缺 required inputs 且请求未授权副作用时，reason 明确表达双重阻塞。
- 主进程补测后发现原 action contract 测试文件达到 warning line budget；已在本轮拆出 `tests/test_autonomous_flow_scheduler_action_preflight.py`，避免把规模风险留到后续。

主进程门禁：

- focused pytest：14 passed。
- ruff：passed。
- process hardening：passed，所有文件低于 warning line budget。
- contract registry：passed。
- diff check：passed。
- full regression：428 passed，147 deselected。

## 5. 重跑记录

无需重跑子进程。主进程补充 combined blockers 测试后触发测试文件 warning，已在主进程内拆分 preflight 测试文件并重跑门禁。

## 6. 自评

本轮把静态 action contract 推进到可调用 preflight 层，但仍保持无副作用。下一轮真实 action 接入时，应先从一个低风险 action 开始，并强制调用 preflight 后再写 execution ledger 或 durable output。
