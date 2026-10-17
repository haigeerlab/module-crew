# module-crew 能力图草案

> 第 2 关草案，待用户审。第 4 关在本仓库运行 `/spec-guard:setup-convention` 后，经 `/spec` 的 Phase 0 正式写入
> `spec/CAPABILITY-MAP.md` 并再审一次。模块 id 正式写入前都可改。需求依据见 `requirements-record.md`。

## 目标

让多个 Claude 会话在同一项目里同时开发多个模块：一个协调会话统筹，模块会话各在自己的 worktree 开发，公共文件与合并由协调会话管，
会话中断或压缩后能从文件恢复。第一版只支持 Claude 桌面版。

| Module id | Responsibility | Depends on |
|---|---|---|
| crew-store | 状态库：仓库公共 git 目录下的运行配置、会话登记、事项、请求、等待单、发出正文与只追加事件日志；事务写入、统一编号、不删除 | — |
| crew-protocol | 按 session-protocol 解析与生成消息（复用 5 种 + 【交审】【公共变更请求】【通知】），严格校验、缺字段退回 | — |
| crew-probe | 依赖体检与只读 `status`：读 spec-guard `interface.json`（开关、`/map` JSON、三个入口）与 agent-relay 接口版本，宿主与仓库前提（worktree、干净基线） | crew-store |
| crew-onboarding | 协调会话约定与模块会话 skill：通信、答复有效性、被挡住与收工、权限弹窗、规则不写进模块 worktree | crew-protocol |
| crew-start | 扩张点：读 `startable`、问用户、生成开工说明、记会话登记、调 spec-guard 写角色标记、开会话（Claude） | crew-store, crew-protocol, crew-probe, crew-onboarding |
| crew-review-batch | 汇总同批【交审】、核对接口对得上、交用户审、批准后调 `review-mark` 并把 Spec／Plan 提交到集成基线、发【通知】开工 | crew-start |
| crew-shared-changes | 【公共变更请求】的查冲突、在基线上提交、回复与通知、要问用户的分流、等待单 | crew-start |
| crew-merge | 本地合并队列：合并前清单、`--no-ff`、完整检查、`revert`、通知下游、收回 worktree 与退役身份；远端按批推送开 PR 的授权与预告 | crew-review-batch, crew-shared-changes |
| crew-recovery-hooks | 启动／恢复／压缩与每轮的按角色注入；压缩后「先核对再动手」；换会话接管流程 | crew-store, crew-probe |
| crew-failure | 挂起释放名额、识别悄悄停下、崩溃换会话、退回串行 | crew-merge, crew-recovery-hooks |

Build order: crew-store, crew-protocol → crew-probe → crew-onboarding → crew-start → crew-review-batch, crew-shared-changes → crew-merge → crew-recovery-hooks → crew-failure

## 说明

- 逗号组只表示「可以同时做」，本仓库自己仍串行开发（第 4 关不拿未完成的能力开发它自己）。
- crew-protocol 依赖 session-protocol 契约 v1.1 已批准（见 `session-protocol-notes.md`）。
- crew-start 起依赖 spec-guard 的规划层改动已发版（见 `spec-guard-additions.md`）；在那之前可用夹具测试推进，但第 7 关必须用真实版本。
- 文档建议（能力图评审处）：README（安装、前提、一次完整流程）、安装说明里的钩子信任与 agent-relay 前提。
