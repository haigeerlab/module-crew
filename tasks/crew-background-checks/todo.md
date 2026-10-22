# Todo: crew-background-checks

> 依据 `tasks/crew-background-checks/plan.md`。

- [x] Task 1：`mergelock` 拿锁、放锁、读锁、失效判断（Spec 验收 1、3）——测试先红后绿
- [x] Task 2：`merge run` 拿放锁（Spec 验收 1、2）——测试先红后绿（「各种结束都放锁」那一条改前就通过，因为改前没有锁；改后照样通过）
- [x] Task 3：其余写命令查锁（Spec 验收 2、3）——在命令分派处统一查；测试先红后绿
- [x] Checkpoint 1（report）：锁就位
- [x] Task 4：`status` 一行（Spec 验收 4）——测试先红后绿
- [ ] Task 5：skill、README、全量测试（Spec 验收 5、6）
- [ ] Checkpoint 2（gate）：最终验收
- [ ] 回告：完成情况发给总协调（local_d7434023）

## 外部审查意见

<!-- spec-guard: external-review declined -->
用户 2026-10-22 批准 Plan 时说「不用外部复核」。
