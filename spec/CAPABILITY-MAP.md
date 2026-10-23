# Capability Map: module-crew（多模块并行开发运行层）

> 由 `/spec` 的 Phase 0 产出。**必须经人工评审后才能往下走。**
> Addy 原文：把图搞错代价很大，评审十行不算什么。
> 需求依据：`docs/requirements-record.md`（第 2 关已批准，2026-10-18）；草案：`docs/capability-map-draft.md`。

## 目标

让多个 Claude 会话在同一项目里同时开发多个模块：一个协调会话统筹，模块会话各在自己的 worktree 开发，公共文件与合并由协调会话管，
会话中断或压缩后能从文件恢复。第一版只支持 Claude 桌面版，给已启用 spec-guard、模块多且彼此独立的项目用。
第六版起协调会话管项目里所有派活：用户明说才升级、一个仓库只一个；单个需求与 bug 走轻流程（不写 Spec、各自 worktree），
和模块一样只从合并队列进集成分支；没升级的会话一切照常。
第七版补上换手与呈现：命令入口跟着安装的插件走（Codex 用固定启动脚本），会话重开与接管有明确做法、只认登记的会话；契约钉到 session-protocol v2.6，审批消息按 spec-guard 的格式呈现。

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
| crew-routing-fixes | 第五版：收发对象收窄——【交审】只送负责该模块或节点的审查者（登记审查者时写明负责范围）、公共变更后的同步基线通知跳过挂起模块并在恢复时补发、启动钩子只给会话登记里的那个会话注入角色 | crew-recovery-hooks, crew-failure, crew-hub-bridge, crew-stage-c-fixes |
| crew-coordinator-switch | 第六版：协调会话开关——用户明说才升级（前提同开工体检、不要求能力图）、一个仓库只一个协调会话、没有协调会话时完全安静、普通会话首次回复提醒一次并告知协调会话、/clear 后身份交接、多模块上限默认改为 2 | crew-probe, crew-recovery-hooks, crew-routing-fixes |
| crew-task-ledger | 第六版：任务记录——状态库新增任务（类型需求／bug、派给谁、worktree 与分支、预计改的文件、状态、结果、由哪个任务带进来），status 显示、takeover 一并接管，预计文件与在做的活重叠就排队、bug 排前 | crew-store, crew-coordinator-switch |
| crew-light-task | 第六版：轻流程——写任务单、开 worktree 与会话、交回带测试结果与实际改的文件（bug 先补复现测试）、进合并队列由用户批准并通知同步、升格／缩小／取消、回滚按轻任务走；不写 Spec、不调 spec-guard | crew-task-ledger, crew-start, crew-merge |
| crew-unqueued-commits | 第六版：不经队列的提交——发现集成分支上不是经合并队列合入的提交，告诉用户并照常通知各模块同步 | crew-merge, crew-coordinator-switch |
| crew-background-checks | 第六版：后台检查——合并时的完整检查改后台运行、协调会话照常回话，同一时间只跑一个合并 | crew-merge, crew-onboarding |
| crew-command-entry | 第七版：命令入口——Codex 会话改用状态库里不带版本号的固定启动脚本（每次转给当前安装的那份），bin/module-crew 不再让当前目录的代码盖过插件自己的代码 | crew-codex-host, crew-host-permissions, crew-recovery-hooks |
| crew-session-handover | 第七版：会话换手——写明怎么重开、跨目录接管模块协调（用户原话，旧会话登记作废）、模块协调的写命令核对调用者会话、同一角色两个活着的会话时 status 报阻塞 | crew-coordinator-switch, crew-recovery-hooks, crew-background-checks |
| crew-contract-v26 | 第七版：钉住 session-protocol v2.6——新样例、C<交审号>-<序号> 待定编号与只发 v2.6 以上收件箱、答复块写法、「验收结果」改名、Spec／Plan 新小项与要点 points；钉住后回报契约负责人 | crew-protocol, crew-hub-bridge, crew-hub-card-fields |
| crew-review-display | 第七版：审批呈现——最终验收按 spec-guard reviewKinds.final 由 review batch 从模块分支生成、开工／公共变更／卡住选做法三种模板、多模块按 Build order 分节、决定内容写在下一步框之前 | crew-review-batch, crew-contract-v26 |
| crew-host-handover | 第八版：空档整体换宿主——一批模块收尾后提示可换宿主，coordinator handover --to codex／claude 核对收尾条件、改模块协调登记的宿主、按新宿主写集成 checkout 的权限规则、生成逐步交接说明，之后开工与派任务的宿主跟随模块协调 | crew-codex-host, crew-host-permissions, crew-light-task, crew-session-handover |
| crew-codex-coordinator | 第八版：模块协调在 Codex 上运行——Codex 版 crew-coordinator skill、放开协调只许 claude-desktop、无钩子时醒来先跑 status、Codex 侧定位插件、模块会话由用户手动开的指引、合并长检查与写 .git 提权方案、handover --to codex 放开 | crew-host-handover, crew-codex-host, crew-command-entry, crew-background-checks |
| crew-reopen-module | 第九版：重开已完成的模块做修订——start prepare 接受用户点名、/map 里进行中且没有 checkout 领走的模块，旧模块分支已合入就快进到集成分支再开、没合入就拒绝，新开会话登记与带后缀的新邮箱名，开工说明写明只做新加的未勾项 | crew-start, crew-light-task, crew-session-handover |

Build order: crew-store, crew-protocol → crew-probe → crew-onboarding → crew-start → crew-review-batch, crew-shared-changes → crew-merge → crew-recovery-hooks → crew-failure → crew-hub-bridge → crew-codex-host → crew-review-nearby → crew-stall-signals → crew-host-permissions → crew-glossary-rename → crew-pilot-fixes → crew-hub-card-fields → crew-stage-c-fixes → crew-routing-fixes → crew-coordinator-switch → crew-task-ledger → crew-light-task → crew-unqueued-commits → crew-background-checks → crew-command-entry → crew-session-handover → crew-contract-v26 → crew-review-display → crew-host-handover → crew-codex-coordinator → crew-reopen-module

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
- 2026-10-20：插入第五版模块 crew-routing-fixes（依赖 crew-recovery-hooks、crew-failure、crew-hub-bridge、crew-stage-c-fixes，排在最后）。原因：收发规则（点对点、沿上下级）自查与总协调排查查到的三处收件对象过宽；来源：用户 2026-10-20 在本会话批准插入与 Spec。
- 2026-10-22：「目标」一节追加第六版范围（协调会话管所有派活）；插入第六版五个模块 crew-coordinator-switch、crew-task-ledger、crew-light-task、crew-unqueued-commits、crew-background-checks，依次排在最后。原因：插件只覆盖多模块并行，单需求与 bug 只能用原生关联会话做，和合并队列两套规则冲突（需求记录第 14 节）；来源：用户 2026-10-22 在本会话经拷问确认需求，并批准五个模块与直接改目标（本仓库没用过 Proposal）。
- 2026-10-22：「目标」一节追加第七版范围；插入第七版四个模块 crew-command-entry、crew-session-handover、crew-contract-v26、crew-review-display，依次排在最后。原因：0.11.1 试用留下的 Codex 命令入口与源码仓库加载问题、spec-guard 负责人试用观测 O9（会话换手）、契约 v2.6 定稿（92309e7）与回显评审（需求记录第 15、16 节）；来源：用户 2026-10-22 在本会话确认 12 项需求并批准四个模块的划分与顺序。
- 2026-10-23：插入第八版模块 crew-host-handover（依赖 crew-codex-host、crew-host-permissions、crew-light-task、crew-session-handover，排在最后）。原因：接缝 S13 修订版需求——一批模块收尾后的空档里，模块协调与模块会话整体在 Claude Code 与 Codex 之间来回切换（不做模块中途换宿主；协调在 Codex 上运行另作模块，待阶段 0 实测与 spec-guard 答复后由用户定）；来源：用户在 ecosystem-lead 会话确认修订版需求，2026-10-23 在 mc-coord 会话批准插入（「批准插入 crew-host-handover」）。
- 2026-10-23：插入第八版模块 crew-codex-coordinator（依赖 crew-host-handover、crew-codex-host、crew-command-entry、crew-background-checks，排在最后）。原因：接缝 S13 的模块 B——模块协调能在 Codex 上运行，配合 crew-host-handover 完成空档整体来回换宿主；依据阶段 0 实测（Codex 沙箱里固定入口可用、写 .git 要提权）、sg-coord #10512、agent-relay #10548；来源：用户在 ecosystem-lead 会话同意开工模块 B，2026-10-23 在 mc-coord 会话批准插入（「批准插入 crew-codex-coordinator」）。
- 2026-10-24：插入第九版模块 crew-reopen-module（依赖 crew-start、crew-light-task、crew-session-handover，排在最后）。原因：接缝 S18——LIVE-SAAS 后台要修订两个已完成模块，spec-guard 按「返工与小模块」原地重开后 /map 记为进行中，module-crew 的 start prepare 只收 startable、同名分支已存在也拒绝，没有重开入口；sg-coord 确认不改 spec-guard 接口，由 module-crew 认 /map 现有字段；来源：用户在 ecosystem-lead 会话定「S18、S19+S21、S20、S22 都做」，2026-10-24 在 mc-coord 会话批准插入并开工写 Spec。
