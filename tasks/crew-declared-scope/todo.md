# Todo: crew-declared-scope

> 依据 `tasks/crew-declared-scope/plan.md`。

- [ ] Task 1：`declared.py`（`enabled`、`read`、`inside`）与 `config set --declared-scope`（Spec 验收 1；验收 3 的四种不可用在 `read` 层）
- [ ] Task 2：`module-crew scope` 子命令与开工说明「全局约束」一行（Spec 验收 3、4）
- [ ] Task 3：`change add` 分类——名单内、混合、冲突、不可用、开关关（Spec 验收 5）
- [ ] Task 4：`change land --from-module`——成功路径与四种拒绝（Spec 验收 6、7）
- [ ] Task 5：`change landed` 与 `--mark-told`（Spec 验收 8）
- [ ] Checkpoint 1（report）：公共变更这一路做完，test_declared_scope 与 test_changes、test_change_partial、test_change_supersede 通过
- [ ] Task 6：最终验收「声明内公共文件」一节、提前落地标注、未声明依赖、`display.declared`（Spec 验收 9）
- [ ] Task 7：有依赖关系的模块不同时开——`plan`、`prepare`、`_why_not`，含重开的上游、已合入不挡、同批互依赖（Spec 验收 10）
- [ ] Task 8：开关没设与 `off` 时各命令输出与改前逐字相同的集中对照（Spec 验收 2）
- [ ] Checkpoint 2（report）：命令层做完，全量测试通过
- [ ] Task 9：skill 四份与 README（Spec 验收 11）
- [ ] Task 10：本机 spec-guard 0.85.0 实测 `declaredScope`；`module-crew sync` 后全量测试（Spec 验收 12）
- [ ] Checkpoint 3（gate）：最终验收
- [ ] 回告：ecosystem-lead（S32 第二节 module-crew 第 1、2 条已就位），经 mc-coord 转
