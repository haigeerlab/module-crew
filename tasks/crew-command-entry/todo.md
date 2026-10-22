# Todo: crew-command-entry

> 依据 `tasks/crew-command-entry/plan.md`。

- [x] Task 1：`bin/module-crew` 插件目录排最前（Spec 验收 6）——测试先红后绿（2edb48b）
- [x] Task 2：`launcher.py` 定位与转发（Spec 验收 2、3、4）——测试先红（模块不存在）后绿（3a0fbd0）
- [x] Task 3：prepare、coordinator up 写入启动脚本（Spec 验收 1）——测试先红后绿；「已是模块协调」时也写入，test_coordinator_switch 的一条旧断言跟着改（a275834）
- [x] Checkpoint 1（report）：启动脚本就位——相关测试通过
- [x] Task 4：Codex 三处改用固定入口（Spec 验收 5）——测试先红后绿；恢复说明（resume_kit）的 Codex 段与 status 的 Codex 规则核对也改用固定入口（c353980）
- [x] Task 5：README、全量测试、本机实测（Spec 验收 7）——634 个测试只失败 1 个（Codex 版 skill 断言还要「绝对路径」，改为「固定入口」后重跑通过，62d8382）；本机实测：临时仓库里的固定入口转给本机安装的 0.11.1，status 报「✅ module-crew 0.11.1」，脚本 755；Codex 沙箱实测未做（本机没有 Codex 模块会话）
- [ ] Checkpoint 2（gate）：最终验收
- [ ] 回告：完成情况发给总协调（local_d7434023）

## 外部审查意见

<!-- spec-guard: external-review declined -->
用户 2026-10-22 批准 Plan 时说「不用外部复核」。
