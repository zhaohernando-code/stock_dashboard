# stock_dashboard

A 股波段决策看板。源码在 `projects/stock_dashboard`，运行时在 `runtime/projects/ashare-dashboard`。

**技术栈**：Python 3.12 FastAPI + React 18 TypeScript + Vite 4 + Ant Design 6

## 命令

```bash
# 安装 / 修复 Git hooks（首次进入或发现 hook 未触发时先跑）
bash scripts/install-git-hooks.sh

# 默认开发快回归；不要把日刷、真实刷新、seeded workspace 长链路放进默认 pytest
python3 -m pytest -q

# 参数与公式治理硬约束；改权重、阈值、窗口、公式、Phase gate 后必须跑
PYTHONPATH=src python3 -m ashare_evidence.cli policy-audit \
  --fail-on-new-unclassified \
  --fail-on-direct-config-read \
  --fail-on-formula-side-effects \
  --fail-on-missing-config-lineage

# 运行时/日刷/真实分析长链路专项验收；只在明确需要 integration 时跑
bash scripts/test-runtime-integration.sh

# 发布（源码 → 运行时）
ASHARE_PUBLISH_REFRESH_MODE=skip bash scripts/publish-local-runtime.sh

# 手动刷新
bash scripts/run-scheduled-refresh.sh

# 前端 dev
cd frontend && npm run dev
```

## 强制门禁

- 本项目的 Git hooks 使用 `core.hooksPath=../../.githooks`，不是仓库内 `.git/hooks`。如果 hook 没触发，先运行 `bash scripts/install-git-hooks.sh`，确认共享 `../../.githooks/pre-push` 存在且可执行。
- push 前必须经过 `scripts/hooks/pre-push-stock-dashboard.sh`：工作树必须干净；推 `origin/main` 时必须是本地 `main` tip；自动运行默认 fast pytest 和 policy audit。
- 默认 `pytest` 是快回归边界。`runtime_integration` 覆盖 Phase 5 日刷、`refresh-runtime-data`、真实分析流水线、seeded workspace 等长链路，不能混回默认测试。
- live-facing 改动不能只停在 repo：必须发布到 `~/codex/runtime/projects/ashare-dashboard`，再用真实 served 页面或 API 验证。无法验证时不能说已完成。
- 收尾时必须明确变更是否已经合入 `main` 且 push 到 `origin/main`。不要把 task 分支、本地未 push 或未发布状态描述为已收尾。
- 参数与公式治理是运行合同：业务代码不得直接读写 `PolicyConfigVersion` 或 `policy_config_versions`，必须通过 `policy_config_loader`；active 参数版本不可原地修改，只能新增版本并 retire 旧版本。

## 已知陷阱

见根级 [KNOWN_TRAPS.md](../../KNOWN_TRAPS.md)，重点关注：
- \#1 Pydantic + future annotations（本项目历史 #1 bug）
- \#2 SQLite WAL 模式
- \#13 JSON `detail` vs `error` key
- \#14 `from __future__ import annotations` 本质
- \#15 大文件拆分前检查循环依赖

## 代码风格

- Python：snake_case，120 列，ruff（E/F/I/N/W/UP 规则）
- TypeScript：strict mode，Ant Design 6，无 ESLint（tsc --noEmit 足够）
- 注释：英文技术注释，中文用户界面文案

## 关键路径

| 文件 | 用途 | 大小 |
|------|------|------|
| `src/ashare_evidence/api.py` | 所有 FastAPI 路由 | - |
| `src/ashare_evidence/schemas/` | Pydantic 模型（7 个域文件） | ⚠️ 循环依赖风险 |
| `src/ashare_evidence/operations.py` | 运营复盘数据聚合 | 1710 行 |
| `frontend/src/App.tsx` | 主应用壳 | 2503 行 |
| `frontend/src/api/core.ts` | API 客户端（URL 重试、错误处理） | - |

## 项目文档

| 文件 | 用途 |
|------|------|
| `PROJECT_STATUS.json` | 当前阶段、阻塞项 |
| `DECISIONS.md` | 耐久决策 |
| `PROCESS.md` | 反回归教训 |
| `PROJECT_RULES.md` | 项目规则 |
