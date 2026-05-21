# Trial CT Context Pack：平台宿主边界回滚与流程固化

目标：停止把自动化中台/平台本体能力继续落入 `stock_dashboard`，回滚已进入本项目的 workbench projection/API/UI，并把宿主边界固化成后续流程门禁。

## 1. 宿主判定

- 当前仓库：`stock_dashboard`
- 判定结果：`managed_project`
- 允许角色：A 股看板业务项目、平台流程试验 fixture、明确的集成适配对象
- 禁止角色：自动化平台本体、跨项目工作台宿主、平台 scheduler 编排宿主、LLM reviewer/CI/CD gate 宿主

## 2. 非目标

- 不继续实现平台工作台 projection manifest。
- 不新增平台级 API、前端总览、任务编排状态机或跨项目治理 UI。
- 不把“流程试验田”的输出包装成股票看板产品能力。

## 3. 必做动作

- 非破坏性 revert 已进入本项目 runtime/product surface 的平台工作台代码。
- 更新 `PROJECT_RULES.md`、`PROCESS.md`、`DECISIONS.md`、`PROJECT_PLAN.md` 和 `PROJECT_STATUS.json`，让边界可恢复、可审计。
- 修正 Trial CN 的后续建议，明确 Trial CO 只能在平台宿主继续。
- 运行回归和边界检索，确认已撤回的 workbench projection/API/UI 不再存在于代码面。

## 4. 失败面

- 若 `stock_dashboard` 源码仍包含平台 workbench 组件名、平台 workbench 路由、平台 workbench artifact 前缀或平台 workbench CLI 动作名，本轮失败。
- 若文档仍建议在本仓库继续 Trial CO 平台工作台实现，本轮失败。
- 若回归测试或前端构建失败，本轮失败。
