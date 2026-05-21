# Trial BN 评估记录：Process Hardening Warning Margin Gate

状态：verified
输入：`TRIAL_BN_CONTEXT_PACK_CN.md`
目标：评估 process hardening 是否能表达“距离 warning 线余量不足时必须拆分”的流程门禁。

## 1. 子任务

| 子进程 | owned files | 目标 | 状态 |
| --- | --- | --- | --- |
| BN1 | warning margin 模块、CLI 组合、测试、本评估文件 | 新增 line budget warning margin 门禁 | passed |

## 2. 评分

| 维度 | 权重 |
| --- | ---: |
| 门禁语义清晰 | 30 |
| 核心模块不膨胀 | 25 |
| CLI 可组合性 | 25 |
| 文件规模与验证 | 20 |

自动重跑阈值：

- 修改 `process_hardening.py`。
- margin 指向未知 line budget 或无 warning limit 时不 fail closed。
- `--fail-on-warning` 不能让 margin warning 失败。
- focused tests、ruff、process hardening、registry 或 full regression 失败。

## 3. BN1 结果

BN1 新增独立 warning margin 模块，提供 path:minimum_remaining 解析和基于既有 line budget 结果的检查。CLI process-hardening-check 新增可重复参数 --line-budget-warning-margin，并将 margin issues 与现有 evaluation、required evidence、forbidden source token issues 合并后统一计算 status。

实现语义：

- margin 指向未声明 line budget 时返回 error issue。
- margin 目标没有 warning_limit 时返回 error issue。
- warning_limit - line_count 小于 minimum_remaining 时返回 warning issue。
- --fail-on-warning 沿用既有合并后的 warning 失败语义。
- src/ashare_evidence/process_hardening.py 未修改。

## 4. 主进程验证

BN1 本地验证通过；主进程并入集成分支后复跑 focused gates：

- Focused tests：BN1 `23 passed in 0.79s`；main `23 passed in 0.71s`。
- Ruff：passed。
- Process hardening：status=pass，issue_count=1；唯一 issue 为既有 `process_hardening.py` 233 行达到 warning 230，本轮未修改该文件。
- Self-check margin gate：按预期失败，`line_budget_warning_margin_low`，BM 测试文件 remaining 2 小于 minimum 5。
- Registry：status=pass，issue_count=0。
- Full regression：main `522 passed, 147 deselected in 23.01s`。

主进程语义复核：

- `process_hardening.py` 未修改，margin 逻辑位于独立模块。
- 未知 line budget 与无 warning limit 均 fail closed 为 error；低余量为 warning，并可由 `--fail-on-warning` 统一升级为失败。
- 路径匹配要求 `--line-budget` 与 `--line-budget-warning-margin` 使用一致路径写法，该限制应在后续上下文包中显式给出。

## 5. 重跑记录

BN1 首轮实现后执行 focused tests、ruff、process hardening、self-check margin gate、registry 和 full regression；主进程复跑 focused gates 与 self-check。

- focused tests: 23 passed。
- ruff: All checks passed。
- process hardening: pass，issue_count 1，既有 process_hardening.py warning。
- self-check margin gate: 预期失败，line_count 178，warning_limit 180，remaining 2，minimum_remaining 5。
- registry: pass，issue_count 0。
- full regression: 522 passed，147 deselected。

## 6. 自评

门禁语义清晰，新增逻辑保持在独立模块；CLI 只负责解析、组合和沿用统一 status 判定。主要风险是 path 匹配沿用 line budget 结果中的字符串表示，调用方需要对 --line-budget 与 --line-budget-warning-margin 使用一致路径写法。
