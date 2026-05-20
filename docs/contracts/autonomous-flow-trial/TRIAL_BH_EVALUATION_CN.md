# Trial BH 评估记录：Process Hardening Forbidden Source Token

状态：verified
输入：`TRIAL_BH_CONTEXT_PACK_CN.md`
目标：评估 `process-hardening-check` 是否能用显式 forbidden source token 把 BG 类 reason 文案改道风险升级为机器门禁。

## 1. 子任务

| 子进程 | owned files | 目标 | 状态 |
| --- | --- | --- | --- |
| BH1 | process hardening source token helper、CLI 接线、测试、本评估文件 | 新增 forbidden source token 门禁 | rejected |
| BH2 | process hardening source token helper、CLI 接线、测试、本评估文件 | 不修改主 hardening 模块的重跑实现 | passed |

## 2. 评分

| 维度 | 权重 |
| --- | ---: |
| forbidden token 检查语义 | 35 |
| CLI 兼容与 JSON 输出 | 25 |
| 模块拆分与文件规模 | 25 |
| 验证完整性 | 15 |

自动重跑阈值：

- 未传 forbidden token 时破坏既有 process-hardening 行为。
- token 解析不能处理 token 内含冒号。
- 命中 forbidden token 时不返回 error issue 或缺少 line。
- 把扫描逻辑继续堆进 `process_hardening.py` 导致接近/跨过 warning。
- 修改业务代码。
- focused tests、ruff、process hardening、forbidden-token smoke、registry 或 full regression 失败。

## 3. BH1 结果

BH1 功能上跑通，但主进程审查后不合入：

- 优点：forbidden token 解析、重复 CLI 参数、命中行号、缺失文件和默认兼容语义都正确。
- 问题：BH1 修改了 `src/ashare_evidence/process_hardening.py`，把该主模块从 233 行推到 239 行，距离 warning 240 只差 1 行。这虽然未触线，但违背“流程工具主模块不能继续贴近 warning 线”的设计目标。
- 结论：重跑 BH2。source token 检查应像 required evidence 一样在 CLI governance 组合层合并到 payload，扫描逻辑留在独立 helper；`process_hardening.py` 不得修改。

## 4. 主进程验证

BH1 子进程自报验证通过，但因设计评价未达标，不作为可合入结果。

BH2 子进程实现结果：

- 新增 `src/ashare_evidence/process_hardening_source.py`，负责 `path:token` 解析和显式 source token 扫描；解析只按第一个冒号切分，token 可包含冒号。
- `process-hardening-check` 新增可重复参数 `--forbidden-source-token path:token`。
- `cli_governance.py` 在组合层调用 `check_forbidden_source_tokens(...)`，将 source issues 与 required evidence / line budget issues 合并，并在 JSON payload 输出 `forbidden_source_tokens` 明细。
- 缺失文件和命中 forbidden token 都返回 error issue；命中 issue 含 `path`、`token`、`line`、`message`。
- 未修改 `src/ashare_evidence/process_hardening.py`；该文件保持 233 行，低于 240 warning。

BH2 验证记录：

- Focused tests：`PYTHONPATH=src python3 -m pytest tests/test_process_hardening_source.py tests/test_process_hardening.py tests/test_process_hardening_evidence.py tests/test_process_hardening_git_status.py -q` -> `23 passed in 1.00s`。
- Ruff：`ruff check src/ashare_evidence/process_hardening_source.py src/ashare_evidence/cli_governance.py tests/test_process_hardening_source.py` -> `All checks passed!`。
- Process hardening：status `pass`，issue_count `0`；行数为 `process_hardening.py` 233、`process_hardening_source.py` 65、`cli_governance.py` 146、`tests/test_process_hardening_source.py` 141、`tests/test_process_hardening.py` 155。
- Forbidden-token smoke：status `pass`，issue_count `0`；payload 含 `forbidden_source_tokens`，目标 `src/ashare_evidence/autonomous_flow_scheduler_action_route_auto_apply.py` 未命中 `route.reason ==`，status `checked`。
- Registry：status `pass`，doc_count `2`，issue_count `0`。
- Full regression：`PYTHONPATH=src python3 -m pytest -q` -> `497 passed, 147 deselected in 21.51s`。

主进程合入 BH2 产物后完成以下复验：

- focused tests：`23 passed in 0.86s`。
- ruff：`All checks passed!`。
- process hardening：`status=pass`，`issue_count=0`。
- forbidden-token smoke：`status=pass`，目标文件存在且 `matches=[]`。
- registry check：`status=pass`，`issue_count=0`。
- full regression：`497 passed, 147 deselected in 20.79s`。

## 5. 重跑记录

- BH1 rejected：功能正确，但让 `process_hardening.py` 贴近 warning 线，后续可维护性不足。
- BH2 rerun：按组合层接线重做，不修改 `process_hardening.py`；新增 helper 和独立测试，验证通过。

## 6. 自评

BH2 满足本轮设计目标：扫描逻辑独立于主 hardening 模块，CLI 层负责合并状态和 payload。默认 `run_process_hardening_check(...)` payload 未增加 `forbidden_source_tokens` 字段，避免 core API 行为漂移；真实 CLI 在无参数时输出空明细，在传入 forbidden token 时输出逐项检查明细。剩余风险较低，主要是当前实现是显式 token 子串扫描，不承担 AST 级语义识别，这与本轮范围一致。
