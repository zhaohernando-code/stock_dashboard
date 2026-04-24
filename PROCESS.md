# PROCESS

## 2026-04-24

- Problem: although the dashboard was already exposed through the server-side `/projects/ashare-dashboard` route, the long-running frontend and backend still started from the editable repo checkout, so unfinished local edits could leak into the live route and there was no repo-level deploy profile to standardize local publish steps.
- Resolution: the project now declares a `local_runtime_service` deploy profile, documents `~/codex/runtime/projects/ashare-dashboard` as the live runtime tree, and the local publish path is defined as “sync runtime -> restart local frontend/backend -> verify local health checks”.
- Prevention: any tunnel-exposed local project must keep development and runtime paths separate and version its machine-readable deploy profile alongside the code.
- Commit ID: pending

## 2026-04-23

- Problem: 项目已经迁移到“服务器入口 + 本机后端/数据库 + 反向隧道”模式后，活跃文档里仍残留 GitHub Pages、在线 API/离线快照双模式和用户手工配置后端地址等旧假设，容易把后续实现再带回静态站思路。
- Resolution: 当前 README、计划和规则已统一改为服务端主路径：公网入口走 `/projects/ashare-dashboard/`，本机负责后端、数据库和本地前端预览，离线快照仅作为历史兼容能力保留。
- Prevention: 一旦项目部署形态已经确定，活跃文档和默认 UI 路径必须同步收口；历史兼容能力不能继续占据主叙述。
- Commit ID: pending

- Problem: 如果前端先展示数据源、模型或配置状态，而后端适配器和真实发布链路还没打通，用户会被误导成“只差配置”，实际却是能力根本不存在。
- Resolution: 项目继续坚持“后端契约先行、前端状态后出”的规则，所有运行时状态都以真实后端适配与发布路径为准。
- Prevention: 任何待配置/已接入/可用类状态都必须以真实后端适配器和线上路径为前提，不能用前端占位替代实现。
- Commit ID: pending

- Problem: 动态项目一旦继续依赖浏览器端历史 `API Base` 覆盖值或演示模板主数据，就会在真实隧道路由和真实证券代码场景下产生错误请求与错误展示。
- Resolution: 当前主路径优先使用服务器挂载路由和真实主数据解析链，历史覆盖值与演示数据只保留为调试或兼容兜底。
- Prevention: 动态项目对外运行时必须优先相信当前挂载路由和真实主数据，不要让历史调试值或演示模板覆盖线上事实。
- Commit ID: pending
