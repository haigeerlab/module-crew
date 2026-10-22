# Todo: crew-unqueued-commits

> 依据 `tasks/crew-unqueued-commits/plan.md`。

- [x] Task 1：认得点的设定与更新（Spec 验收 1）——测试先红后绿
- [x] Task 2：`unqueued` 只读列出（Spec 验收 2、6）——与 Task 3 同一次提交；这两项的实现先于运行测试写成（测试先写好，但没先跑看红），补跑全过
- [x] Task 3：`unqueued --notify`（Spec 验收 3）——收件人规则抽成 merge.sync_targets，合并相关回归测试通过
- [x] Checkpoint 1（report）：发现与通知就位
- [x] Task 4：`merge run` 合并前检查（Spec 验收 4）——测试先红后绿
- [x] Task 5：`status` 一行（Spec 验收 5）——测试先红后绿
- [x] Task 6：skill、README、全量测试（Spec 验收 7）——全量 599 个测试首轮 3 处失败：认得点事件的 data 用了 `source` 键，和批准来源字段撞名（改为 `by`）；两处钩子／导出计时超 1 秒，当时负载均值 26～38，单独重跑通过；补跑相关测试全过
- [ ] Checkpoint 2（gate）：最终验收
- [ ] 回告：完成情况发给总协调（local_d7434023）

## 外部审查意见

<!-- spec-guard: external-review declined -->
用户 2026-10-22 批准 Plan 时说「不用外部复核」。
