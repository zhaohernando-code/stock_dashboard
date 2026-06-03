# 治理方案：日刷 DB 锁竞争导致面板全量超时

状态：定稿（已通过 DeepSeek 审核，并入 6 条补充）
日期：2026-06-04
worktree：`worker-workspaces/stock_dashboard/20260604-fix-refresh-db-lock-contention-074716`

## 0. 阶段落地状态

| 步骤 | 状态 | 说明 |
|------|------|------|
| P0 备份 ashare_dashboard.db | ✅ 已完成 | `data/backups/ashare_dashboard.before-wal-migration-20260604T005059Z.db` |
| P1-A db.py 开 WAL | ✅ 已完成并合入 main | commit ff66447；发布后 runtime DB 已 journal_mode=wal；**实测写锁持有 8s 期间 backend 读 3 次全部 HTTP 200（0.3-0.6s），不再被阻塞** |
| P1-C plist RunAtLoad=0 | ✅ 已完成并合入 main | publish `ensure_scheduled_refresh_calendar` 固定 `RunAtLoad=False` + 删除结尾强制 `kickstart -k`；live plist 已改并 reload 验证不触发日刷（8s 内无 phase5-daily-refresh 启动）；静态测试通过。**发现并修复第二个触发源：publish 结尾的 `kickstart -k`。** |
| P2-B1 四步各自 session_scope | ⬜ 未开始 | — |
| P3-D SLOT_RETRY_INTERVAL 1800→7200 | ⬜ 未开始 | — |
| 归档 | ⬜ 未开始 | 全部完成后 docs/contracts→docs/archive |

状态图例：⬜ 未开始 / ⏳ 进行中 / ✅ 已完成并合入 main。

## 1. 事故复盘

### 现象
网页能打开（前端静态文件正常），但所有 tab 数据请求超时。后端在 8000 端口 LISTEN，但每个查询撞 `sqlite3.OperationalError: database is locked`。

### 直接原因链
1. `phase5-daily-refresh`（盘后日刷）是一条 ~50 分钟的全量分析+落库流水线。
2. 运行时库 `ashare_dashboard.db` 处于 `journal_mode=delete`（写者排他，阻塞所有读者）。
3. 日刷期间反复写库，后端读查询被 30s busy_timeout 挡死后超时 → 所有 tab 超时。

### 导火索（前序治理）
- scheduled-refresh plist 是 `RunAtLoad=1`。SessionCreate/EADDRINUSE 治理期间我反复 `launchctl unload/load`，每次 reload 都立即起一次重型日刷。
- 反复 `pkill`/`kill -KILL` 打断了进行中的日刷 → 没写 `.ok` → 守卫认为"今天没成功跑过" → 30 分钟退避后又起一次。今天异常跑了 3 次（19:19/22:24/22:59）。

## 2. 三个根因（用户确认）

### 根因 A：写阻塞读（最高优先级）
- `db.py:get_engine` 只设了 `busy_timeout=30000`，**从未设 `journal_mode=WAL`**，实际是 `delete`。
- delete journal 下写者持排他锁，所有读者阻塞。WAL 模式下读写可并发（读者读快照，写者另写 WAL），后端在日刷期间仍可读。

### 根因 B：refresh 全程持有 session（写动作不应跨网络 I/O）
- `cli.py:1225 phase5-daily-refresh` 在一个 `session_scope` 里串行做：关注池逐只刷新（含 akshare/tushare **网络抓取**）→ horizon study(latest) → horizon study(history, 含全历史) → holding policy study。
- 虽然 `refresh_watchlist_symbol` 内部 per-symbol commit，但整条流水线在同一个 session 内，网络抓取和重分析期间持有 SQLite 连接。SQLite 写锁本应只在"实际 INSERT/UPDATE 落库的那一刻"持有，而现在连接在慢速网络/计算期间也占着，放大了与后端读的冲突窗口。

### 根因 C：reload 即重启（不该）
- `RunAtLoad=1` 让任何 `launchctl load` 都立即起一次重型日刷。reload agent（治理、改配置、重启机器）本意只是"让定时器生效"，不应触发一次全量计算。

## 3. 修复方案

### 修复 A：开启 WAL（根治写阻塞读）
- 文件：`src/ashare_evidence/db.py` 的 `get_engine` sqlite 连接事件。
- 在 `_set_sqlite_busy_timeout` 同处追加：
  - `PRAGMA journal_mode=WAL`
  - `PRAGMA synchronous=NORMAL`（WAL 下安全且更快；FULL 没必要）
- 影响：日刷写 WAL 期间，后端读走快照不再被阻塞。是 KNOWN_TRAP #2 的根治方向。
- 注意：WAL 会产生 `-wal`/`-shm` 文件；备份/发布脚本若按单文件拷贝需确认（rsync 已含同目录，但 `.gitignore` 与备份逻辑要核对，避免只拷主库丢未 checkpoint 的 WAL）。需要定期 `wal_checkpoint(TRUNCATE)` 控制 WAL 体积——日刷收尾处做一次 checkpoint。

### 修复 B：缩短写事务持有窗口（写只在写时发生）
- 原则：网络抓取/重分析在 session 外完成，只有落库瞬间开短事务。
- 现实约束：这是大改，`refresh_watchlist_symbol` 等已 per-symbol commit，主要膨胀点是 horizon/holding study 的长读+写 artifact。
- 分两步：
  - B1（低风险，先做）：把 `phase5-daily-refresh` 的四个步骤**各自独立 session_scope**，而不是共享一个外层 session。每步结束即释放连接，缩短锁占用窗口。即把 `cli.py:1227-1251` 的单个 `with session_scope()` 拆成每步一个 `with session_scope()`。
  - B2（可选，后续）：horizon/holding study 内部把"读取数据→纯计算→写 artifact/落库"解耦，计算阶段不持有 DB 连接。属于更大重构，本次只记录不实施。
- 配合 WAL（修复 A）后，B 的紧迫性下降——WAL 已让读不被写挡住；B 进一步降低写者之间和 checkpoint 的争用。

### 修复 C：reload 不再触发全量日刷
- 文件：`~/Library/LaunchAgents/com.codex.ashare-dashboard.scheduled-refresh.plist`（仓库外配置）。
- 把 `RunAtLoad=1` 改为 `RunAtLoad=0`（或移除）。依赖 `StartInterval=300` 的下一次 tick 自然触发；slot 守卫（`.ok` 文件）保证当天只跑一次。
- 这样 reload agent 只是"重新登记定时器"，不立即起重型任务。
- 代价：机器刚启动/刚 load 后，最多等一个 StartInterval(5min) 才开始当天首刷。可接受（盘后刷新不在乎 5 分钟）。
- 备选：保留 `RunAtLoad` 但让 `run-scheduled-refresh.sh` 启动时先判断"距上次 attempt 不足 N 分钟则跳过"。但这是给脚本加状态，不如直接关 RunAtLoad 干净。

### 修复 D（附带）：打断不留状态导致重试风暴
- 现状：被 kill 的日刷不写 `.ok`，30min 退避后重试。治理/手动操作期间反复打断会放大。
- 轻量加固：`run-scheduled-refresh.sh` 在 `acquire_run_lock` 已有并发保护；可把 `SLOT_RETRY_INTERVAL_SECONDS` 从 1800s 调大（如 7200s，与日刷超时同量级），减少"刚被打断又立刻重试"。低风险。
- 本次仅记录，是否实施待定。

## 4. 实施顺序与风险（DeepSeek 审核后定稿）

| 优先级 | 步骤 | 改动 | 风险 | 验证 |
|------|------|------|------|------|
| **P0** | **强制备份 `ashare_dashboard.db`** | 切 WAL 前 `cp` 带时间戳备份到 `data/backups/` | — | 备份文件存在且大小一致 |
| P1 | A：db.py 开 WAL + synchronous=NORMAL + wal_autocheckpoint | `get_engine` sqlite connect 事件追加 PRAGMA | 中 | 单测 + 手动并发读写 + 日刷期间面板可读 |
| P1 | C：plist RunAtLoad=0 | 仓库外 plist 配置 | 低 | reload 后不立即起日刷；等一个 tick 正常起 |
| P2 | B1：四步各自 session_scope | `cli.py:1227-1251` 拆成 4 个 `with session_scope()` | 低（已验证返回 dict，无跨步 ORM 对象传递） | 日刷端到端 + artifact 正常 |
| P3 | D：SLOT_RETRY_INTERVAL 1800→7200 | 脚本环境变量默认值 | 低 | 配置项 |
| P4 | B2：study 内部读算写解耦 | 本次不做，仅记录为后续 | 高 | — |

A 和 C 无依赖，可并行发布。

### DeepSeek 审核并入的 6 条补充
1. **前置备份提升为 P0**（已采纳，见上表）。WAL 切换对该 db 文件不可逆，发布前必须先带时间戳备份。
2. **wal_autocheckpoint**：A 步骤同时设 `PRAGMA wal_autocheckpoint=1000`，靠 SQLite 自动 checkpoint 控制 WAL 体积；日刷收尾再做一次 `wal_checkpoint(TRUNCATE)` 兜底。运行期可 `du -sh *.db-wal` 监控（预期 <200MB，超 500MB 在 study 内加 PASSIVE checkpoint）。
3. **B1 跨步一致性已代码验证**：四步函数都只返回 plain dict（`refresh_payload`/`latest_study`/`history_study`/`holding_policy_study`），无 ORM 对象跨步传递、无懒加载依赖。拆 session 安全。
4. **日常备份脚本核查**（非 publish）：`prune-runtime-db-backups.sh` 管理 `.before-*.db`。WAL 下备份单 `.db` 可能丢未 checkpoint 的 WAL；备份前应先 `wal_checkpoint(TRUNCATE)` 或用 `sqlite3 .backup`/`VACUUM INTO`。本次记录，备份机制单独跟进。
5. **切 WAL 后重启后端**：后端旧连接仍以 delete 模式运行直到断开。A 发布后必须重启 backend，确保所有连接统一到 WAL。
6. **SQLite 版本已确认**：运行时 `sqlite 3.49.1` ≥ 3.7.0（WAL 引入），满足。

### DeepSeek 对三个疑点的结论
1. **WAL 能解决面板可读**：✅ 根治手段。backend 与 scheduled-refresh 两进程同时连库时，WAL 允许多读单写并发，读者读快照不被写者阻塞。
2. **B1 拆 session 安全**：✅ 已代码验证返回 dict，无跨步未提交依赖；拆后不会读到半完成状态（每步自己的事务原子提交）。
3. **关 RunAtLoad 代价可接受**：✅ 最优方案。重启当天首刷最多延迟一个 StartInterval(5min)。`synchronous=NORMAL`+WAL 崩溃只丢未 sync 事务（非 corruption），`.ok` 守卫已提供重跑容忍。

## 5. 收尾要求
- A/B1 是 live-facing 代码改动：必须 `publish-local-runtime.sh` 发布到 runtime，**A 发布后重启 backend**，再真实验证面板在日刷期间可读。
- C/D 是配置：plist 改完 `launchctl unload/load` 生效，`plutil -lint` 验证。
- WAL 切换前 **P0 强制备份** `ashare_dashboard.db`。
- 参数治理：A 的 `journal_mode`/`synchronous`/`wal_autocheckpoint` 属基础设施 PRAGMA，非业务阈值；按 `stable_rule` 记录，收尾跑 `policy-audit`。
- 合入 stock_dashboard `origin/main`，worktree 清理。

## 6. 疑点（已由 DeepSeek 审核闭环，见 §4）
全部 4 个原始疑点已闭环：WAL 副作用、B1 一致性、RunAtLoad 代价、备份均已在 §4 覆盖。
