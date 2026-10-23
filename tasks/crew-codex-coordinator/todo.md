# Todo: crew-codex-coordinator

> 依据 `tasks/crew-codex-coordinator/plan.md`。

- [x] Task 1：`status` 在 Codex 里认出／否认模块协调与 `codexSelf`（Spec 验收 7）——测试先红后绿；模块协调在 Codex 时末尾的宿主行改为「模块协调：Codex 桌面版；模块会话：Codex 桌面版」，Claude 时逐字不变
- [x] Task 2：`host-check` 按模块协调查与 `role`（Spec 验收 6）——测试先红后绿；集成 checkout 里改按模块协调查（检查项 store、registered、version、git-writable、spec-guard、entry），`test_codex_host` 里「集成 checkout 不通过」那条按新行为改为用未登记的 worktree 断言
- [x] Task 3：沙箱拒绝与找不到插件的补句（Spec 验收 8）——测试先红后绿；只在 Codex 里加补句（Claude 上原样报错）；`index.lock` 只认 Permission denied，File exists 是另一个 git 进程、不是沙箱，不加提示
- [x] Task 4：模块协调在 Codex 时各协调命令照常可用（Spec 验收 3）——写命令守门认 Codex 线程（登记的放行、别的线程退出码 7 且不写），review add → merge approve → merge run → merge cleanup、start prepare、coordinator down 从 Codex 线程跑通；现有代码已支持，未改代码，测试作为回归保留
- [x] Checkpoint 1（report）：Codex 协调认得出自己、查得出障碍——test_codex_coordinator 与 session_handover、host_handover、codex_host、background_checks 共 97 个测试通过
- [x] Task 5：拆 `merge.run`，加 `merge run --detach`（Spec 验收 4 启动、锁、被杀部分）——测试先红后绿；没有整段拆函数，改为 `_run` 在拿到锁后按 `detach` 交给子进程（`pass_fds` 交锁、新会话、输出进 `merge-output/C号.log`），子进程以 `--detached-child` 接管同一把锁再跑一遍，前台路径不变（合并相关已有测试全过）；结果在全部输出刷盘后才写回；交给后台记在批准事项上（事件 `item.merge-detached`，Spec 写的 `merge.detached` 不符合「种类.动作」，随最终验收报）
- [x] Task 6：`merge result` 与 `status` 的结果提示（Spec 验收 4 结果部分、5）——测试先红后绿；成功、检查失败退回、冲突三种情况下后台结果的正文（换掉临时路径与提交号后）与退出码和前台 `merge run` 逐字一致；`--wait` 以分钟计、每 5 秒看一次、上限 8；读结果记在批准事项上（事件 `item.merge-result-read`）；给的 C 号不是最近一次后台合并时退出码 3 并给出日志路径（不从日志末行猜退出码，比 Plan 风险一节说的简单）
- [x] Task 7：开工输出的 Codex 指引与交接说明补句（Spec 验收 9、2 说明部分）——测试先红后绿；模块协调在 Codex 时 `start prepare`、`task dispatch` 末尾加「请用户去 Codex 新建任务」段（逐模块／T 号一行），`task dispatch` 同时不再打印「用桌面版开新会话」那句；交接说明 Codex 方向开场文字加 `host-check` 一步与「每轮开头三步」；协调在 Claude 时输出不变（开工、轻任务、换宿主已有测试通过）
- [x] Checkpoint 2（report）：命令层做完，全量测试通过——Task 7 提交（fc013a1）后全量 774 个测试通过
- [x] Task 8：Codex 版 crew-coordinator skill（Spec 验收 1）——由 Claude 版逐节改写（各节同名同序，另加「Codex 特有的几件事（先读）」），`test_skills` 断言共同关键句 27 条、Codex 特有 16 条、不含 Claude 专属做法；skill 先写、断言后补（文档类，没有先红）
- [x] Task 9：`handover --to codex` 端到端（Spec 验收 2）——不打桩，用插件里真实的 Codex 版 skill：Claude 协调 `handover --to codex` → Codex 线程 `bind --takeover` → `status` 首行认出、`host-check` 按协调查 → 从 Codex 线程 `handover --to claude` → 新 Claude 会话接管，全部经命令行跑通（Task 8 之前这条会因缺 skill 退出码 3）；`--to claude` 与已有换宿主测试照常通过
- [x] Task 10：README、plugin.json、Claude 版 skill、全量测试（Spec 验收 10、11）——README「换宿主」加「模块协调在 Codex 上」一小节、命令一览补 `merge run --detach`／`merge result` 与 `host-check`、「尚未验证」补 Codex 协调未实测；插件描述与 Claude 版「空档换宿主」不再写等待模块 B；同步集成分支 64ae2c6 后全量 783 个测试通过（3212666）
- [x] Checkpoint 3（gate）：最终验收
- [ ] 回告：ecosystem-lead（模块 B 就位、`--to codex` 已放开、实地结果），经 mc-coord 转
