# 使用手册

怎么用 module-crew 在一个项目里并行开发多个模块。安装与前提见 [README](../README.md)，每条命令的参数见[命令参考](commands.md)，内部怎么运作见[架构](architecture.md)。

## 术语

| 名称 | 意思 |
|---|---|
| 模块协调 | 统筹整个项目的那一个会话：收件记账、转达用户的决定、管集成分支与公共文件、合并。一个仓库只有一个 |
| 模块会话 | 只开发一个模块的会话，在自己的 git worktree 里，只和模块协调说话 |
| 轻任务会话 | 只做一个轻任务（单个需求或 bug）的会话，不写 Spec，同样在自己的 worktree 里 |
| 审查者 | 可选。登记后，交审先送它审，用户只看要拍板的事 |
| 决策收件箱 | 可选。另一个插件（decision-inbox），把各会话要用户决定的事汇到一处问 |
| 集成分支 | 各模块合并进去的本地分支（通常是 `main`），所在的 checkout 叫集成 checkout，模块协调在那里工作 |
| worktree | 每个模块、每个轻任务各一个 git worktree，默认建在 `<仓库名>-crew/<模块>` |
| 状态库 | 放在仓库 git 公共目录下的 `module-crew/`，所有 worktree 共用一份，不进版本库；`events.jsonl` 是事实来源 |
| 能力图 | spec-guard 的 `spec/CAPABILITY-MAP.md`：模块清单、依赖与 Build order |
| 用户原话 | 用户在模块协调里亲手输入的话。要批准的命令都要带它；别的会话转来的话不算批准 |
| C 编号 | module-crew 自己的事项编号（交审、请求、合并批准等），如 C15；命令参数写 `15` 或 `C15` 都行 |
| W 编号、T 编号 | 等待记录、轻任务 |
| `#数字` | 只表示决策收件箱的待决事项号 |
| 消息标签 | 会话之间的消息以【交审】【等待用户】【等待其他会话】【公共变更请求】【用户答复】【协调通知】【已恢复】等标签开头，格式由 session-protocol 契约规定 |

## 角色与边界

- **模块协调**（加载 `crew-coordinator` skill）：统筹、收件记账、转达用户的决定、管集成分支与公共文件、合并。不开发任何模块，不出审查结论。
- **模块会话**（加载 `crew-dev` skill）：只在自己的 worktree 里开发一个模块，只和模块协调说话。
  不改公共文件（要改就发【公共变更请求】），不推送、不删除、不改全局配置；被别的会话或外部条件挡住必须发【等待其他会话】；做完发最终验收【交审】。
- **所有批准都由用户在模块协调里亲手给出**：Spec、Plan、最终验收、合并、推送。决策收件箱或审查者转来的决定，要先把它们登记为可信批准来源（见「审查就近与决策收件箱」）。
- 远端合并始终由用户自己做；module-crew 不开自动合并，不推集成分支本身。

没升级为模块协调的会话照常用，插件不管；项目里有了模块协调之后，别的会话会被提醒一次。

## 一次完整流程

0. **升级模块协调**：在你想让它统筹的会话里明说「把本会话升级为模块协调」，它运行 `module-crew coordinator up --short <项目简称> --original-file <原话文件>`。
1. **开工**（模块协调）
   - `module-crew start plan`：按能力图的 Build order 提议可开的模块（不超过空位，默认同时最多 2 个）。
   - 只问用户一次「开这 N 个吗？」，用户答应后
     `module-crew start prepare <模块>… --original-file <原话文件> --project-short <简称>`：为每个模块建 worktree、登记会话、生成开工说明。
   - 用桌面版在每个 worktree 里开新会话，第一条消息用开工说明全文。
2. **写 Spec 与 Plan**（模块会话）：注册邮箱名、`module-crew bind <邮箱名>` 登记身份后，写好 Spec 发【交审】；收到开工类【协调通知】之前不构建。
   评审节奏由 spec-guard 的项目配置 `reviewCadence` 决定：`separate`（默认）先只交 Spec，批准后再交 Plan；`combined` 一起交。
3. **批量批准**（模块协调）
   - `module-crew review add` 记下每条【交审】，`module-crew review batch` 汇总，把要点写在正文里交用户审。
   - 用户批准后 `module-crew review approve <编号>… --original-file <原话文件>`：在集成分支记批准标记，生成【用户答复】与开工通知。
   - 模块会话单独执行 `module-crew sync` 把集成分支合进自己的分支（Spec／Plan 冲突自动取集成分支版本）后开始构建；写 Plan 前可用 `module-crew review show C<号>` 读审查原文。
4. **公共文件**：模块会话不改公共文件，发【公共变更请求】；模块协调 `change add` → 在集成 checkout 改 → `change land`，其他在用模块收到同步基线通知。
   - 几条已批请求要一起进集成分支时 `change land <编号> <编号> …` 合成一个提交：先跑检查，任一条不满足或检查不过就整批不提交。
   - 随锁文件校验的保护文件（哈希、批准清单等）凭用户原话用 `config set --protected-file <路径>` 登记；请求改到锁文件时 `change add` 会提示它们可能要连带改。
   - 声明范围开关打开时，Plan 里预先声明过的公共文件模块直接改，见下文「项目开关」。
5. **合并**
   - 模块做完发最终验收【交审】，用户批准后 `module-crew merge approve <交审编号> --original-file <原话文件>`。
     提请批准时按 spec-guard 的最终验收小项排：做了什么、验收结果、改了哪些文件（文档表、代码文件表——新增／修改／删除与行数，超出 Plan 的标出——、提交表、新增依赖表），以及 Spec 中途改过吗（改过就附差异）；这几张表由 module-crew 从版本库算出，不用模块自己报。
   - `module-crew merge run`（第一次带 `--check-command "<完整检查命令>"`）：按队列一次只合一个，`--no-ff` 合入本地集成分支后跑完整检查；
     不过就把集成分支重置回合并前（模块分支原样保留）并退回该模块，冲突就中止并退回。
   - 合并成功：该模块收到收尾通知，其他在用模块收到同步基线通知。
   - 完整检查可能很慢：模块协调把 `merge run` 放后台跑，照常回话（Codex 上用 `merge run --detach` 再 `merge result` 取结果）；跑的时候别的写集成 checkout 的命令会被合并锁挡住（退出码 6），`status` 显示正在跑的合并。
   - 完整检查的时限默认 1800 秒，全量测试慢的项目凭用户原话 `config set --check-timeout <秒>` 调大。
6. **收尾与推送**
   - 用户同意后 `module-crew merge cleanup <模块> --original-file <原话文件>` 收回 worktree（分支保留）。
   - `module-crew merge push-plan` 预告；用户明确授权后 `module-crew merge push --original-file <原话文件>`，推到远端新分支 `crew/batch-<号>` 并开一个 PR。
   - **远端合并始终由用户做**。

每条要发的消息，命令都会生成正文文件；模块协调用 agent-relay `bridge_send` 的 `bodyFile` 原样发出，不改一字。
module-crew 自己的提交信息默认以 `chore(crew): ` 开头，`config set --commit-prefix` 可改（空字符串表示不加）。

## 项目开关

都存在状态库的运行配置里（自治档位存在 spec-guard 的 `.agent/config.json`），默认都关；设或改都要用户原话，由模块协调执行。不打开时一切照旧。

| 开关 | 默认 | 作用 |
|---|---|---|
| `declaredScope` 声明范围 | 关（没设过时跟随自治档位，standard 及以上视为开） | Plan「预先声明」名单内的公共文件模块直接改 |
| `checkLedger` 检查记账 | 关 | 平时快检查、按树哈希记账；完整检查只在合并队列里跑 |
| `autonomyTier` 自治档位 | `strict` | 交审节奏与消息汇总的松紧 |
| `codexOffload` 额度外包 | 关 | 开工后把模块的 Task 交给 Codex 实现 |
| `moduleConcurrency` 多模块并行 | 由 spec-guard 管 | 关掉就退回一次一个模块 |

### 声明范围（`declaredScope`）

`module-crew config set --declared-scope on --original-file <原话文件>` 打开后：

- Plan「预先声明」名单内的公共文件，模块直接在自己分支改、不发公共变更请求（`module-crew scope <文件>` 可查在不在名单内）；最终验收单列「声明内公共文件」一节一并审，默认合并时才进集成分支。
- 确实要提前进集成分支时模块照旧发请求：名单内的由模块协调 `module-crew change land <编号> --from-module` 从模块分支取文件落地、不问用户，`change landed` 汇总给用户；名单外照旧。
- 开关打开时，有依赖关系的模块不同时开工。读不到 spec-guard interface 1.11 的 `declaredScope` 时一切照旧。

### 检查记账（`checkLedger`）

模块协调凭用户原话设快检查命令（`config set --quick-check-command "<命令>"`，项目自己的脚本，只跑受影响部分）并打开 `--check-ledger on`；还要已经有完整检查命令（第一次 `merge run --check-command` 时记下），三者齐了才生效。之后：

1. **平时快检查**：同步后、自测、交最终验收前，模块会话先提交再跑 `module-crew check quick`；结果按树哈希记进状态库的检查账，同一棵树不重跑。通知里的「跑完整检查」都改成「跑 `module-crew check quick`」。
2. **完整检查只在合并队列里跑**：`merge run` 照旧每次跑，结果自动记账；合入后的勾选、批准标记提交继承这次结果。
3. **基线只跑一次**：集成分支被落地或不经队列的提交推进后，模块协调把 `module-crew check baseline` 放后台跑一次；红了自动建一个「修基线」bug 任务，不再让每个模块各记一遍。
4. **最终验收引用检查账**：交审事项自动附上那棵树的检查记录，模块不再提交证据文件。`change land` 提交前也先跑快检查。

### 自治档位（`autonomyTier`）

档位存在 spec-guard 的 `.agent/config.json`。模块协调先跑 `module-crew tier --preflight` 确认本机 spec-guard ≥ 0.85.0，再引用用户原话用 `/spec-guard:config` 写入并单独提交。

- `strict`（默认）：每个节点照常交审。没设档位时 module-crew 什么都不变，也不给升档建议。
- `standard`：Spec 与 Plan 一起交审（同一句原话里另设 `reviewCadence=combined`，spec-guard 不联动它）；`declaredScope` 没设过时按 Plan「预先声明」处理公共文件。
- `relaxed`：再把同步、快检查与检查账、不经队列的提交、提前落地这几类消息改为收尾时一次汇总（`module-crew tier digest`）。
- **升档只建议**：当前档位开始后连续 3 个合入的模块合并退回 0、撤销 0、返工 ≤ 1、用户退回 0，`tier`、`status`、`merge run` 提示可以升一档，用户确认才升。
- **出事自动降一档**：合并因模块原因退回、撤销合并批准、返工满 3 次、基线新跑出失败，生效档位立刻降一档并告诉用户；恢复用 `module-crew tier restore`，要原话。
- **底线**：任何档位都不低于 spec-guard 共享检查点规则「自治档位与底线」——能力图、Spec（可以和 Plan 一起批）、最终验收要用户批，三种情况必停（测试改不红、Spec 没覆盖的决策、高风险不可逆改动），合并队列里照样跑完整检查。

### 额度外包（`codexOffload`）

Claude 额度紧张时，先打开检查记账，再由模块协调凭用户原话 `config set --codex-offload on`（用户口头说「下一个模块交给 Codex」也一样）。之后**开工的**模块：

1. **开工**：`review approve` 批齐 Spec、Plan 时，条件满足就把模块记为交给 Codex，把用户打开开关的原话存成授权文件，开工通知改成外包写法；模块会话在 Codex 上时照旧、不外包。
   条件不满足（delegate 接口低于 1.3 或缺接续、长期限、结果文件、写入授权能力，Codex 把项目标为不信任等）时不发开工通知，交用户决定（`offload decline` 改由模块会话构建）。已经开工的模块不中途换手。
2. **派出与收结果都在模块会话**：`module-crew offload start <模块>` 取 todo 第一个未勾的 Task，给出 `/delegate:run` 写法——第一个 Task `--resumable` 起头，之后 `--continue <runId>` 接着**同一个 Codex 会话**，都带 `--strict --timeout 1800 --authorized-by <授权文件>`，放后台跑；
   跑完 `module-crew offload settle <模块> --output … --stderr … --exit …` 读结果，按结束状态分流。模块协调不调 Codex、不代提交。
3. **结束状态**：做完就核对勾选、改动范围（spec-guard `scopeCheck`，加预先声明名单）、跑快检查，模块会话自己提交；Codex 要问用户就把问题原样转给用户，带着答复 `offload resume`；超时不提交、先交进度，续跑要用户点头。
   核对不过、`unmarked`／`failed`／`empty` 第 1 次自动重来；超时、被停下、回收不了（125）、delegate 拒绝（64）与认不出的状态停下问用户，认不出的一律不当成完成。
4. **退回 Claude**：同一个 Task 连续 2 次没通过，这一项改由模块会话自己写并告诉用户，下一个 Task 照旧交给 Codex；用户在停下时也可以选 `offload takeover`。检查点、最终验收照常由模块会话处理，最终验收由用户批。Codex 只改文件，从不提交、推送或删除。

### 并行与串行

同时开发的模块数默认最多 2 个。想收手、不再并行：`module-crew serial --original-file <原话文件>`——不再开新模块，已开的模块照常交审、合并、收尾；再用 `/spec-guard:config` 关掉 `moduleConcurrency`。恢复用 `serial --off`。

## 轻任务

不值得开模块的活（单个需求或 bug）走轻流程，不写 Spec、不调 spec-guard，但和模块一样只从合并队列进集成分支：

1. **记任务**（模块协调）：用户明说要做后 `module-crew task add --type feature|bug --title … --what … --expect <预计文件> --done <完成标准> --original-file <原话文件>`。
   预计文件和在做的任务或模块分支已改的文件重叠就排队，`task next` 按 bug 在前提为可开。两个点名的文件相同才算重叠；目录（如 `tests/`）只和同一目录或嵌套目录算重叠，不和点名的文件算。
   在做的任务凭用户原话可以用 `task scope` 收窄预计文件，再 `task next` 放行排队的任务。
2. **派出**：`module-crew task dispatch T<号>` 建 `task/t<号>` 分支与 worktree、登记轻任务会话（不占多模块名额）、生成开工说明；模块协调用桌面版开会话，第一条消息用开工说明全文。
3. **做与交回**（轻任务会话，`crew-dev` skill 的「轻任务」一节）：bug 先补复现测试、确认它失败再修；检查通过后发最终验收【交审】（`模块：无`，带「任务：T<号>」）。
   `review add` 会比对实际改动和任务单，多改的文件和越界重叠写进交审。交回后分支又多了提交（如同步）时重新发最终验收【交审】，旧交审与合并批准作废，用户重新批准。
4. **批准与合并**：用户点一次批准，`merge approve` → `merge run`。队列顺序：bug 任务、模块（Build order）、需求任务。合入后在用的模块和在做的任务收到同步通知；`merge cleanup T<号>` 收回 worktree（分支保留）。
5. **做大了**：轻任务会话停下发升格请求（【等待用户】「卡住选做法」），用户选 A 升格（`/spec-guard:add-module`）、B 缩小（`task scope`）或 C 取消（`task cancel`）。

决策收件箱登记的契约版本低于 2.5 时，轻任务的提请批准不经过它，模块协调在会话里直接问用户。

## 修订已完成的模块

已合入的模块要返工时，不新开模块，原地重开：

1. **在 spec-guard 里重开**（用户或模块协调按 spec-guard「返工与小模块」的做法）：在原 `tasks/<模块 id>/todo.md` 追加未勾任务、`plan.md` 补一节；超出原范围的把 Plan 改回待审。`/map` 会把它显示为进行中。
2. **确认旧一轮已收回**：`merge cleanup <模块 id>` 做过；没做 `start prepare` 会拒绝。
3. **用户点名后开会话**：`module-crew start prepare <模块 id> --original-file <原话文件>`。旧模块分支已合入就快进到集成分支再开 worktree，有没合进来的提交就拒绝、交用户决定；
   新邮箱名带轮次后缀（`<简称>-<模块 id>-r2`），开工说明写明「只做 todo 新加的未勾项」。Spec、Plan 都还是批准状态时点名即开工；Plan 要重新交审时先交审；todo 新加的第一项是修订 Spec 时先改 Spec、交 Spec 节点。
4. **退役旧邮箱名**：由用户在 agent-relay 里退役第一轮的名字（新名字不用 `reactivate`）。之后的交审、合并、收回和新模块一样，旧一轮的批准与合并记录不算进新一轮。

## Codex 模块会话

模块协调在 Claude 桌面版时，模块会话也可以开在 Codex 桌面版里；模块协调本身也可以在一批收尾后整体换到 Codex，见下一节「换宿主」。

1. 在 Codex 里装同一版本的 module-crew（`.codex-plugin/plugin.json`，提供 Codex 版 `crew-dev` 与 `crew-coordinator` 两个 skill）；Codex 插件更新后要完全退出 ChatGPT 应用再打开。
2. 模块协调用 `module-crew start prepare <模块>… --host codex --original-file <原话文件>` 开工；要混用就按宿主分两次。
3. 用户在 Codex 里新建任务，工作目录选那个模块的 worktree，第一条消息贴开工说明全文。
4. Codex 会话先跑 `module-crew host-check`：检查登记、版本、能否写 git 目录、能否读状态库。开工说明给的命令是状态库里的固定入口 `<git 公共目录>/module-crew/bin/module-crew`，它每次转给当前安装的 module-crew，升级后不用换。
5. Codex 默认沙箱不让写 `.git`：第一次提交会弹提权，用户在那个 Codex 会话里批准（有「本会话一直允许」就选）。
6. ChatGPT 应用重启后 Codex 会话不会自动加载，要用户逐个点开；Codex 会话掉了联调身份时用原名重新注册即可。

## 换宿主

一批模块收尾后的空档里，模块协调连同下一批模块会话可以整体在 Claude Code 与 Codex 之间来回换。换不换、换到哪边由用户决定；module-crew 不看额度、不自动换，也不做模块做到一半换宿主。

1. **什么时候能换**：没有在用的模块会话与轻任务会话、没有排队或进行中的合并、module-crew 侧没有未结的事项、公共变更请求和等待记录。
   最后一个会话收回时 `merge cleanup` 会输出「本批已收尾，具备换宿主的条件」，`status` 也显示这一行。`module-crew coordinator handover --check [--to codex|claude]` 逐条列出哪项不满足；决策收件箱那边的待决请用 decision-inbox 再看一眼。
2. **换**：用户明说后，原宿主上的模块协调运行 `module-crew coordinator handover --to codex|claude --original-file <原话文件>`。它改模块协调登记的宿主、按新宿主给集成 checkout 追加权限规则（项目 apply 过才写，原有规则保留），并把逐步交接说明打印出来、存到状态库目录 `handover-guide/`。
3. **照交接说明做**：每一步写明去哪个会话、做什么、做完的样子。要点：
   - Claude → Codex：先归档 Claude 上原来那个模块协调（agent-relay 不让接管还在运行的 Claude 会话）；在 Codex 里信任项目（贴开场文字之前）；在 Codex 新建任务、目录选集成 checkout、贴开场文字；它用 `takeover:true` 加 `wake:{app:"codex", sessionId:<CODEX_THREAD_ID>}` 接管邮箱名，再 `bind --takeover`（会弹提权）；之后每轮开头不带 takeover 重新注册。
   - 新宿主的规则文件（如 `.codex/rules/module-crew.rules`）没被 git 忽略时，规则没写上，交接说明多一步：模块协调在 `.gitignore`（公共文件）加上这个文件并提交，再凭用户原话重跑 `permissions apply`。
   - Codex → Claude：先确认原 Codex 任务已停（agent-relay 判断不了，它被接走后也收不到通知）；在 Claude 桌面版新开会话、贴开场文字；它用 `takeover:true, wake:"auto"` 接管，再 `bind --takeover`。新开会话不要用 worktree，要开在集成 checkout。
   - `bind --takeover` 只认登记宿主上的会话：没先跑 handover 就在另一边接管会被拒。
4. **之后**：`start prepare`、`task dispatch` 不写 `--host` 时用模块协调所在的宿主。模块协调在 Codex 时只开 Codex 会话（Codex 叫不醒停掉的 Claude 会话），`--host claude` 被拒。
5. **代价**：Codex 上写状态库、提交、合并都在 `.git` 里，要用户点提权；Codex 模块会话要用户手动开；ChatGPT 应用重启后要逐个点开。批准照旧由用户在该端模块协调那里亲口给。
6. **前提**：插件里要有 Codex 版模块协调规矩（`codex-skills/crew-coordinator/SKILL.md`，随插件发）；没有时 `handover --to codex` 拒绝执行，换回 Claude 不受影响。

### 模块协调在 Codex 上

Codex 版 `crew-coordinator` skill 管下面这些与 Claude 不同的地方，交接说明的开场文字会让新线程加载它：

- **每轮开头三步**：Codex 每轮重启 MCP、会丢联调身份，也没有钩子注入角色。每一轮先用原名 `bridge_register`（`wake:{app:"codex", sessionId:<CODEX_THREAD_ID>}`，不带 takeover）→ 运行 `module-crew status`（首行写明本线程是不是登记的模块协调）→ 读收件箱。
- **提权**：几乎所有模块协调的写命令都写状态库或 `.git`，Codex 默认沙箱不让写。skill 列出要「申请在沙箱外运行」的命令，用户在模块协调那个线程里点批准；被沙箱拒绝时报错会带「申请在沙箱外运行」（退出码 1），不换写法绕过。
- **预检**：接手后在集成 checkout 跑 `module-crew host-check`，按模块协调查：登记、版本、能否写 git 公共目录、能否读状态库、找得到 spec-guard、固定入口在不在。
- **合并长检查**：Codex 没有「后台跑、跑完叫醒」。`module-crew merge run --detach / merge result` 这一对命令代替：`merge run --detach` 拿到合并锁后把合并交给后台进程、立即返回，输出写到状态库目录 `merge-output/C<号>.log`；
  `module-crew merge result [C<号>] [--wait <分钟>]`（单次最多等 8 分钟；第一次取到结果时记进状态库）分段取结果，跑完时打印与前台 `merge run` 相同的内容、以同样的退出码结束，还在跑时退出码 6。`status` 会提示「已结束，运行 merge result 取通知」。
- **开会话**：模块会话、轻任务会话都开在 Codex，由用户手动开；`start prepare`、`task dispatch` 输出末尾有「请用户去 Codex 新建任务」一段，逐个写出工作目录与开工说明文件。
- **找插件**：module-crew、spec-guard、agent-relay 都按 Claude 的插件安装记录找（Codex 沙箱里读得到）；Codex 侧自己的插件安装 module-crew 不读，所以本机要在 Claude Code 里装着这些插件。
- **代价**：提权次数多；ChatGPT 应用重启后要逐个点开模块协调和模块会话；决策收件箱在 Claude，它被桌面版停掉时 Codex 叫不醒，要用户点开。

## 审查就近与决策收件箱

**审查就近**（登记了审查者时）：审查改在模块协调这一层就近来回，用户只看要拍板的事。

1. 模块会话按项目的评审节奏交审；最终验收的「要点」里要有「验收结果」一节（按 Spec 的验收标准逐条写结果与证据）。
2. `review add` 收下交审，输出把【交审】原样转给审查者的送审发送项。
3. 审查者回【审查结论】，`review note [<C号>] … [--then-batch [--for-hub]]` 记下（一条消息几段也行）：
   「有须修改项 N 条」时输出返工通知，模块改完重交、再送审，不问用户；返工满 3 次、模块写了「不同意」、或送审 15 分钟没结论，都变成要用户决定的待定问题。
4. 只有审查通过（或带待定问题）的交审才提请批准：`review batch --for-hub` **一个模块一条**【等待用户】，
   带交审要点全文、「批了会怎样」、「产物」（路径 ＠ 提交，重交带上一版）、「交审原文」「审查原文」（状态库 `originals/` 下的原文文件）和待定问题（字段名：待用户决定）。
5. 用户的答复要答到每个待定问题；没答全批准命令退出码 3、什么都不做。退回、等审查这类答案分别让交审退回或保持未答。
6. 最终验收批准后、合并前可以 `merge revoke <C号>` 撤回；`status` 与 `sessions --json` 显示返工轮次（`review` 字段）。

**接入决策收件箱**：

1. 在模块协调里由用户亲口登记可信批准来源：`module-crew source add <决策收件箱邮箱名> --kind hub --original-file <原话>`；审查者登记为 `--kind lead`（要写 `--modules`、`--nodes`）。
2. 提请批准的正文逐条用 `bodyFile` 原样发给决策收件箱；要用户决定的事只在那里问，会话里不放可以点的决定按钮。
3. 决策收件箱转来【用户答复】后，批准命令带 `--source <决策收件箱> --source-item <H> --source-relay-id <消息号> --source-from <实际发件人> --original-file <那条消息>`，用户原话从消息里读出；实际发件人不是来源本身或是模块会话时拒收。
4. `module-crew source map <H>` 查一个待决事项批准了哪些 C 编号。
5. **待定问题的编号**：决策收件箱登记为契约 2.6 及以上、或没有决策收件箱时，待定问题编成 `C<交审号>-<序号>`（如 C15-1），答复块一块只答一件事（如「C16 A；C16-1 B」）；登记低于 2.6 时用 D 编号。登记 2.6：`source add <邮箱名> --kind hub --protocol 2.6 --original-file <原话>`。
6. 外部插件读 `module-crew sessions --json`（字段见[架构](architecture.md#对外出口)），只给事实、不判断是否卡住；出口与契约版本登记在根目录 `interface.json`。

**并行边界重叠**（`review batch` 末尾）三种结论：有冲突就列出模块与路径；比对过且没有冲突写「无（已按交审中的 Spec 比对）」或「无（已按集成分支上的 Spec 比对）」；比不了写「未比对：<原因>」（例如交审中的 Spec 还没落到集成分支、spec-guard 低于 1.10 没有 `scopeOverlap`）。只有比对过才写「无」。

**不配决策收件箱、不配审查者时**：一切照常在模块协调里由用户亲手批准；没有审查者就不送审、不返工，提请批准里写「未审查」；待定问题由模块协调直接问用户。

审查者用【负责人转交】转来的批准只记账、不写批准标记（spec-guard 只认用户亲手与决策收件箱转来的批准）；带来源批准时，给模块的【用户答复】按契约带「转自」，命令同时给出发回决策收件箱的【已恢复】「结束：#H」。

## 权限预配

不可逆操作不能只靠弹窗：宿主确认在别的会话代开的会话里也会弹，但点一次「允许」就执行了，点的人未必清楚上下文。所以 module-crew 把常规操作写成宿主认的放行规则，把不可逆操作写成禁止规则，再用 git 的 pre-push 钩子守住推送：

- **放行**：module-crew 自己的命令（放行的是状态库里的固定入口，升级插件后不用重跑）、常规 git 与测试命令、按锁文件装依赖与往项目里加新包（`npm ci`、`npm install <包名>`、`pnpm add`、`yarn add`、`uv add`、`.venv/bin/pip install` 等）。
- **禁止**：推送、删除、全局安装（`-g`／`--global` 在任意位置、`yarn global`、`uv --system`、`brew install`）、改全局配置。禁止规则直接拒绝，不依赖有人当场判断。
- **不写规则**：裸 `pip install <包名>`（不在 venv 里会装进系统 Python）交宿主默认确认；Codex 侧加新包也不写规则，因为前缀规则挡不住 `npm install x -g`。spec-guard 的命令入口路径带版本号，暂不放进放行清单。

步骤：

0. 先有模块协调登记（`coordinator up`，或已经用 `start prepare` 开过工），`plan`／`apply` 才列得出集成 checkout 与各模块；没登记时 `plan` 会直接提示先 `coordinator up`。
1. `module-crew permissions plan`：只读预览每个 checkout 要追加什么、文件有没有被 git 忽略、钩子能不能装、Codex 项目是否受信任，以及别处（主 checkout 的设置、用户设置等）有没有确认或禁止规则会盖过要写的放行——宿主先看禁止、再看确认、最后看放行，模块 worktree 的会话也读主 checkout 的本地设置。
2. `module-crew permissions apply --original-file <用户原话>`：Claude 写 `.claude/settings.local.json`（只追加条目），Codex 模块写 `.codex/rules/module-crew.rules`；有一个文件不能写就全部不写。之后 `start prepare` 新开的模块自动跟随。
3. 开好会话后 `module-crew permissions verify`：四条应直接运行、一条应被拒的实测清单；结果用 `verify --record` 记下，`status` 显示每个会话最近一次实测，没测过写「权限未实测」。
4. 推送只经 `module-crew merge push`：钩子拒绝模块 worktree 的推送，以及集成 checkout 上没有一次性放行凭证的推送。你自己在终端推送可以加 `--no-verify`。
   仓库设了 `core.hooksPath`（如 husky）或已有 pre-push 钩子时不装，`plan` 会写明；这时推送只靠宿主的禁止规则（实测在 husky 仓库里，代开的会话 `git push` 被禁止规则拦下、不弹窗）。
5. Codex 的项目级规则只在项目被 Codex 信任后生效；module-crew 不改你的全局配置，只提示。
6. `module-crew permissions remove --original-file <用户原话>`：只撤 module-crew 加的条目；按「不删文件」的约定，Codex 规则文件清空、钩子改成空操作，可以手动删除。

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
| 合并被退回 | 集成分支已回到合并前、模块分支不动；模块修好后重新发最终验收【交审】（不用撤销任何提交）。退回原因判错了，模块协调用 `merge renotice` 按另一种原因重发 |
| 合并收尾超时、状态库没记下合并 | `module-crew merge record C<号> --original-file <原话文件>` 补记 |
| 写类 git 命令超时，worktree 删了一半 | 命令以退出码 4 结束并写明恢复步骤；`merge cleanup` 能收完只剩已跟踪文件被删的 worktree |
| 同一个 gate 再次挡住、异常停点、要改能力图 | 按 spec-guard 的规则办，把选项与代价交用户决定 |

一个模块挂起、退回或崩溃，不影响其他模块的交审、合并与通知。

插件更新后：在用的 Claude 会话在原会话里 `/clear` 一次；Codex 侧重新装本插件并完全退出 ChatGPT 再打开。动 Codex 侧插件前先备份 `~/.codex/config.toml`；`codex plugin marketplace remove` 报「not configured」时停下核对，不要接着装。

## 已知限制与尚未验证

已经实地验证过的：真实 spec-guard 与 agent-relay、会话间真实收发、开工、批量批准、审查就近与决策收件箱转达、合并与退回、挂起与恢复、换模块协调与换模块会话、退回串行、收尾与推送到本机远端；权限预配的禁止规则（编辑 worktree 里的 `.claude/` 被拒）；钩子按会话认身份、给真实桌面会话注入角色与命令入口。还没验证的：

- 用 `gh` 真正开 PR（试点远端是本机裸仓库，只打印 PR 正文）。
- 权限预配的放行规则：在本机宿主上和不写规则时看不出差别，是否真的减少弹窗还没证实。
- 桌面版整个退出重开后会话 id 是否不变：压缩、`/clear`、`claude --resume` 接上都实测不变，退出整个桌面版这一种没测。
- Codex 的固定入口：在真实 Codex 沙箱里跑过 `status`（读得到 Claude 的安装记录）与 `host-check`（写 `.git` 要提权，提权后能提交）；登记过的 Codex 模块会话完整走一遍 bind、交审还没测。
- 声明范围、检查记账、自治档位、额度外包四个开关：都只用测试和本机接口实测验证过，还没在真实项目上打开试跑。额度外包只用夹具测过两种情形（带 `--resumable` 的长期限运行被中止后的收尾、长期限下回收不了时的真实表现）；needs-input 续跑与整个模块的长链外包没实跑。自治档位的升档门槛与收尾汇总时机是先定的，等试点数据再调。
- 模块协调在 Codex 上：只用测试验证过。`merge run --detach` 的后台进程能否活过 Codex 的一轮、提权是否随之继承，单次工具调用最长能等多久，一次提权批准能覆盖多少条命令，都还没在真实 Codex 线程里试过。
