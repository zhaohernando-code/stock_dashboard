# Trial AN 评估记录：Clean Git Status Closeout Check

状态：completed, main verification passed
输入：`TRIAL_AN_CONTEXT_PACK_CN.md`
目标：评估 clean git status closeout 检查是否能捕获未跟踪/未提交残留，避免流程文档或代码在 closeout 时被漏提交。

## 1. 子任务

| 子进程 | owned files | 目标 |
| --- | --- | --- |
| AN1 | process-hardening git status check、测试、本评估文件 | 为 closeout 增加可选 clean git status 门禁 |

## 2. 评分

| 维度 | 权重 |
| --- | ---: |
| Git status 语义 | 35 |
| CLI 兼容与 JSON 输出 | 25 |
| 测试覆盖 | 25 |
| 文件规模治理 | 15 |

自动重跑阈值：

- untracked 文件不能被发现。
- staged 或 modified tracked 文件不能被发现。
- 非 git 目录不 fail closed。
- 未传 clean status 参数时破坏既有 process-hardening 行为。
- focused tests、ruff、process hardening、registry 或 full regression 失败。

## 3. AN1 结果

AN1 已实现 `process-hardening-check` 的可选 clean git status closeout 检查：

- CLI 新增 `--require-clean-git-status` 与 `--git-root`；未传 clean 参数时保持既有评估文档、line budget、required evidence 行为。
- `run_process_hardening_check` 在 JSON 中输出 `git_status` 区块；默认 `status=skipped`，显式启用后返回 `clean`、`dirty` 或 `unavailable`。
- dirty 检查使用 `git status --porcelain=v1 --untracked-files=all`，保留 raw porcelain entries；untracked、staged、modified tracked 均产生 `git_status_dirty`。
- 非 git 目录或 git 命令不可用返回 `git_status_unavailable`，按 fail closed 处理。
- 新增 `tests/test_process_hardening_git_status.py`，覆盖 clean repo、untracked、staged+modified、非 git 目录、CLI JSON 且不初始化数据库。

AN1 focused gates：

- `PYTHONPATH=src python3 -m pytest tests/test_process_hardening.py tests/test_process_hardening_evidence.py tests/test_process_hardening_git_status.py -q`：16 passed。
- `ruff check src/ashare_evidence/process_hardening.py src/ashare_evidence/cli_governance.py tests/test_process_hardening.py tests/test_process_hardening_evidence.py tests/test_process_hardening_git_status.py`：passed。
- `PYTHONPATH=src python3 -m ashare_evidence.cli process-hardening-check ...`：status=pass，issue_count=0；line budgets 分别为 233、134、154、149。
- `PYTHONPATH=src python3 -m ashare_evidence.cli contract-registry-check ...`：status=pass，issue_count=0。
- `git diff --check`：passed。
- `PYTHONPATH=src python3 -m pytest -q`：412 passed，147 deselected。

## 4. 主进程验证

主进程语义审查：

- clean status 检查是 opt-in；未传 `--require-clean-git-status` 时 `git_status.status=skipped`，不会破坏既有门禁调用。
- dirty 检查覆盖 modified 与 untracked 条目；主进程在当前脏 worktree 上实测返回 `git_status_dirty`，并列出本轮代码、Context Pack、Evaluation、新测试文件。
- 非 git 目录 fail closed；测试覆盖 `git_status_unavailable`。
- 新检查不执行任何 git mutation，只读取 `git status --porcelain=v1 --untracked-files=all`。
- 主进程补充了默认路径 skipped 断言，防止后续把该 closeout 检查误改为默认强制。

主进程门禁：

- focused pytest：16 passed。
- ruff：passed。
- process hardening：passed；git clean 检查未启用时 status 为 skipped。
- dirty worktree probe：按预期 fail，issue 为 `git_status_dirty`。
- contract registry：passed。
- diff check：passed。
- full regression：412 passed，147 deselected。

## 5. 重跑记录

无需重跑子进程。主进程只补充了一个默认 skipped 兼容断言，并重跑 focused tests、ruff、process hardening 与 full regression。

## 6. 自评

自评：实现满足可选 closeout 门禁目标，默认路径不触发 git 检查；新增测试文件保持在 warning line budget 内。该门禁应在后续 trial commit 后、merge 前或 merge 后用于确认没有遗漏未跟踪流程文档。残余风险是 Windows porcelain path quoting 未单独覆盖，本项目当前 focused gates 在 macOS/Linux 风格路径下验证。
