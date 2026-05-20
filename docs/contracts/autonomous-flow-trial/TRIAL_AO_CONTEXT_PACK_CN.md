# Trial AO Context Pack：Solidify Clean Closeout Gate

状态：active input
上游：Trial AN
目标：把 AN 新增的 clean git status 门禁写回全局自运行开发流程合同，确保后续 trial closeout 不再只依赖人工记忆检查未跟踪文件。

## 1. 背景

Trial AN 已为 `process-hardening-check` 增加 `--require-clean-git-status` 与 `--git-root`，并验证它能捕获 modified、staged、untracked 文件。当前全局流程合同仍只写了“保持工作树干净”和“git diff 检查”，没有明确要求 closeout 阶段使用该可执行门禁。

本轮是流程固化，不改业务代码。

## 2. 本轮目标

- 更新 `docs/contracts/AUTONOMOUS_DEVELOPMENT_FLOW_CN.md` 的 P6 closeout，明确：
  - `git diff --stat` 不可作为 clean worktree 依据。
  - commit 后、merge 前或 merge 后必须运行 clean git status 门禁。
  - 若门禁发现 untracked / modified / staged 残留，必须回到 P4/P5 判断是漏提交、越权改动还是需要拆新任务。
- 更新实现试验硬化规则，加入 clean status closeout 规则。
- 评估文档记录本轮是 Trial AN 的流程固化，而非新实现。

## 3. 非目标

- 不修改 `process-hardening-check` 代码。
- 不修改 scheduler、artifact store、frontend 或 stock research 业务代码。
- 不新增自动 git mutation。
- 不要求子进程运行 clean status closeout；该职责属于主进程。

## 4. Owned Files

默认允许修改：

- `docs/contracts/AUTONOMOUS_DEVELOPMENT_FLOW_CN.md`
- `docs/contracts/autonomous-flow-trial/TRIAL_AO_EVALUATION_CN.md`

禁止修改：

- `src/ashare_evidence/**`
- `tests/**`
- unrelated contracts。

## 5. 文件规模要求

- `docs/contracts/AUTONOMOUS_DEVELOPMENT_FLOW_CN.md` 当前 276 行，hard limit 340，warning 320。
- `docs/contracts/autonomous-flow-trial/TRIAL_AO_EVALUATION_CN.md` hard limit 140，warning 110。

## 6. 验收

- `PYTHONPATH=src python3 -m ashare_evidence.cli process-hardening-check --evaluation-doc docs/contracts/autonomous-flow-trial/TRIAL_AO_EVALUATION_CN.md --line-budget docs/contracts/AUTONOMOUS_DEVELOPMENT_FLOW_CN.md:340:320 --line-budget docs/contracts/autonomous-flow-trial/TRIAL_AO_EVALUATION_CN.md:140:110 --required-evidence docs/contracts/AUTONOMOUS_DEVELOPMENT_FLOW_CN.md:require-clean-git-status`
- `PYTHONPATH=src python3 -m ashare_evidence.cli contract-registry-check --registry docs/contracts/registry/autonomous_flow_registry.v1.json --docs docs/contracts/AUTONOMOUS_DEVELOPMENT_FLOW_CN.md --docs docs/contracts/autonomous-flow-trial/TRIAL_AO_CONTEXT_PACK_CN.md --docs docs/contracts/autonomous-flow-trial/TRIAL_AO_EVALUATION_CN.md --fail-on-unregistered --fail-on-deprecated`
- `git diff --check`
- `PYTHONPATH=src python3 -m pytest tests/test_process_hardening.py tests/test_process_hardening_git_status.py -q`
- `PYTHONPATH=src python3 -m pytest -q`
