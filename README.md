# module-crew

让多个 Claude 桌面版会话在同一个项目里**并行开发多个模块**：一个模块协调统筹，每个模块会话在自己的 git worktree 里开发；
所有批准都由用户在模块协调里亲手给出；会话中断、压缩或换新会话后，从状态库恢复，不靠对话记忆。

> 版本 0.5.0。已在试点项目上跑过两轮实地验证（见 `docs/pilot-report.md`），还没验证的见文末「尚未验证」。

## 0.5.1 的变化（决定 62：装包放宽）

- 权限预配：往项目里加新包也放行（`npm install <包名>`、`pnpm add`、`yarn add`、`uv add`、`uv pip install`、`.venv/bin/pip install`），新增依赖由 spec-guard SG-5 在最终验收列出；裸 `pip install <包名>` 仍交宿主默认确认；全局安装禁止补全到 `-g`／`--global` 在任意位置、`yarn global`、`uv --system`（代价：`npm ls -g` 这类只读查询也被拒）。Codex 侧加新包仍不写规则（前缀规则挡不住后置的 `-g`）。
- skill：去掉「Plan 没列的依赖只问一次」，加新包直接装。

## 0.5.0 的变化（R21 模块打转）

- 权限预配：按锁文件或清单装依赖放行，加新包不写规则（宿主默认确认＋先问一次），全局安装仍禁止；Codex 规则同步。
- skill：已批范围内直接做、不讨小许可、小步骤不送审、Plan 没列的依赖只问一次；碰到宿主确认经模块协调告诉用户去哪个会话点什么。
- 契约钉到 session-protocol v2.2：模块会话碰到宿主确认时发「类型：去会话操作」的【等待用户】，模块协调原样转给决策收件箱（没有就直接告诉用户去哪点）。
- `sessions --json` 加 `answers`：每次「你的答复」之后的提交数与 todo 勾选增量，供决策收件箱判断打转。

## 0.4.1 的变化

- 评审节奏优先读 spec-guard（0.73.0 起）`/map --json` 的顶层 `reviewCadence`，`status` 写明来源；spec-guard 较旧时照旧读 `.agent/config.json`。
- `permissions remove` 把 `.claude/settings.local.json` 逐字还原为 apply 之前的原文。

## 0.4.0 的变化

- **停滞事实出口**（R14）：`sessions --json` 每个模块加开工时间、最近一次产出提交、同一节点问过你几次（带每次的时间）、合并退回、模块报来的【等待用户】；只给事实，判断与提问归决策收件箱。见 [spec/crew-stall-signals.md](spec/crew-stall-signals.md)。
- **权限预配与推送守门**（R16）：`module-crew permissions plan|apply|verify|remove`，把常规操作写进宿主认的放行规则，推送、删除等写成禁止，再用 pre-push 钩子守住推送；推送只经 `merge push`。见下文「权限预配」与 [spec/crew-host-permissions.md](spec/crew-host-permissions.md)。
- **术语改名**：README、skill、命令说明与输出按术语表 v1.1；等待记录编号改写 `W<号>`（命令参数 `W25`、`C25`、`25` 都认）。契约标签、字段名、命令与选项名不变，状态库照旧可用。

## 前提

| 依赖 | 要求 |
|---|---|
| 宿主 | 模块协调：Claude 桌面版（Code 标签）；模块会话：Claude 桌面版或 Codex 桌面版。都在同一台 Mac 上 |
| agent-relay | **必需**，接口主版本 2。会话之间用它收发消息（`bridge_send` 的 `bodyFile`、`replyTo`、`expectsReply`） |
| spec-guard | 项目已启用本地多 Spec 约定（`spec/CAPABILITY-MAP.md`）。开工、批量批准、合并依赖 spec-guard 0.68.0（`interface.json` 1.1、`/map --json` 的 `moduleConcurrency`、`startable`） |
| 项目 | git 仓库，能建 worktree；有一条能在本地跑完的完整检查命令，合并后用它判断集成是否通过 |
| 运行环境 | Python 3（只用标准库） |

消息格式以 [session-protocol](../session-protocol) 契约为准（现钉住 v1.9）。

## 安装

1. 本仓库自带本地插件市场清单（`.claude-plugin/marketplace.json`，市场名 `module-crew-local`），用本机路径装上，同时装好 agent-relay 与 spec-guard：

   ```bash
   claude plugin marketplace add /path/to/module-crew
   claude plugin install module-crew@module-crew-local
   ```

2. **信任 module-crew 的钩子**：首次使用时 Claude Code 会询问是否信任插件钩子，要同意；否则压缩、换会话后不会注入角色提示。
3. **插件更新后要开新会话**才生效：已开着的会话还在用旧版本的钩子与 skill。

装好后在项目里跑一次体检：

```bash
bin/module-crew status
```

它检查 git、agent-relay、spec-guard、spec-guard 规划层、集成分支与状态库六项，任何一项阻塞都会写明原因。

## 角色

- **模块协调**（加载 `crew-coordinator` skill）：统筹、收件记账、转达用户的决定、管集成分支与公共文件、合并。不开发任何模块，不出审查结论。
- **模块会话**（加载 `crew-dev` skill）：只在自己的 worktree 里开发一个模块，只和模块协调说话；被挡住必须发【等待其他会话】。

状态库放在仓库公共 git 目录下的 `module-crew/`（`events.jsonl` 是事实来源），所有 worktree 共用一份；不进版本库。

## 一次完整流程

1. **开工**（模块协调）
   - `module-crew start plan`：按能力图的 Build order 提议可开的模块（不超过空位，默认上限 3）。
   - 只问用户一次「开这 N 个吗？」，用户答应后
     `module-crew start prepare <模块>… --original-file <原话文件> --project-short <简称>`：为每个模块建 worktree（`<仓库名>-crew/<模块>`）、登记会话、生成开工说明。
   - 用桌面版在每个 worktree 里开新会话，第一条消息用开工说明全文。
2. **写 Spec 与 Plan**（模块会话）：写好后发【交审】；收到开工类【协调通知】之前不构建。
3. **批量批准**（模块协调）
   - `module-crew review add` 记下每条【交审】，`module-crew review batch` 汇总，把要点写在正文里交用户审。
   - 用户批准后 `module-crew review approve <编号>… --original-file <原话文件>`：在集成分支记批准标记，生成【用户答复】与开工通知。
   - 模块会话把集成分支合进自己的分支（Spec／Plan 冲突取集成分支版本）后开始构建。
4. **公共文件**：模块会话不改公共文件，发【公共变更请求】；模块协调 `change add` → 在集成 checkout 改 → `change land`，其他模块收到同步基线通知。
5. **合并**
   - 模块做完发最终验收【交审】，用户批准后 `module-crew merge approve <交审编号> --original-file <原话文件>`。
   - `module-crew merge run`（第一次带 `--check-command "<完整检查命令>"`）：按 Build order 一次只合一个，`--no-ff` 合入本地集成分支后跑完整检查；
     不过就把集成分支重置回合并前（模块分支原样保留）并退回该模块，冲突就中止并退回。
   - 合并成功：该模块收到收尾通知，其他在用模块收到同步基线通知。
6. **收尾与推送**
   - 用户同意后 `module-crew merge cleanup <模块> --original-file <原话文件>` 收回 worktree（分支保留）。
   - `module-crew merge push-plan` 预告；用户明确授权后 `module-crew merge push --original-file <原话文件>`，推到远端新分支 `crew/batch-<号>` 并开一个 PR。
   - **远端合并始终由用户做**；不开自动合并，不推集成分支本身。

每条要发的消息，命令都会生成正文文件；模块协调用 `bridge_send` 的 `bodyFile` 原样发出，不改一字。

## Codex 模块会话

模块会话可以开在 Codex 桌面版里，模块协调仍在 Claude 桌面版。

1. 在 Codex 里装同一版本的 module-crew（`.codex-plugin/plugin.json`，只提供 Codex 版 `crew-dev` skill）；Codex 插件更新后要完全退出 ChatGPT 应用再打开。
2. 模块协调用 `module-crew start prepare <模块>… --host codex --original-file <原话文件>` 开工；要混用就按宿主分两次。
3. 用户在 Codex 里新建任务，工作目录选那个模块的 worktree，第一条消息贴开工说明全文。
4. Codex 会话先跑 `module-crew host-check`（开工说明里有绝对路径）：检查登记、版本、能否写 git 目录、能否读状态库。
5. Codex 默认沙箱不让写 `.git`：第一次提交会弹提权，用户在那个 Codex 会话里批准（有「本会话一直允许」就选）。
6. ChatGPT 应用重启后 Codex 会话不会自动加载，要用户逐个点开；Codex 会话掉了联调身份时用原名重新注册即可。

## 出状况时怎么办

| 情况 | 做法 |
|---|---|
| 不知道哪个会话停下了 | `module-crew sessions` 列出每个模块会话的最后动静、未关的等待记录与事项、当前档位、挂起原因；只列事实，结合 agent-relay 在线状态自己判断 |
| 某个模块会话在「等待审批」 | 权限弹窗只能用户去那个会话亲手点；模块协调醒来时会提醒，并核对各模块会话的权限模式有没有变宽 |
| 消息发出去对方没反应 | 桌面版会停掉空闲会话，agent-relay 叫不醒（`pendingReason: offline`）；用桌面版跨会话消息发一句「去读 agent-relay 收件箱」 |
| 模块在等外部条件（设计稿、别人交付） | 用户同意后 `module-crew suspend <模块> --reason "<原因>" --original-file <原话文件>`，不再占名额；按输出把挂起正文发给模块会话，它在自己的 worktree 里用 spec-guard 挂起。条件满足、用户同意后 `module-crew resume <模块> --original-file <原话文件>` |
| 会话崩溃或要换新会话 | `module-crew resume-kit <模块>` 生成恢复说明；用户同意后 `module-crew takeover <邮箱名> --original-file <原话文件>`，在原 worktree 开新会话，第一条消息用恢复说明，新会话用同一个邮箱名重新注册 |
| 会话被压缩 | 钩子会提醒先跑 `module-crew status`、以状态库为准，不按压缩前的记忆重做 |
| 想收手、不再并行 | `module-crew serial --original-file <原话文件>`：不再开新模块，已开的模块照常交审、合并、收尾；再用 `/spec-guard:config` 关掉 `moduleConcurrency`。恢复用 `serial --off` |
| 合并被退回 | 集成分支已回到合并前、模块分支不动；模块修好后重新发最终验收【交审】（不用撤销任何提交） |
| 同一个 gate 再次挡住、异常停点、要改能力图 | 按 spec-guard 的规则办，把选项与代价交用户决定 |

一个模块挂起、退回或崩溃，不影响其他模块的交审、合并与通知。

## 审查就近与决策收件箱

> 用词按 LIVE-SAAS 接入的术语表 v1.1（`livesaas-integration/GLOSSARY.md`），旧称与新名称的对照见 [spec/crew-glossary-rename.md](spec/crew-glossary-rename.md) 关键决策 1。

**审查就近**（登记了审查者时）：审查改在模块协调这一层就近来回，用户只看要拍板的事。

1. 模块会话按项目的评审节奏交审（spec-guard 项目配置 `reviewCadence`：`separate` 默认先只交 Spec，`combined` 一起交）；最终验收的「要点」里要有「验收标准与证据」一节。
2. `review add` 收下交审，输出把【交审】原样转给审查者的送审发送项。
3. 审查者回【审查结论】，`review note [<C号>] … [--then-batch [--for-hub]]` 记下（一条消息几段也行）：
   「有须修改项N条」时输出返工通知，模块改完重交、再送审，不问用户；返工满 3 次、模块写了「不同意」、或送审 15 分钟没结论，都变成「待你决定」的问题（D 编号）。
4. 只有审查通过（或带「待你决定」问题）的交审才提请批准：`review batch --for-hub` **一个模块一条**【等待用户】，
   带交审要点全文、「批准会发生什么」、「产物」（路径 ＠ 提交，重交带上一版）、「交审原文」「审查原文」（`<状态库>/originals/` 下的原文文件）和「待你决定」（字段名：待用户决定）。
5. 「你的答复」要答到每个 D（如「A；D1 B」）；没答全批准命令退出码 3、什么都不做。退回、等审查这类答案分别让交审退回或保持未答。
6. 最终验收批准后、合并前可以 `merge revoke <C号>` 撤回；`status` 与 `sessions --json` 显示返工轮次（`review` 字段）。

**接入决策收件箱**：

1. 在模块协调里由用户亲口登记可信批准来源：`module-crew source add <决策收件箱邮箱名> --kind hub --original-file <原话>`；审查者登记为 `--kind lead`。
2. 提请批准的正文逐条用 bodyFile 原样发给决策收件箱；要用户决定的事只在那里问，会话里不放可以点的决定按钮。
3. 决策收件箱转来【用户答复】后，批准命令带 `--source <决策收件箱> --source-item <H> --source-relay-id <消息号> --source-from <实际发件人> --original-file <那条消息>`，用户原话从消息里读出；实际发件人不是来源本身或是模块会话时拒收。
4. `module-crew source map <H>` 查一个待决事项批准了哪些 C 编号。
5. 外部插件读 `module-crew sessions --json`（`schemaVersion` 1：module、relayName、worktree、stage、stageText、suspended、lastActivity、review；0.4.0 起加停滞事实 startedAt、commits、asks、returns、waitUser，见 [spec/crew-stall-signals.md](spec/crew-stall-signals.md)，只给事实、不判断是否卡住），出口与契约版本登记在根目录 `interface.json`。

**不配决策收件箱、不配审查者时**：一切照常在模块协调里由用户亲手批准；没有审查者就不送审、不返工，提请批准里写「未审查」；「待你决定」的问题由模块协调直接问用户。

module-crew 自己的编号对外一律写 C 前缀（如 C15），`#数字` 只表示决策收件箱的待决事项号；命令参数写 `15` 或 `C15` 都行。
审查者用【负责人转交】转来的批准只记账、不写批准标记（spec-guard 只认用户亲手与决策收件箱转来的批准）；带来源批准时，给模块的【用户答复】按契约带「转自」，命令同时给出发回决策收件箱的【已恢复】「结束：#H」。

## 命令一览

```text
module-crew status [--json]                      体检与全貌（只读）
module-crew store init|check                     状态库
module-crew protocol check <文件>                消息自检
module-crew inbox add <文件> --from --relay-id   收件记账
module-crew answer <编号> --original(-file)      转达「你的答复」
module-crew start plan|prepare                   开工
module-crew review add|batch|approve|answer      交审与批量批准
module-crew change add|list|land|answer          公共变更请求
module-crew merge approve|revoke|queue|run|cleanup|push-plan|push
module-crew suspend|resume|sessions|resume-kit|serial
module-crew takeover <邮箱名> --original(-file)  换会话接管
module-crew source add|remove|list|map           可信批准来源（决策收件箱、审查者）与对照
module-crew review note [--then-batch]|batch --for-hub   审查结论、返工、提请批准正文（一个模块一条）
module-crew ticket close <编号> --reason …        模块协调关等待记录
module-crew permissions plan|apply|verify|remove  宿主权限预配与推送守门
module-crew hook session-start|prompt            插件钩子入口（只读，永远退出码 0）
```

需要用户批准的命令都要 `--original` 或 `--original-file`：只记用户在模块协调里亲手输入的话，别的会话转来的话不算批准。

## 开发

```bash
python3 -m unittest discover -s tests -v
```

需求与设计在 `docs/requirements-record.md`、`spec/CAPABILITY-MAP.md` 与 `spec/<模块>.md`。

## 权限预配

由别的会话代开的会话里，宿主的 ask 规则实测不弹确认就执行了，所以不可逆操作不能只靠权限弹窗。module-crew 把第 44 条范围内的常规操作（含装依赖与往项目里加新包：`npm ci`、`npm install <包名>`、`pnpm add`、`yarn add`、`uv add`、`.venv/bin/pip install` 等）写成宿主认的放行规则，把推送、删除、全局安装（`-g`／`--global` 在任意位置、`yarn global`、`uv --system`、`brew install`）、改全局配置写成禁止；裸 `pip install <包名>` 不写规则、交宿主默认确认（不在 venv 里会装进系统 Python）；Codex 侧加新包也不写规则，因为前缀规则挡不住 `npm install x -g`。不写 ask：代开的会话里 ask 规则实测不弹，而不写规则时默认确认会弹（0.5.0 补测）。再用 git 的 pre-push 钩子守住推送：

1. `module-crew permissions plan`：只读预览每个 checkout（集成 checkout 与各模块 worktree）要追加什么、文件有没有被 git 忽略、钩子能不能装、Codex 项目是否受信任。
2. `module-crew permissions apply --original-file <用户原话>`：Claude 写 `.claude/settings.local.json`（只追加条目），Codex 模块写 `.codex/rules/module-crew.rules`；有一个文件不能写就全部不写。之后 `start prepare` 新开的模块自动跟随。
3. 开好会话后 `module-crew permissions verify`：四条应直接运行、一条应被拒的实测清单；结果用 `verify --record` 记下，`status` 显示每个会话最近一次实测，没测过写「权限未实测」。
4. 推送只经 `module-crew merge push`：钩子拒绝模块 worktree 的推送，以及集成 checkout 上没有一次性放行凭证的推送。你自己在终端推送可以加 `--no-verify`。仓库设了 `core.hooksPath`（如 husky）或已有 pre-push 钩子时不装，`plan` 会写明。这时推送只靠宿主的禁止规则：2026-10-19 在 crew-rehearsal（husky 仓库）实测，由别的会话代开的 default 权限模式会话里 `git push` 被禁止规则拦下、不弹窗；没有 git 钩子这一层兜底，用 husky 的项目（如 LIVE-SAAS）都是这种情况。
5. Codex 的项目级规则只在项目被 Codex 信任后生效；module-crew 不改你的全局配置，只提示。
6. `module-crew permissions remove --original-file <用户原话>`：只撤 module-crew 加的条目；按「不删文件」的约定，Codex 规则文件清空、钩子改成空操作，可以手动删除。

spec-guard 的命令入口路径带版本号，暂不放进放行清单。细节见 [spec/crew-host-permissions.md](spec/crew-host-permissions.md)。

## 尚未验证

两轮试点（第一轮 auto 权限、第二轮默认权限）已经实地验证：真实 spec-guard 0.68.0、会话间真实收发、开工、批量批准、合并与退回、
挂起与恢复、换模块协调与换模块会话、退回串行、收尾与推送到本机远端。还没验证的：

- 用 `gh` 真正开 PR（试点远端是本机裸仓库，只打印 PR 正文）。
- 权限预配在真实宿主里的效果（代开的模块会话里放行不弹窗、禁止规则拦得住）：要按 `permissions verify` 实地跑一遍。
- 挂起、恢复类【协调通知】（契约 v1.8）在真实会话之间收发。
