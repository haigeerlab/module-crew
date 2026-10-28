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
