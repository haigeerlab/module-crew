# Todo: crew-session-handover

> 依据 `tasks/crew-session-handover/plan.md`。

- [x] Task 1：钩子按会话编号认身份（Spec 验收 1）——测试先红后绿；test_coordinator_switch 里断言「别处的登记会话什么都听不到」的旧测试按 Spec 改为新预期（767f0cb）
- [x] Task 2：`bind --takeover` 一步接管（Spec 验收 2）——测试先红后绿（9e57896）
- [x] Task 3：旧会话失效提示（Spec 验收 3）——测试先红后绿（ad41868）
- [x] Checkpoint 1（report）：身份与接管就位——相关测试通过
- [x] Task 4：写命令会话守门（Spec 验收 4）——先写实现后补测试，撤掉实现确认测试会红、恢复后绿；带会话编号的四个测试文件 101 个测试通过（bfc2e46）
- [x] Task 5：status 标出本会话（Spec 验收 5）——测试先红后绿（15b21bd）
- [x] Task 6：README、skill、全量测试与钩子耗时（Spec 验收 6、7）——全量测试全部通过（负载 40～54）；钩子 session-start 143 ms、prompt 138 ms，与改前同一量级（885c7c4）
- [x] Checkpoint 2（gate）：最终验收——用户 2026-10-22 批准；不算 spec/tasks 8 个文件 +319 −12（767f0cb..885c7c4），构建中 Spec 未修订
- [x] 回告：总协调（local_d7434023）与 spec-guard 负责人（local_0a689563）——2026-10-22 已发会话消息

## 外部审查意见

<!-- spec-guard: external-review declined -->
用户 2026-10-22 批准 Plan 时说「不用外部复核」。
