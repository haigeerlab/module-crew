# Todo: crew-routing-fixes

> 依据 `tasks/crew-routing-fixes/plan.md`。

- [x] Checkpoint 0（gate）：实测前停下问用户——用户 2026-10-20 同意做实测
- [x] Task 1：实测会话 id 稳定性（Spec 验收 6）——2026-10-20 已测：启动、续聊、`claude --resume` 接上、`/compact`、压缩后再接上，payload `session_id` 始终 37c02350…不变；`CLAUDE_CODE_HOST_SESSION_ID` 从父进程继承（接上的进程读到的是起它的会话的 id），不可用。桌面版整个应用退出重开未测（会关掉本会话），记「宿主未验证」。Spec 已随之修订，用户 2026-10-20 复审批准
- [x] Task 2：审查者负责范围（Spec 验收 1、2）
- [x] Task 3：同步基线跳过挂起模块、恢复时补写（Spec 验收 3）
- [x] Checkpoint 1（report）：两处收件收窄就位，全量测试通过（2026-10-20，466 个测试全过）
- [x] Task 4：身份登记与 bind（Spec 验收 5）
- [x] Task 5：钩子按会话核对（Spec 验收 4）
- [x] Task 6：skill、README、版本 0.9.0、全量测试（Spec 验收 7）——全量 475 个测试通过（含旧称扫描）
- [x] Checkpoint 2（gate）：最终验收——用户 2026-10-20 批准（含构建中补改 interface 节点的 Spec）；不算 spec/tasks 27 个文件 +497 −44（baa634c..e7d83f5）；整个桌面版退出重开未验证
- [x] 回告：完成情况发给总协调（local_d7434023）——2026-10-20 已发会话消息（三条修复要点、0.9.0、升级时要 bind 与补登记审查者范围）
- [x] Task 7（2026-10-21 追加，Spec 范围第 5 条，用户批准）：`review note` 只认收到这条交审的审查者（Spec 验收 8）；版本 0.9.2——复现测试 `NoteSenderTest`（4 个，改前全红），全量 484 个测试通过；未打标签、未升级本机
- [x] Task 8（2026-10-21 追加，评审第 8 条，Spec 范围第 6 条）：同步基线的跳过规则统一（Spec 验收 9）
- [x] Task 9（2026-10-21 追加，评审第 9 条，Spec 范围第 7 条）：`bind` 目录核对、模块协调身份要用户原话（Spec 验收 10、11）；版本 0.9.3——全量 488 个测试：首轮旧称扫描抓到 README 一处「评审」，改为「审查」后该组通过，其余 487 个首轮已过；未打标签、未升级本机
