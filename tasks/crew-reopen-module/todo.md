# Todo: crew-reopen-module

> 依据 `tasks/crew-reopen-module/plan.md`。

- [x] Task 1：状态库认 `reopen` 与 `reopened`，加 `round_since`——测试先红后绿；状态库没有事项字段的校验器，`reopened` 不另加校验（与 `modules` 等字段一致），只校验会话的 `reopen`
- [x] Task 2：`prepare` 校验——可重开判据、旧会话未收回、旧分支非祖先或已检出时退出码 3 且什么都不写（Spec 验收 2 拒绝部分、3）——与 Task 3 一起实现后补测试，换回改前 `start.py` 确认新测试全红（12 失败 1 错误）再还原；重开计划挂在 `Proposal.reopen` 上，`validate` 仍返回三元组（`test_failure` 照用）
- [x] Task 3：`prepare` 落地——快进或新切、worktree、`-r<轮次>` 登记、开工批准事项 `reopened`、输出与 `--json`（Spec 验收 1、2、4、8）——`--json` 原样带出 prepared 的键，未改 `__main__.py`；test_start_prepare、test_start_plan、test_failure 照常通过
- [x] Task 4：开工说明「重开修订」一段与三种 `review` 写法（Spec 验收 5）——测试先红后绿；没有旧分支时写「旧的模块分支不在了，已从集成分支新切」；不重开时开工说明逐字不变（test_start_prepare 通过）
- [x] Task 5：`start plan` 不提议、原因写「已重开…要用户点名」（Spec 验收 7）——测试先红后绿；`_why_not` 多一个可选参数 `db` 用来算轮次
- [x] Checkpoint 1（report）：重开能开出来，开工说明与 plan 输出对——test_reopen_module 与 start_plan、start_prepare、failure、light_task、store_session 共 91 个测试通过
- [x] Task 6：只看本轮——start、hooks、merge、review、stall 按模块查的地方只算本轮（Spec 验收 6 单元部分）——测试先红后绿；`store` 加 `reopen_of`、`round_items`；改了 `start._merged_modules`、`hooks._stage`（多一个可选参数 `sessions`）、`merge.no_sync`／`tick`／`_cleanup`、`review._approved_nodes`／`_rounds`、`stall.returns`（多一个可选参数 `sessions`）。`review._approved_nodes` 不改会让重开模块 Plan 重新批准后发不出开工通知（旧一轮的批准算在 approved_before 里）。另改了并行边界外的 `module_crew/failure.py` 两处调用（传 `sessions` 给 `_stage` 与 `returns`，没人在改它），最终验收的越界检查里报。`review._previous_commit`／`_last_changes` 没改：它们给交审正文找上一版做对比，跨轮拿到上一轮批准的版本正合用。受影响模块 213 个测试通过
- [x] Task 7：端到端——重开 → bind → 交审 → 批准 → merge run → merge cleanup（Spec 验收 6）——`EndToEndTest`：第一轮 b 合入并收回后重开，`-r2` 的 worktree 在集成分支顶端、`hooks.bind` 成功、阶段依次为构建、最终验收已交审、等合并、已合入，本轮合入前 `merge cleanup` 拒绝、合入后收回并退役 `shop-b-r2`；没有新增漏网的地方。换回 Task 6 之前的代码时它报错（`_stage` 不收 `sessions`），不是在断言上失败；只看本轮的先红由 Task 6 的单元测试证明
- [ ] Checkpoint 2（report）：命令层做完，全量测试通过
- [x] Task 8：skill 两份「开工」、crew-dev、README（Spec 验收 9）——断言先红后绿（写在 test_reopen_module 的 `DocsTest`）；两份协调 skill「开工」加第 6 步、crew-dev「交审节奏」加「重开修订」一条、README 加「修订已完成的模块（第九版）」一节；test_skills 照常通过。Codex 版 `codex-skills/crew-dev` 不在并行边界里，没改（重开的做法已写在开工说明里），作为后续建议报
- [ ] Task 9：`module-crew sync` 后全量测试（Spec 验收 10）
- [ ] Checkpoint 3（gate）：最终验收
- [ ] 回告：ecosystem-lead（S18 的 module-crew 一侧已就位），经 mc-coord 转
