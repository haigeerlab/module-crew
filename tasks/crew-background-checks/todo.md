# Todo: crew-background-checks

> 依据 `tasks/crew-background-checks/plan.md`。

- [x] Task 1：`mergelock` 拿锁、放锁、读锁、失效判断（Spec 验收 1、3）——测试先红后绿
- [x] Task 2：`merge run` 拿放锁（Spec 验收 1、2）——测试先红后绿（「各种结束都放锁」那一条改前就通过，因为改前没有锁；改后照样通过）
- [x] Task 3：其余写命令查锁（Spec 验收 2、3）——在命令分派处统一查；测试先红后绿
- [x] Checkpoint 1（report）：锁就位
- [x] Task 4：`status` 一行（Spec 验收 4）——测试先红后绿
- [x] Task 5：skill、README、全量测试（Spec 验收 5、6）——全量测试先后查出两处真问题：静态检查不许删除调用（锁改用 flock、运行记录原子替换，Spec 决策 1、2 修订），合并前清单不过时锁文件已建（改为清单通过后才拿锁、查锁不建文件）；最后一轮 613 个测试只剩钩子计时一项超 1 秒，同时刻 v0.9.6／v0.10.2／当前钩子耗时一样（180～430 ms，负载均值 40～50），判定为机器负载，计时门槛没改
- [x] Checkpoint 2（gate）：最终验收——用户 2026-10-22 批准（含构建中修订的 Spec：flock 锁）；不算 spec/tasks 7 个文件 +386 −3（80ecd6b..9dad9d6）
- [x] 回告：完成情况发给总协调（local_d7434023）——2026-10-22 已发会话消息

## 外部审查意见

<!-- spec-guard: external-review declined -->
用户 2026-10-22 批准 Plan 时说「不用外部复核」。
