# A-Share Evidence Dashboard

A-Share Evidence Dashboard 是一个面向 A 股研究和模拟交易复盘的全栈数据看板。项目目标不是给出“买入建议”，而是把行情数据、候选池、因子规则、LLM 辅助研究、历史回放、模拟持仓和运营复盘放到同一个可审计系统里，让每个结论都能追溯到数据、规则和验证证据。

> Disclaimer: This project is for research, product, and engineering demonstration only. It is not financial advice, investment advice, or a trading recommendation system.

## Features

- Watchlist and stock workspace: 管理关注池，查看个股画像、K 线、财务指标、新闻和研究记录。
- Evidence-first recommendations: 将候选股票、因子依据、人工复核和模型输出拆开记录，避免把结论包装成不可解释黑盒。
- Short Pick Lab: 面向短线候选池的历史回放、分组对照、入场假设比较、稳定性分析和纸面跟踪。
- Simulation workspace: 支持模拟持仓、订单事件、T+1 可卖约束、涨跌停和整手数量等 A 股交易规则校验。
- Operations dashboard: 汇总刷新状态、数据质量、模型轨道、用户轨道和关键运行事件。
- LLM-assisted research: 支持 OpenAI-compatible / Anthropic-compatible 模型配置，并保留模型选择、故障切换和研究产物。
- Scheduled refresh: 支持盘后刷新、盘中对照任务、补跑保护和刷新状态反馈。

## Architecture

```text
Market data and research inputs
  -> FastAPI service
  -> SQLite data store
  -> signal engine / validation / simulation modules
  -> React dashboard
  -> research artifacts and release evidence
```

Key directories:

- `src/ashare_evidence/`: FastAPI API, signal engine, validation, research artifact, simulation, access, and scheduler logic.
- `frontend/`: Vite + React + TypeScript dashboard UI.
- `scripts/`: local backend/frontend startup, scheduled refresh, runtime publish, and verification scripts.
- `tests/`: Python regression tests for API contracts, signal logic, simulation, scheduler behavior, and frontend static checks.
- `docs/contracts/`: active research, rollout, and metric contracts.
- `docs/archive/`: historical audits and research notes.

## Tech Stack

- Backend: Python 3.10+, FastAPI, SQLAlchemy, Pydantic
- Frontend: React 18, TypeScript, Vite, Ant Design, ECharts
- Data: SQLite for local persistence, AKShare and Tushare-compatible market data paths
- Research and automation: deterministic factor studies, replay artifacts, LLM-assisted manual research, scheduled refresh scripts
- Testing: pytest, TypeScript build checks, release verifier scripts

## Quick Start

Create a Python environment and install the backend package:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

Start the backend:

```bash
mkdir -p data
export ASHARE_DATABASE_URL="sqlite:///$(pwd)/data/ashare_dashboard.db"
PYTHONPATH=src uvicorn ashare_evidence.api:app --reload --host 127.0.0.1 --port 8000
```

Start the frontend in another terminal:

```bash
cd frontend
npm install
export VITE_API_BASE_URL=http://127.0.0.1:8000
npm run dev
```

The local frontend defaults to Vite's development server. The backend exposes `/health` for a basic readiness check.

## Configuration

Common environment variables:

- `ASHARE_DATABASE_URL`: SQLAlchemy database URL; defaults to a local SQLite database in startup scripts.
- `ASHARE_ARTIFACT_ROOT`: output root for research and replay artifacts.
- `OPENAI_API_KEY`, `OPENAI_BASE_URL`, `OPENAI_MODEL`: optional OpenAI-compatible model settings.
- `ANTHROPIC_AUTH_TOKEN`, `ANTHROPIC_BASE_URL`: optional Anthropic-compatible model settings.
- `VITE_API_BASE_URL`: frontend API base URL for local development.

Market data credentials can also be managed through the application settings flow where supported. Do not commit API keys, account credentials, or runtime databases.

## Validation

Backend tests:

```bash
PYTHONPATH=src pytest
```

Frontend build:

```bash
cd frontend
npm run build
```

For release-style local verification, use the scripts under `scripts/`. They are intentionally stricter than development startup commands because they check build output, service health, and selected user-visible routes.

## Project Notes

The project is intentionally conservative about claims. Historical replay, paper tracking, and simulation artifacts are treated as evidence for product and engineering decisions, not as proof of real-market profitability. Strategy lines that do not pass account eligibility, data quality, forward-window, or sample-size checks remain research candidates rather than production recommendations.

Useful internal documents:

- `PROJECT_STATUS.json`: current phase, blockers, and handoff state
- `PROJECT_RULES.md`: repository constraints and live verification rules
- `DECISIONS.md`: durable research and product decisions
- `PROCESS.md`: reusable lessons and anti-regression notes
- `PROJECT_PLAN.md`: long-lived roadmap and phase summary
