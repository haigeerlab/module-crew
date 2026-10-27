# Spec: crew-codex-offload

<!-- spec-guard: review approved d94a4167b4c8 -->

> 能力图模块 `crew-codex-offload`（第十版第 4 个），**第 2 轮修订**（2026-10-28 重开，用户在 mc-coord 会话原话「开工 crew-codex-offload 修订，重开模块写 Spec 交审」，开会话依据：用户批准事项 C304）。
> 需求来源：意图 `docs/intent/codex-offload-native.md`（用户 2026-10-27 确认，S38）；已批方案 plugin-ecosystem `proposals/2026-10-27-S38-模块整体外包给Codex.md`（用户 2026-10-27「假设全部确认，五个决定点按推荐批准」），
> 取代第 1 轮所依据的 S32「模块协调代调用、代提交」那一段。上游 delegate v0.8.0（interface 1.3，标签 v0.8.0 → 16290d0）。
> 依赖 `crew-declared-scope`（`module_crew/declared.py`：名单内判据）、`crew-check-ledger`（`module_crew/checks.py`：快检查与检查账）；spec-guard interface 1.11 的 `scopeCheck`。
> 标「新」的是这一轮写 Spec 时补的实现取舍，请重点审；第 1 轮已实现的命令、记录在「与第 1 轮的差别」一节逐条列出改法。

## 目标

Claude 额度紧张时，用户打开项目开关 `codexOffload`（或口头说「下一个模块交给 Codex」，模块协调凭原话打开），之后**开工的**模块交给 Codex 实现，效果接近 Claude 原生：稳定、能持续做完。
Spec、Plan 照旧由 Claude 模块会话写、用户批；批完后，**Claude 模块会话自己**经 delegate 把 Plan 里的 Task 一个一个交给**同一个 Codex 会话**（第一个 Task 用 `--resumable` 起头，之后每个 Task 用 `--continue` 接着同一条链），
每个 Task 回来由模块会话核对改动范围、跑快检查、自己提交；检查点、最终验收照今天的做法由模块会话处理。模块协调只转达用户的答复、记账、合并，不调 Codex、不代提交。
同一个 Task 连续 2 次没通过，这个 Task 退回模块会话自己写、并告诉用户，下一个 Task 照旧交给 Codex。认不出的结束状态一律不当成完成。开关关着、或读不到 delegate 1.3 的能力标记时，一切和今天一样。

## 范围

**范围内**

1. **项目开关** `codexOffload`（运行配置 `config/main`，`on`／`off`，没设过等于 `off`）：模块协调凭用户原话 `config set --codex-offload on|off` 写入（第 1 轮已有，照旧）。
2. **能不能外包的核对**（决策 2）：改为读 delegate interface ≥ 1.3 的五项能力标记；模块会话宿主是 Claude Code（delegate 是 Claude Code 插件，由模块会话调用）；其余条件照旧。
3. **交接点在开工通知**（决策 3、4）：`review approve` 批齐 Spec 与 Plan 时看开关，开着且核对通过就把这个模块记为「交给 Codex」、存下写入授权文件、开工通知改成外包写法；之后开关怎么变都不影响这个模块。
4. **派出**（模块会话）：`offload start <模块>` 取 todo 第一个未勾的 Task，写任务说明，给出模块会话在本 worktree 后台执行的 `/delegate:run` 写法（第一次 `--resumable`，之后 `--continue <runId>`）。
5. **收结果**（模块会话）：`offload settle <模块> --output <stdout 文件> --stderr <stderr 文件> --exit <退出码>`，读结果行、`delegate: result=` 行和结果文件，按结束状态分流（决策 7～11）；done 时核对、跑快检查、模块会话自己提交。
6. **失败计数与退回 Claude**（决策 10、11）：同一个 Task 连续 2 次没通过就退回模块会话自己写；第一次没通过时能自动重来的自动重来，不能的停下问用户。
7. **续跑**：needs-input、timeout 带用户的答复 `offload resume`（`--resume <runId>`）。
8. **只读查看**：`offload show [<模块>] [--json]`。
9. **skill 与文档**：`crew-dev`、`crew-coordinator`（Claude 与 Codex 各两份）的「额度外包」一节重写，README 同步。

**范围外**

- 改 delegate、spec-guard、session-protocol、decision-inbox：只按它们已发布的接口与契约用；**不新增消息类型**。
- Claude 额度用完后的接手（整体换到 Codex）；模块中途在 Claude 与 Codex 之间整体切换（意图「不做」）。
- 模块协调替模块调 Codex 或代提交（第 1 轮的做法，这一轮去掉）。
- delegate 1.4 的回滚（`run.restore`）、并发额度（`run.concurrent`、`doctor.quota`）；按次放开沙箱。
- delegate 的 `--check`、`--rules-file`、`--model`、`--effort`（决策 12）。
- 意图里「怎么算成功」的三项指标：由 LIVE-SAAS 试点（livesaas-lead）对比测量，本模块只提供做法与 `offload show` 里的记录。
- 合并本身：`module_crew/merge.py` **不改**。

## 假设（请逐条确认）

1. **这一轮取代第 1 轮的分工**：模块会话自己跑 `offload start`／`settle`／`resume` 并执行 `/delegate:run`、自己提交；模块协调只做开关、开工通知、转达【等待用户】与【用户答复】、合并。Codex 仍只改文件、不提交、不推送（delegate 的规矩不变）。
2. **写入授权按 S38 决定点 3 的折中**：用户打开开关的原话由 module-crew 在模块交给 Codex 那一刻存成授权文件，模块会话每次 `--write` 都带 `--authorized-by <这个文件>`；
   只派已批 Plan 里的 Task，同一模块、同一 worktree。delegate 的四条纪律（`references/run.md`「`--authorized-by`」一节）都满足时不再每个 Task 问用户。
3. **重来时的任务正文**：delegate 要求 `--continue` 的任务正文来自已批 Plan 或用户本人。本模块的任务说明只由「Plan 里这个 Task 的原文」加上 module-crew 机器生成的固定句子与核对结果（越界文件、快检查失败行、上一项由谁提交）组成，
   不由模型临时编写；这样的重来算在已批 Plan 之内，不问用户。
4. **只认 delegate 的对外接口**：interface.json 的能力标记；stdout 末行的结果行 `delegate: run_id=<id> status=<状态> resumable=<true|false>`；它前一行（或 stderr 里）的 `delegate: result=<路径>`；
   结果文件 JSON 里 README 列出的顶层字段 `status`、`exitCode`、`runId`、`authorization`；`NEED_USER:`、`TIME_UP:`、`DONE:` 标记。不读 delegate 的脚本和过程日志，不依赖结果文件里 README 没写名字的字段。
5. **needs-input 的问题正文**取 stdout 里 `NEED_USER:` 之后的全部内容，去掉末行结果行；倒数第二行以 `delegate: result=` 开头时也去掉（这一行不一定有：无结果行时在 stderr，结果文件写失败时不打印；delegate-owner #12109 确认）。
6. **期限固定 1800 秒**：每次都带 `--timeout 1800`，超过 Claude Code 前台 600 秒，所以模块会话一律用 Bash 后台模式运行、等完成通知、不轮询（`run.longRun.background == "caller"`）。不做成配置项。
7. **两个模块同时外包互不干扰**：S38 实测 T4「两个 worktree 同时跑互不干扰」，本模块不加跨模块的锁。
8. **关开关只影响之后开工的模块**：已经交给 Codex 的模块照旧做完（意图「绝不中途切换」）；用户要停，在停下问用户时选「这一项改由 Claude 写」或「先停」。打开开关也不影响已经开工的模块。
9. **快检查、范围判据沿用第 1 轮**：范围按 spec-guard `scopeCheck` 判（`exclusive`、`own`，`declaredScope` 打开时加上预先声明名单内的文件；删除一律当越界）；快检查取暂存区的树按 `checks.check_tree` 跑并记账（`by: offload`）。
10. **第 1 轮的外包从没在真实项目打开过**（意图：delegate 到位前不开、试点不开）：旧记录不迁移，读到第 1 轮格式的 `offload` 记录时 `show` 标「旧版记录」，`start` 拒绝并说明。
11. **每条新行为都只在开关打开、且模块在开工时被记为交给 Codex 时生效**；开关 `off` 时 `review approve`、开工通知、`status` 与改前逐字相同。

## 关键决策与取舍（请重点审）

1. **开关**（第 1 轮已有，不改）：`config set --codex-offload on (--original <原话> | --original-file <文件>)`，`checkLedger` 不是 `on` 就拒绝；其余条件不满足照样写入，但逐条警告。
   用户口头说「下一个模块交给 Codex」时，模块协调用这句原话执行同一条命令（`crew-coordinator` skill 写明）。
2. **（新）能不能外包（`offload.ready(db, project, module)`）**，全部满足才外包，否则给出第一条原因：
   ① 开关 `on`；② `checkLedger` 为 `on`；
   ③ 经 `probe.find_plugin("delegate")`／`read_interface` 读到 interface `>=1.3,<2.0`，且：`run.resume.option == "--resume"`、`"codex"` 在 `run.resume.backends`、`statuses` 含 `needs-input` 与 `timeout`；
   `run.continue.option == "--continue"`、`accepts` 含 `done`、`chain == "--resumable"`；`run.longRun.option == "--timeout"` 且 `maxSeconds >= 1800`；
   `run.result.schemaVersion == 1` 且有 `strict`；`run.writeAuthorization.option == "--authorized-by"`。缺哪一项就报哪一项；
   ④ spec-guard 接口有 `scopeCheck` 且 `moduleConcurrency` 打开；⑤ 该模块的模块会话宿主是 Claude Code（状态库会话登记）；⑥ `permissions.codex_trust` 不是 `untrusted`。
   第 1 轮的「模块协调在 Claude Code」去掉（模块协调不再调 delegate）。不要求 `run.check`（决策 12）。
3. **（新）交接点与授权文件**：`review approve` 批齐 Spec 与 Plan、要发开工通知的那一刻：
   - 开关关：逐字照旧。
   - 开关开、模块会话在 Codex（⑤ 不满足且宿主是 Codex）：照旧发今天的开工通知，输出多一行「外包：模块会话在 Codex，本模块不外包」——Codex 本来就在写，不必问用户。
   - 开关开、其余条件不满足：**不发**开工通知，输出原因与两条路（第 1 轮已有）：`offload decline <模块> --original-file <原话>` 改由模块会话自己构建，或补齐条件后重新 `review approve`。
   - 开关开、条件全满足：在同一事务里写 `offload/<模块>` 记录（`state: assigned`），并把授权文件写进状态库正文目录（普通文件、0600、写一次不再改），内容固定为：
     「用户打开额度外包开关的原话：<原话>（<时间>，config 事件号）；模块 <id>；Spec、Plan 批准事项 C<号>；模块 worktree <路径>」。记录里存它的路径与 sha256。
   - 开工时没被记为交给 Codex 的模块，以后 `offload start` 一律拒绝（「本模块开工时没交给 Codex，由 Claude 做完」），保证不中途切换。
4. **（新）开工通知的外包写法**（`review._start_todo`）：「要你做什么」改为
   「本模块的实现交给 Codex（项目开关 codexOffload）：先 `module-crew sync`；然后照 crew-dev「额度外包」一节，每个 Task 用 `module-crew offload start <模块>` 派给 Codex、跑完用 `offload settle` 核对并提交；检查点、最终验收照常由你处理。」
   不再要求模块会话发【等待其他会话】停下（第 1 轮的写法去掉）；`approve` 的输出多一行「外包：<模块> 交给 Codex，授权文件 <路径>」。
5. **（新）`offload start <模块>`（模块会话，在模块 worktree 里跑）**：核对 ①～⑥；记录是 `assigned`／`idle`（不是就按状态给出该跑的命令，退出码 3）；worktree 干净（重来时例外，见决策 10）；
   分支已包含 Spec、Plan 的批准提交；授权文件还在且 sha256 没变（变了退出码 3，停下问用户）。取 `tasks/<模块>/todo.md` 第一个未勾项：
   - 不是「Task」开头（检查点、最终验收、回告）：不派，退出码 3，提示「这一项由你按 Plan 处理，勾上后再 offload start」。
   - 这个 Task 已退回 Claude（决策 11）：不派，同样提示由模块会话自己写。
   - 否则写任务说明到状态库正文目录，记 `running`，输出要执行的命令（Bash **后台**运行，等完成通知，不轮询；stdout、stderr 分别存到给定文件，记下退出码）：
     - 记录里没有可接的 runId：`/delegate:run --write --resumable --strict --timeout 1800 --authorized-by <授权文件> -- "$(cat <任务说明>)"`
     - 有（上一轮 `done` 且没被接过）：`/delegate:run --continue <runId> --write --strict --timeout 1800 --authorized-by <授权文件> -- "$(cat <任务说明>)"`
   - 跑完：`module-crew offload settle <模块> --output <stdout 文件> --stderr <stderr 文件> --exit <退出码>`。
6. **（新）任务说明**（中文，短，机器生成）：模块、只做哪一个 Task（Plan 原文）、读 `spec/<模块>.md` 与 `tasks/<模块>/plan.md`；只改 Spec「并行边界」独占路径、本模块 spec 与 tasks、预先声明名单内的文件；
   不提交、不推送、不删除文件，改完留在工作区由模块会话核对提交；做完、相关测试通过后把 todo 里这一项勾上，别的项不动；
   遇到 Spec 没覆盖的决策、测试改不红、高风险不可逆改动就停下，答复首行以 `NEED_USER:` 开头写问题与选项；做完时首行以 `DONE:` 开头（`--strict` 要求）。
   接着同一条链时多一句「上一项已核对并提交（<提交号>，由 Codex／模块会话完成），先看一眼再做这一项」；重来时多一句核对结果（决策 10）。
7. **（新）`settle` 判结束状态**：先找结果行（stdout 末行）、`delegate: result=<路径>`（stdout 倒数第二行，或 stderr 里）；有路径就读结果文件。按下表归类，**表外一律「认不出」**：

   | 退出码 | 结果行／结果文件 `status` | 归类 |
   |---|---|---|
   | 0 | `done` | 做完 → 核对（决策 8） |
   | 0 | `needs-input` | 要问用户（决策 9） |
   | 124 | `timeout` | 超时（决策 9） |
   | 非 0（不是下面几行的退出码；`unmarked` 文档写明是 1，`failed`、`empty` 没写明） | 结果文件 `unmarked`、`failed`、`empty` | 没通过，可以重来 |
   | 143、130、129 | `interrupted` | 被停下，问用户 |
   | 125 | `unreaped`（或无结果文件） | 回收不了，问用户，提醒 Codex 起的进程可能还在改工作区 |
   | 64 | 无 | delegate 拒绝（参数、授权不一致等），问用户 |

   另外按「认不出」处理：结果行与结果文件的 `status`／`runId` 对不上；结果文件的 `authorization` 缺失或 sha256 与记录不同；输出文件读不出。
   「认不出」与上表里「问用户」的几类都附 stdout、stderr 最后 20 行，记 `stopped`。
8. **（新）done 的核对与提交**（核对步骤沿用第 1 轮）：① 本 Task 在 todo 里已勾、别的条目勾选状态没变；② `scopeCheck` 全在范围内；③ `git add` 后取暂存区的树按 `checks.check_tree` 跑快检查并记账（`by: offload`）；
   ④ 在模块分支提交，信息「<前缀>：<模块> <Task 编号>（Codex 实现，delegate run <runId>）」，前缀取 `commits.prefix_of`。成功：记 `idle`，记下可接的 runId 与提交号，计数清零，退出码 0，输出下一步。
   任何一步不过都**不提交、不回滚**，算这个 Task 没通过一次（决策 10）；这一轮的 runId 仍可接（状态是 done）。
9. **（新）needs-input 与 timeout**：都要用户的答复才往下走，模块会话把草稿正文作为【等待用户】发给模块协调（「模块：<模块>」「类型：卡住选做法」），由模块协调照现有规则转决策收件箱。
   - needs-input：问题原文逐字记下（假设 5），**不算没通过**；草稿「出了什么事：Codex 做 <Task> 时停下来问：」后接原文。
   - timeout：不跑快检查、不提交；进度说明为 `git status --short`、`git diff --stat`（相对派出时的顶端）与 `TIME_UP:` 之后的原文；**算没通过一次**。草稿选项：A 续跑／B 这一项改由 Claude 写（`offload takeover`）／C 先停。
   - 答复到了：`offload resume <模块> (--original-file <答复> | --source …)` 输出 `/delegate:run --resume <runId> --write --strict --timeout 1800 --authorized-by <授权文件> -- "$(cat <答复文件>)"`，同样后台跑、跑完 `settle`。没原话退出码 3；模块协调与模块会话都不替用户回答。
10. **（新）没通过时怎么办**：每个 Task 记连续没通过次数（核对不过、超时、`unmarked`／`failed`／`empty`、认不出、被停下、回收不了、delegate 拒绝都算；needs-input 不算；通过一次清零）。
    - **第 1 次**，且是「核对不过」或「`unmarked`／`failed`／`empty`」：**自动重来，不问用户**，`settle` 退出码 4 并直接给出重来的命令——核对不过时用 `--continue <这一轮 runId>`，任务说明多一段核对结果（越界文件、没勾或多勾的条目、快检查失败的最后 20 行）；
      `unmarked`／`failed`／`empty` 不能接链，另起一条 `--resumable` 链，任务说明多一句「工作区里有上次留下的改动，先看懂再接着做」。重来时工作区不必干净，沿用原 Task 与基线。
    - **第 1 次**，且是超时、认不出、被停下、回收不了、delegate 拒绝：停下问用户（退出码 5，草稿选项 A 续跑或重派／B 这一项改由 Claude 写／C 先停）。用户选 A：超时用 `offload resume`，其余用 `offload start <模块> --again --original-file <答复>`（另起链）。
    - **第 2 次**：自动退回 Claude（决策 11），退出码 4。唯一例外是「回收不了」（125）：Codex 起的进程可能还在改工作区，模块会话此时动手会和它抢，所以仍停下问用户。
11. **（新）退回 Claude**：记录里把这个 Task 记入 `claudeTasks`，状态回 `idle`，改动原样留在工作区；`settle` 输出给用户看的一句「<Task> 改由 Claude 写（Codex 连续 2 次没通过：<两次的原因>）」，模块会话照常 TDD 写完、自己提交、勾上。
    用户在停下时选 B 就跑 `offload takeover <模块> (--original-file <答复> | --source …)`，效果相同、记下用户原话。之后 `offload start` 派下一个 Task：有可接的 runId 就 `--continue`（任务说明写明上一项由模块会话完成），没有就另起 `--resumable` 链。
    **告诉用户的方式**：不发消息（契约里没有「只告知」的类型，本模块不新增类型，也不为告知占用一次【等待用户】）；模块会话在本会话回复与任务列表里写这一句，`offload show` 列出，最终验收的「做了什么」里写明哪些 Task 由 Claude 写、为什么。
12. **（新）不用的 delegate 参数**：
    - `--check`：检查账按树哈希记、只认 module-crew 跑出来的结果；delegate 的检查结果写在它的结果文件里，进不了检查账，两边都跑等于快检查跑两遍。快检查失败也已经能经 `--continue` 交回 Codex 修。
    - `--rules-file`：任务说明已经带规则；Codex 自己会读 worktree 根的 AGENTS.md；首行标记由 `--strict` 兜住。
    - `--model`、`--effort`：用 delegate 的默认（第 1 轮已定）。
13. **（新）外包记录**：`offload/<模块>`，内容
    `{"module", "version": 2, "state": "assigned"|"running"|"needs-input"|"timeout"|"stopped"|"idle", "approval": <C号>, "authorization": {"path", "sha256", "original"},
    "task": "<当前 Task 原文>", "base": "<派出时模块分支顶端>", "head": "<可接的 runId 或 null>", "failures": {"<Task 原文>": [<原因>, …]}, "claudeTasks": ["<Task 原文>", …],
    "runs": [{"runId", "parent", "task", "mode": "resumable"|"continue"|"resume", "startedAt", "settledAt", "exit", "status", "class", "question", "commit", "reason", "answer": {"original", "source"}}]}`。
    没有 `version` 的是第 1 轮记录（假设 10）。
14. **（新）模块协调这边**：`offload decline`（条件不满足时改由模块会话构建，第 1 轮已有）保留在模块协调；`offload handback` **去掉**（检查点、最终验收本来就在模块会话手里）；`offload start`／`settle`／`resume`／`takeover` 只能在该模块的模块会话 worktree 里跑（按 `module-crew bind` 登记的身份判断），别处跑退出码 3。
    `offload show` 任何会话都能跑。
15. **（新）已知未验证，写进 README「尚未验证」**：① 带 `--resumable` 的长期限运行被中止后的收尾轮（delegate-owner 的实测只覆盖了普通 run 的 `--timeout 600` 中止）；② 长期限下回收不了（退出 125）的真实情形。
    本模块对这两种情形分别按「超时」「回收不了」处理并用夹具测过，真实表现以后补测。

## 与第 1 轮的差别

| 第 1 轮 | 第 2 轮 |
|---|---|
| 模块协调跑 `offload start`／`settle`、执行 `/delegate:run`、代提交 | 模块会话自己跑、自己提交；模块协调不调 Codex |
| 每个 Task 新起一次 `--resumable` 运行 | 同一条链：首个 `--resumable`，之后 `--continue` |
| 前台、540 秒上限、退出 124 无结果行 | 后台、`--timeout 1800`、结果行 `status=timeout` |
| 只读结果行，认得三种组合 | 结果行 + `delegate: result=` 行 + 结果文件；新状态与退出码 125、64 逐个归类 |
| 认不出、核对不过一律停下问用户 | 同一 Task 连续 2 次没通过退回 Claude；第 1 次能自动重来的自动重来 |
| 写入授权靠「开关原话 + 批准」的口头约定 | `--authorized-by` 授权文件，结果文件里核对 sha256 |
| 外包期间模块会话发【等待其他会话】停下，检查点 `handback` 交还 | 模块会话一直在跑；`handback` 去掉 |
| interface ≥ 1.1，1.2 可选 | interface ≥ 1.3 且五项能力标记齐全，否则不外包 |

## 接口约定

### 命令

```bash
bin/module-crew config set --codex-offload on|off (--original <原话> | --original-file <文件>)       # 模块协调
bin/module-crew offload decline <模块> (--original <原话> | --original-file <文件>)                    # 模块协调：条件不满足时改由模块会话构建
bin/module-crew offload start <模块> [--again (--original <原话> | --original-file <文件> | --source …)]   # 模块会话
bin/module-crew offload settle <模块> --output <stdout 文件> --stderr <stderr 文件> --exit <退出码>     # 模块会话
bin/module-crew offload resume <模块> (--original <答复> | --original-file <文件> | --source …)          # 模块会话
bin/module-crew offload takeover <模块> (--original <答复> | --original-file <文件> | --source …)        # 模块会话：用户选「这一项改由 Claude 写」
bin/module-crew offload show [<模块>] [--json]
```

- 退出码：`0` 成功（`settle` 的 done 已提交）；`2` 参数错；`3` 拒绝、什么都不写（开关没开、条件不满足、不是交给 Codex 的模块、状态不对、worktree 不干净、不在模块会话、没有原话）；
  `4` `settle` 没通过但不用问用户（自动重来或退回 Claude，照输出下一步做）；`5` `settle` 停下要问用户（needs-input、超时、认不出等，记录已写、草稿已给）。
- `settle` 只读给它的文件，不自己跑 delegate；module-crew 从不直接调 delegate 的脚本。

### 记录

```json
// config/main
{"codexOffload": "on"}
// offload/<模块>：见决策 13
```

### 读的上游接口

- delegate `interface.json`：`interface`、`run.resume`、`run.continue`、`run.longRun`、`run.result`、`run.writeAuthorization`（决策 2 ③）。
- delegate 输出：结果行、`delegate: result=<路径>`、结果文件顶层 `status`、`exitCode`、`runId`、`authorization`；`NEED_USER:`、`TIME_UP:`、`DONE:`。
- spec-guard `interface.json`：`scopeCheck`（`python3 -B hooks/module_scope.py check --project <模块 worktree> --module <id> --base <派出时顶端> --format json`）。

## 项目结构（要改的文件与函数）

```text
module_crew/offload.py       改：ready 读 1.3 能力标记；assign（开工时记录与授权文件）；start/settle/resume 改由模块会话跑、链与续接；结果文件解析、
                             归类表、失败计数、takeover；去掉 handback；show 区分旧版记录
module_crew/review.py        _start_todo：外包写法改文案；开关开、条件满足时调 offload.assign；模块会话在 Codex 时照旧发通知
module_crew/__main__.py      offload 子命令：settle 加 --stderr，加 takeover，去掉 handback
skills/crew-dev/SKILL.md、codex-skills/crew-dev/SKILL.md                   「额度外包」一节重写（Claude 版写派出、后台运行、settle 各退出码；Codex 版写「模块会话在 Codex 时不外包」）
skills/crew-coordinator/SKILL.md、codex-skills/crew-coordinator/SKILL.md   「额度外包」一节重写（只管开关、开工、转达、decline）
README.md                    命令一览、「一次完整流程」的外包一段、「尚未验证」补决策 15 的两项
tests/test_codex_offload.py  改写
```

只调用、不改：`declared.py`、`checks.py`、`permissions.codex_trust`、`probe.find_plugin`／`read_interface`、`commits.prefix_of`、`protocol.render_coordination_notice`、`store`（`KINDS` 已有 `offload`）。
不改：`merge.py`、`probe.py`、`start.py`、`changes.py`、`present.py`、`protocol.py`、`sync.py`、`store.py`。

## 命令

```bash
python3 -m unittest discover -s tests
PYTHONPATH=tests python3 -m unittest test_codex_offload
```

## 代码风格

沿用现有模块：代码与注释英文，输出中文；只用标准库；git 与 spec-guard 调用带超时、参数列表、不经 shell；上游一律经 interface.json 与 README 列出的输出取，不读 delegate 内部文件。

## 测试策略

- 假 delegate 插件夹具：只放 `interface.json`（1.2、1.3 完整、1.3 各缺一项能力标记），不放脚本；delegate 的输出用测试写好的 stdout、stderr 文本与结果文件喂给 `settle`：
  done、needs-input（有无 `delegate: result=` 行两种）、timeout、unmarked、failed、empty、interrupted、125、64、未知状态、结果行与结果文件不一致、授权 sha256 不同、输出文件读不出。
- 假 spec-guard 夹具、集成 checkout 与模块 worktree、快检查小脚本沿用第 1 轮。
- 开关关着：`review approve`、开工通知与改前输出逐字相同。
- 回归：全量测试通过（放后台跑）。

## 边界

- **始终**：只在开关打开、开工时记为交给 Codex 的模块上外包；每次 `--write` 都带同一个授权文件；只认 delegate 的对外输出；越界、快检查不过、没认出做完都不提交、不回滚；检查点与最终验收由模块会话处理。
- **先问**：打开或关掉开关；needs-input 的答复；超时后续跑；第 1 次就认不出、被停下、回收不了、delegate 拒绝之后的下一步；条件不满足时改由模块会话构建。
- **绝不**：替用户回答 Codex 的问题；把认不出的状态当完成；超时时提交或跑快检查；模块协调调 Codex 或代提交；读 delegate 的内部文件或直接调它的脚本；删除或回滚 Codex 改的文件；推送；模块中途整体换手。

## 验收标准

1. `ready`：delegate 1.2、1.3 各缺一项能力标记（`run.continue`、`run.longRun` 或 `maxSeconds < 1800`、`run.result`、`run.writeAuthorization`、`run.resume` 没有 `timeout`）时各给出对应原因；spec-guard 与信任两项照旧；全满足时通过。
2. 开关没设或 `off`：`review approve` 的输出与开工通知和改前逐字相同（用改前的输出做对照）。
3. 开关 `on` 且条件满足：`review approve` 批齐后写 `offload/<模块>`（`assigned`、`version: 2`）与授权文件（内容含原话、模块、批准事项号，sha256 记进记录），开工通知是决策 4 的写法、被 `protocol.parse` 判为合格；
   模块会话在 Codex 时照旧发通知并输出「不外包」一行；其余条件不满足时不发通知并输出原因；`offload decline` 带原话后发出今天的开工通知。
4. `offload start`：第一次输出 `--resumable --strict --timeout 1800 --authorized-by <授权文件>` 写法，上一轮 done 后输出 `--continue <runId>` 写法；任务说明含 Task 原文、三种必停情况、`NEED_USER:`、`DONE:`、不提交不推送不删除；
   下一项不是 Task、Task 已退回 Claude、模块开工时没交给 Codex、不在模块会话、授权文件 sha256 变了、worktree 不干净、分支没包含批准提交时退出码 3 且什么都不写。
5. `settle` done：只改范围内文件、勾了本 Task、快检查通过时模块分支多一个提交（信息含 Task 编号与 runId），检查账有 `by: offload` 的记录，记录 `idle`、`head` 为这一轮 runId；
   越界、没勾、多勾、快检查失败时不提交、文件原样留着，退出码 4，输出 `--continue <runId>` 的重来命令，任务说明含核对结果。`declaredScope` 打开时名单内的公共文件算范围内。
6. `settle` needs-input：问题原文逐字相同；stdout 倒数第二行是 `delegate: result=…` 时不进问题正文，没有这一行时问题正文不缺字；草稿被 `protocol.parse` 判为合格；不计没通过次数。
   `offload resume` 没原话退出码 3，有原话时输出 `--resume <runId> --write --strict --timeout 1800 --authorized-by` 写法并记下答复。
7. `settle` timeout：快检查脚本没被调用、不提交，记录 `timeout`，输出 `git status --short`、`diff --stat`、`TIME_UP:` 原文与 ABC 三个选项，退出码 5。
8. 归类表每一行与「认不出」的四种情形各有测试：退出码与归类、`stopped` 时附最后 20 行；`unmarked`／`failed`／`empty` 第 1 次退出码 4、给出另起 `--resumable` 链的命令；125 在第 2 次仍退出码 5。
9. 同一 Task 第 2 次没通过：退出码 4，记录把它记入 `claudeTasks`，输出「改由 Claude 写」一句与两次的原因；之后 `offload start` 对这个 Task 拒绝、对下一个 Task 照常派出（有可接 runId 时 `--continue`）。`offload takeover` 没原话退出码 3，有原话时效果相同并记下原话。
10. 读到第 1 轮格式的记录：`offload show` 标「旧版记录」，`offload start` 退出码 3。`offload handback` 已不存在（参数错，退出码 2）。
11. `offload show` 与 `--json` 列出状态、当前 Task、链上的 runId、外包提交、退回 Claude 的 Task 与原因、待答问题。
12. skill：`crew-dev`（两份）写明模块会话自己派出、后台运行与等通知、`settle` 各退出码怎么办、needs-input 与超时发【等待用户】、退回 Claude 时照常写并告诉用户；
    `crew-coordinator`（两份）写明开关凭原话（含口头说「交给 Codex」）、开工时的三种情形、不调 Codex 不代提交、转达答复不替用户回答。
13. 全量测试通过；本机 delegate 0.8.0 在一个临时仓库实测一次：`--resumable --strict --timeout 600` 跑一个小 Task、`settle` 判 done 并提交，再 `--continue` 跑第二个小 Task 同样提交；把两次的结果行、结果文件状态与 `settle` 输出写进最终验收（测不成照实写原因）。

## 并行边界

- 独占：`module_crew/offload.py`、`module_crew/review.py`、`module_crew/__main__.py`、`skills/crew-dev/SKILL.md`、`codex-skills/crew-dev/SKILL.md`、`skills/crew-coordinator/SKILL.md`、`codex-skills/crew-coordinator/SKILL.md`、`README.md`、`tests/test_codex_offload.py`
- 公共：测试资源

## 未决问题

- 能力图里本模块那一行还是第 1 轮的描述（「由模块协调经 delegate……代为提交」「delegate 1.2 作可选依赖」）：能力图是公共文件，请模块协调安排改写（建议：「额度外包第 2 轮——开关打开后开工的模块由 Claude 模块会话经 delegate 1.3 把 Task 交给同一个 Codex 会话（--resumable 起头、--continue 接续），自己核对、快检查、提交；同一 Task 连续 2 次没通过退回 Claude；认不出的状态不算完成」）。
- 决策 15 的两项真实表现待补测；delegate 以后给 `statuses` 追加的新值一律落「认不出」，到时再按需修订归类表。

## 文档建议

README「命令一览」改 `offload` 子命令（加 `takeover`、`settle --stderr`，去 `handback`）；「一次完整流程」的外包一段按新分工重写；「尚未验证」补决策 15 的两项。CHANGELOG 随发版写。

## 变更记录

- 2026-10-28：第 2 轮修订——外包改由模块会话自己调用 delegate、自己提交，同一个 Codex 会话跨 Task 续接（`--continue`），接入 delegate 接口 1.3（结果文件、`--timeout`、`--authorized-by`、`--strict`），退出码 125、64 与新结束状态逐个归类，`delegate: result=` 行不进问题正文，同一 Task 连续 2 次没通过退回 Claude，去掉 `handback`，已知未验证两项写进决策 15。
  原因：外包做法按 S38 意图改方向（用户 2026-10-27 确认意图、批准 S38），delegate v0.8.0 已发布。来源：用户本人在 mc-coord 会话（原话「开工 crew-codex-offload 修订，重开模块写 Spec 交审」，用户批准事项 C304）。
