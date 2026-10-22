# Todo: crew-task-ledger

> 依据 `tasks/crew-task-ledger/plan.md`。

- [x] Task 1：`task` 记录、校验、编号与 T 前缀（Spec 验收 1、9）——测试先红后绿
- [x] Task 2：重叠判断（Spec 验收 2、3）——测试先红后绿
- [x] Task 3：状态转换、`task next`、`task cancel`（Spec 验收 4、5、6）——测试先红后绿；排查时发现任务没进统一编号（每条都是同一个号），已修并补回归测试（改前红）
- [x] Checkpoint 1（report）：记账与排队就位——任务、状态库、编号相关测试全过
- [x] Task 4：命令行与 `--json`；接管后任务不变（Spec 验收 8）——测试先红后绿
- [x] Task 5：`status` 任务段（Spec 验收 7）——测试先红后绿
- [x] Task 6：skill、README、全量测试（Spec 验收 10）——全量 557 个测试通过（含旧称扫描）；版本号不变（随第六版发）
- [x] Checkpoint 2（gate）：最终验收——用户 2026-10-22 批准；不算 spec/tasks 8 个文件 +630 −6（258603f..be0af70）
- [x] 回告：完成情况发给总协调（local_d7434023）——2026-10-22 与 0.10.0 发版预告一起发

## 外部审查意见

<!-- spec-guard: external-review declined -->
用户 2026-10-22 批准 Plan 时说「不用外部复核」。
