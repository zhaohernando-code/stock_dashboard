# Trial AL 评估记录：CLI Output Tests Split

状态：completed, main verification passed  
输入：`TRIAL_AL_CONTEXT_PACK_CN.md`  
目标：评估 CLI output 测试拆分是否消除文件规模 warning 且保持行为覆盖。

## 1. 子任务

| 子进程 | owned files | 目标 |
| --- | --- | --- |
| AL1 | CLI output tests、本评估文件 | 拆分 plan、dry-run、full output 测试 |

## 2. 评分

| 维度 | 权重 |
| --- | ---: |
| 行为覆盖保持 | 40 |
| 文件规模治理 | 35 |
| 测试与门禁 | 25 |

自动重跑阈值：

- 拆分后丢失任一既有场景。
- 任一新测试文件超过 hard limit。
- 原 output 测试文件仍处于 warning 区间。
- focused tests、ruff、process hardening、registry 或 full regression 失败。

## 3. AL1 结果

- 仅拆分测试结构，未修改生产代码。
- 原 `tests/test_cli_autonomous_flow_outputs.py` 降为 4 行，作为兼容锚点保留。
- 新增 plan、dry-run、full 三个主题测试文件，分别承载拆分前全部 7 个场景。
- 文件规模结果：plan 125 行，dry-run 116 行，full 79 行，均低于 Context Pack hard limit。

## 4. 主进程验证

- focused pytest：7 passed。
- ruff：passed。
- process hardening：passed，4 个测试文件均低于 warning limit。
- contract registry：passed，AL Context Pack 与本评估文档无未注册合约引用。
- diff check：passed。
- full regression：405 passed，147 deselected。

## 5. 重跑记录

暂无重跑。首次拆分后 focused pytest 与文件规模检查通过。

## 6. 自评

拆分符合本轮边界：行为断言保持不变，主题归属更清晰，后续 output 行为变更可以落在对应测试文件中，避免单文件再次堆叠。残余风险是本轮只做结构迁移，未增加新的语义覆盖；这符合 Context Pack 的“不改生产行为、不新增 CLI output”约束。
