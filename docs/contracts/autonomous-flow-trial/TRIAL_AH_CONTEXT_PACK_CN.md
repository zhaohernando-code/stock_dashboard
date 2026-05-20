# Trial AH Context Pack：Process Hardening Audit CLI

状态：active input  
上游：Trial AG  
目标：把 Trial AG 固化的流程规则升级为第一版机器门禁，先支持显式文件输入，不做全仓历史扫描。

## 1. 背景

Trial AG 已把文件规模治理、子进程输出验收、基座硬状态、legacy migration 和评估文档记录要求写入流程合同。当前残余风险是这些规则仍主要靠主进程人工执行。本轮只做最小可执行门禁。

## 2. 本轮目标

新增一个 CLI governance command，建议命名为 `process-hardening-check`。

必须支持：

- 显式传入 evaluation doc，检查评估文档是否包含核心章节。
- 检查评估文档是否仍含待补录、待执行、等待主进程接收等未完成状态。
- 显式传入文件行数预算，检查关注文件是否超过 warning 或 hard limit。
- 输出结构化 JSON，包含 status、issue_count、issues、checked docs、line budgets。
- 支持 `--fail-on-warning`，让接近上限也可作为失败。
- 不初始化数据库，不读网络，不写文件。

## 3. 非目标

- 不扫描所有历史 Trial。
- 不接 GitHub Actions。
- 不自动判断 legacy migration 测试是否存在。
- 不修改业务代码。
- 不修改 registry。

## 4. Owned Files

默认允许修改：

- `src/ashare_evidence/cli_governance.py`
- `src/ashare_evidence/process_hardening.py`
- `tests/test_process_hardening.py`
- `docs/contracts/autonomous-flow-trial/TRIAL_AH_EVALUATION_CN.md`

如命令接线确实需要，可修改 `src/ashare_evidence/cli.py` 的 import / dispatch。

## 5. 合同要求

Evaluation doc 必需章节：

- 子任务
- 评分
- 结果
- 主进程验证
- 重跑记录
- 自评

未完成状态检测至少覆盖：

- 待执行
- 待补录
- 等待主进程
- TODO

Line budget 输入建议：

- `--line-budget path:hard_limit`
- `--line-budget path:hard_limit:warning_limit`

判定：

- line count 大于 hard limit -> failure。
- line count 大于等于 warning limit -> warning；如果 `--fail-on-warning` 打开则 failure。
- missing file -> failure。

## 6. Tests

至少覆盖：

- 完整 evaluation doc 通过。
- 缺章节失败。
- 未完成状态失败。
- line count 超 hard limit 失败。
- line count 达 warning limit 在默认模式 warning 但 status pass。
- `--fail-on-warning` 时 warning 变 failure。
- CLI command 不初始化数据库。

## 7. 验收

- `PYTHONPATH=src python3 -m pytest tests/test_process_hardening.py -q`
- `ruff check src/ashare_evidence/cli_governance.py src/ashare_evidence/process_hardening.py tests/test_process_hardening.py`
- `PYTHONPATH=src python3 -m ashare_evidence.cli process-hardening-check --evaluation-doc docs/contracts/autonomous-flow-trial/TRIAL_AG_EVALUATION_CN.md --line-budget docs/contracts/AUTONOMOUS_DEVELOPMENT_FLOW_CN.md:320:260 --line-budget docs/contracts/AUTONOMOUS_FLOW_TRIAL_2026-05-20_CN.md:240:200 --line-budget docs/contracts/autonomous-flow-trial/TRIAL_AG_EVALUATION_CN.md:140:110`
- `PYTHONPATH=src python3 -m ashare_evidence.cli contract-registry-check --registry docs/contracts/registry/autonomous_flow_registry.v1.json --docs docs/contracts/autonomous-flow-trial/TRIAL_AH_CONTEXT_PACK_CN.md --docs docs/contracts/autonomous-flow-trial/TRIAL_AH_EVALUATION_CN.md --fail-on-unregistered --fail-on-deprecated`
- `git diff --check`
- `PYTHONPATH=src python3 -m pytest -q`
