# module-crew

让多个 Claude 或 Codex 桌面版会话在同一个项目里**并行开发多个模块**：一个模块协调统筹，每个模块会话在自己的 git worktree 里开发；
所有批准都由用户在模块协调里亲手给出；会话中断、压缩或换新会话后，从状态库恢复，不靠对话记忆。

> 版本 0.16.1。已在试点项目和 LIVE-SAAS 演练（阶段丙、短验证）上实地跑过（见 `docs/pilot-report.md`），还没验证的见文末「尚未验证」。

## 0.16.1 的变化（热修：LIVE-SAAS 现场问题）

只修缺陷，不加开关；接口与契约不变（`interface.json` 1.0、session-protocol v2.6），状态库不用迁移。

- **写类 git 命令按 checkTimeout 限时**（S39）：收回 worktree、开模块与派轻任务建 worktree、合并失败后的 `merge --abort`／`reset --hard`、`sync` 的合并与提交，原来分别用只读的 30 秒、60 秒或没有期限，现在都用项目的 `checkTimeout`。超时不再抛 Python 调用栈：退出码 4，写明「删了一半（或建了一半）、状态库没动」和恢复步骤。
- **`merge cleanup` 能收完删了一半的 worktree**（S39）：worktree 里只剩已跟踪文件被删、没有改过／暂存／未跟踪的文件、已合入集成分支（已取消、已升格的轻任务不查这一条）、会话登记仍是这个模块或任务时，先说明再 `git worktree remove --force` 续做；目录已不在而 git 仍登记时先 `git worktree prune`；其他情况照旧拒绝并给出 `git checkout -- .` 后重跑的办法。
- **模块协调不在集成 checkout 时有提示**（S40）：换宿主的交接说明写明新开会话不要用 worktree；`bind`、`status` 发现模块协调的当前目录不是集成 checkout 时提示一行；`.agent/config.json` 被 git 忽略、当前 worktree 里没有时，spec-guard 两项体检按集成 checkout 判断，不再误报。
- **新 worktree 补上被忽略的 `.agent/config.json`**：`start prepare`、`task dispatch` 建 worktree 后，集成 checkout 里这个文件被 git 忽略、新 worktree 里没有时复制过去（不会被提交），spec-guard 写 checkout 角色时读得到 `moduleConcurrency`。
- **模块会话能跑 `check quick`**（S42）：`check quick`、`check show`、`check list` 不再被当成模块协调专用命令拦下（打开 `checkLedger` 后原先所有模块的快检查都跑不了）；`check baseline` 仍只有模块协调能跑。
- **提交标题只取第一行**（S44）：「改什么」里有换行时，`change land` 等拼出的提交标题不再把正文带进去（commitlint `body-leading-blank`）。
- **重开模块先交 Spec 修订**（S45）：Spec 仍是批准状态、但 todo 新加的第一个未勾项是 Spec 修订（REV-SPEC、修订 Spec）时，开工说明写先改 Spec、交 Spec 节点，不再写「只交 Plan」。
- 升级后：在用的 Claude 会话在原会话里 `/clear` 一次；Codex 侧重新装本插件并完全退出 ChatGPT 再打开。动 Codex 侧插件前先备份 `~/.codex/config.toml`；`codex plugin marketplace remove` 报「not configured」时停下核对，不要接着装。

更早的版本见 [CHANGELOG.md](CHANGELOG.md)。

## 前提

| 依赖 | 要求 |
|---|---|
| 宿主 | 模块协调：平时在 Claude 桌面版（Code 标签），一批收尾后可用 `coordinator handover` 整体换到 Codex 桌面版（见「换宿主」）；模块会话：Claude 桌面版或 Codex 桌面版。都在同一台 Mac 上 |
| agent-relay | **必需**，接口主版本 2。会话之间用它收发消息（`bridge_send` 的 `bodyFile`、`replyTo`、`expectsReply`） |
| spec-guard | 项目已启用本地多 Spec 约定（`spec/CAPABILITY-MAP.md`）。开工、批量批准、合并依赖 spec-guard 0.68.0（`interface.json` 1.1、`/map --json` 的 `moduleConcurrency`、`startable`）；第十版的声明范围、自治档位、额度外包的范围核对要 0.85.0（interface 1.11） |
| 项目 | git 仓库，能建 worktree；有一条能在本地跑完的完整检查命令，合并后用它判断集成是否通过 |
| delegate | 可选，只有打开额度外包（`codexOffload`）时才要：0.6.0 起（interface 1.1）；1.2 起超时也能续跑 |
| 运行环境 | Python 3（只用标准库） |

消息格式以 [session-protocol](../session-protocol) 契约为准（现钉住 v2.6）。

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

它检查 git、agent-relay、spec-guard、项目是否启用 spec-guard、spec-guard 规划层、集成分支与状态库七项，任何一项阻塞都会写明原因。

然后在你想让它统筹的那个会话里，明说「把本会话升级为模块协调」，由它运行 `module-crew coordinator up`。没升级的会话照常用，插件不管；有了模块协调之后，别的会话会被提醒一次。

## 角色

- **模块协调**（加载 `crew-coordinator` skill）：统筹、收件记账、转达用户的决定、管集成分支与公共文件、合并。不开发任何模块，不出审查结论。
- **模块会话**（加载 `crew-dev` skill）：只在自己的 worktree 里开发一个模块，只和模块协调说话；被挡住必须发【等待其他会话】。

状态库放在仓库公共 git 目录下的 `module-crew/`（`events.jsonl` 是事实来源），所有 worktree 共用一份；不进版本库。

## 一次完整流程

1. **开工**（模块协调）
   - `module-crew start plan`：按能力图的 Build order 提议可开的模块（不超过空位，默认上限 2）。
   - 只问用户一次「开这 N 个吗？」，用户答应后
     `module-crew start prepare <模块>… --original-file <原话文件> --project-short <简称>`：为每个模块建 worktree（`<仓库名>-crew/<模块>`）、登记会话、生成开工说明。
   - 用桌面版在每个 worktree 里开新会话，第一条消息用开工说明全文。
2. **写 Spec 与 Plan**（模块会话）：写好后发【交审】；收到开工类【协调通知】之前不构建。
3. **批量批准**（模块协调）
   - `module-crew review add` 记下每条【交审】，`module-crew review batch` 汇总，把要点写在正文里交用户审。
   - 用户批准后 `module-crew review approve <编号>… --original-file <原话文件>`：在集成分支记批准标记，生成【用户答复】与开工通知。
   - 模块会话单独执行 `module-crew sync` 把集成分支合进自己的分支（Spec／Plan 冲突自动取集成分支版本）后开始构建；写 Plan 前可用 `module-crew review show C<号>` 读审查原文。
4. **公共文件**：模块会话不改公共文件，发【公共变更请求】；模块协调 `change add` → 在集成 checkout 改 → `change land`，其他模块收到同步基线通知。
   - **声明范围开关 `declaredScope`**（默认关，`module-crew config set --declared-scope on --original-file <原话文件>` 凭用户原话打开）：Plan「预先声明」名单内的公共文件模块直接在自己分支改（`module-crew scope <文件>` 可查），最终验收单列「声明内公共文件」一节一并审，默认合并时才进集成分支。确实要提前进集成分支时模块照旧发请求，名单内的由模块协调 `module-crew change land <编号> --from-module` 从模块分支取文件落地、不问用户，`change landed` 汇总给用户；名单外照旧。开关打开时，有依赖关系的模块不同时开工。读不到 spec-guard 1.11 的 `declaredScope` 时一切照旧。
5. **合并**
   - 模块做完发最终验收【交审】，用户批准后 `module-crew merge approve <交审编号> --original-file <原话文件>`。
     提请批准时按 spec-guard 的最终验收小项排：做了什么、验收结果、改了哪些文件（文档表、代码文件表——新增／修改／删除与行数，超出 Plan 的标出——、提交表、新增依赖表），以及 Spec 中途改过吗（改过就附差异）；这几张表由 module-crew 从版本库算出，不用模块自己报。
     声明范围开关打开时，「代码」表之后多一节「声明内公共文件」（提前落地过的标出请求号与提交），新增依赖表里没声明过的标「（未声明）」。
   - `module-crew merge run`（第一次带 `--check-command "<完整检查命令>"`）：按 Build order 一次只合一个，`--no-ff` 合入本地集成分支后跑完整检查；
     不过就把集成分支重置回合并前（模块分支原样保留）并退回该模块，冲突就中止并退回。
   - 合并成功：该模块收到收尾通知，其他在用模块收到同步基线通知。
   - 完整检查可能很慢：模块协调把 `merge run` 放后台跑，照常回话（Codex 上的模块协调用 `merge run --detach` 再 `merge result` 取结果，见「换宿主」）；跑的时候别的写集成 checkout 的命令会被合并锁挡住（退出码 6），`status` 显示正在跑的合并。
6. **收尾与推送**
   - 用户同意后 `module-crew merge cleanup <模块> --original-file <原话文件>` 收回 worktree（分支保留）。
   - `module-crew merge push-plan` 预告；用户明确授权后 `module-crew merge push --original-file <原话文件>`，推到远端新分支 `crew/batch-<号>` 并开一个 PR。
   - **远端合并始终由用户做**；不开自动合并，不推集成分支本身。

每条要发的消息，命令都会生成正文文件；模块协调用 `bridge_send` 的 `bodyFile` 原样发出，不改一字。

## 检查记账（第十版，项目开关 checkLedger，默认关）

模块协调凭用户原话设快检查命令（项目自己的脚本，只跑受影响部分）并打开 `checkLedger` 之后：

1. **平时快检查**：同步后、自测、交最终验收前，模块会话跑 `module-crew check quick`；结果按树哈希记进状态库的检查账，同一棵树不重跑。通知里的「跑完整检查」都改成「跑 `module-crew check quick`」。
2. **完整检查只在合并队列里跑**：`merge run` 照旧每次跑，结果自动记账；合入后的勾选、批准标记提交继承这次结果。
3. **基线只跑一次**：集成分支被落地或不经队列的提交推进后，模块协调把 `module-crew check baseline` 放后台跑一次；红了自动建一个「修基线」bug 任务，不再让每个模块各记一遍。
4. **最终验收引用检查账**：交审事项自动附上那棵树的检查记录，模块不再提交证据文件。`change land` 提交前也先跑快检查。

开关关着时一切照旧。

## 自治档位（第十版，spec-guard autonomyTier，默认 strict）

档位存在 spec-guard 的 `.agent/config.json`，设或改都要用户原话：模块协调先跑 `module-crew tier --preflight` 确认本机 spec-guard ≥ 0.85.0，再引用原话用 `/spec-guard:config` 写入并单独提交。

- `strict`（默认）：和今天一样。没设档位时 module-crew 什么都不变，也不给升档建议。
- `standard`：Spec 与 Plan 一起交审（同一句原话里另设 `reviewCadence=combined`，spec-guard 不联动它）；`declaredScope` 没设过时按 Plan「预先声明」处理公共文件。
- `relaxed`：再把同步、快检查与检查账、不经队列的提交、提前落地这几类消息改为收尾时一次汇总（`module-crew tier digest`）。
- **升档只建议**：当前档位开始后连续 3 个合入的模块合并退回 0、撤销 0、返工 ≤ 1、用户退回 0，`tier`、`status`、`merge run` 提示可以升一档，用户确认才升。
- **出事自动降一档**：合并因模块原因退回、撤销合并批准、返工满 3 次、基线新跑出失败，生效档位立刻降一档并告诉用户；恢复用 `module-crew tier restore`，要原话。
- **底线**：任何档位都不低于 spec-guard 共享检查点规则「自治档位与底线」——能力图、Spec（可以和 Plan 一起批）、最终验收要用户批，三种情况必停，合并队列里照样跑完整检查。

## 额度外包（第十版，项目开关 codexOffload，默认关）

打开检查记账后，模块协调凭用户原话打开 `codexOffload`，Spec、Plan 照旧由模块会话写、由用户批，之后：

1. **开工**：开工通知改成外包写法，模块会话 sync 后发【等待其他会话】停下；外包条件不满足（delegate 低于 1.1、模块协调在 Codex、Codex 把项目标为不信任等）时不发开工通知，交用户决定。
2. **派出与收结果**：模块协调 `module-crew offload start <模块>` 取 todo 第一个未勾的 Task，照输出执行 `/delegate:run --write --resumable`（放后台）；跑完 `module-crew offload settle` 收结果。一次只派一个 Task（delegate 单次上限 540 秒）。
3. **三种结束状态**：做完就核对改动都在本模块范围内（spec-guard scopeCheck，加预先声明名单）、跑快检查，在模块分支代提交；Codex 要问用户就把问题原样转给用户，带着答复 `offload resume`；超时不提交、先交进度，续跑要用户点头。认不出的一律停下问用户，不自动重派。
4. **交还**：做到检查点或最终验收时 `offload handback` 交还模块会话，最终验收照常由用户批。Codex 只改文件，从不提交、推送或删除。

开关关着时一切照旧。

## 轻任务（单个需求或 bug，第六版）

不值得开模块的活走轻流程，不写 Spec、不调 spec-guard，但和模块一样只从合并队列进集成分支：

1. **记任务**（模块协调）：用户明说要做后 `module-crew task add --type feature|bug --title … --what … --expect <预计文件> --done <完成标准> --original-file <原话文件>`。
   预计文件和在做的任务或模块分支已改的文件重叠就排队，`task next` 按 bug 在前提为可开。
2. **派出**：`module-crew task dispatch T<号>` 建 `task/t<号>` 分支与 worktree、登记轻任务会话（不占多模块名额）、生成开工说明；模块协调用桌面版开会话，第一条消息用开工说明全文。
3. **做与交回**（轻任务会话，`crew-dev` skill 的「轻任务」一节）：bug 先补复现测试；完整检查通过后发最终验收【交审】（`模块：无`，带「任务：T<号>」）。
   `review add` 会比对实际改动和任务单，多改的文件和越界重叠写进交审。
4. **批准与合并**：用户点一次批准，`merge approve` → `merge run`。队列顺序：bug 任务、模块（Build order）、需求任务。合入后在用的模块和在做的任务收到同步通知；`merge cleanup T<号>` 收回 worktree（分支保留）。
5. **做大了**：轻任务会话停下发升格请求（【等待用户】「卡住选做法」），用户选 A 升格（`/spec-guard:add-module`）、B 缩小（`task scope`）或 C 取消。

决策收件箱升到契约 v2.5 之前，轻任务的提请批准不经过它，模块协调在会话里直接问用户。

## 修订已完成的模块（第九版）

已合入的模块要返工时，不新开模块，原地重开：

1. **在 spec-guard 里重开**（用户或模块协调按 spec-guard「返工与小模块」的做法）：在原 `tasks/<模块 id>/todo.md` 追加未勾任务、`plan.md` 补一节；超出原范围的把 Plan 改回 pending。`/map` 会把它显示为进行中。
2. **确认旧一轮已收回**：`merge cleanup <模块 id>` 做过；没做 `start prepare` 会拒绝。
3. **用户点名后开会话**：`module-crew start prepare <模块 id> --original-file <原话文件>`。旧模块分支已合入就快进到集成分支再开 worktree，有没合进来的提交就拒绝、交用户决定；
   新邮箱名带轮次后缀（`<简称>-<模块 id>-r2`），开工说明写明「只做 todo 新加的未勾项」。Spec、Plan 都还是批准状态时点名即开工，Plan 要重新交审时先交审。
4. **退役旧邮箱名**：由用户在 agent-relay 里退役第一轮的名字（新名字不用 `reactivate`）。之后的交审、合并、收回和新模块一样，旧一轮的批准与合并记录不算进新一轮。

## Codex 模块会话

模块协调在 Claude 桌面版时，模块会话也可以开在 Codex 桌面版里；模块协调本身也可以在一批收尾后整体换到 Codex，见下一节「换宿主」。

1. 在 Codex 里装同一版本的 module-crew（`.codex-plugin/plugin.json`，提供 Codex 版 `crew-dev` 与 `crew-coordinator` 两个 skill）；Codex 插件更新后要完全退出 ChatGPT 应用再打开。
2. 模块协调用 `module-crew start prepare <模块>… --host codex --original-file <原话文件>` 开工；要混用就按宿主分两次。
3. 用户在 Codex 里新建任务，工作目录选那个模块的 worktree，第一条消息贴开工说明全文。
4. Codex 会话先跑 `module-crew host-check`：检查登记、版本、能否写 git 目录、能否读状态库。开工说明给的命令是状态库里的固定入口 `<git公共目录>/module-crew/bin/module-crew`（`start prepare`、`coordinator up` 时写入），它每次转给当前安装的 module-crew，升级后不用换；0.12.0 之前开工的 Codex 会话记着的是带版本号的旧路径，升级后由模块协调转告一次新入口。
5. Codex 默认沙箱不让写 `.git`：第一次提交会弹提权，用户在那个 Codex 会话里批准（有「本会话一直允许」就选）。
6. ChatGPT 应用重启后 Codex 会话不会自动加载，要用户逐个点开；Codex 会话掉了联调身份时用原名重新注册即可。

## 换宿主（空档，第八版）

一批模块收尾后的空档里，模块协调连同下一批模块会话可以整体在 Claude Code 与 Codex 之间来回换。换不换、换到哪边由用户决定；module-crew 不看额度、不自动换，也不做模块做到一半换宿主。

1. **什么时候能换**：没有在用的模块会话与轻任务会话、没有排队或进行中的合并、module-crew 侧没有未结的事项、公共变更请求和等待记录。
   最后一个会话收回时 `merge cleanup` 会输出「本批已收尾，具备换宿主的条件」，`status` 也显示这一行。`module-crew coordinator handover --check [--to codex|claude]` 逐条列出哪项不满足；决策收件箱那边的待决请用 decision-inbox 的 waits 再看一眼。
2. **换**：用户明说后，原宿主上的模块协调运行 `module-crew coordinator handover --to codex|claude --original-file <原话文件>`。它改模块协调登记的宿主、按新宿主给集成 checkout 追加权限规则（项目 apply 过才写，原有规则保留），并把逐步交接说明打印出来、存到状态库目录 `handover-guide/`。
3. **照交接说明做**：每一步写明去哪个会话、做什么、做完的样子。要点：
   - Claude → Codex：先归档 Claude 上原来的模块协调（会话）（agent-relay 不让接管还在运行的 Claude 会话）；在 Codex 里信任项目（贴开场文字之前）；在 Codex 新建任务、目录选集成 checkout、贴开场文字；它用 `takeover:true` 加 `wake:{app:"codex", sessionId:<CODEX_THREAD_ID>}` 接管邮箱名，再 `bind --takeover`（会弹提权）；之后每轮开头不带 takeover 重新注册。
   - 新宿主的规则文件（如 `.codex/rules/module-crew.rules`）没被 git 忽略时，规则没写上，交接说明多一步：模块协调在 `.gitignore`（公共文件）加上这个文件并提交，再凭用户原话重跑 `permissions apply`。
   - Codex → Claude：先确认原 Codex 任务已停（agent-relay 判断不了，它被接走后也收不到通知）；在 Claude 桌面版新开会话、贴开场文字；它用 `takeover:true, wake:"auto"` 接管，再 `bind --takeover`。
   - `bind --takeover` 只认登记宿主上的会话：没先跑 handover 就在另一边接管会被拒。
4. **之后**：`start prepare`、`task dispatch` 不写 `--host` 时用模块协调所在的宿主。模块协调在 Codex 时只开 Codex 会话（Codex 叫不醒停掉的 Claude 会话），`--host claude` 被拒。
5. **代价**：Codex 上写状态库、提交、合并都在 `.git` 里，要用户点提权；Codex 模块会话要用户手动开；ChatGPT 应用重启后要逐个点开。批准照旧由用户在该端模块协调那里亲口给。
6. **前提**：插件里要有 Codex 版模块协调规矩（`codex-skills/crew-coordinator/SKILL.md`，第八版起随插件发）；没有时 `handover --to codex` 拒绝执行，换回 Claude 不受影响。

### 模块协调在 Codex 上（第八版）

Codex 版 `crew-coordinator` skill 管下面这些与 Claude 不同的地方，交接说明的开场文字会让新线程加载它：

- **每轮开头三步**：Codex 每轮重启 MCP、会丢联调身份，也没有钩子注入角色。每一轮先用原名 `bridge_register`（`wake:{app:"codex", sessionId:<CODEX_THREAD_ID>}`，不带 takeover）→ 运行 `module-crew status`（首行写明本线程是不是登记的模块协调）→ 读收件箱。
- **提权**：几乎所有模块协调的写命令都写状态库或 `.git`，Codex 默认沙箱不让写。skill 列出要「申请在沙箱外运行」的命令，用户在模块协调那个线程里点批准；被沙箱拒绝时报错会带「申请在沙箱外运行」，不换写法绕过。
- **预检**：接手后在集成 checkout 跑 `module-crew host-check`，按模块协调查：登记、版本、能否写 git 公共目录、能否读状态库、找得到 spec-guard、固定入口在不在。
- **合并长检查**：Codex 没有「后台跑、跑完叫醒」。`module-crew merge run --detach` 拿到合并锁后把合并交给后台进程、立即返回，输出写到状态库目录 `merge-output/C<号>.log`；
  `module-crew merge result [C<号>] [--wait <分钟>]`（单次最多等 8 分钟；第一次取到结果时记进状态库）分段取结果，跑完时打印与前台 `merge run` 相同的内容、以同样的退出码结束，还在跑时退出码 6。`status` 会提示「已结束，运行 merge result 取通知」。
- **开会话**：模块会话、轻任务会话都开在 Codex，由用户手动开；`start prepare`、`task dispatch` 输出末尾有「请用户去 Codex 新建任务」一段，逐个写出工作目录与开工说明文件。
- **找插件**：module-crew、spec-guard、agent-relay 都按 Claude 的插件安装记录找（Codex 沙箱里读得到）；Codex 侧自己的插件安装 module-crew 不读，所以本机要在 Claude Code 里装着这些插件。
- **代价**：提权次数多；ChatGPT 应用重启后要逐个点开模块协调和模块会话；决策收件箱在 Claude，它被桌面版停掉时 Codex 叫不醒，要用户点开。

## 出状况时怎么办

| 情况 | 做法 |
|---|---|
| 不知道哪个会话停下了 | `module-crew sessions` 列出每个模块会话的最后动静、未关的等待记录与事项、当前档位、挂起原因；只列事实，结合 agent-relay 在线状态自己判断 |
| 某个模块会话在「等待审批」 | 权限弹窗只能用户去那个会话亲手点；模块协调醒来时会提醒，并核对各模块会话的权限模式有没有变宽 |
| 集成分支上有不经合并队列的提交 | `status` 会显示数量；`module-crew unqueued` 列出（短号、作者、时间、标题），`--notify` 给在开发的模块与在做的轻任务发同步通知，同一批只报一次；`merge run` 合并前也会自动做这一步。插件不拦、不撤回 |
| 消息发出去对方没反应 | 桌面版会停掉空闲会话，agent-relay 叫不醒（`pendingReason: offline`）；用桌面版跨会话消息发一句「去读 agent-relay 收件箱」 |
| 模块在等外部条件（设计稿、别人交付） | 用户同意后 `module-crew suspend <模块> --reason "<原因>" --original-file <原话文件>`，不再占名额；按输出把挂起正文发给模块会话，它在自己的 worktree 里用 spec-guard 挂起。条件满足、用户同意后 `module-crew resume <模块> --original-file <原话文件>` |
| 会话崩溃或要换新会话 | `module-crew resume-kit <模块>` 生成恢复说明；用户同意后 `module-crew takeover <邮箱名> --original-file <原话文件>`，在原 worktree 开新会话，第一条消息用恢复说明，新会话用同一个邮箱名重新注册 |
| 模块协调要重开或换会话 | 在原会话里 `/clear`，或退出应用再打开，身份会自动接上；不要新开会话。已经新开了：用户同意后在新会话运行 `module-crew bind <邮箱名> --takeover --original-file <原话文件>`（同一仓库任一目录），旧会话随即失效；模块协调的写命令只有登记的会话能跑（别的会话退出码 7），`status` 里标着「← 本会话」 |
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
   带交审要点全文、「批了会怎样」、「产物」（路径 ＠ 提交，重交带上一版）、「交审原文」「审查原文」（`<状态库>/originals/` 下的原文文件）和「待你决定」（字段名：待用户决定）。
5. 「你的答复」要答到每个 D（如「A；D1 B」）；没答全批准命令退出码 3、什么都不做。退回、等审查这类答案分别让交审退回或保持未答。
6. 最终验收批准后、合并前可以 `merge revoke <C号>` 撤回；`status` 与 `sessions --json` 显示返工轮次（`review` 字段）。

**接入决策收件箱**：

1. 在模块协调里由用户亲口登记可信批准来源：`module-crew source add <决策收件箱邮箱名> --kind hub --original-file <原话>`；审查者登记为 `--kind lead`。
2. 提请批准的正文逐条用 bodyFile 原样发给决策收件箱；要用户决定的事只在那里问，会话里不放可以点的决定按钮。
3. 决策收件箱转来【用户答复】后，批准命令带 `--source <决策收件箱> --source-item <H> --source-relay-id <消息号> --source-from <实际发件人> --original-file <那条消息>`，用户原话从消息里读出；实际发件人不是来源本身或是模块会话时拒收。
4. `module-crew source map <H>` 查一个待决事项批准了哪些 C 编号。
   待定问题（契约 v2.6）：决策收件箱登记为 2.6 及以上、或没有决策收件箱时，给用户看的待定问题编成 `C<交审号>-<序号>`（如 C15-1），登记低于 2.6 时照旧用 D；答复块一块只答一件事（如「C16 A；C16-1 B」）。登记 2.6：`source add <邮箱名> --kind hub --protocol 2.6 --original-file <原话>`。
5. 外部插件读 `module-crew sessions --json`（`schemaVersion` 1：module、relayName、worktree、stage、stageText、suspended、lastActivity、review；0.4.0 起加停滞事实 startedAt、commits、asks、returns、waitUser，见 [spec/crew-stall-signals.md](spec/crew-stall-signals.md)，只给事实、不判断是否卡住），出口与契约版本登记在根目录 `interface.json`。

**并行边界重叠**（`review batch` 末尾）三种结论：有冲突就列出模块与路径；比对过且没有冲突写「无（已按交审中的 Spec 比对）」或「无（已按集成分支上的 Spec 比对）」；比不了写「未比对：<原因>」（例如交审中的 Spec 还没落到集成分支、spec-guard 低于 1.10 没有 scopeOverlap）。只有比对过才写「无」。

**不配决策收件箱、不配审查者时**：一切照常在模块协调里由用户亲手批准；没有审查者就不送审、不返工，提请批准里写「未审查」；「待你决定」的问题由模块协调直接问用户。

module-crew 自己的编号对外一律写 C 前缀（如 C15），`#数字` 只表示决策收件箱的待决事项号；命令参数写 `15` 或 `C15` 都行。
审查者用【负责人转交】转来的批准只记账、不写批准标记（spec-guard 只认用户亲手与决策收件箱转来的批准）；带来源批准时，给模块的【用户答复】按契约带「转自」，命令同时给出发回决策收件箱的【已恢复】「结束：#H」。

## 命令一览

```text
module-crew status [--json]                      体检与全貌（只读）
module-crew coordinator up|down --original(-file)  把本会话升级为模块协调／关闭（一个仓库一个）
module-crew coordinator handover --check|--to     空档换宿主：核对收尾条件（只读）／换到 codex 或 claude 并生成交接说明
module-crew task add|list|show|next|cancel       轻任务记录（单个需求或 bug，T 编号）：预计文件和在做的活重叠就排队，bug 在前
module-crew unqueued [--notify] [--json]         集成分支上不经合并队列的提交：列出／通知各模块同步
module-crew task dispatch|scope                  派出可开的轻任务（worktree、登记、开工说明）／升格请求选缩小后改任务单
module-crew store init|check                     状态库
module-crew protocol check <文件>                消息自检
module-crew inbox add <文件> --from --relay-id   收件记账
module-crew answer <编号> --original(-file)      转达「你的答复」
module-crew start plan|prepare                   开工
module-crew config set [--commit-prefix <值>] [--check-timeout <秒>] [--declared-scope on|off] --original(-file)  已开工项目改提交信息前缀（空字符串表示不加）、提交与检查的时限或声明范围开关
module-crew config set --quick-check-command "<命令>" | --check-ledger on|off --original(-file)  快检查命令与检查记账开关（默认关）
module-crew check quick|baseline [--rerun]       检查记账：模块 worktree 里跑快检查／模块协调对集成分支跑一次完整检查（放后台），同一棵树不重跑
module-crew check show [<提交>]|list [--json]    检查账（只读）：一个提交的树跑过哪些检查／最近的记录
module-crew tier [--json] | tier --preflight      自治档位（只读）：设的档位、降档上限、生效档位、证据与升档建议／写 autonomyTier 前核对 spec-guard
module-crew tier restore --original(-file)       降档后恢复一档（要用户原话）
module-crew tier digest [--json] [--mark-told]   relaxed 档的收尾汇总；--mark-told 记为已汇总（只是记账）
module-crew config set --codex-offload on|off --original(-file)  额度外包开关（默认关；要先开检查记账）
module-crew offload start <模块> [--again]        额度外包：派出下一个 Task，给出 /delegate:run 写法（重派要原话）
module-crew offload settle <模块> --output <文件> --exit <码>  收 delegate 的输出：做完的核对范围、跑快检查后代提交，其余停下问用户
module-crew offload resume|decline <模块> --original(-file)  带用户的答复续跑／外包条件不满足时改由模块会话构建
module-crew offload handback <模块>               交还模块会话（检查点、最终验收，或用户选交还）
module-crew offload show [<模块>] [--json]        外包状态（只读）
module-crew review add|batch|approve|answer      交审与批量批准
module-crew change add|list|land|answer [--reason superseded]  公共变更请求（被取代的可直接关；检查记账打开时 land 先跑快检查，--skip-quick-check 要原话）
module-crew change land <编号> --from-module / change landed [--mark-told <编号>…]  名单内提前落地（从模块分支取文件）／待汇总给用户的提前落地
module-crew scope [<文件>…] [--json]             模块 worktree 里查文件在不在 Plan「预先声明」名单内（只读）
module-crew merge approve|revoke|queue|run|cleanup|push-plan|push
module-crew merge record C<号> --original(-file)  合并收尾超时、状态库没记下合并时补记
module-crew merge run --detach / merge result [C<号>] [--wait <分钟>]   后台合并（Codex 上的模块协调用）／取它的结果（第一次取到时记进状态库）
module-crew host-check [--json]                  宿主预检：模块 worktree 里按模块会话查，集成 checkout 里按模块协调查
module-crew suspend|resume|sessions|resume-kit|serial
module-crew takeover <邮箱名> --original(-file)  换会话接管
module-crew bind <邮箱名> --takeover --original(-file)  新会话一步接手模块协调（同一仓库任一目录，旧会话失效）
module-crew source add|remove|list|map           可信批准来源（决策收件箱、审查者）与对照；hub 可带 --protocol 2.3|2.4|2.5|2.6（不写按 2.4）
module-crew review note [--then-batch]|batch --for-hub   审查结论、返工、提请批准正文（一个模块一条）
module-crew ticket close <编号> --reason …        模块协调关等待记录
module-crew wait add --file --to --relay-id --about  记下模块协调自己发出的等待记录
module-crew sync                                 模块 worktree 里合入集成分支（模块会话用）
module-crew review show <C号> [--submission]     审查原文全文与 sha256（只读）
module-crew permissions plan|apply|verify|remove  宿主权限预配与推送守门
module-crew hook session-start|prompt|session-end  插件钩子入口（永远退出码 0；只写见到记录与清空交接）
```

需要用户批准的命令都要 `--original` 或 `--original-file`：只记用户在模块协调里亲手输入的话，别的会话转来的话不算批准。

## 开发

```bash
python3 -m unittest discover -s tests -v
```

需求与设计在 `docs/requirements-record.md`、`spec/CAPABILITY-MAP.md` 与 `spec/<模块>.md`。

## 权限预配

不可逆操作不能只靠弹窗：宿主确认（ask 规则或默认确认）在代开会话里也会弹，但点一次「允许」就执行了，点的人未必清楚上下文。module-crew 把第 44 条范围内的常规操作（含装依赖与往项目里加新包：`npm ci`、`npm install <包名>`、`pnpm add`、`yarn add`、`uv add`、`.venv/bin/pip install` 等）写成宿主认的放行规则，把推送、删除、全局安装（`-g`／`--global` 在任意位置、`yarn global`、`uv --system`、`brew install`）、改全局配置写成禁止；裸 `pip install <包名>` 不写规则、交宿主默认确认（不在 venv 里会装进系统 Python）；Codex 侧加新包也不写规则，因为前缀规则挡不住 `npm install x -g`。不可逆操作写禁止、不写 ask：禁止规则直接拒绝，不依赖有人当场判断。（0.5.2 更正：早先说代开会话里 ask 确认不会出现，经 E3 会话记录核实不成立，两次 `git push` 都是弹了确认、被点了「允许一次」。）再用 git 的 pre-push 钩子守住推送：

0. 先有模块协调登记：在要当模块协调的会话里运行 `module-crew coordinator up`（或已经用 `start prepare` 开过工），状态库里有了模块协调和集成分支，`plan`／`apply` 才列得出集成 checkout 与各模块；没登记时 `plan` 会直接提示先 `coordinator up`。
1. `module-crew permissions plan`：只读预览每个 checkout（集成 checkout 与各模块 worktree）要追加什么、文件有没有被 git 忽略、钩子能不能装、Codex 项目是否受信任，以及别处（主 checkout 的设置、用户设置等）有没有 ask 或禁止规则会盖过要写的放行——宿主先看禁止、再看 ask、最后看放行，模块 worktree 的会话也读主 checkout 的本地设置。
2. `module-crew permissions apply --original-file <用户原话>`：Claude 写 `.claude/settings.local.json`（只追加条目），Codex 模块写 `.codex/rules/module-crew.rules`；有一个文件不能写就全部不写。之后 `start prepare` 新开的模块自动跟随。module-crew 自己的命令放行的是状态库里的固定入口（0.12.1 起），升级插件后不用重跑。
3. 开好会话后 `module-crew permissions verify`：四条应直接运行、一条应被拒的实测清单；结果用 `verify --record` 记下，`status` 显示每个会话最近一次实测，没测过写「权限未实测」。
4. 推送只经 `module-crew merge push`：钩子拒绝模块 worktree 的推送，以及集成 checkout 上没有一次性放行凭证的推送。你自己在终端推送可以加 `--no-verify`。仓库设了 `core.hooksPath`（如 husky）或已有 pre-push 钩子时不装，`plan` 会写明。这时推送只靠宿主的禁止规则：2026-10-19 在 crew-rehearsal（husky 仓库）实测，由别的会话代开的 default 权限模式会话里 `git push` 被禁止规则拦下、不弹窗；没有 git 钩子这一层兜底，用 husky 的项目（如 LIVE-SAAS）都是这种情况。
5. Codex 的项目级规则只在项目被 Codex 信任后生效；module-crew 不改你的全局配置，只提示。
6. `module-crew permissions remove --original-file <用户原话>`：只撤 module-crew 加的条目；按「不删文件」的约定，Codex 规则文件清空、钩子改成空操作，可以手动删除。

spec-guard 的命令入口路径带版本号，暂不放进放行清单。细节见 [spec/crew-host-permissions.md](spec/crew-host-permissions.md)。

## 尚未验证

已经实地验证过的：真实 spec-guard 与 agent-relay、会话间真实收发、开工、批量批准、审查就近与决策收件箱转达、合并与退回、挂起与恢复、换模块协调与换模块会话、退回串行、收尾与推送到本机远端；权限预配的禁止规则（编辑 worktree 里的 `.claude/` 被拒，0.8.0）。还没验证的：

- 用 `gh` 真正开 PR（试点远端是本机裸仓库，只打印 PR 正文）。
- 权限预配的放行规则：在本机宿主上和不写规则时看不出差别（0.8.0 对照实测），是否真的减少弹窗还没证实。
- 0.9.0 起的钩子按会话认身份：只用钩子事件数据做过测试，没在真实桌面会话里看过注入出来的文字。
- 桌面版整个退出重开后会话 id 是否不变：压缩、`claude --resume` 接上都实测不变，退出整个桌面版这一种没测。
- 0.12.0 的 Codex 固定入口：2026-10-23 在真实 Codex 沙箱里跑过 `status`（读得到 Claude 的安装记录）与 `host-check`（写 `.git` 要提权，提权后能提交）；登记过的 Codex 模块会话完整走一遍 bind、交审还没测。
- 第十版四个开关：都只用测试和本机接口实测验证过，还没在真实项目上打开试跑（留给 LIVE-SAAS 下一轮，量同步与核验类提交占比、每个模块的批准次数等四个数）。额度外包对 delegate 0.6.0 真跑过一次（done），1.2 的 timeout 续跑只用夹具测过；多个 Task、needs-input 续跑的整轮外包没实跑。自治档位的升档门槛与收尾汇总时机是先定的，等试点数据再调。
- 第八版的模块协调在 Codex 上：只用测试验证过。`merge run --detach` 的后台进程能否活过 Codex 的一轮、提权是否随之继承，单次工具调用最长能等多久，一次提权批准能覆盖多少条命令，都还没在真实 Codex 线程里试过。
