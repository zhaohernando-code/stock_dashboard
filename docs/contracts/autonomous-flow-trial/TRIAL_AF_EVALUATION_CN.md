# Trial AF 评估记录：Scheduler Execution Idempotency Reservation

状态：已完成  
输入：`TRIAL_AF_CONTEXT_PACK_CN.md`  
目标：评估 scheduler execution 是否具备原子 reservation 层，并验证 crash replay 与 conflict side effect 边界。

## 1. 子任务

| 子进程 | owned files | 目标 |
| --- | --- | --- |
| AF1 | artifacts、store、record、reservation tests、本评估文件 | 增加 idempotency reservation 与 record 集成 |

## 2. 评分

| 维度 | 权重 |
| --- | ---: |
| 原子 reservation 语义 | 35 |
| record 层恢复与冲突边界 | 30 |
| 合同注册与持久化设计 | 20 |
| 测试覆盖与文件规模 | 15 |

自动重跑阈值：

- reservation 写入会覆盖 existing payload。
- same key + different execution id 写入 ledger 或修改 cycle。
- reservation existing + ledger missing 不能恢复 same execution id。
- digest 文件 payload key mismatch 未 fail closed。
- focused tests、ruff、registry 或 full regression 失败。

## 3. AF1 结果

已实现。

- 将 reservation 建模为注册 artifact family，而不是内部 sidecar。理由：reservation 是跨进程幂等边界和 crash replay 恢复入口，本身需要可审计、可校验、可被后续检视流程定位。
- 新增稳定 digest reservation id。文件名只包含固定前缀和 key digest，不把原始 key 放入路径。
- store 层采用原子 create-if-absent 语义：首次创建成功；已有文件时读取 existing 并返回；若 digest 文件中的 key 与请求 key 不一致则 fail closed。
- record 层改为 reserve-first。same key + same execution id + ledger missing 会恢复写 ledger；same key + different execution id 复用 Trial AE typed conflict，且不写 requested ledger、不修改 cycle。
- 保留 Trial AE replay 语义：ledger existing 时不重写 ledger，只补缺失的 cycle event。
- 测试拆分为 ledger、idempotency、reservation 三个文件，避免把单一测试文件推到高风险规模。

本轮新增注册 artifact family：

- `phase5_scheduler_execution_reservation`

当前文件规模：

- scheduler execution store：187 行
- reservation tests：172 行
- idempotency tests：131 行
- ledger tests：158 行
- shared helper：38 行

## 4. 主进程验证

AF1 已执行门禁：

- focused pytest：27 passed
- ruff：passed
- wc：187 / 172 / 131 / 158 / 38
- contract registry check：passed，2 docs，0 issues
- policy audit：passed，0 hard constraint failures
- git diff check：passed
- full regression：381 passed，147 deselected

主进程评估后发现一个迁移边界缺口：如果 Trial AE 时期已经存在 execution ledger，但还没有 reservation，新请求使用相同 key、不同 execution id 时，AF1 的 reserve-first 主路径会先创建 requested reservation，再按 execution id 读取 ledger，导致无法发现旧 ledger。主进程已修正为：

- record 层先读取 legacy existing ledger，用 existing ledger seed reservation。
- legacy existing ledger 与请求 execution id 不一致时，抛 Trial AE typed conflict。
- 该 conflict 不写 requested ledger、不修改 cycle；只允许创建指向 existing execution 的 reservation，作为旧数据迁移索引。

主进程修正后已执行：

- focused pytest：28 passed
- ruff：passed
- wc：store 187，reservation tests 172，idempotency tests 165，ledger tests 158，helper 38
- contract registry check：passed，2 docs，0 issues，registered ids 57
- policy audit：passed，0 hard constraint failures
- git diff check：passed
- full regression：382 passed，147 deselected

## 5. 重跑记录

无需重跑子进程。AF1 聚焦门禁未触发原始阈值，但主进程代码审查发现 legacy ledger migration gap，已在主进程补测试并修正。

## 6. 自评

当前自评分：92 / 100。

- 原子 reservation 语义：满足 digest path、create-if-absent、existing 不覆盖、mismatch fail closed。
- record 恢复与冲突边界：覆盖 first record、crash replay、reservation conflict no side effect、legacy ledger conflict migration。
- 合同注册：已补 registry 和 schema。
- 残余风险：当前原子性依赖本地文件系统语义；Context Pack 明确非目标包含跨机器分布式锁，因此未引入外部锁服务。
