# Trial BJ 评估记录：Scheduler Attempt Context Core

状态：verified
输入：`TRIAL_BJ_CONTEXT_PACK_CN.md`
目标：评估 scheduler attempt context core 是否能稳定生成可复放 `attempt_id`，并在缺参时 fail closed。

## 1. 子任务

| 子进程 | owned files | 目标 | 状态 |
| --- | --- | --- | --- |
| BJ1 | attempt context core、测试、本评估文件 | 新增稳定 attempt context core | passed |

## 2. 评分

| 维度 | 权重 |
| --- | ---: |
| 稳定 ID 与文件名安全 | 35 |
| 缺参 fail-closed | 25 |
| 无时间/随机/IO 副作用 | 25 |
| 文件规模与验证 | 15 |

自动重跑阈值：

- 读取当前时间、使用随机数或 UUID。
- 缺 `cycle_id`、`issued_at` 或 `runner_id` 时抛异常或生成 attempt。
- `attempt_id` 不稳定、不可读或文件名不安全。
- 修改 CLI、route/apply、artifact writer 或业务代码。
- focused tests、ruff、process hardening、registry 或 full regression 失败。

## 3. BJ1 结果

已新增 `build_phase5_scheduler_attempt_context(...)` 与 typed result
`Phase5SchedulerAttemptContextResult`。

实现结果：

- `cycle_id`、`issued_at`、`runner_id` 均显式作为函数输入；默认 `None`，漏传或空字符串返回 blocked typed result。
- ready result 返回稳定 `attempt_id`，格式含 cycle slug、runner slug、issued_at slug 与 12 位 SHA-256 digest。
- digest 输入为原始 `cycle_id`、`runner_id`、`issued_at`，用于区分 slug 相同但原始值不同的输入。
- core 不读当前时间、不使用 uuid/random、不写 artifact、不接 CLI、不调用 route/apply/writer。

## 4. 主进程验证

BJ1 本地验证通过；主进程并入工作树后复核通过：

```bash
PYTHONPATH=src python3 -m pytest tests/test_autonomous_flow_scheduler_attempt.py -q
# main: 5 passed in 0.19s

ruff check src/ashare_evidence/autonomous_flow_scheduler_attempt.py tests/test_autonomous_flow_scheduler_attempt.py
# main: All checks passed!

PYTHONPATH=src python3 -m ashare_evidence.cli process-hardening-check \
  --evaluation-doc docs/contracts/autonomous-flow-trial/TRIAL_BJ_EVALUATION_CN.md \
  --line-budget src/ashare_evidence/autonomous_flow_scheduler_attempt.py:180:150 \
  --line-budget tests/test_autonomous_flow_scheduler_attempt.py:220:190 \
  --line-budget docs/contracts/autonomous-flow-trial/TRIAL_BJ_EVALUATION_CN.md:140:110 \
  --required-evidence tests/test_autonomous_flow_scheduler_attempt.py:test_attempt_context_blocks_missing_inputs_without_io \
  --forbidden-source-token src/ashare_evidence/autonomous_flow_scheduler_attempt.py:'datetime.now' \
  --forbidden-source-token src/ashare_evidence/autonomous_flow_scheduler_attempt.py:'uuid' \
  --forbidden-source-token src/ashare_evidence/autonomous_flow_scheduler_attempt.py:'random'
# main: status: pass, issue_count: 0

PYTHONPATH=src python3 -m ashare_evidence.cli contract-registry-check \
  --registry docs/contracts/registry/autonomous_flow_registry.v1.json \
  --docs docs/contracts/autonomous-flow-trial/TRIAL_BJ_CONTEXT_PACK_CN.md \
  --docs docs/contracts/autonomous-flow-trial/TRIAL_BJ_EVALUATION_CN.md \
  --fail-on-unregistered --fail-on-deprecated
# main: status: pass, issue_count: 0

PYTHONPATH=src python3 -m pytest -q
# main: 502 passed, 147 deselected in 21.61s
```

主进程语义复核：

- 未触发重跑阈值；source scan 未发现 clock、random、uuid、IO、CLI、route/apply/writer 依赖。
- digest 原始串带 scheduler attempt namespace，同时保留原始 `cycle_id`、`runner_id`、`issued_at`，可接受为跨用途防碰撞设计。

## 5. 重跑记录

1 次实现后验证全通过；无失败重跑。

## 6. 自评

自评：通过。实现保持纯 core 范围，缺参 fail-closed，`attempt_id` 可读、稳定、文件名安全，未修改 CLI 或生产业务链路。
