# 一个关于a股的当前数据和投资建议看板

当前仓库已经完成第 2 步“证据化数据底座”的后端骨架，目标是让任一建议都能按股票、时间、模型版本、提示词版本和原始证据完整回溯。

## 当前实现

- 后端技术栈：`Python 3.12 + FastAPI + SQLAlchemy`
- 数据路线预留：`Tushare Pro + 巨潮资讯/交易所披露 + Qlib`，当前用 `DemoLowCostRouteProvider` 证明链路
- 强制血缘字段：`license_tag`、`usage_scope`、`redistribution_scope`、`source_uri`、`lineage_hash`
- 已落表域模型：
  - 股票与板块：`stocks`、`sectors`、`sector_memberships`
  - 行情与事件：`market_bars`、`news_items`、`news_entity_links`
  - 特征与模型：`feature_snapshots`、`model_registries`、`model_versions`、`model_runs`、`model_results`
  - 建议与证据：`prompt_versions`、`recommendations`、`recommendation_evidence`
  - 模拟交易：`paper_portfolios`、`paper_orders`、`paper_fills`
  - 采集审计：`ingestion_runs`
- 已交付入口：
  - CLI：初始化数据库、写入 demo 数据、查看最新建议、查看完整 trace
  - API：`/health`、`/bootstrap/demo`、`/stocks/{symbol}/recommendations/latest`、`/recommendations/{id}/trace`

## 目录

- [src/ashare_evidence/models.py](./src/ashare_evidence/models.py): 证据化数据模型
- [src/ashare_evidence/providers.py](./src/ashare_evidence/providers.py): 低成本路线 provider contract 与 demo provider
- [src/ashare_evidence/services.py](./src/ashare_evidence/services.py): 入库、trace、建议查询服务
- [src/ashare_evidence/api.py](./src/ashare_evidence/api.py): FastAPI 应用
- [tests/test_traceability.py](./tests/test_traceability.py): 回溯链路验证

## 本地运行

当前环境可直接用 `PYTHONPATH=src` 启动，无需先打包安装。

```bash
PYTHONPATH=src python3 -m ashare_evidence load-demo --database-url sqlite:///./data/validation.db
PYTHONPATH=src python3 -m ashare_evidence latest --database-url sqlite:///./data/validation.db --symbol 600519.SH
PYTHONPATH=src python3 -m ashare_evidence trace --database-url sqlite:///./data/validation.db --recommendation-id 1
PYTHONPATH=src uvicorn ashare_evidence.api:app --reload
```

## 当前边界

- 真实 `Tushare / 巨潮 / Qlib` 网络适配器还未接入，当前以 demo provider 验证 schema、血缘字段和 trace 逻辑
- 第 3 步会在此底座上继续补真实特征生产、滚动验证、融合打分和建议降级规则
