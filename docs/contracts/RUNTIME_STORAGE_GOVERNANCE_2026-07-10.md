# 运行时存储治理合同（2026-07-10）

## 完成状态

| 项目 | 状态 | 结果 |
|---|---|---|
| 真实研究目录生命周期门禁 | completed | 在线研究目录门禁 `passed` |
| 当前 v3 可复用核心固定 | completed | 完整特征矩阵 1 份、完整候选源 2 份、R14 确定性执行快照 1 份 |
| 旧研究载荷冷归档 | completed | 64 文件，16,387,148,025 字节压缩为 1,773,438,982 字节 |
| 旧数据库备份归档 | completed | 2 份 SQLite `quick_check=ok`，压缩归档约 1.5 GiB |
| 冷热拆分遗留库归档 | completed | 历史主键缺失 0；五张研究表行数一致；压缩归档约 442 MiB |
| 发布快照轮转 | completed | 152 份收敛为最近 10 份 |
| 可重建运行时缓存清理 | completed | runtime `node_modules`、Chrome profile、Playwright 缓存已移除 |
| 旧工作树收敛 | completed | 6 个已合入且干净的工作树已移除；未合入/有修改的工作树保留 |
| 发布流程持续治理 | completed | 发布前归档过期 DB 备份、审计研究生命周期；成功标记前轮转输出 |

## 容量结果

- 在线运行目录：`33.456 GiB -> 10.211 GiB`，减少 `23.245 GiB`。
- 当前在线研究制品：`6,025,913,243` 字节。
- 当前钉住制品：完整特征矩阵、两个候选源及 R14 确定性执行快照；精确字节数以自动门禁输出为准。
- 当前小型治理证据：保持在 `256 MiB` 门禁内；精确字节数以自动门禁输出为准。
- 当前待归档大载荷：`0`。
- 冷归档保留了完整源文件 SHA-256、压缩文件完整性测试和逐文件恢复元数据。

## 在线权威来源

| 类别 | 权威来源 | 允许的次级来源 | 过期/清理规则 |
|---|---|---|---|
| 日刷写入数据库 | `data/ashare_dashboard.db` | 压缩数据库恢复点 | 当前主库永不进入清理脚本 |
| 在线 API 数据库 | `data/ashare_hot.db` | 主库可用于重建 | 运行进程打开时禁止迁移 |
| 完整历史 v3 特征 | `pit-feature-matrix-9e2854ba4a2cd78e` | 对应冷归档旧版本 | 只能由策略政策显式替换 |
| 完整历史候选源 | `84adc785808483d3`、`0d6333a65ae410f0` | 冷归档旧 candidate-run | 非钉住完整载荷必须归档 |
| R14 确定性执行基线 | `shortpick-v3-execution-snapshot-067c5b83e085f95f` | 对应实验合同与分析 notebook | 摘要不一致时 fail closed；钉住文件不得归档 |
| 前端静态历史指标 | `docs/contracts/SHORTPICK_V3_R14_QUALITY_REPLACEMENT_REBALANCE_2026-07-10.json` 等合同 | 完整候选源和账户回放 | 前端不得请求时重算 |
| 被拒绝研究证据 | 在线小型 comparison/governance/diagnostic 报告 | 冷归档完整载荷 | 小型证据总量上限 256 MiB |
| 临时探索 | `/private/tmp/shortpick_*` | 提炼后的合同或冷归档 | 不作为权威来源；轮次结束后提炼再过期 |

## 血缘边界

`pit-feature-matrix-9e2854ba4a2cd78e` 是当前唯一完整历史 v3 特征矩阵。其
`source_universe_date_matrix_id=universe-date-matrix-8a8408ca4048dc45` 是
`input_snapshot_only + streaming rebuild` 流程生成的逻辑引用，不是遗漏的独立大文件。
新建 input snapshot 和流式矩阵现在会明确写入 materialization 状态，避免后续再次误判。

原制品的 `code_version=unresolved_local_checkout` 无法事后修造成精确提交。治理合同只允许声明：

- 冻结矩阵本身可作为确定输入复用；
- 行内容摘要固定为 `9e2854ba4a2cd78e71d9cb9ab57f1542c62f588d8ce2a334f027b0fe9479075b`；
- 可以按记录的 input snapshot 和 CLI 重建新版本；
- 不得声称新重建结果与 2026-07-09 的历史工作区逐字节一致。

## 自动门禁

```bash
PYTHONPATH=src python3 -m ashare_evidence.cli runtime-storage-governance-audit \
  --artifact-root ~/codex/runtime/projects/ashare-dashboard/data/artifacts \
  --policy-json docs/contracts/SHORTPICK_V3_RUNTIME_STORAGE_POLICY_2026-07-10.json
```

门禁要求：

- 当前完整矩阵、两个候选源、R14 执行快照和 input snapshot 必须存在；
- 在线研究制品总量不超过 7 GiB；
- 小型治理证据不超过 256 MiB；
- 大载荷目录中不得存在未钉住文件；
- 逻辑 universe 引用和历史代码版本限制必须被显式记录。

## 冷归档与恢复

研究归档：

`~/Library/Logs/codex-archive/ashare-dashboard-research-artifacts/20260710-runtime-storage-governance`

数据库备份归档：

`~/Library/Logs/codex-archive/ashare-dashboard-db-backups`

冷热拆分遗留库归档：

`~/Library/Logs/codex-archive/ashare-dashboard-legacy-split-databases/20260710`

恢复 zstd 文件时，先读取同名 `.metadata.json`，执行 `zstd -t`，解压后重新计算 SHA-256，
只有与 `source_sha256` 一致时才能放回运行目录。gzip 数据库备份先执行 `gzip -t`，再解压到
隔离路径并运行 SQLite `PRAGMA quick_check`；不能直接覆盖在线数据库。
