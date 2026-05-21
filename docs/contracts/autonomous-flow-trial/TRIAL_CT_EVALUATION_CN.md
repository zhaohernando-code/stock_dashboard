# Trial CT 评估记录：平台宿主边界回滚与流程固化

状态：verified
输入：`TRIAL_CT_CONTEXT_PACK_CN.md`
目标：评估本轮是否已把自动化平台本体能力从 `stock_dashboard` 撤回，并把后续流程边界固化为可执行规则。

## 1. 子任务

| 子进程 | owned files | 目标 | 状态 |
| --- | --- | --- | --- |
| CT1 | revert commits、边界文档、验证记录 | 撤回平台能力误落点并固化宿主边界 | passed |

## 2. 评分

| 维度 | 权重 |
| --- | ---: |
| 产品面回滚完整性 | 35 |
| 宿主边界清晰度 | 30 |
| 流程门禁可执行性 | 20 |
| 验证完整性 | 15 |

自动重跑阈值：

- `stock_dashboard` 源码仍包含平台 workbench UI/API/CLI/runtime 标记。
- 文档仍建议在本仓库继续平台 workbench projection。
- 回归测试、前端构建、registry 或 process hardening 失败。

## 3. 结果

### 偏移结论

本轮偏移成立。原始目标是建设一个新的自动化中台/平台，并用当前会话作为流程试验田；实际执行时，平台 workbench projection、API 和前端状态面被继续实现进 `stock_dashboard`。这说明目标不是完全从文档层遗忘，而是在执行层被路由惯性和缺失的宿主门禁覆盖了。

### 原因

- 长任务上下文持续把工作目录锁在 `stock_dashboard`，每轮没有重新执行宿主判定。
- “试验田”没有被限定为流程验证和合同输出，导致试验输出进入业务项目 runtime。
- Context Pack 未要求声明 `platform_core / managed_project / integration_adapter`，子进程评审也没有把宿主越界列为硬失败。
- 主进程在多轮自动推进后只检查了实现质量，没有检查实现位置是否仍符合最初目标。

### 已执行纠偏

- 已用非破坏性 revert 撤回进入业务项目的 workbench projection/API/UI 相关提交：`2c2034b`、`816adeb`、`e0c28e6`、`186c3de`、`c4c6d18`。
- `PROJECT_RULES.md` 增加平台宿主边界规则。
- `PROCESS.md` 增加平台本体落点门禁、试验田边界、Context Pack 宿主声明和越界回滚原则。
- `DECISIONS.md` 记录本次边界事故的原因和长期决策。
- `PROJECT_PLAN.md` 与 `PROJECT_STATUS.json` 补充当前仓库只作为被纳管业务项目的状态。
- `TRIAL_CN_EVALUATION_CN.md` 已撤销“在本仓库继续 Trial CO workbench projection”的后续建议。

## 4. 主进程验证

- Boundary grep：`rg -n "WorkbenchProjection|workbench-projection|phase5_workbench|attempt-run-workbench-projection" src frontend tests`，无源码命中。
- Focused tests：`PYTHONPATH=src python3 -m pytest tests/test_scheduler_auto_progress_readout.py tests/test_cli_autonomous_flow_auto_progress_readout_output.py tests/test_scheduler_auto_progress_recorder.py tests/test_cli_autonomous_flow_auto_progress_run_record_output.py -q`，结果 `8 passed`。
- Focused ruff：`ruff check` 覆盖 auto-progress readout/recorder/CLI 与对应测试，结果 `All checks passed!`。
- Contract registry：首跑失败，原因是本文档和 context pack 使用了未注册的 registry-like 标记；已改为自然语言描述后待重跑。
- Process hardening：首跑失败，原因是评估文档缺少标准章节；已按模板补齐后待重跑。
- Contract registry 重跑：`status=pass`、`issue_count=0`。
- Process hardening 重跑：`status=pass`、`issue_count=0`，且 forbidden source tokens 无命中。
- Policy audit：`status=pass`。
- Frontend build：`npm --prefix frontend run build` 通过，保留既有 chunk size warning。
- Full regression：`PYTHONPATH=src python3 -m pytest -q`，结果 `626 passed, 147 deselected`。
- Full ruff baseline：`ruff check src tests` 仍因仓库既有 import/order/type-annotation 基线失败，本轮未改动这些文件，不能作为本次边界回滚的完成门禁。

## 5. 重跑记录

- 第 1 次 registry 重跑：去掉未注册的 registry-like 标记，避免把失败 token 写进正式合同。
- 第 1 次 process-hardening 重跑：补齐 `子任务 / 评分 / 结果 / 主进程验证 / 重跑记录 / 自评` 章节。

## 6. 自评

本轮已把平台 workbench 误落点从 `stock_dashboard` 产品面撤回，并把宿主边界写入规则、流程、决策、状态和 Trial 文档。后续平台工作应先创建或切换到独立平台宿主，再以本项目作为被纳管样本验证流程。
