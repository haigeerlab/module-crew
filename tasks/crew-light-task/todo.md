# Todo: crew-light-task

> 依据 `tasks/crew-light-task/plan.md`。

- [x] Task 1：契约钉到 v2.5（Spec 验收 1）——v2.5 样例 110 个解析全过（先红后绿），v2.2～v2.4 照旧
- [x] Task 2：`task` 登记角色、名额只数模块、钩子认任务 worktree——测试先红后绿
- [x] Task 3：`task dispatch` 与开工说明；`bind` 后 `working`（Spec 验收 2、3）——测试先红后绿
- [x] Checkpoint 1（report）：契约与派出就位——任务、钩子、路由、权限、开工、模块协调开关相关测试全过
- [x] Task 4：交回记账、比对、提请批准与 hub 分流（Spec 验收 4、7）——测试先红后绿
- [x] Task 5：合并队列与任务合并、收回（Spec 验收 5、8）——测试先红后绿；顺带修了会话唯一性规则把两个轻任务会话当成同一模块的问题，派出登记失败时收回刚建的 worktree
- [x] Task 6：升格请求与答复、`task scope`（Spec 验收 6）——测试先红后绿
- [x] Checkpoint 2（report）：整条轻流程的单元测试通过——全量 579 个测试首轮 2 处失败：Task 6 给 Reply 加 notes 字段后，merge.Revoked 按位置构造把 superseded_by 错放，已改为关键字（775c7e7），相关测试重跑全过
- [x] Task 7：端到端测试（Spec 验收 9）——命令行走完整条轻流程，一次通过（它验证的是前面各步的组合）
- [x] Task 8：skill、README、全量测试（Spec 验收 9）——全量 580 个测试通过（含旧称扫描）；README 加「轻任务」一节与「下一版（未发版）」，契约版本改为 v2.5；CHANGELOG 随发版时从 README 移入
- [ ] Checkpoint 3（gate）：最终验收
- [ ] 回告：总协调；契约负责人（v2.5 已钉住）

## 外部审查意见

<!-- spec-guard: external-review declined -->
用户 2026-10-22 批准 Plan 时说「不用外部复核」。
