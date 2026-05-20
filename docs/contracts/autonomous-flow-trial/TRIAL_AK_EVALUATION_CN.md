# Trial AK 评估记录：Autonomous Flow CLI Handler Split

状态：已完成  
输入：`TRIAL_AK_CONTEXT_PACK_CN.md`  
目标：评估 autonomous flow CLI output handler 拆分是否降低主 CLI 文件规模且保持行为兼容。

## 1. 子任务

| 子进程 | owned files | 目标 |
| --- | --- | --- |
| AK1 | CLI handler split、CLI tests、本评估文件 | 拆分 phase5-local-cycle-step output handler |

## 2. 评分

| 维度 | 权重 |
| --- | ---: |
| 行为兼容性 | 35 |
| 文件规模治理 | 30 |
| CLI 无副作用边界 | 20 |
| 测试与门禁 | 15 |

自动重跑阈值：

- 任一现有 CLI output 行为改变。
- `phase5-local-cycle-step` 触发数据库初始化。
- 主 CLI 文件未降到 140 行以下。
- 新 handler 文件超过 hard limit。
- focused tests、ruff、process hardening、registry 或 full regression 失败。

## 3. AK1 结果

AK1 已完成结构拆分，未提交、未合并、未推送。

修改文件：

- `src/ashare_evidence/cli_autonomous_flow.py`
- `src/ashare_evidence/cli_autonomous_flow_outputs.py`
- `docs/contracts/autonomous-flow-trial/TRIAL_AK_EVALUATION_CN.md`

实现说明：

- 主 CLI 模块保留 parser 注册和 dispatch glue。
- 新 output handler 模块承接 status、plan、dry-run、diagnostic、execution、full 分支。
- 为保持现有测试兼容，主 CLI 模块继续暴露原有依赖名，并在 dispatch 时把当前 callable 注入 handler。
- 未新增 CLI output、artifact、registry 或测试场景。

文件规模：

- `src/ashare_evidence/cli_autonomous_flow.py`：62 行，低于 140 行硬要求。
- `src/ashare_evidence/cli_autonomous_flow_outputs.py`：168 行，低于 180 行硬要求。
- `tests/test_cli_autonomous_flow_outputs.py`：284 行，未追加场景。

## 4. 主进程验证

语义 diff 结论：

- `phase5-local-cycle-step` 的 output choice、参数校验、exit code 和 JSON shape 保持兼容。
- diagnostic 和 execution 的必填参数仍在 tick 前校验。
- status、plan、dry-run、diagnostic、execution 分支仍只走 tick 和 scheduler plan 链路；full 分支仍走 service。
- `phase5-local-cycle-step` 仍在主 CLI 数据库初始化前 dispatch，由 smoke 测试覆盖。

门禁记录：

- focused CLI pytest：33 passed。
- ruff：passed。
- `git diff --check`：passed。
- full regression：405 passed，147 deselected。
- process hardening：passed，1 个 warning，来源为既有 `tests/test_cli_autonomous_flow_outputs.py` 284 行达到 warning 线 280。
- contract registry：passed，0 issues。

主进程复验：

- focused CLI pytest：33 passed。
- ruff：passed。
- process hardening：passed，1 个 warning，来源仍为既有 output 测试文件。
- contract registry：passed，2 docs，0 issues。
- `git diff --check`：passed。
- full regression：405 passed，147 deselected。

## 5. 重跑记录

- 第一次拆分后 focused CLI pytest 通过，但新 handler 179 行，距离 180 行硬线只有 1 行余量。
- 主进程主动压缩内部签名和 import，handler 降到 168 行后重跑 focused CLI pytest 与 ruff。

## 6. 自评

本轮满足 Context Pack：只做结构拆分，没有新增行为。设计上用依赖注入保留测试与调用兼容面，避免新模块直接绑定不可替换的底层实现。

残余风险：

- 新 handler 仍是单一 output 分发模块；后续真实 scheduler action 接入前，应继续避免把 action 执行语义堆进该文件。
- `tests/test_cli_autonomous_flow_outputs.py` 已达到 warning 线，后续 output 相关测试应拆新文件或复用 helper。
