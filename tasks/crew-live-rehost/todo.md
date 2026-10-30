# Todo: crew-live-rehost

> 依据 `tasks/crew-live-rehost/plan.md`。

- [x] Task 1：store 校验 `rehost` 字段与 `previousSessions.reason`（Spec 验收 4 状态库部分）——测试先红后绿（5 个）；store 各测试照常通过（90db36e）
- [x] Task 2：挡住清单、快照与确认码，`coordinator rehost --check`（Spec 验收 1、2 确认码部分）——新增 module_crew/rehost.py 与 8 个测试（七项挡住逐项、确认码稳定与随改动／提交／绑定变化、CLI 只读）；这一项测试与实现同步写，没有先单独看红
- [x] Task 3：`coordinator rehost --to claude`：守门窄口、原话与确认码核对、一个事务改登记（Spec 验收 2、3、4）——测试先红后绿（6 个：四种原话／确认码拒绝、预览后状态变、三种守门 7、整批迁移与未结记录逐字不变、终端不绑、CLI 过守门）
- [x] Task 4：权限跟随全部 checkout、恢复说明、迁移说明（Spec 验收 5、6）——2 个测试（恢复说明与迁移说明的关键句、未提交文件原样列出、原话文件；已 apply 时 Claude 规则写进原 Codex worktree、Codex 规则逐字不变）；实现先于测试写，没有先单独看红；failure.resume_kit 改为调用新的 session_kit（模块与轻任务共用），test_failure 照常通过
- [x] Checkpoint 1（report）：迁移本身走通，相关测试通过——test_live_rehost 21 个、test_failure、test_host_handover、test_session_handover、test_coordinator_switch、test_routing 全部通过
- [x] Task 5：旧会话失效（Spec 验收 7）——测试先红后绿（3 个：旧 Codex 编号跑 sync、check quick、offload start、bind 退出码 7；status、sessions 照常；别的会话不受影响）
- [x] Task 6：盘点闸：钩子档位、`rehost show`、`rehost release`、最终验收拦截、status（Spec 验收 8）——测试先红后绿（6 个）；轻任务的最终验收也拦；只读出口的 stage 枚举不变（新档位照旧报 build）；hooks、review_add、light_task、probe_status、failure 测试照常通过
- [x] Task 7：`coordinator rehost --undo`（Spec 验收 9）——测试先红后绿（4 个）；为逐字恢复，迁移时在 rehost 里多存一份迁移前的登记（before），Spec 关键决策 4 没写这个字段，最终验收随 Spec 变更记录报
- [x] Task 8：钩子陌生 Claude 会话提示（Spec 验收 10）——测试先红后绿（2 个）；hooks 仍不 import subprocess，test_hooks、test_readonly_and_hooks 照常通过
- [ ] Checkpoint 2（report）：命令层做完，全量测试通过
- [x] Task 9：文档与技能（Spec 验收 11）——断言先红后绿（RehostDocsTest 2 个）；docs/guide.md「批次内迁到 Claude」、docs/commands.md（coordinator rehost 与新的 rehost 一节）、README／README.en、crew-coordinator「接手 Codex 上没做完的一批」、crew-dev「迁来之后」；另给 codex-skills/crew-coordinator 加同名小节（Plan 影响面没列，test_skills 要求两版小节一致），Spec 末尾补变更记录，最终验收复审；test_docs、test_skills、test_readme_hosts、test_handover_docs、test_codex_coordinator 通过
- [ ] Task 10：`module-crew sync` 后全量测试（Spec 验收 12 测试部分）
- [ ] Checkpoint 3（gate）：实地演练要不要现在做
- [ ] Checkpoint 4（gate）：最终验收
- [ ] 回告：mc-coord（转用户）LIVE-SAAS 可按迁移说明迁
