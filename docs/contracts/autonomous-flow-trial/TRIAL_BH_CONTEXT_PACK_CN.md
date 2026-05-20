# Trial BH 上下文包：Process Hardening Forbidden Source Token

目标：把 BG 轮暴露的“子进程通过解析 `route.reason` 自然语言改写 route type”升级为可执行流程门禁。`process-hardening-check` 应支持显式检查某些源码 token 不得出现，使后续试运行可以把“禁止 reason 文案驱动分支”写成机器门禁，而不只依赖主进程人工 review。

## 1. 背景

Trial BG1 产物能通过测试，但在 core 中用 `route.reason == "scheduler action preflight blocked by missing inputs"` 改写 route type。主进程拒绝后，BG2/BG3 回到真实 route contract。该经验需要固化到流程工具：当上下文包禁止某类源码写法时，主进程应能在 `process-hardening-check` 中传入明确的 forbidden token。

当前 `src/ashare_evidence/process_hardening.py` 已接近 warning 线，不能继续把扫描逻辑堆进去。本轮必须拆出独立 helper module，并避免修改主模块。

## 2. 本轮范围

必须做：

- 为 `process-hardening-check` 新增可选参数，例如 `--forbidden-source-token path:token`。
- 支持重复传入多个 forbidden token。
- token 解析必须允许 token 内含冒号；因此只按第一个冒号切分。
- 如果目标文件不存在，返回 error issue。
- 如果目标文件包含 token，返回 error issue，至少包含 path、token、line、message。
- JSON payload 中新增 `forbidden_source_tokens` 检查明细。
- 默认不传该参数时，既有行为完全不变。
- 新增独立模块，例如 `src/ashare_evidence/process_hardening_source.py`，避免 `process_hardening.py` 继续膨胀。
- source token 检查可以像 required evidence 一样在 CLI governance 组合层合并到 payload；不得为了新增明细让 `process_hardening.py` 贴近 warning 线。
- 新增独立测试文件，不扩写 `tests/test_process_hardening.py`。
- 用真实 CLI 测试验证不触发数据库初始化。

不得做：

- 不做复杂 AST 规则引擎。
- 不扫描整个 repo；必须显式传 path。
- 不默认禁止所有 `.reason` 使用；本轮只提供显式 token 门禁。
- 不修改业务代码。

## 3. 子进程任务

| 子进程 | owned files | 目标 |
| --- | --- | --- |
| BH1 | process hardening source token helper、CLI 接线、测试、本评估文件 | 新增 forbidden source token 门禁 |
| BH2 | process hardening source token helper、CLI 接线、测试、本评估文件 | 不修改主 hardening 模块的重跑实现 |

子进程注意：本轮是流程工具，不是业务修复。设计要小、可组合、可在后续 trial context 中直接复用。

## 4. 文件规模预算

- `src/ashare_evidence/process_hardening.py`：hard 280，warning 240，不得修改。
- `src/ashare_evidence/process_hardening_source.py`：hard 180，warning 150。
- `src/ashare_evidence/cli_governance.py`：hard 180，warning 150。
- `tests/test_process_hardening_source.py`：hard 220，warning 190。
- `tests/test_process_hardening.py`：hard 220，warning 190，不得扩写。

如果达到 warning，必须拆分或压缩。

## 5. 验证命令

Focused tests：

```bash
PYTHONPATH=src python3 -m pytest tests/test_process_hardening_source.py tests/test_process_hardening.py tests/test_process_hardening_evidence.py tests/test_process_hardening_git_status.py -q
```

Ruff：

```bash
ruff check src/ashare_evidence/process_hardening_source.py src/ashare_evidence/cli_governance.py tests/test_process_hardening_source.py
```

Process hardening：

```bash
PYTHONPATH=src python3 -m ashare_evidence.cli process-hardening-check \
  --evaluation-doc docs/contracts/autonomous-flow-trial/TRIAL_BH_EVALUATION_CN.md \
  --line-budget src/ashare_evidence/process_hardening.py:280:240 \
  --line-budget src/ashare_evidence/process_hardening_source.py:180:150 \
  --line-budget src/ashare_evidence/cli_governance.py:180:150 \
  --line-budget tests/test_process_hardening_source.py:220:190 \
  --line-budget tests/test_process_hardening.py:220:190 \
  --required-evidence tests/test_process_hardening_source.py:forbidden_source_token
```

Forbidden-token smoke：

```bash
PYTHONPATH=src python3 -m ashare_evidence.cli process-hardening-check \
  --evaluation-doc docs/contracts/autonomous-flow-trial/TRIAL_BH_EVALUATION_CN.md \
  --line-budget src/ashare_evidence/process_hardening.py:280:240 \
  --forbidden-source-token src/ashare_evidence/autonomous_flow_scheduler_action_route_auto_apply.py:'route.reason =='
```

Registry：

```bash
PYTHONPATH=src python3 -m ashare_evidence.cli contract-registry-check \
  --registry docs/contracts/registry/autonomous_flow_registry.v1.json \
  --docs docs/contracts/autonomous-flow-trial/TRIAL_BH_CONTEXT_PACK_CN.md \
  --docs docs/contracts/autonomous-flow-trial/TRIAL_BH_EVALUATION_CN.md \
  --fail-on-unregistered --fail-on-deprecated
```

Full regression：

```bash
PYTHONPATH=src python3 -m pytest -q
```
