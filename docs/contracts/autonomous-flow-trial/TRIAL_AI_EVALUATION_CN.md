# Trial AI 评估记录：Legacy Migration Evidence Check

状态：completed  
输入：TRIAL_AI_CONTEXT_PACK_CN.md  
目标：评估流程硬化 CLI 是否能显式检查 legacy migration 测试证据存在。

## 1. 子任务

| 子进程 | owned files | 目标 |
| --- | --- | --- |
| AI1 | process hardening evidence check、tests、本评估文件 | 增加 required evidence 检查 |

## 2. 评分

| 维度 | 权重 |
| --- | ---: |
| Required evidence 检查语义 | 35 |
| CLI 无副作用与 JSON 输出 | 20 |
| 文件规模治理 | 20 |
| 测试与门禁 | 25 |

自动重跑阈值：

- 文件缺失或 token 缺失仍返回 pass。
- CLI 输出缺少 required evidence 检查结果。
- `process_hardening.py` 被推过 warning 线且未拆分。
- CLI 初始化数据库或写文件。
- focused tests、ruff、registry 或 full regression 失败。

## 3. AI1 结果

已完成 required evidence 门禁：

- 新增独立 evidence helper，解析 path:token 并检查文件存在与 token 命中。
- process-hardening-check 新增 required evidence 参数，并在 JSON payload 中输出 required evidence 检查明细。
- 文件缺失和 token 缺失均产生 error issue，并使命令失败。
- CLI 接线只修改治理命令模块，未修改主 CLI 文件。
- process hardening 主模块保持 191 行，未继续膨胀。

## 4. 主进程验证

AI1 worker 已完成本轮自验：

- focused tests：11 passed。
- ruff：passed。
- Context Pack CLI 验收：passed，required evidence 命中 legacy ledger conflict 测试证据。
- registry check：passed，0 issues。
- git diff check：passed。
- full regression：393 passed，147 deselected。

主进程复验：

- focused tests：11 passed。
- ruff：passed。
- process hardening check：本评估文档、AI 相关代码文件预算和 legacy evidence 均通过，0 issues。
- process hardening check：AH 评估文档结合 legacy evidence 通过，0 issues。
- registry check：通过，2 docs，0 issues。
- full regression：393 passed，147 deselected。
- 文件规模：process_hardening.py 191 行，process_hardening_evidence.py 60 行，cli_governance.py 147 行，evidence tests 102 行；主模块未跨过 warning 线。

## 5. 重跑记录

本轮未触发重跑。实现一次通过 focused tests、ruff 和 CLI 验收。

## 6. 自评

本轮符合 Context Pack 约束：没有修改业务代码，没有修改 registry，没有修改主 CLI 文件，也没有让 process hardening 主模块越过规模预警线。残余风险是 required evidence 仍是显式 token 证明，不验证测试语义；这与本轮非目标一致，后续可在 CI 中配置更多 evidence 条目。
