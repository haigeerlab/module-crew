# Todo: crew-stage-c-fixes

> 依据 `tasks/crew-stage-c-fixes/plan.md`。

- [x] Task 1：MC-10 同步通知跳过已交最终验收的模块（Spec 验收 1）——提交 8f48d1b
- [x] Task 2：MC-11 新合并批准取代旧批准（Spec 验收 2、3）——提交 09e4865
- [x] Task 3：MC-13 模块 worktree 内编辑放行（Spec 验收 4）——提交 be0680c
- [x] Checkpoint 1（report）：三处修复就位，全量测试通过（2026-10-20，456 个测试全过）
- [x] Task 4：MC-9 契约 v2.4 与「模块」字段（Spec 验收 7）——提交 74bb6e7；v2.2／v2.3／v2.4 样例 97／101／104 份全过；0.6.0 回归夹具不动，去掉「模块：」一行后逐字一致
- [x] Task 5：三份 skill（Spec 验收 6、7）——提交 0a66f44
- [x] Task 6：README、版本 0.8.0、全量测试（Spec 验收 8）——提交 31a0a00；全量 457 个测试通过（含旧称扫描）
- [x] Checkpoint 2（gate）：实地验证前停下问用户——用户 2026-10-20 同意做实地验证，并按推荐加做对照
- [x] Task 7：实地验证（Spec 验收 5）——2026-10-20 在 scratchpad 的 crew-rehearsal 临时副本里做（不碰原仓库）。会话「实地验证：模块会话在 worktree 内写文件」（default 模式，0.8.0 规则）：Write、Edit worktree 内文件直接执行，权限来源 `user_permanent`；Edit `.claude/settings.local.json` 被拒（「File is in a directory that is denied by your permission settings」），文件未改——**禁止规则有效**。对照会话「对照验证：没有编辑放行规则时写文件」（同样 default 模式，去掉所有 Edit 规则）：Write 同样直接执行、来源同样 `user_permanent`——**放行规则在本机宿主看不出效果**（不写也不弹），演练 #39 的弹窗另有原因、现有记录查不出，记为「放行部分宿主未证实有效」；规则无害，保留
- [x] Checkpoint 3（gate）：最终验收——用户 2026-10-20 批准；契约样例外 24 个文件 +393 −28，另钉 v2.4 契约样例 212 个文件（b0617fe..14926ff）；验收 5 只证实禁止部分
- [x] 回告：清单抄送接入协调（local_4f410de8），告诉契约负责人（local_a9d06942）已按 v2.4 写「模块」——2026-10-20 已发会话消息；MC-13 放行部分请阶段丙-2 观察
