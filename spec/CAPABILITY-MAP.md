# Capability Map: module-crew（多模块并行开发运行层）

> 由 `/spec` 的 Phase 0 产出。**必须经人工评审后才能往下走。**
> Addy 原文：把图搞错代价很大，评审十行不算什么。
> 需求依据：`docs/requirements-record.md`（第 2 关已批准，2026-10-18）；草案：`docs/capability-map-draft.md`。

## 目标

让多个 Claude 会话在同一项目里同时开发多个模块：一个协调会话统筹，模块会话各在自己的 worktree 开发，公共文件与合并由协调会话管，
会话中断或压缩后能从文件恢复。第一版只支持 Claude 桌面版，给已启用 spec-guard、模块多且彼此独立的项目用。

<!-- 这一段是 Proposal 评审的目标指纹底本（`spec-digest.py` 计算）。
     改写目标会让已发布的 Proposal 被判为过期，所以改了先人工评审；追加模块不需要改这里。
     标题必须是 `## 目标`（或 `## Goal`）—— 指纹脚本按标题定位这一节。 -->

## 模块

| Module id | Responsibility | Depends on |
|---|---|---|
| crew-store | 状态库：`$(git rev-parse --git-common-dir)/module-crew/` 下的运行配置、会话登记、待用户决定事项与原话、变更请求、等待单、发出正文与只追加事件日志；事务写入、统一编号、不删除 | — |
| crew-protocol | 按 session-protocol v1.1 解析与生成消息（复用 v1.0 的【等待用户】【用户答复】【等待其他会话】【已恢复】【撤回】，新增【交审】【公共变更请求】【协调通知】）；严格校验、缺字段退回；钉住契约样例跑一致性测试 | — |
| crew-probe | 依赖体检与只读 `status`：读 spec-guard `interface.json` 与 `/map --json`（开关、`startable`、三个入口）、agent-relay 接口版本，宿主与仓库前提（worktree 可建、集成基线干净） | crew-store |
| crew-onboarding | 协调会话约定与模块会话 skill：通信、答复有效性（总协调转达【用户答复】）、被挡住与收工、权限弹窗；规则不写进模块 worktree | crew-protocol |
| crew-start | 扩张点：读 `startable`、问用户一次「开这 N 个吗」、生成开工说明、记会话登记、调 spec-guard 写角色标记、开 Claude 会话与 worktree | crew-store, crew-protocol, crew-probe, crew-onboarding |
| crew-review-batch | 汇总同批【交审】、核对接口对得上、交用户审、批准后调 `review-mark` 并把 Spec／Plan 提交到集成基线、发开工类【协调通知】 | crew-start |
| crew-shared-changes | 【公共变更请求】：查冲突、在集成基线上单独提交、回复与发同步基线类【协调通知】、要问用户的分流、完全停住时记等待单 | crew-start |
| crew-merge | 本地合并队列：合并前清单、`--no-ff`、完整检查、失败 `revert -m 1`、通知下游、收回 worktree 与退役邮箱身份；远端按批推送开 PR 的授权与预告 | crew-review-batch, crew-shared-changes |
| crew-recovery-hooks | 启动／恢复／压缩与每轮的按角色注入；压缩后「先核对再动手」；换会话的 `takeover` 接管流程 | crew-store, crew-probe |
| crew-failure | 挂起释放名额、识别悄悄停下、崩溃在原 worktree 换会话、退回串行 | crew-merge, crew-recovery-hooks |
| crew-hub-bridge | 接入收件枢纽：批准来源登记与校验（self／hub／lead）、枢纽事项号与 crew 编号一对多对照、审查行、交枢纽的【等待用户】正文、只读线状态出口（sessions --json 契约与 interface.json）、skill 措辞与协调会话规则 | crew-review-batch, crew-merge, crew-failure |
| crew-codex-host | 第二版：Codex 桌面版模块会话——Codex 插件包与 crew-dev 的 Codex 版、start prepare --host codex 与开工说明的 Codex 段、host-check 只读预检（.git 可写、命令可用、agent-relay）、身份重登与未加载提示；协调会话仍为 Claude | crew-start, crew-onboarding, crew-recovery-hooks |
| crew-review-nearby | 第三版：审查就近与决策集中——审查结论就近退回返工（上限 3 次、不同意并排交用户、超时照常送审）、送审、待用户决定问题单列与追问、多段审查结论、合并批准撤回窗口、交审编号前缀 C、合批正文摘要与要点不截断、最终验收选项写真实后果；不配收件枢纽或审查者时照常可用 | crew-protocol, crew-review-batch, crew-merge, crew-hub-bridge |
| crew-stall-signals | 第四版：停滞事实只读出口——sessions --json 加模块最近提交、开工时间、领先提交数与同一节点问过用户几次、模块发来的【等待用户】首行；只给事实不设阈值，判断与提问归决策收件箱 | crew-hub-bridge, crew-review-nearby |
| crew-host-permissions | 第四版：宿主权限预配与推送守门——permissions plan／apply／verify 把第 44 条范围内的常规操作写进集成 checkout 与模块 worktree 的 .claude/settings.local.json（推送、删除写 deny）、开会话后实测放行；pre-push 钩子拦模块 worktree 推送与无 merge push 放行凭证的推送 | crew-start, crew-merge |
| crew-glossary-rename | 第四版：术语表 v1.1 全面改名——README、命令说明、两份 skill、命令输出与生成正文里的自由文字换成新名称，等待记录显示 W 前缀，旧称扫描测试；代码标识符、命令选项、状态库字段与契约标签不动 | crew-stall-signals, crew-host-permissions |
| crew-pilot-fixes | 第五版：演练修复——module-crew sync 合入集成分支、review show 读审查原文、撤销批准不重开已被取代的交审并作废过期合并批准、模块协调自开的等待记录经 CLI 记账并提示关闭、派活后核对模块会话是否卡在权限弹窗 | crew-merge, crew-review-nearby, crew-host-permissions, crew-glossary-rename |
| crew-hub-card-fields | 第五版：决策卡片字段——交给决策收件箱的【等待用户】按 session-protocol v2.3 写「类型」与各类小项，「注意」「推荐理由」「批了会怎样」由 module-crew 生成，模块协调自己提的请示按类别写；契约 v2.3 定稿后写 Spec | crew-hub-bridge, crew-review-nearby, crew-glossary-rename |
| crew-stage-c-fixes | 第五版：阶段丙补修（R22）——【等待用户】带「模块」、已交最终验收的模块不再收同步通知、新合并批准取代旧批准、不重复提请已答过的事、权限预配放行本 worktree 内的编辑、提请批准只发 for-hub 正文不手写合问 | crew-pilot-fixes, crew-hub-card-fields |

Build order: crew-store, crew-protocol → crew-probe → crew-onboarding → crew-start → crew-review-batch, crew-shared-changes → crew-merge → crew-recovery-hooks → crew-failure → crew-hub-bridge → crew-codex-host → crew-review-nearby → crew-stall-signals → crew-host-permissions → crew-glossary-rename → crew-pilot-fixes → crew-hub-card-fields → crew-stage-c-fixes

<!-- Spec Guard 按严格串行推进。为兼容上游格式，逗号分组会按左到右顺序展开为单模块步骤，不代表并行授权。 -->

## 说明

- 逗号组只表示「可以同时做」；本仓库自己串行开发（第 4 关不拿未完成的能力开发它自己）。
- crew-protocol 依据 session-protocol v1.1（提交 78da46f，2026-10-18 批准）；现钉住 v1.9（f47631b；v1.2～v1.9 只增不改，v1.9 只写明【撤回】事项号条文：修正样例、补写现行做法、新增「退回」「挂起」「恢复」通知类型、转交答复的「转自」与【负责人转交】、【取代】只认枢纽事项号）。
- crew-start 起依赖 spec-guard 规划层发版（`moduleConcurrency`、`/map --json` 新字段、`interface.json` 1.1）；发版前用夹具推进，
  第 7 关实地验证必须用真实版本。
- 防线 L1–L5（需求记录第 9 节）：出现「要改 spec-guard 阶段判断核心」「要在 spec-guard 里管会话」就停下复盘。

---

## 评审记录

- [x] 模块边界确认（砍掉或替换一个模块，不需要重写其他模块的需求）
- [x] 依赖方向单向无环（互相依赖 = 它们本来就是一个模块）
- [x] module id 已定稿（kebab-case，之后绝不改名 —— 同一个 id 同时是
      `spec/<id>.md`、`tasks/<id>/`、`.agent/state.json` 的 `activeModule` 和 Proposal 中的模块名，
      已发布的 Proposal 改不动）
- [x] 构建顺序符合依赖拓扑

评审人：用户（对话中回复「批准」）
日期：2026-10-18

## 变更记录

- 2026-10-18：「说明」里补记 crew-protocol 现钉住 session-protocol v1.3（42fe5f6）。原因：契约负责人修正 v1.1 的一份样例；来源：用户在 crew-protocol 最终验收时选 A。模块、依赖与顺序不变。
- 2026-10-18：「说明」改为 crew-protocol 现钉住 session-protocol v1.4（e33c077）。来源：用户批准升级。模块、依赖与顺序不变。
- 2026-10-18：「说明」改为 crew-protocol 现钉住 session-protocol v1.5（246e138）。来源：用户批准升级。模块、依赖与顺序不变。
- 2026-10-18：「说明」改为 crew-protocol 现钉住 session-protocol v1.7（1e14a49）。原因：crew-hub-bridge 需要 v1.6 的转交条文；来源：用户批准的契约版本。模块、依赖与顺序不变。
- 2026-10-18：「说明」改为 crew-protocol 现钉住 session-protocol v1.8（c982bc3）。原因：crew-failure 需要挂起、恢复通知（第二轮试点问题 I）；来源：第二轮试点修法，用户 2026-10-18 批准。模块、依赖与顺序不变。
- 2026-10-18：插入第二版模块 crew-codex-host（依赖 crew-start、crew-onboarding、crew-recovery-hooks，排在 crew-hub-bridge 之后）。原因：需求记录第 13 节「Codex 模块会话」；来源：用户 2026-10-18 确认 14 条假设并批准插入。
- 2026-10-18：「说明」改为 crew-protocol 现钉住 session-protocol v1.9（f47631b）。原因：v1.9 写明【撤回】只认枢纽事项号；来源：用户 2026-10-18 定为 0.1.2 待办，随 0.2.0 做。模块、依赖与顺序不变。
- 2026-10-19：插入第三版模块 crew-review-nearby（依赖 crew-protocol、crew-review-batch、crew-merge、crew-hub-bridge，排在 crew-codex-host 之后）。原因：用户决定 41–43「审查就近、决策集中」与批 2 暴露的问题（livesaas-integration/REQ-REVIEW-NEARBY.md 的 R1–R9）；来源：用户 2026-10-19 确认 21 条假设并批准插入。
- 2026-10-19：插入第四版三个模块 crew-stall-signals（依赖 crew-hub-bridge、crew-review-nearby）、crew-host-permissions（依赖 crew-start、crew-merge）、crew-glossary-rename（依赖前两个），依次排在 crew-review-nearby 之后。原因：0.3.0 放到下一版的 R14 停滞检测、R16 宿主权限与术语表 v1.1 全面改名（livesaas-integration/REQ-REVIEW-NEARBY.md、GLOSSARY.md）；来源：用户 2026-10-19 确认 19 条假设并批准插入。
