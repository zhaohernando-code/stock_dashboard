# Trial AN Context Pack：Clean Git Status Closeout Check

状态：active input
上游：Trial AH、AI、AL、AM
目标：把 closeout 阶段“不能遗留未提交/未跟踪文件”的人工检查升级为 `process-hardening-check` 可执行门禁。

## 1. 背景

Trial AL 与 AM 暴露了同一类 closeout 风险：

- `git diff --stat` 不显示未跟踪文件。
- Context Pack / Evaluation 文档在创建后默认是 untracked，如果主进程只看 diff stat，可能提交了代码却漏掉流程记录。
- 该问题属于自动化平台 closeout 基座缺口，不应长期依赖人工记忆。

本轮新增一个可选 git clean status 检查，供“commit 后、merge 前”或“merge 后、push 前”调用，确认当前 worktree 没有 staged、unstaged 或 untracked 残留。

## 2. 本轮目标

- 为 `process-hardening-check` 增加可选参数，建议为 `--require-clean-git-status`。
- 支持可选 `--git-root`，默认当前目录。
- 当 git status 不是 clean 时，输出 JSON issue，包含 dirty entries。
- 当目标目录不是 git repo 或 git 命令不可用时，fail closed。
- 保持既有 evaluation doc、line budget、required evidence 行为兼容。
- 不改变当前各 Trial 常规门禁调用；clean status 检查应作为 closeout 后置门禁使用。

## 3. 非目标

- 不自动执行 git add / commit / merge / push。
- 不解析业务文件归属。
- 不改变 branch-per-trial 流程。
- 不把 clean status 设为 `process-hardening-check` 默认行为。

## 4. Owned Files

默认允许修改：

- `src/ashare_evidence/process_hardening.py`
- `src/ashare_evidence/cli_governance.py`
- `tests/test_process_hardening.py`
- `docs/contracts/autonomous-flow-trial/TRIAL_AN_EVALUATION_CN.md`

如需拆分测试，允许新增：

- `tests/test_process_hardening_git_status.py`

禁止修改：

- scheduler execution、artifact store、frontend、stock research 业务文件。

## 5. 文件规模要求

- `src/ashare_evidence/process_hardening.py` hard 280，warning 240。
- `src/ashare_evidence/cli_governance.py` hard 180，warning 150。
- `tests/test_process_hardening.py` hard 220，warning 190；如接近 warning，必须新增独立 git status 测试文件。
- 新测试文件 hard 180，warning 150。

## 6. 必测场景

- clean git repo passes when `--require-clean-git-status` is set.
- untracked file fails with `git_status_dirty` and exposes porcelain entry.
- staged or modified tracked file fails.
- non git directory fails closed with `git_status_unavailable` or equivalent typed issue。
- CLI JSON 包含 `git_status` 区块，且不初始化数据库。
- 未传 `--require-clean-git-status` 时行为与当前兼容。

## 7. 验收

- `PYTHONPATH=src python3 -m pytest tests/test_process_hardening.py tests/test_process_hardening_evidence.py tests/test_process_hardening_git_status.py -q`
- `ruff check src/ashare_evidence/process_hardening.py src/ashare_evidence/cli_governance.py tests/test_process_hardening.py tests/test_process_hardening_evidence.py tests/test_process_hardening_git_status.py`
- `PYTHONPATH=src python3 -m ashare_evidence.cli process-hardening-check --evaluation-doc docs/contracts/autonomous-flow-trial/TRIAL_AN_EVALUATION_CN.md --line-budget src/ashare_evidence/process_hardening.py:280:240 --line-budget src/ashare_evidence/cli_governance.py:180:150 --line-budget tests/test_process_hardening.py:220:190 --line-budget tests/test_process_hardening_git_status.py:180:150 --required-evidence tests/test_process_hardening_git_status.py:git_status_dirty`
- `PYTHONPATH=src python3 -m ashare_evidence.cli contract-registry-check --registry docs/contracts/registry/autonomous_flow_registry.v1.json --docs docs/contracts/autonomous-flow-trial/TRIAL_AN_CONTEXT_PACK_CN.md --docs docs/contracts/autonomous-flow-trial/TRIAL_AN_EVALUATION_CN.md --fail-on-unregistered --fail-on-deprecated`
- `git diff --check`
- `PYTHONPATH=src python3 -m pytest -q`
