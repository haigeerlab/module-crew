# 架构

module-crew 内部怎么运作、和上游插件怎么接。怎么用见[使用手册](guide.md)，命令见[命令参考](commands.md)。

## 总览

```mermaid
flowchart LR
  U([用户]) -- 原话批准 --> C[模块协调<br/>集成 checkout]
  C <-- agent-relay 消息 --> D1[模块会话 A<br/>worktree A]
  C <-- agent-relay 消息 --> D2[模块会话 B<br/>worktree B]
  C <-. 可选 .-> H[决策收件箱 / 审查者]
  C -- 读写 --> S[(状态库<br/>git 公共目录/module-crew)]
  D1 -- 读写 --> S
  D2 -- 读写 --> S
  C -- 读 /map --json 等 --> G[spec-guard]
  D1 -. 额度外包 .-> X[delegate → Codex]
  C -- merge run --> I[集成分支]
  D1 -- module-crew sync --> I
```

- 每个模块一个 git worktree、一个分支、一个会话；模块协调在集成 checkout 里。
- 会话之间只经 agent-relay 收发消息，消息格式由 session-protocol 契约规定；模块会话只和模块协调说话。
- 所有 worktree 共用一份状态库：谁登记了什么、哪些事项开着、谁批准了什么，都以状态库为准，不靠对话记忆。
- 规划（能力图、Spec、Plan、批准标记、阶段）归 spec-guard，module-crew 只读它的输出、不改它的阶段判断。

## 组件

| 位置 | 作用 |
|---|---|
| `bin/module-crew` | 命令入口，一个薄 shell 包装：把插件目录放在 `sys.path` 最前面再运行 `module_crew` 包，当前目录下的同名包不会盖过它 |
| `module_crew/` | 全部逻辑，只用 Python 3 标准库（见下表） |
| `skills/crew-coordinator`、`skills/crew-dev` | Claude 侧的两份规矩：模块协调、模块会话（含轻任务会话） |
| `codex-skills/crew-coordinator`、`codex-skills/crew-dev` | Codex 侧的同两份规矩（Codex 没有钩子，规矩里另写每轮开头要做的事与提权） |
| `hooks/hooks.json` | Claude Code 的 SessionStart、UserPromptSubmit、SessionEnd 钩子，都调 `module-crew hook …`，出错也退出码 0 |
| `interface.json` | 对外出口的登记：插件版本、钉住的契约版本、`sessions --json` 的命令与 schema 版本 |
| `.claude-plugin/`、`.codex-plugin/` | 两个宿主的插件清单；`.claude-plugin/marketplace.json` 是本地插件市场清单 |

`module_crew/` 里每个文件的职责：

| 文件 | 职责 |
|---|---|
| `__main__.py` | 命令行解析与分发；判断命令是不是只有登记的模块协调能跑（不是就退出码 7）；后台合并期间挡住写集成 checkout 的命令 |
| `store.py` | 状态库：只追加的事件日志、快照、编号、事务、消息正文 |
| `protocol.py` | 按 session-protocol 契约解析与生成消息（`protocol check` 用它） |
| `probe.py` | 只读体检与 `status` 汇总；读本机插件安装记录与各依赖的 `interface.json` |
| `hostcheck.py` | `host-check`：本会话在这里能不能完成 module-crew 的工作 |
| `coordinator.py` | 升级与关闭模块协调 |
| `start.py` | 开工：提议可开的模块，建 worktree、登记会话、生成开工说明 |
| `role.py` | 读 spec-guard 写的 checkout 角色标记 |
| `inbox.py` | 模块协调收件记账、转达用户的答复 |
| `review.py` | 交审的记账、汇总、审查结论与返工、批准（在集成分支写批准标记） |
| `present.py` | 提请批准时给用户看的样子：文档表、代码文件表、提交表、新增依赖表 |
| `sources.py` | 可信批准来源（决策收件箱、审查者）的登记与核对 |
| `changes.py` | 公共变更请求：记账、保护文件提示、落地、拒绝或被取代 |
| `declared.py` | 声明范围：读已批 Plan「预先声明」的公共文件名单 |
| `merge.py` | 本地合并队列、完整检查、退回、收尾、推送与 PR |
| `mergelock.py` | 后台合并期间一次只合一个的合并锁 |
| `sync.py` | `sync`：把集成分支合进模块分支，本模块的 Spec 与 `tasks/` 冲突时取集成分支版本 |
| `checks.py` | 快检查与完整检查分开、按树哈希记的检查账、修基线任务 |
| `unqueued.py` | 集成分支上不经合并队列的提交 |
| `tasks.py` | 轻任务记录（T 编号）：重叠判断、排队、派出、收窄 |
| `autonomy.py` | 自治档位：每档放松什么、升档证据、出事降档 |
| `offload.py` | 额度外包：派出 Task、读 delegate 的结果、核对后提交 |
| `failure.py` | 挂起、`sessions` 事实、恢复说明、退回串行 |
| `stall.py` | 给决策收件箱看的停滞事实（只读，不判断是否卡住） |
| `hooks.py` | 钩子：按会话编号认出登记的会话，注入角色、当前阶段与命令入口；换会话接管 |
| `handover.py` | 空档换宿主：核对收尾条件、改登记、生成交接说明 |
| `launcher.py` | 状态库里的固定入口，供没有钩子的会话（Codex）与权限规则使用 |
| `permissions.py`、`prepush.py` | 宿主权限规则的预览、写入、实测与撤销；装在 git 公共目录的推送守门钩子 |
| `commits.py` | module-crew 自己提交的提交信息前缀与提交钩子失败的处理 |
| `refs.py` | 对外编号的写法（C 编号） |

## 状态库

- **位置**：仓库 git 公共目录下的 `module-crew/`（主 checkout 是 `.git/module-crew/`），所有 worktree 读写同一份。放在 git 目录里所以不进版本库、不随分支切换。
- **事实来源**：`events.jsonl` 是只追加的事件日志，每次写入追加一条带着改后完整记录的事件；`state/` 下按种类存的快照只是缓存，随时可以从日志重算。
- **记录种类**：`config`（运行配置与项目开关）、`session`（会话登记）、`item`（事项：交审、合并批准等，C 编号）、`request`（公共变更请求）、`ticket`（等待记录，W 编号）、`body`（消息正文）、`sighting`（钩子见到的会话）、`handover`（换会话、换宿主的交接）、`task`（轻任务，T 编号）、`check`（检查账）、`offload`（外包记录）。
- **其他文件**：`meta.json`（状态库格式）、`tmp/`（外包等的临时文件）、`bodies/`（要发出的消息正文文件，模块协调用 `bodyFile` 原样发出）、`originals/`（交审与审查的原文）、`bin/`（固定入口）、`merge.lock` 与 `merge-running.json`（合并锁）、`merge-output/`（后台合并的输出）、`handover-guide/`（换宿主的交接说明）。
- **写入**：每次写在一个事务里，带操作者；编号统一分配，多个 worktree 同时写不会撞号。

## 消息与批准

- **通道**：会话之间只经 agent-relay 收发。要回复的消息标 `expectsReply`；回复填 `replyTo`，首行写「回复：#N」；正文走 `bodyFile`，不经 shell 转义。
- **格式**：消息以契约标签开头（【交审】【等待用户】【用户答复】【协调通知】等），字段与必填项由 session-protocol 契约规定。module-crew 钉住契约 v2.6（`interface.json` 的 `contract`）；每条消息发出前用 `protocol check` 自检。
- **批准链**：批准只来自用户在模块协调里亲手输入的话（`--original`／`--original-file`，原话存进状态库）。决策收件箱或审查者转来的决定，要先由用户亲口把它们登记为可信来源，批准命令再核对来源、事项号、消息号与实际发件人；别的会话转来的话一律不算批准。
- **批准落在哪**：Spec、Plan 的批准由 `review approve` 在集成分支写 spec-guard 的批准标记并提交；模块会话 `sync` 时自动取这一版。
- **钩子**：Claude Code 会话每次启动、每次提交提示词时，钩子按会话编号查状态库，只给登记过的会话注入它的角色、当前阶段、未关的等待记录与命令入口；没登记的会话不注入角色。

## 合并与检查

- **队列**：最终验收批准后排进合并队列，顺序是 bug 轻任务、模块（按能力图 Build order）、需求轻任务；一次只合一个。
- **合并**：`--no-ff` 合入本地集成分支，再跑项目的完整检查命令。通过就记合并、勾最终验收、给其他在用模块发同步通知；不通过就把集成分支重置回合并前、模块分支原样保留并退回；冲突就中止并退回。
- **合并锁**：后台跑合并时持有合并锁，别的写集成 checkout 的命令退出码 6；`merge run --detach` 把合并交给后台进程，`merge result` 取结果。
- **检查记账**（开关打开时）：快检查在模块 worktree 里跑、按树哈希记账，同一棵树不重跑；完整检查只在合并队列与基线检查里跑。
- **不经队列的提交**：集成分支上别的途径进来的提交会被认出来、通知各模块同步，插件不拦、不撤回。
- **推送**：只经 `merge push` 推到远端新分支并开 PR；pre-push 钩子拒绝模块 worktree 的推送和集成 checkout 上没有一次性放行凭证的推送。远端合并由用户做。

## 与上游的接口

module-crew 读各依赖安装目录里的 `interface.json`，按主版本与次版本判断能力；读不到或版本不够时报原因，涉及的功能照旧或停下问用户，不猜。

| 依赖 | module-crew 要什么 |
|---|---|
| agent-relay | 接口主版本 2：注册邮箱名、`bridge_send` 的 `bodyFile`／`replyTo`／`expectsReply`、收件箱与会话状态 |
| spec-guard | 接口 1.1 起的规划层（spec-guard 0.68.0）：`/map --json` 的模块状态与 `moduleConcurrency`、`startable`，checkout 角色标记；1.10 的 `scopeOverlap`（并行边界比对）；1.11（spec-guard 0.85.0）的 `declaredScope`、`autonomyTier`、`scopeCheck` |
| delegate | 只有额度外包要：接口 1.3（delegate 0.8.0 起）的接续、续跑、长期限、结果文件与写入授权能力标记 |
| session-protocol | 消息契约，钉住 v2.6 |

## 对外出口

- **`module-crew sessions --json`**（`schemaVersion` 1）：给决策收件箱等外部插件读的会话事实，只给事实、不判断是否卡住。顶层 `schemaVersion`、`sessions`；每个会话的字段：
  `name`、`relayName`、`module`、`worktree`、`host`、`stage`、`stageText`、`lastActivity`、`ago`、`openTickets`、`openTicketRefs`、`openItems`、`suspended`、`review`（返工轮次），以及停滞事实 `startedAt`、`commits`（领先集成分支的提交数与最后一次提交）、`asks`（各节点问过用户几次）、`returns`、`waitUser`、`answers`。
  只增不改：新字段只加不删，`schemaVersion` 不变。
- **`interface.json`**：`interface`（出口登记格式版本）、`plugin`、`version`、`contract`（钉住的契约版本）、`sessions`（命令、`schemaVersion`）。

## 设计取舍

- **只用 Python 标准库**：装插件就能跑，没有依赖要装、要升级。
- **状态库放 git 公共目录、不进版本库**：所有 worktree 天然共用一份，不会因切分支、合并而丢或冲突；代价是换机器不随仓库走。
- **事件日志是唯一事实来源**：快照坏了能重算，谁在何时凭什么原话做了什么都查得到。
- **不自动推送、不远端合并、不推集成分支**：本地错了能重置回去，远端的事由用户做。
- **不可逆操作写禁止规则，不写确认**：代开的会话里确认弹窗也会弹，但点「允许」的人未必清楚上下文；禁止规则直接拒绝。
- **只给事实，不判断会话卡没卡住**：卡住的判断交给用户或决策收件箱，module-crew 不按猜测去叫醒或重试。
