# Todo: crew-check-ledger

> 依据 `tasks/crew-check-ledger/plan.md`。

- [x] Task 1：检查账打底——记录种类、读写与开关、`config set` 两个新参数（Spec 验收 2）——测试先红（没有 checks 模块）后绿
- [x] Task 2：`check quick`、`check show`、`check list`（Spec 验收 3、4、12）——测试先红（没有 check 子命令）后绿；`check baseline` 先占位退出码 3，Task 5 实现
- [x] Task 3：`merge run` 记账与继承记录（Spec 验收 5）——测试先红后绿；merge.py 只改 `_run_check`（加 db 参数记账）与 `_run`（合入通过后调 `checks.inherit`）
- [x] Checkpoint 1（report）：检查账与快检查就位——本模块 20 个测试与合并、后台检查、轻任务等 76 个回归测试通过
- [x] Task 4：六处通知措辞跟着开关走（Spec 验收 6、1）——测试先红（开关开时六处仍写完整检查）后绿；关着时原文不变，128 个回归测试通过
- [x] Task 5：`check baseline`、锁互挡、修基线任务、基线红提示（Spec 验收 7、8、9）——测试先红后绿；合并锁的描述在基线检查时写「基线检查（集成分支 <短哈希>）」，合并的原措辞不变
- [x] Task 6：`change land` 提交前快检查（Spec 验收 10）——测试先红后绿；取暂存区的树（`git write-tree`）跑快检查，跳过要原话并记进请求的 `quickCheckSkipped`
- [x] Task 7：最终验收附检查账（Spec 验收 11）——测试先红后绿；模块与轻任务的交审事项记 `checks`，`review show`／`review batch` 多一行「检查账」，查不到只提醒
- [x] Task 8：`status` 的检查账（Spec 验收 12）——测试先红后绿；开关关着时 `checks` 为 null、文本不变
- [x] Checkpoint 2（report）：命令与记账全部就位——本模块 40 个测试与各任务的回归测试通过，全量测试在 Task 9 跑
- [ ] Task 9：skill、README、`module-crew sync` 后全量测试（Spec 验收 13、14、1）
- [ ] Checkpoint 3（gate）：最终验收
- [ ] 回告：完成情况经模块协调转告 ecosystem-lead
