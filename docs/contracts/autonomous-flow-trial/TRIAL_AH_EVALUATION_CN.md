# Trial AH 评估记录：Process Hardening Audit CLI

状态：completed  
输入：`TRIAL_AH_CONTEXT_PACK_CN.md`  
目标：评估第一版流程硬化机器门禁是否能覆盖评估文档完整性和文件规模预算。

## 1. 子任务

| 子进程 | owned files | 目标 |
| --- | --- | --- |
| AH1 | governance CLI、process audit module、tests、本评估文件 | 实现显式输入的流程硬化审计命令 |

## 2. 评分

| 维度 | 权重 |
| --- | ---: |
| 评估文档完整性检查 | 30 |
| 文件规模预算检查 | 30 |
| CLI 无副作用与 JSON 输出 | 20 |
| 测试与门禁 | 20 |

自动重跑阈值：

- CLI 初始化数据库或写文件。
- 未完成评估文档仍返回 pass。
- 超 hard line limit 未失败。
- warning 不能通过 `--fail-on-warning` 升级为失败。
- focused tests、ruff、registry 或 full regression 失败。

## 3. AH1 结果

AH1 已实现第一版 `process-hardening-check`：

- 新增无副作用检查模块，显式读取 evaluation doc 与 line budget 参数。
- CLI 输出结构化 JSON，包含 status、issue_count、issues、checked_docs 和 line_budgets。
- Evaluation doc 检查覆盖核心章节和未完成状态标记。
- Line budget 检查覆盖 missing file、hard limit、warning limit，以及 `--fail-on-warning`。
- CLI 接线位于 governance command 分支，业务数据库初始化逻辑前直接返回。

## 4. 主进程验证

已完成本轮主进程验证：

- Focused tests：`7 passed`。
- Ruff：通过。
- Context Pack 指定 CLI 验收：通过，输出 status 为 pass，issue_count 为 1。
- 该唯一 issue 是 `AUTONOMOUS_DEVELOPMENT_FLOW_CN.md` 达到 warning line budget，未超过 hard limit。
- 文件规模：cli 1243 行，cli_governance 114 行，process_hardening 191 行，test_process_hardening 154 行，本评估 70 行。
- Registry check：通过，0 issues。
- `git diff --check`：通过。
- Full regression：389 passed，147 deselected。
- 主进程额外自检：使用新命令检查本评估文档和本轮新增/修改代码文件，status 为 pass；`cli.py` 达到 warning line budget，但低于 hard limit。

## 5. 重跑记录

本轮发生两次自动修正：

- 子进程阶段 ruff 报 `process_hardening.py` import 排序问题，已用 ruff fix 修复后重跑通过。
- 主进程提交阶段 pre-commit 阻止 `cli.py` 继续增长。主进程将 governance 命令分发收敛到 `cli_governance.py`，避免继续给既有大文件加行数后重跑 focused 门禁通过。

## 6. 自评

评分：92 / 100。

扣分项：

- Line budget 输入目前只支持 path:hard 和 path:hard:warning 的字符串格式，后续接入 CI 时可以补充配置文件输入。
- 未完成状态检测是显式关键词匹配，适合作为第一版门禁；复杂语义判断仍应留给后续 reviewer 或 LLM 审计层。
- `cli.py` 已低于当前 pre-commit manifest 基线，但仍处于 warning 区间，后续 CLI 扩展应继续向子模块分发，避免主入口增长。

残余风险：

- 本轮不做全仓历史扫描，不能发现未显式传入的评估文档。
- 本轮不自动判断 legacy migration 测试是否存在，该项仍需后续独立 hardening trial。
