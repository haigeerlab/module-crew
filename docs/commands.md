# 命令参考

module-crew 的全部命令。每个命令组写：做什么、谁跑、在哪跑、子命令与常用参数、要不要用户原话、特有的退出码。
完整参数以 `module-crew <命令> [<子命令>] --help` 为准，这里只写常用的。流程里什么时候用哪条命令，见[使用手册](guide.md)。

## 用法总述

**入口**：插件里的 `bin/module-crew`。开工后状态库里另有一个固定入口 `<git 公共目录>/module-crew/bin/module-crew`，它每次转给本机当前安装的 module-crew，插件升级后不用换路径；开工说明、权限规则里写的都是这个固定入口。

**谁能跑**：标「模块协调」的命令只有状态库里登记为模块协调的那个会话能跑，别的会话跑会被拒（退出码 7，什么都不写）；在终端里直接跑（没有会话编号）不受这条限制。
标「任何会话」的是只读命令、模块会话那一侧的命令和钩子入口。

**用户原话**：要用户批准的命令都要 `--original "<原话>"` 或 `--original-file <文件>`，只记用户在模块协调里亲手输入的话；别的会话转来的话不算批准。
决策收件箱或登记过的审查者转来的决定，改用 `--source <邮箱名> --source-item <H> --source-relay-id <消息号> --source-from <实际发件人>`，`--original-file` 放对方消息全文（见 `source`）。

**退出码**（各命令通用的含义；个别命令另有约定的写在该命令下）：

| 码 | 含义 |
|---|---|
| 0 | 成功 |
| 1 | Codex 沙箱拒绝写状态库（报错里写明要「申请在沙箱外运行」） |
| 2 | 用法错误、缺用户原话、找不到状态库 |
| 3 | 拒绝执行：前提不满足，什么都没做（输出写明原因） |
| 4 | 超时或跑不起来（不记账、不改状态） |
| 5 | 做了但没通过：检查失败、合并被退回、外包要停下问用户 |
| 6 | 合并锁被占（后台合并正在跑）；`merge result` 表示还没跑完 |
| 7 | 本会话不是登记的模块协调 |

## 体检与查看

### `status`

体检与全貌（只读，任何会话）。检查 git、agent-relay、spec-guard、项目是否启用 spec-guard、spec-guard 规划层、集成分支、状态库，再列出会话与待办、模块协调、任务、模块进度与评审节奏。`--json` 输出机器可读版本。

### `sessions`

列出模块会话的事实（只读，任何会话）：最后动静、未关的等待记录与事项、档位、挂起原因、返工轮次。只给事实，不判断是否卡住。`--json` 是对外出口（`schemaVersion` 1，字段见[架构](architecture.md#对外出口)）。

### `host-check`

宿主预检（只读，任何会话）：在模块 worktree 里按模块会话查，在集成 checkout 里按模块协调查——登记、版本、能否写 git 公共目录、能否读状态库、找不找得到 spec-guard、提交钩子能不能跑、固定入口在不在。Codex 会话开工必跑。`--json`。

### `store`

状态库。`store init` 建状态库（模块协调）；`store check` 校验状态库（任何会话，只读）。

### `protocol`

`protocol check <文件>`：按 session-protocol 契约自检一条消息正文（任何会话，只读）。退出码不是 0 就是不合格，改到合格再发。

## 模块协调的身份

### `coordinator`

- `coordinator up [--short <项目简称>] --original(-file)`：把本会话升级为本项目的模块协调（任何会话可发起；一个仓库只一个模块协调，第一次要给项目简称：小写字母、数字、连字符）。前提同 `status` 的体检，不要求已有能力图。
- `coordinator down --original(-file)`：关闭模块协调（模块协调）。没有在用的模块会话时才行，状态库保留。
- `coordinator handover --check [--to codex|claude]`：只读核对空档换宿主的收尾条件（任何会话）。
- `coordinator handover --to codex|claude --original(-file)`：换宿主（模块协调）：改登记的宿主、追加新宿主的权限规则、生成交接说明到状态库的 `handover-guide/`。

### `bind`

`bind <邮箱名>`：登记本会话就是状态库里的某个会话（任何会话）。module-crew 的钩子只给登记过的会话注入角色。
`bind <邮箱名> --takeover --original(-file)`：新会话接手模块协调（同一仓库任一目录都行），旧会话随即失效。

### `takeover`

`takeover <邮箱名> --original(-file)`：记录用户同意新会话接管某个模块会话的邮箱名（模块协调）。配合 `resume-kit` 用。

### `resume-kit`

`resume-kit <模块>`：生成换会话用的恢复说明（模块协调）。新会话在原 worktree 里开，第一条消息用这份说明。

## 开工

### `start`

- `start plan [--json]`：按能力图的 Build order 提议可开的模块，不超过空位（只读，任何会话）。
- `start prepare <模块>… --original(-file) [--project-short <简称>] [--max <上限>] [--host claude|codex] [--commit-prefix <前缀>]`：为每个模块建 worktree（`<仓库名>-crew/<模块>`）、登记会话、生成开工说明（模块协调）。重开已完成的模块也用它（见使用手册「修订已完成的模块」）。

### `config`

`config set … --original(-file)`：改项目的运行配置（模块协调）。一次可以设多项：

| 参数 | 作用 |
|---|---|
| `--commit-prefix <值>` | module-crew 提交信息的前缀；空字符串表示不加 |
| `--check-timeout <秒>` | 完整检查与提交钩子的时限 |
| `--declared-scope on\|off` | 声明范围开关 |
| `--quick-check-command "<命令>"` | 快检查命令（项目脚本，只跑受影响部分；不经 shell） |
| `--check-ledger on\|off` | 检查记账开关 |
| `--codex-offload on\|off` | 额度外包开关（要先开检查记账） |
| `--protected-file <路径>`（可重复）／`--clear-protected-files` | 随锁文件校验的保护文件名单（整份替换）／清空 |

### `serial`

`serial --original(-file)`：退回串行——不再开新模块，已开的模块照常交审、合并、收尾（模块协调）。`serial --off --original(-file)` 恢复并行。

## 收件、交审与批准

### `inbox`

`inbox add <文件> --from <发件人> --relay-id <消息号>`：模块协调收到消息后记账（模块协调）。

### `review`

- `review add <文件> --from <发件人> --relay-id <消息号>`：记下一条【交审】（模块协调）；登记了审查者时输出送审的发送项。
- `review batch [--for-hub] [--parallel-with <模块>] [--json]`：汇总待批的交审，生成提请批准的正文（只读，任何会话）；`--for-hub` 生成交给决策收件箱的【等待用户】正文，一个模块一条。末尾附并行边界重叠的结论。
- `review note [<C号>] --from <审查者> --file <文件> [--then-batch [--for-hub]]`：记下审查者的【审查结论】（模块协调）；有须修改项时输出返工通知。
- `review show <C号> [--submission] [--spec-diff]`：交审的审查原文全文与 sha256（只读，任何会话）；`--submission` 另附交审原文，`--spec-diff` 只出最终验收时 Spec 相对集成分支的差异。
- `review approve <C号>… --original(-file)`：批准（模块协调）：在集成分支记批准标记，生成【用户答复】与开工通知。用户的答复没答全每个待定问题时退出码 3、什么都不做。
- `review answer <C号> --original(-file)`：转达用户对交审的其他答复（退回、等审查等）（模块协调）。

### `answer`

`answer <编号> --original(-file) [--option <选项>]`：把用户的答复转达给发起【等待用户】的会话（模块协调）。

### `source`

可信批准来源（决策收件箱、审查者）。登记、改范围、移除都要用户原话（模块协调）。

- `source add <邮箱名> --kind hub|lead [--protocol 2.2|2.3|2.4|2.5|2.6] [--modules …] [--nodes …] --original(-file)`：登记一个可信批准来源。决策收件箱用 `hub`（`--protocol` 不写按 2.4）；审查者用 `lead`，必须写负责的模块与节点（`spec`、`plan`、`interface`、`final`，或「全部」）。
- `source scope <邮箱名> [--modules …] [--nodes …] --original(-file)`：补登记或修改审查者的负责范围。
- `source remove <邮箱名> --original(-file)`：移除来源。
- `source list [--json]`、`source map <H> [--json]`：列出来源；查一个待决事项批准了哪些 C 编号（只读，任何会话）。

## 公共文件

### `change`

公共变更请求（锁文件、全局配置、迁移、测试资源等公共文件的改动）。

- `change add <文件> --from <发件人> --relay-id <消息号>`：记下一条【公共变更请求】（模块协调）。请求里有锁文件改动时，提示保护文件名单里可能要连带改的文件。
- `change list [--json]`：列出请求（只读，任何会话）。
- `change land <编号>… --original(-file)`：在集成 checkout 改好后落地（模块协调）。两个及以上编号合成一个提交，先逐条核对、再跑检查（检查记账打开时跑快检查，否则跑完整检查），任一条不满足整批不提交；其他在用模块收到同步基线通知。
  `--partial` 先落地已改的部分（请求保持打开）；`--from-module` 是声明范围内的提前落地，从请求方模块分支取文件；`--skip-check` 跳过检查，要用户原话。
- `change landed [--mark-told <编号>…] [--json]`：声明范围内提前落地、还没汇总给用户的（模块协调）。
- `change answer <编号> --original(-file)`：转达用户对请求的答复；`change answer <编号> --reason superseded --by <新编号>`：被新请求取代的直接关掉（模块协调）。

### `scope`

`scope [<文件>…] [--json]`：在模块 worktree 里查文件在不在 Plan「预先声明」名单内（只读，任何会话）。声明范围开关打开时用。

## 合并与收尾

### `merge`

- `merge approve <交审号>… --original(-file)`：批准最终验收，排进合并队列（模块协调）。
- `merge revoke <交审号> --original(-file)`：合并前撤回最终验收的批准（模块协调）。
- `merge queue [--json]`：合并队列（只读，任何会话）。顺序：bug 任务、模块（按 Build order）、需求任务。
- `merge run [--check-command "<完整检查命令>"] [--replace-check] [--detach]`：一次合一个：`--no-ff` 合入本地集成分支后跑完整检查；不过就把集成分支重置回合并前、退回该模块，冲突就中止并退回（模块协调）。第一次要给 `--check-command`。
  退出码 5：模块被退回；6：合并锁被占。`--detach` 交给后台进程、立即返回（Codex 上的模块协调用）。
- `merge result [<C号>] [--wait <分钟>] [--json]`：取后台合并的结果（模块协调），单次最多等 8 分钟；跑完时输出与前台 `merge run` 相同、退出码相同，还在跑时退出码 6。
- `merge renotice <C号> --env|--module`：按另一种原因重发退回通知（模块协调判断，不用用户原话）：`--env` 检查环境出了问题、模块不用改代码；`--module` 模块要修改。
- `merge cleanup <模块或 T号> --original(-file)`：收回 worktree（分支保留），列出要退役的邮箱名（模块协调）。本批最后一个会话收回时输出「本批已收尾，具备换宿主的条件」。
- `merge tick <模块> --original(-file)`：补勾漏勾的最终验收（模块协调）。
- `merge record <C号> --original(-file)`：合并收尾超时、状态库没记下合并时补记（模块协调）。
- `merge push-plan [--pr-base <分支>] [--json]`：预告要推什么（只读，任何会话）。
  远端是空仓库（没有任何分支）时没有 PR 目标，预告会写明首次发布的做法：由用户自己在终端运行 `git push --no-verify -u <远端> <集成分支>`，推完后的批次再走 `merge push`；module-crew 不放行也不替用户推送。
- `merge push --original(-file) [--pr-base <分支>]`：推到远端新分支 `crew/batch-<号>` 并开一个 PR（远端是 github.com 时用 `gh`，否则只打印 PR 正文）（模块协调）。远端合并始终由用户做。

### `unqueued`

集成分支上不经合并队列的提交：不带参数只读列出（短号、作者、时间、标题，任何会话）；`--notify` 给在开发的模块与在做的轻任务发同步通知，同一批只报一次（模块协调）。`--json`。

### `sync`

在模块 worktree 里把集成分支合进模块分支（任何会话，模块会话用）。本模块的 Spec、`tasks/` 冲突时自动取集成分支的版本（那份带批准标记）。
退出码 2：还有别的文件冲突，合并没有中止，解决后 `git add`、`git commit --no-edit` 再跑一次。要单独执行，不和别的命令连写。

## 轻任务

### `task`

单个需求或 bug，T 编号。

- `task add --type feature|bug --title … --what … --expect <预计文件> --done <完成标准> [--caused-by …] --original(-file)`：记下一件事（模块协调）。预计文件逗号分隔，以 `/` 结尾表示整个目录；和在做的活重叠就排队。
- `task list [--all]`、`task show <T号>`、`task next`：在做与排队的任务；看一件；把已不重叠的排队任务提为可开、bug 在前（只读，任何会话）。
- `task dispatch <T号> [--host claude|codex]`：派出可开的任务：建 `task/t<号>` 分支与 worktree、登记轻任务会话（不占多模块名额）、生成开工说明（模块协调）。
- `task scope <T号> --expect … --done … --original(-file)`：改任务单——升格请求选了缩小，或在做的任务收窄预计文件（新范围必须落在原范围里）（模块协调）。
- `task cancel <T号> --original(-file)`：取消（模块协调）。

## 挂起、等待与换会话

### `suspend`

`suspend <模块> --reason "<原因>" --original(-file)`：挂起在等外部条件的模块，不再占名额（模块协调）。模块会话在自己的 worktree 里另用 spec-guard 挂起。

### `resume`

`resume <模块> --original(-file)`：撤销挂起（模块协调）。

### `wait`

`wait add --file <文件> --to <收件人> --relay-id <消息号> --about <#N 或 C号>`：记下模块协调自己发出的【等待其他会话】（模块协调）。所等事项的答复转达时，会给出要发的【已恢复】。

### `ticket`

`ticket close <W号> --reason happened|user --original(-file)`：关等待记录——所等的事已发生，或用户说关（模块协调）。

## 检查记账

### `check`

项目开关 `checkLedger` 打开时用。

- `check quick [--rerun]`：在模块或轻任务 worktree 里跑快检查，按树哈希记账（任何会话）。同一棵树记过就直接报结果，`--rerun` 强制重跑。退出码：0 通过、5 失败（已记账）、3 工作区不干净（先提交）、4 超时或跑不起来（不记账）。
- `check baseline [--rerun]`：对集成分支顶端跑一次完整检查并记账（模块协调，放后台跑）；红了自动建一个修基线的 bug 任务。
- `check show [<提交>] [--json]`、`check list [--limit <条数>] [--json]`：一个提交的树有哪些检查记录；最近的检查账（只读，任何会话）。

## 自治档位

### `tier`

- `tier [--json]`：设的档位、降档上限、生效档位、证据与升档建议（只读，任何会话）。
- `tier --preflight`：写 `autonomyTier` 之前核对 spec-guard 版本与接口（只读）。
- `tier restore --original(-file)`：降档后恢复一档（模块协调）。
- `tier digest [--json] [--mark-told]`：relaxed 档的收尾汇总（同步、检查账、不经队列的提交、提前落地）；只读查看任何会话都能跑，`--mark-told` 记为已汇总给用户（只是记账，不是批准）由模块协调跑。

## 额度外包

### `offload`

项目开关 `codexOffload` 打开、且模块开工时被记为交给 Codex 时用。`start`、`settle`、`resume`、`takeover` 只能在该模块会话的 worktree 里跑。

- `offload start <模块> [--again --original(-file)]`：派出 todo 里第一个未勾的 Task，生成任务说明与 `/delegate:run` 写法（第一个 Task `--resumable`，之后 `--continue <runId>`）（模块会话）。`--again` 是停下问用户后用户选重派，另起一条链。
- `offload settle <模块> --output <stdout 文件> --stderr <stderr 文件> --exit <退出码>`：收 delegate 的输出并按结束状态分流（模块会话）。退出码 0：核对通过、已提交；4：没通过但不用问用户（照输出重来，或这一项改由 Claude 写）；5：要用户决定，输出末尾是一份【等待用户】草稿。
- `offload resume <模块> --original(-file)`：带用户的答复续跑（needs-input、超时）（模块会话）。
- `offload takeover <模块> --original(-file)`：用户选「这一项改由 Claude 写」（模块会话）。
- `offload decline <模块> --original(-file)`：外包条件不满足时改由模块会话构建，发普通的开工通知（模块协调）。
- `offload show [<模块>] [--json]`：各模块的外包状态（只读，任何会话）。

## 权限预配

### `permissions`

- `permissions plan [--json]`：只读预览每个 checkout（集成 checkout 与各模块 worktree）要追加什么规则、文件有没有被 git 忽略、推送守门钩子能不能装、Codex 项目是否受信任，以及别处有没有规则会盖过要写的放行（任何会话）。要先有模块协调登记。
- `permissions apply --original(-file)`：写规则、装推送守门（模块协调）。有一个文件不能写就全部不写。
- `permissions verify [--host claude|codex]`：输出实测清单（只读，任何会话）；`--record <会话名> --allowed ok|prompted --denied ok|ran` 记下实测结果（模块协调）。
- `permissions remove --original(-file)`：只撤 module-crew 加的条目与钩子（模块协调）。

## 钩子入口

### `hook`

`hook session-start|prompt|session-end`：插件钩子的入口（由 `hooks/hooks.json` 调用，任何会话）。只读、永远退出码 0：给登记过的会话注入角色与命令入口，只写见到记录与清空交接。
