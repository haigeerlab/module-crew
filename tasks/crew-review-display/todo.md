# Todo: crew-review-display

> 依据 `tasks/crew-review-display/plan.md`。

- [x] Task 1：并行边界重叠三种结论与 scopeOverlap（Spec 验收 6）——测试先红后绿；未比对时仍列集成分支上已知的重叠；test_merge_pilot 一条断言误报「无」的旧测试、test_review_add 一条跟着改（c3e5a58、a540d96）
- [x] Task 2：最终验收四张表（Spec 验收 1、2）——测试先红后绿；卡片不再把证据复制一份放最前（R17 的做法），改按 reviewKinds.final 顺序，test_review_nearby 一条旧断言跟着改（ae92d8c）
- [x] Checkpoint 1（report）：重叠与最终验收就位——相关测试通过
- [x] Task 3：三种请示模板（Spec 验收 3）——测试先红后绿（a9375e2）
- [x] Task 4：分节测试、skill、README（Spec 验收 4、5）——分节是现有行为，测试改前就通过（bf2dc1c）
- [x] Task 5：全量测试与旧称扫描（Spec 验收 7）——全量 694 个测试通过；本机实测：经 probe.safe_command 调本机 spec-guard 0.84.0（接口 1.10）的 scopeOverlap，传入当初漏检的两份 Spec，报出两个重叠路径，退出码 0
- [x] Checkpoint 2（gate）：最终验收——用户 2026-10-23 批准；不算 spec/tasks/docs 8 个文件 +575 −21（c3e5a58..a5926cb），构建中 Spec 未修订；第七版四个模块全部完成
- [x] 回告：总协调（local_d7434023）与 spec-guard 负责人（local_0a689563）——2026-10-23 已发会话消息

## 外部审查意见

<!-- spec-guard: external-review declined -->
用户 2026-10-23 批准 Plan 时说「不用外部复核」。
