# Todo: crew-codex-offload

> 依据 `tasks/crew-codex-offload/plan.md`。

- [x] Task 1：打底——`store.KINDS` 加 `offload`、开关 `codexOffload` 与 `config set --codex-offload`、`ready` 六项条件（Spec 验收 1、3）——测试先红（没有 offload 模块）后绿；本模块 17 个、状态库与配置回归 39 个通过；`problems` 逐条列出不满足的条件供打开开关时警告
- [x] Task 2：`offload start` 与任务说明、`parse_result`（Spec 验收 5、2）——测试先红（没有 Outcome、start）后绿；本模块 33 个通过；派出时任务说明写进状态库正文，输出文件放 `<状态库>/tmp/offload-<模块>-<号>.out`
- [x] Task 3：`settle` 的 done 分支：勾选核对、范围核对、暂存区快检查、代提交（Spec 验收 6）——测试先红（没有 settle）后绿；本模块 44 个通过；认不出的结束状态先统一走「停下问用户」，Task 4 补齐 needs-input、timeout
- [x] Checkpoint 1（report）：派出与 done 代提交就位——本模块 44 个与 review、checks、declared、approve 回归 170 个通过；sync 到 main 6878f41 后在快照上跑的全量基线 980 个通过
- [x] Task 4：`settle` 的 needs-input、timeout（1.1／1.2）、认不出与【等待用户】草稿（Spec 验收 7、8、9）——测试先红后绿；与 Task 5 同一提交 efbc63d
- [x] Task 5：`offload resume`、`offload start --again`（Spec 验收 7、8）——测试先红后绿；重派时工作区有遗留改动就沿用原 Task 与基线，任务说明多一句「先看懂上次留下的改动」
- [x] Task 6：开工通知分叉 `review._start_todo`、`offload decline`、`offload handback`（Spec 验收 4、10、2）——实现与测试同步写，没有先看到红；6 个测试通过；关着时开工通知逐字不变（`review.start_todo_today` 原文抽出），decline 记为 handed-back 并带用户原话
- [x] Task 7：`offload show` 与 `--json`（Spec 验收 11）——实现与测试同步写；2 个测试通过；只读，任何会话都能跑
- [x] Checkpoint 2（report）：命令全部就位——本模块 65 个与术语表测试通过；review、approve、start prepare、skill、文档相关回归 147 个通过
- [x] Task 8：四份 skill、README；`module-crew sync` 后后台跑全量测试；本机 delegate 0.6.0 实测一次（Spec 验收 12、13）——sync 已是最新（main 6878f41）；全量 1045 个在 68c660c 通过；delegate 0.6.0（接口 1.1）在临时仓库实测一次：退出码 0、结果行 status=done、Codex 只改两个文件未提交，真实输出喂给 settle 判为 done 并代提交；1.2 的 timeout 续跑只用夹具测过
- [x] Checkpoint 3（gate）：最终验收
- [x] 回告：完成情况经模块协调转告 ecosystem-lead——已经 mc-coord 回告（2026-10-27）

## 第 2 轮修订（2026-10-28 重开，见 plan.md「修订（第 2 轮）」）

- [x] 修订 Spec 交审：按 `docs/intent/codex-offload-native.md` 与 delegate 接口 1.3 改写，Spec 末尾加「变更记录」——用户 2026-10-28 批准（C306「C306 A」，集成分支 6a0aa58）
- [x] Spec 批准后重写 Plan 第 2 轮任务交审——用户 2026-10-28 批准 Plan（C310「C310 A」，开工 C311）
- [x] R1：`ready` 改读 delegate 1.3 能力标记，条件⑤改为该模块会话在 Claude Code（Spec 验收 1）
- [x] R2：开工交接——`offload.assign`、授权文件、`review._start_todo` 三种情形与新文案、旧记录处理（Spec 验收 2、3、10 前半）
- [x] R3：`offload start` 由模块会话跑，`--resumable`／`--continue` 两种写法与任务说明（Spec 验收 4）
- [x] Checkpoint R-1（report）：交接与派出就位——与 R-2 一起核对，见下
- [x] R4：`settle` 解析与归类、needs-input 问题正文、timeout 分支（Spec 验收 6 前半、7、8）
- [x] R5：done 去向、失败计数、自动重来、退回 Claude、`takeover`、`resume` 新写法（Spec 验收 5、6 后半、9）
- [x] R6：命令行 `settle --stderr`、`takeover`、去 `handback`；`offload show` 加列（Spec 验收 10 后半、11）
- [x] Checkpoint R-2（report）：命令全部就位——R1～R6 在同一提交里实现，实现先写、测试随后同步写，没有逐项先看到红；本模块 46 个测试通过；review、approve、start prepare、check ledger、declared scope、轻任务、skill 回归 238 个通过
- [x] R7：四份 skill「额度外包」一节重写、README（Spec 验收 12）——skill、术语表、README 相关测试通过
- [ ] R8：sync 后快检查与全量测试；本机 delegate 0.8.0 实测 `--resumable` + `--continue`（Spec 验收 13）
- [ ] Checkpoint R-3（gate）：最终验收
- [ ] 回告：完成情况经模块协调转告 ecosystem-lead
