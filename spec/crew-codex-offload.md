# Spec: crew-codex-offload

> 能力图模块 `crew-codex-offload`（第十版第 4 个）。需求来源：接缝 S32，已批方案 plugin-ecosystem `proposals/2026-10-24-S32-并行流畅与额度外包.md`（612634c，用户 2026-10-24「按推荐批准」）
> 第二节 module-crew 第 6 条与文末补记（2026-10-25：提交走兜底，由协调会话代提交，这一轮不写前缀放行规则）；第三节守门。开会话依据：用户批准事项 C230。
> 依赖 `crew-declared-scope`（`module_crew/declared.py`：名单内判据）、`crew-check-ledger`（`module_crew/checks.py`：快检查与检查账）；上游 delegate 0.6.0（interface 1.1 的 `run.resume`）、spec-guard 0.85.0（interface 1.11 的 `scopeCheck`）。
> 标「新」的是写 Spec 时补的实现取舍，请重点审。

## 目标

项目打开开关 `codexOffload` 后，模块的 Spec、Plan 照旧由模块会话（Claude）写、由用户批；批完后，Plan 里的实现任务不再由模块会话自己做，
而由模块协调经 delegate 把任务一个一个交给 Codex 在模块 worktree 里跑，省下 Claude 的额度。Codex 只改文件、不提交；
模块协调核对改动都在本模块范围内、跑过快检查后，替它在模块分支上提交。Codex 停下来的方式按结束状态分别处理：
做完（done）就核对并代提交；要问用户（needs-input）就把问题原样转给用户、带着用户的答复续跑；超时（timeout）不代提交，先把进度交给用户，续跑要用户点头；
认不出的结果一律停下问用户，不自动重派。检查点和最终验收交回模块会话，照今天的做法。没打开开关、或读不到需要的新接口时，一切和今天一样。

## 范围

**范围内**

1. **项目开关** `codexOffload`（运行配置 `config/main`，`on`／`off`，没设过等于 `off`）：`config set --codex-offload on|off` 凭用户原话写入。
2. **能不能外包的核对**（决策 2）：delegate 接口 ≥ 1.1 且有 `run.resume`、spec-guard 有 `scopeCheck`、检查记账已打开、模块协调在 Claude Code、Codex 没把项目标为不信任。
3. **开工通知分叉**（决策 4）：`review approve` 批齐 Spec 与 Plan、开关打开且核对通过时，开工通知改成「外包」写法；核对不通过时不发开工通知，交用户决定。
4. **派出**：新命令 `module-crew offload start <模块>`，取 todo 里第一个未勾的实现任务，生成交给 Codex 的任务说明，给出模块协调要执行的 `/delegate:run` 写法。
5. **收结果**：新命令 `module-crew offload settle <模块> --output <文件> --exit <退出码>`，按结束状态分流（决策 6～9），done 时核对范围、跑快检查、代提交。
6. **续跑与重派**：`offload resume`（needs-input，以及 delegate ≥ 1.2 的 timeout）带用户的答复续跑；`offload start --again`（1.1 的 timeout、认不出、核对失败后）在用户点头后重派。
7. **交还模块会话**：做到检查点、最终验收，或用户选「交还模块会话」时，`offload handback` 生成给模块会话的通知。
8. **只读查看**：`offload show [<模块>] [--json]`。
9. **skill 与文档**：`crew-coordinator`、`crew-dev`（Claude 与 Codex 各两份）、README。

**范围外**

- 给外包写 `.codex/rules` 的 `git add`／`git commit` 前缀放行规则（方案补记：这一轮不用）；改 delegate 写入模式「可以修改文件，但不要提交、不要推送」的规矩。
- 改 delegate、spec-guard、session-protocol、decision-inbox：只按它们已发布的接口与契约用；不新增消息类型。
- 自动审查代理代批（方案第二节第 6 条：不用）；Codex 的交付仍由用户在最终验收时批。
- 自治档位（`crew-autonomy-tier`）：它以后按自己的规则替用户开关本开关，本模块只提供开关。
- Codex 版模块协调发起外包：delegate 是 Claude Code 插件，模块协调在 Codex 时不外包（决策 2）。
- 指定 Codex 的模型、推理档：用 delegate 的默认，不加 `--model`／`--effort`。
- 合并本身：`module_crew/merge.py` **不改**。

## 假设（请逐条确认）

1. **提交走兜底（用户在 ecosystem-lead 会话原话「走 A：…由 mc-coord 代为 git add 和 commit（用方案里已有的兜底）…」）**：Codex 只在模块 worktree 改文件，不提交、不推送；
   模块协调核对改动全在本模块范围内、快检查通过后，用 module-crew 命令在模块分支上代为 `git add` 和 `git commit`。这一轮不为外包写 `.codex/rules` 的 git 前缀放行规则。
2. **写入授权的来源**：delegate 要求「用户明确要求写文件才加 `--write`」。本模块把「打开 `codexOffload` 的用户原话」加上「该模块 Spec、Plan 的用户批准」当作对这个模块全部实现任务的写入授权，
   每次派出、每个任务不再单独问用户；续跑（needs-input、timeout）与重派仍要用户的答复或点头（决策 8、9）。
3. **（新）一次只派一个任务**：delegate 单次上限 540 秒（超时退出 124），整个模块一次跑不完。每次只交 todo 里第一个未勾的「Task」条目，做完代提交后再派下一个；
   检查点（`Checkpoint`）、最终验收、回告等非 Task 条目不交给 Codex，交还模块会话按今天的做法处理（决策 10）。
4. **「本模块范围」按 spec-guard `scopeCheck` 判**：相对派出时模块分支的顶端，改动（含未提交、未跟踪）的每个文件都必须是 `exclusive`（Spec「并行边界」的独占路径）或 `own`（本模块的 `spec/<id>.md`、`tasks/<id>/`）；
   `declaredScope` 开关打开且声明可用时，Plan「预先声明」名单内的文件也算范围内（`declared.inside`）。其余都是越界，一个越界整次不代提交。删除文件一律当越界（spec-guard 规定删除不能预先声明）。
5. **快检查来自 `crew-check-ledger`**：打开 `codexOffload` 前必须已打开 `checkLedger`（因而已有 `quickCheckCommand` 与 `checkCommand`）；代提交前的快检查照 `change land` 的做法取暂存区的树跑并记账（`by: offload`）。
6. **结束状态的来源**：只认 delegate 的结果行 `delegate: run_id=<id> status=<状态> resumable=<true|false>`（stdout 最后一行）和退出码；`needs-input` 的问题是答复里 `NEED_USER:` 之后的全文。
   delegate 1.1 认得的组合只有三种：退出码 0 + `status=done`、退出码 0 + `status=needs-input`、退出码 124 且没有结果行（超时）。其余一律「认不出」。
7. **delegate 1.2 是可选依赖**：1.2（还在实测）超时时也返回 `runId` 并附进度说明。读到 interface ≥ 1.2 且 `run.resume.statuses` 含 `timeout`、结果行是 `status=timeout` 时，用这个 `runId` 续跑；
   读到 1.1 时超时只能看 diff、经用户点头后从头重派。1.2 的进度说明格式还没定，本模块原样转给用户、不解析。
8. **Codex 信任**：Codex 在 git worktree 里运行时信任键是主仓库路径，查主仓库路径即可（复用 `permissions.codex_trust`）；delegate 起 `--write` 不再改 `~/.codex/config.toml`。
   用户明确标为 `untrusted` 时不外包、停下问用户；没设（`not-set`）照常外包，由 delegate 自己的检查决定能不能跑。
9. **needs-input 的问题经模块协调转给用户**：走现有的【等待用户】、决策收件箱和【用户答复】转达；答复要用户原话（或用户明确同意的转述），模块协调不替用户回答。
10. **外包期间模块会话不动 worktree**：收到外包开工通知后先 `module-crew sync`，再发一条【等待其他会话】（等 Codex 外包实现）后停下；期间收到同步基线通知也先不同步（工作区可能有 Codex 改到一半的文件）。
11. **每条新行为都只在开关打开时生效**；开关 `off` 时 `review approve`、开工通知、`status` 与改前逐字相同，`offload` 子命令退出码 3 并说明开关没开。

## 关键决策与取舍（请重点审）

1. **（新）开关凭用户原话写**：`config set --codex-offload on (--original <原话> | --original-file <文件>)`，与 `--check-ledger` 同一入口、同一事务，事件里记原话。
   打开时 `checkLedger` 不是 `on` 就拒绝（退出码 3，说明先开检查记账）；其余条件（决策 2）不满足照样写入，但逐条警告「打开后这几项不满足时不外包，照今天由模块会话构建前先问用户」。
2. **（新）能不能外包（`offload.ready(db, project, module)`）**，全部满足才外包，否则给出第一条原因：
   ① 开关 `on`；② `checkLedger` 为 `on`；③ 经 `probe.find_plugin("delegate")`／`read_interface` 读到 interface `>=1.1,<2.0` 且 `run.resume.option == "--resume"`、`"codex"` 在 `run.resume.backends`；
   ④ spec-guard 接口有 `scopeCheck` 且 `moduleConcurrency` 打开；⑤ 模块协调宿主是 Claude Code（`handover.coordinator_host`）；⑥ `permissions.codex_trust` 不是 `untrusted`。
   这里只读 interface.json，不读 delegate 的内部文件（delegate README：「供其他插件按版本对接，不读本插件内部文件」）。
3. **（新）由模块协调亲自执行 `/delegate:run`，module-crew 不直接调 delegate 的脚本**：module-crew 只生成任务说明和命令写法、事后解析输出。原因：delegate 的对外接口是 `/delegate:run` 命令，脚本路径不属于接口；
   这样 delegate 的授权、超时、日志规矩原样生效。代价是派出与收结果要模块协调各跑一步命令（`offload start`、`offload settle`）。
4. **（新）开工通知的「外包」写法**（`review.approve` 里渲染开工通知的那一段，抽成 `_start_todo(db, m)`）：开关打开、`ready` 通过时，「要你做什么」改为
   「本模块的实现外包给 Codex（项目开关 codexOffload）：先 `module-crew sync`，然后不构建、不改本 worktree；发一条【等待其他会话】给模块协调（等：Codex 外包实现）后停下；外包期间收到同步基线通知先不同步。
   做到检查点或最终验收时模块协调会发恢复通知交还给你。」；`approve` 的输出多一行「外包：模块会话发来等待后运行 module-crew offload start <模块>」。
   `ready` 不通过时**不发**开工通知，输出「外包条件不满足：<原因>；问用户：改由模块会话自己构建（offload decline <模块> --original-file 发今天的开工通知），还是先补齐条件（补齐后 offload start）」。开关关闭时逐字不变。
5. **（新）`offload start <模块>`（模块协调，在集成 checkout 跑）**：核对 `ready`；模块 worktree 干净；模块分支已包含 Spec、Plan 的批准提交（没有就退出码 3「等模块会话 sync」）；
   没有正在跑或待处理（`running`／`needs-input`／`timeout`／`stopped`）的外包。取 `tasks/<模块>/todo.md` 第一个未勾项：不是「Task」开头的条目就不派，改提示 `offload handback`（决策 10）。
   派出时记 `offload` 记录（决策 11），把任务说明写到状态库的正文目录，输出模块协调要执行的命令：
   在模块 worktree 里、Bash 后台运行、超时 600000，`/delegate:run --write --resumable -- "$(cat <任务说明文件>)"`，标准输出存到给定文件，跑完再 `offload settle`。
   任务说明（中文，短）写明：模块、只做哪一个 Task（原文）、读 `spec/<模块>.md`、`tasks/<模块>/plan.md`；只改 Spec「并行边界」独占路径、本模块 spec 与 tasks、预先声明名单内的文件；
   不提交、不推送、不删除文件；做完这个 Task、相关测试通过后把 todo 里这一项勾上，别的项不动；先做不受待定决策影响的部分，遇到 Spec 没覆盖的决策、测试改不红、高风险不可逆改动三种情况，用 `NEED_USER:` 开头写出要问用户的问题后停下。
6. **（新）`offload settle` 的 done 分支**：按顺序核对，任何一步不过都**不提交、不回滚**（文件原样留在 worktree），状态记为 `stopped` 并给出原因与【等待用户】草稿（决策 9）：
   ① 本次的 Task 在 todo 里已勾、且除它之外没有别的条目的勾选状态变化（没勾就是「没认出做完」，模型漏写 `NEED_USER:` 也会判为 done）；
   ② `scopeCheck` 全部在范围内（假设 4），列出越界文件；③ `git add` 这些文件后用 `git write-tree` 取树，按 `checks.check_tree` 跑快检查并记账（通过或已有通过记录才继续）；
   ④ 在模块分支提交，信息「<前缀>：Codex 外包 <模块> <Task 编号>（delegate run <runId>）」，前缀取 `commits.prefix_of`。成功后输出提交号与下一步（下一个是 Task 就 `offload start`，否则 `offload handback`）。
   已批范围内的连续派出不问用户（R21）。
7. **（新）needs-input 分支**：状态记 `needs-input`，记下 `runId` 与问题原文（`NEED_USER:` 之后全文，不改字）；输出一份【等待用户】正文草稿（「模块：<模块>」「类型：卡住选做法」，「出了什么事：Codex 做 <Task> 时停下来问：」后接问题原文），
   由模块协调照现有规则交决策收件箱或在本会话问用户。用户答复到了：`offload resume <模块> (--original-file <答复> | --source …)`，输出 `/delegate:run --resume <runId> --write -- "$(cat <答复文件>)"` 的写法，跑完同样 `offload settle`。
8. **（新）timeout 分支**：不跑快检查、不提交。状态记 `timeout`，输出进度说明：模块 worktree 的 `git status --short` 与 `git diff --stat`（相对派出时的顶端），delegate 1.2 的进度说明原样附上；
   给出【等待用户】草稿，选项：A 续跑（1.2 有 `runId` 时 `offload resume`；1.1 时 `offload start --again`，Codex 在已有改动上接着做）／B 交还模块会话自己做（`offload handback`）／C 先停（用户自己看）。三个选项都要用户的答复才执行，模块协调不自动续跑。
9. **（新）认不出与核对失败**：退出码 64（delegate 拒绝）、其他非 0 退出码、退出码 0 却没有结果行、`status` 不在已知集合、`--output` 文件读不出——状态记 `stopped`（原因「认不出 delegate 的结束状态：…」），附输出最后 20 行，
   【等待用户】选项：A 重派（`offload start --again --original-file`）／B 交还模块会话／C 先停。**不自动重派**。done 核对失败（决策 6）用同一组选项。
10. **（新）交还模块会话（`offload handback <模块>`）**：没有待处理的外包时可用；生成一条【协调通知】（类型「恢复」，依据写 Spec、Plan 的批准事项号与外包的提交范围），
    「要你做什么」：「外包已停在 <条目>：先 `module-crew sync`，对照 Spec 看一遍 Codex 的提交（`git log <起>..<止>`），再按 Plan 处理这一项（检查点照 gate／report 规则、最终验收照常交审）；
    做完检查点、还有 Task 时再发【等待其他会话】，模块协调接着外包」；同时提示模块协调关掉模块会话那张等待记录（模块会话收到后自己发【已恢复】）。
    选「恢复」是因为契约里没有更贴切的类型，而它要求依据写批准事项号、语义是「从停点继续」，不用改契约。用户选 B 时由 handback 把状态从 `stopped`／`timeout` 改成 `handed-back`，此后不再外包这个模块，除非用户说重新开始（`offload start --again`）。
11. **（新）外包记录**：状态库新增记录种类 `offload`，键为模块 id，内容
    `{"module", "state": "running"|"needs-input"|"timeout"|"stopped"|"idle"|"handed-back", "approval": <C号>, "task": "<条目原文>", "base": "<派出时模块分支顶端>",
    "runs": [{"runId", "task", "startedAt", "settledAt", "exit", "status", "question", "commit", "reason", "answer": {"original", "source"}}]}`。旧版读到当作不认识的种类跳过（同 `check`）。
12. **（新）`offload show`**：只读，列出每个模块的外包状态、当前 Task、已提交的外包提交、待用户答复的问题；`--json` 输出记录原样。`status` 不改（避免和 `crew-autonomy-tier` 抢 `probe.py`）。

## 接口约定

### 命令

```bash
bin/module-crew config set --codex-offload on|off (--original <原话> | --original-file <文件>)
bin/module-crew offload start <模块> [--again (--original <原话> | --original-file <文件> | --source …)]
bin/module-crew offload settle <模块> --output <文件> --exit <退出码>
bin/module-crew offload resume <模块> (--original <答复> | --original-file <文件> | --source …)
bin/module-crew offload handback <模块>
bin/module-crew offload decline <模块> (--original <原话> | --original-file <文件>)    # 条件不满足时改由模块会话构建
bin/module-crew offload show [<模块>] [--json]
```

- 退出码：`0` 成功（`settle` 的 done 已提交）；`2` 参数错；`3` 拒绝、什么都不写（开关没开、条件不满足、状态不对、worktree 不干净、没有原话）；
  `5` `settle` 停下要问用户（needs-input、timeout、认不出、核对失败，记录已写、草稿已给）。
- `settle` 用 `--output` 与 `--exit` 收 delegate 的输出，不自己跑 delegate。

### 记录（只增不改）

```json
// config/main
{"codexOffload": "on"}
// offload/<模块>：见决策 11
```

### 读的上游接口

- delegate `interface.json`：`interface`、`run.resume.{option, backends, statuses}`；结果行 `delegate: run_id=<id> status=<状态> resumable=<true|false>`；`NEED_USER:`。
- spec-guard `interface.json`：`scopeCheck`（`python3 -B hooks/module_scope.py check --project <模块 worktree> --module <id> --base <派出时顶端> --format json`）。

## 项目结构（要改的文件与函数，供协调排写码先后）

```text
module_crew/offload.py       新：enabled、ready、render_brief、start、settle、resume、handback、decline、show；结果行解析；进度说明
module_crew/store.py         KINDS 加 offload
module_crew/review.py        approve：开工通知那一段抽成 _start_todo(db, m)，开关打开时走外包写法或扣下通知
module_crew/__main__.py      config set --codex-offload；offload 子命令组
skills/crew-coordinator/SKILL.md、codex-skills/crew-coordinator/SKILL.md   新增「额度外包」一节
skills/crew-dev/SKILL.md、codex-skills/crew-dev/SKILL.md                   新增「外包期间」一节
README.md                    命令一览与「一次完整流程」补外包
tests/test_codex_offload.py  新
```

只调用、不改：`declared.py`（`enabled`、`read`、`inside`）、`checks.py`（`enabled`、`check_tree`）、`permissions.codex_trust`、`handover.coordinator_host`、`probe.find_plugin`／`read_interface`／`safe_command`、`commits.prefix_of`、`protocol.render_coordination_notice`。
不改：`merge.py`、`probe.py`、`start.py`、`changes.py`、`present.py`、`protocol.py`、`sync.py`。

## 命令

```bash
python3 -m unittest discover -s tests
PYTHONPATH=tests python3 -m unittest test_codex_offload
```

## 代码风格

沿用现有模块：代码与注释英文，输出中文；只用标准库；git 与 spec-guard 调用带超时、参数列表、不经 shell；上游一律经 interface.json 取，不读 delegate 内部文件。

## 测试策略

- 假 delegate 插件夹具：只放 `interface.json`（1.0、1.1、1.2 三份），不放脚本；delegate 的「输出」用测试写好的文本文件喂给 `settle`：done、needs-input、超时（124、无结果行）、1.2 的 `status=timeout`、退出码 64、0 但无结果行、未知状态。
- 假 spec-guard 夹具沿用 `crew-declared-scope` 的（加 `scopeCheck` 指向小脚本，按文件名答 exclusive／own／outside）。
- 复用 crew-merge／crew-check-ledger 的测试基类：集成 checkout、模块 worktree、快检查小脚本（按文件是否存在决定成败）。在模块 worktree 里直接改文件模拟 Codex 的改动。
- 开关关着：`review approve`、开工通知与改前输出逐字相同；`offload` 各子命令退出码 3。
- 回归：全量测试通过（放后台跑）。

## 边界

- **始终**：只在开关打开且条件满足时外包；只认 delegate 的结果行与退出码；越界、快检查不过、没认出做完都不提交、不回滚；检查点与最终验收交还模块会话。
- **先问**：打开或关掉开关；needs-input 的答复；timeout 后续跑或重派；认不出、核对失败后的任何下一步；条件不满足时改由模块会话构建。
- **绝不**：替用户回答 Codex 的问题；自动重派或自动续跑；超时时代提交或跑快检查；读 delegate 的内部文件或直接调它的脚本；删除或回滚 Codex 改的文件；推送。

## 验收标准

1. `config set --codex-offload on --original "打开额度外包"`：`checkLedger` 为 `on` 时写入、事件记原话，条件不满足时逐条警告；`checkLedger` 不是 `on` 时退出码 3、配置不变；没原话退出码 3。
2. 开关没设或 `off`：`review approve` 的输出与开工通知和改前逐字相同（用改前的输出做对照）；`offload start|settle|resume|handback|decline|show` 退出码 3 并说明开关没开。
3. `ready`：六项条件各缺一项时给出对应原因（delegate 1.0、没有 `run.resume`、没有 `scopeCheck`、`moduleConcurrency` 关、模块协调在 Codex、项目 `untrusted`）；全满足时通过。
4. 开关 `on` 且条件满足：`review approve` 批齐 Spec 与 Plan 后的开工通知是决策 4 的外包写法、被 `protocol.parse` 判为合格；条件不满足时不发开工通知并输出原因；`offload decline` 带原话后发出今天的开工通知。
5. `offload start`：todo 第一个未勾项是 Task 时记 `running`、写任务说明（含 Task 原文、三种必停情况、`NEED_USER:`、不提交不推送不删除）并输出 `/delegate:run --write --resumable` 写法；
   第一个未勾项是 Checkpoint 时不派、提示 handback；worktree 不干净、模块分支没包含批准提交、已有待处理外包时退出码 3 且什么都不写。
6. `settle` done：只改了范围内文件、勾了本 Task、快检查通过时，模块分支多一个提交（信息含 Task 编号与 runId），检查账有 `by: offload` 的快检查记录，记录 `idle` 并记 `commit`；
   有越界文件、没勾本 Task、勾了别的项、快检查失败时都不提交、文件原样留着，退出码 5，记录 `stopped` 带原因，草稿列出越界文件或失败行。`declaredScope` 打开时名单内的公共文件算范围内。
7. `settle` needs-input：记录 `needs-input`、`runId`、问题原文逐字相同；【等待用户】草稿含原文、被 `protocol.parse` 判为合格；`offload resume` 没原话退出码 3，有原话时输出 `--resume <runId> --write` 写法并记下答复。
8. `settle` 超时（1.1：退出码 124、无结果行）：不跑快检查（脚本没被调用）、不提交，记录 `timeout`，输出 `git status --short` 与 `diff --stat`、ABC 三个选项；`offload start --again` 没原话退出码 3。
   delegate 1.2 夹具、结果行 `status=timeout`：选项 A 给 `offload resume` 写法、进度说明原样附上。
9. 认不出：退出码 64、其他非 0、0 但无结果行、未知状态值、输出文件读不出，都记 `stopped`、退出码 5、附最后 20 行，不给任何自动续跑的命令。
10. `offload handback`：生成类型「恢复」的【协调通知】，依据含批准事项号，被 `protocol.parse` 判为合格；之后记录 `handed-back`，`offload start` 不带 `--again` 时退出码 3。
11. `offload show` 与 `--json` 列出状态、当前 Task、外包提交与待答问题。
12. skill：`crew-coordinator`（两份）写明开关要用户原话、派出与收结果的两步、三种结束状态各怎么办、认不出停下问用户、不替用户答复、交还时机；
    `crew-dev`（两份）写明收到外包开工通知后 sync、发等待、外包期间不动 worktree 也不同步、收到交还通知后的做法。
13. 全量测试通过；本机 delegate 0.6.0 实测一次：在一个临时仓库里用 `/delegate:run --write --resumable` 跑一个小任务，把结果行与 `settle` 的输出写进最终验收（测不成照实写原因）。

## 并行说明

`crew-autonomy-tier` 同时在写 Spec，可能改到的共同文件：`review.py`（它可能改评审节奏相关段落；本模块只改 `approve` 里渲染开工通知的那一段）、`__main__.py`（各加子命令与 `config set` 参数，不同段落）、
两份 `crew-coordinator`、两份 `crew-dev` skill 与 README（各加一节）、`store.py` 的 `KINDS`（若它也加记录种类，同一行）。建议它先合入、本模块后写码，或反过来，由模块协调排。

## 并行边界

- 独占：`module_crew/offload.py`、`module_crew/review.py`、`module_crew/store.py`、`module_crew/__main__.py`、`skills/crew-dev/SKILL.md`、`codex-skills/crew-dev/SKILL.md`、`skills/crew-coordinator/SKILL.md`、`codex-skills/crew-coordinator/SKILL.md`、`README.md`、`tests/test_codex_offload.py`
- 公共：测试资源

## 未决问题

- delegate 1.2 的进度说明格式、`status=timeout` 结果行的确切写法以 1.2 发版为准；与假设 7 不一致时，按发版的写法补一次修订（只改 `settle` 的 timeout 分支）。
- 方案「落地时要补测」的三项（大模块的时长与超时、要开浏览器的检查、和基线冲突）：本模块按「一次一个 Task」避开大模块超时；浏览器检查与基线冲突留给 LIVE-SAAS 试点（livesaas-lead）。

## 文档建议

README「命令一览」补 `config set --codex-offload` 与 `offload` 子命令；「一次完整流程」在开工后补一段「打开额度外包后：派出、收结果、三种结束状态、交还模块会话」。CHANGELOG 随发版写。
