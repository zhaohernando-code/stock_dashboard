# 一个关于a股的当前数据和投资建议看板 Rules

- Follow the global conventions from `~/codex/CODEX.md`.
- Keep the project GitHub-ready and record important changes in `PROCESS.md` with commit IDs.
- Preserve interoperability with other projects under `~/codex`.
- If the project includes a UI, implement it as a TypeScript + React app with a formal framework/toolchain by default.
- The live deployment model is server entrypoint plus local backend/database/tunnel; do not reintroduce GitHub Pages or browser-side backend configuration as the primary path.
- The editable repo under `~/codex/projects/stock_dashboard` is not the live runtime. Public service must run from `~/codex/runtime/projects/ashare-dashboard`, and `.codex.deploy.json` plus LaunchAgent paths must stay aligned with that runtime split.
- 本项目 UI 风格参考 `VoltAgent/awesome-design-md` 中接近 `Coinbase` 的金融产品规约：强调可信、克制、数据密度与清晰层级；在实现上使用浅色底、蓝绿信号色、强对比标题和证据卡片，而不是通用后台模板。
- 任何数据源、配置入口、状态标签或“待配置/已接入”提示，只有在对应后端适配器、验证链路和真实发布路径都已落地后才能出现在前端；禁止前端先行占位制造“只差用户配置”的假象。
