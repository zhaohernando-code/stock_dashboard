# Trial BP 评估记录：CLI Attempt Route Test Split

状态：verified
输入：`TRIAL_BP_CONTEXT_PACK_CN.md`
目标：评估 BM CLI 测试文件是否完成结构性减压，并满足 warning margin。

## 1. 子任务

| 子进程 | owned files | 目标 | 状态 |
| --- | --- | --- | --- |
| BP1 | attempt-route CLI 测试拆分、本评估文件 | 降低临界测试文件行数并保持语义 | passed |

## 2. 评分

| 维度 | 权重 |
| --- | ---: |
| 测试语义保持 | 35 |
| 文件规模减压 | 30 |
| margin 门禁 | 20 |
| 验证完整性 | 15 |

自动重跑阈值：

- 修改生产代码。
- 删除关键断言导致行为覆盖下降。
- 主测试文件未满足 warning margin。
- 修改旧 action-route-auto-apply 输出测试。
- focused tests、ruff、process hardening、registry 或 full regression 失败。

## 3. BP1 结果

- 新增 `tests/helpers_cli_autonomous_flow_attempt_route.py`，承接 attempt-route 输出测试专用的 `_FakeResult`、`_result`、`_apply_result`、`_files_under`。
- `tests/test_cli_autonomous_flow_attempt_route_auto_apply_output.py` 仅保留流程与阻断语义断言；handler 顺序、参数透传、缺上下文不写 artifact、旧 bind/apply 不进入的覆盖保持不变。
- 未修改生产代码，未修改 `tests/test_cli_autonomous_flow_action_route_auto_apply_output.py`。
- 行数结果：attempt-route 测试 138 行，helper 45 行，action-route 测试 177 行，本评估 47 行；attempt-route warning margin 为 42 行。

## 4. 主进程验证

主进程复核隔离 worktree diff 后并入集成分支；BP1 本地验证与主进程 focused gates 均通过：

- Focused tests：BP1 `9 passed`；main `9 passed in 0.54s`。
- Ruff：passed。
- Process hardening：status=pass，issue_count=0；attempt-route 测试 138 行，warning 180，margin remaining 42。
- Registry：status=pass，issue_count=0。
- Full regression：main `522 passed, 147 deselected in 22.20s`。

主进程语义复核：

- 未修改生产代码。
- 未修改旧 action-route-auto-apply 输出测试。
- handler 顺序、参数透传、缺上下文不写 artifact、旧 bind/apply 不进入等关键断言保留。

## 5. 重跑记录

- focused tests：9 passed。
- ruff：All checks passed。
- process hardening：pass，attempt-route warning margin 剩余 42 行。
- registry：pass，issue_count 0。
- full regression：BP1 `522 passed, 147 deselected`；main `522 passed, 147 deselected in 22.20s`。

## 6. 自评

通过 helper 拆分降低临界测试文件增长风险，没有改变被测 CLI 路由语义；后续新增 attempt-route CLI 测试应复用 helper 或新增文件，不能再让主测试文件接近 warning。
