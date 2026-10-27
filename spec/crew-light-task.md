# Spec: crew-light-task

<!-- spec-guard: review pending -->

> 能力图模块 `crew-light-task`（第六版第 3 个）。需求来源：`docs/requirements-record.md` 第 14 节第 3、4、6、8、9、11 条与契约 v2.5 两段（用户 2026-10-22 确认、批准）。
> 依赖 `crew-task-ledger`（任务记录与排队）、`crew-start`（worktree 与开工说明）、`crew-merge`（合并队列）。标「新」的是写 Spec 时补的实现取舍，请重点审。

## 目标

让一件「可开」的轻任务（单个需求或 bug）走完整条轻流程：模块协调派出去 → 做事的会话在自己的 worktree 里做 → 测试全过后交回 →
进同一个合并队列、用户点一次批准 → 合入集成分支并通知在开发的模块同步。做大了就停下交回升格请求，由用户选升格、缩小或取消。
不写 Spec，不调 spec-guard。

## 范围

**范围内**

- 契约钉到 session-protocol v2.5（566f0de）：解析与生成「任务」字段、T 前缀、`bad-task-ref`／`module-task-both`；顺带修 `module` 键缺失（契约负责人发现）。
- `task dispatch T<n>`：建 worktree 与分支、登记做事的会话、生成开工说明（任务单 + 规矩）、跟随权限预配。
- 做事的会话的规矩：`crew-dev` skill 加「轻任务」一节；钩子认得任务 worktree。
- 交回：轻任务的最终验收【交审】（`模块：无`，`任务：T<n>`）经 `review add` 记账，自动比对实际改动与任务单。
- 合并：`merge approve`／`merge run`／`merge cleanup` 支持任务；排队顺序 bug 优先；不调 gateTick；合入后照常通知各模块同步。
- 升格请求：【等待用户】「卡住选做法」带「任务」，用户答 A 升格／B 缩小／C 取消后改任务状态。
- 回滚按轻任务走（只在 skill 里写做法，不加专门命令）。

**范围外**

- 发现不经队列的提交（crew-unqueued-commits）、合并检查改后台（crew-background-checks）。
- 派给 Codex；自动开会话（开会话仍由模块协调用桌面版工具做）。
- 升格后的模块流程本身（走 spec-guard add-module 与现有模块流程）。

## 假设（来自需求记录第 14 节与契约 v2.5）

1. 做事的会话测试全过才交回；交回附测试命令与结果、实际改的文件、和任务单是否一致（写进【交审】的「要点」「改动统计」「越界检查」）。
2. bug 任务必须先补能复现的测试再修；需求任务不强制。
3. 合并仍走同一个队列，用户点一次批准；bug 先合，不打断正在合的那一件。
4. 做大了或要碰别人的文件：停下交回升格请求，代码留在任务分支；用户选升格（占一个模块名额）、缩小或取消。只多改了没人在碰的文件，交回时报一句即可。
5. 被别的会话消息叫醒的一轮开不了会话，只出卡片等用户点；插件不绕过。
6. 契约 v2.5 写法：【交审】`模块：无` 且「任务」紧跟「要点」；【等待用户】「任务」在「模块」前（轻任务不写「模块」）；【审查结论】写「任务」时必须有「要点」、「任务」紧跟其后；【协调通知】「任务」写在最后一行。
7. 决策收件箱升到 v2.5 之前，带 T 编号的卡可能被误读：hub 登记的协议低于 2.5 时，任务的提请批准与升格请求不经决策收件箱，由模块协调在本会话直接问用户。

## 关键决策与取舍（请重点审）

1. **（新）做事的会话是新的登记角色 `task`**：`store.ROLES` 加 `task`，登记带 `task`（号）与 `worktree`；不占多模块名额（`start.plan` 只数 `dev`）。
   邮箱名 `<简称>-t<号>`，worktree `<crewDir>/task-t<号>`，分支 `task/t<号>`，都从集成分支切出。
2. **派出**：`module-crew task dispatch T<n> [--host claude]`，只对 `ready` 的任务：建 worktree、登记、生成开工说明正文、`permissions.follow`，任务改为 `dispatched`（带 `assignee`、`worktree`、`branch`）。
   开会话由模块协调按输出做：用户本人发话的一轮直接开（`start_session`，第一条消息用开工说明全文）；被会话消息叫醒的一轮出卡片。做事的会话第一次 `bind` 后，任务记为 `working`。
3. **开工说明**内容：任务单原文（做什么、预计文件、完成标准、由谁带进来）、工作目录与分支、模块协调邮箱名、`bind` 一步、完整检查命令（取 `checkCommand`，没设就写「项目 Spec 的 Commands 一节」）、
   bug 先写复现测试、交回与升格的消息写法（按契约 v2.5 给样例）、「不改公共文件，要改发【公共变更请求】」。
4. **钩子**：`detect` 认得任务 worktree（登记的 `worktree` 路径），注入「你是 T<n> 的轻任务会话，只和模块协调说话」与当前阶段；陌生会话在任务 worktree 里得到与模块 worktree 相同的 bind 提示。
5. **交回记账**：`review add` 收到 `模块：无` 加「任务」的最终验收【交审】：核对发件人是该任务的登记会话、任务在 `working`；
   **（新）自动比对**：`git diff --name-only <集成分支>...task/t<n>` 得实际改动，和 `expectedFiles` 比——多出来的文件列在交审事项里；多出来的又和在做的模块或任务重叠（`tasks.overlaps`）时，标「越界重叠」，交审正文写明并建议走升格。
   bug 任务的「要点」里没有「复现测试」字样时只提示，不拒收。记账后任务改为 `returned`，`result.files` 记实际改动。
6. **提请批准**：轻任务的最终验收和模块一样进 `review batch`／`for-hub`，审批卡写「任务」（一张卡一个任务）；hub 协议低于 2.5 时不生成 for-hub 正文，提示在本会话问用户（假设 7）。
7. **（新）合并队列顺序**：先 bug 任务（按号），再模块（按 Build order），再需求任务（按号）。理由：bug 往往挡着别人，需求任务和模块的先后没有硬依赖，放后面最不打扰。
   合任务分支同样 `--no-ff`、跑完整检查、失败重置并退回（退回类【协调通知】带「任务」）、冲突中止退回；合入后任务改为 `merged`，**不调 gateTick**（任务没有 todo），
   其他在用模块与在做的任务按现有 `no_sync` 规则收同步基线通知。`merge cleanup T<n>` 收回任务 worktree（分支保留），列出待退役的邮箱名。
8. **升格请求**：做事的会话发【等待用户】「类型：卡住选做法」「任务：T<n>」，选项 A 升格／B 缩小／C 取消；`inbox add` 记账并把任务改为 `escalated`。
   用户答复后（`answer`）：A → `promoted`，输出提示模块协调和用户一起用 `/spec-guard:add-module` 加模块，任务分支留作参考；
   B → 模块协调用 `task scope T<n> --expect … --done … --original-file` 改任务单，任务回到 `working`，给做事的会话发缩小后的任务单；C → `cancelled`，收回 worktree。
9. **回滚**：skill 写明——合入后的问题默认另开 bug 任务（`--caused-by T<n>`）往前修；挡住在开发的模块时，用户点头后记一个 bug 任务，`what` 写「撤回 <合并提交> 的合并」，派出去由做事的会话 `git revert -m 1` 后交回，走同一队列。不加专门命令。
10. **契约 v2.5**：`protocol.py` 认「任务」字段与 T 前缀，按 v2.5 的位置规则解析与生成；新问题代码先报 `bad-task-ref` 再报 `module-task-both`；
    钉住的样例目录换成 v2.5（含 6 份新样例）；`contract()` 对没写「模块」的消息给 `module: null`。`sources.PROTOCOLS` 加 `2.5`。

## 接口约定

```bash
module-crew task dispatch T<n> [--json]                     # ready → dispatched；输出 worktree、分支、邮箱名、开工说明正文路径
module-crew task scope T<n> --expect … --done … --original-file <原话文件>   # 缩小（升格请求选 B 后）
module-crew review add <文件> --from <邮箱名> --relay-id <号>  # 认得任务的最终验收【交审】
module-crew merge approve <C号> --original-file …            # 任务同样适用
module-crew merge run                                       # 队列含任务，顺序见决策 7
module-crew merge cleanup T<n> --original-file …
```

状态库：`session` 新角色 `task`（必填 `task`、`worktree`）；`task` 记录的 `result` 加 `files`、`extraFiles`、`overlapExtra`；
合并批准事项加 `task`（号）与 `module` 二选一。

## 项目结构

```text
module_crew/protocol.py         v2.5
module_crew/tasks.py            dispatch、scope、开工说明
module_crew/review.py           任务的交审与比对、提请批准
module_crew/merge.py            任务进队列、合并、退回、收回
module_crew/inbox.py, answer    升格请求与答复
module_crew/hooks.py            任务 worktree 的角色注入
module_crew/store.py, start.py  task 角色；名额只数 dev
module_crew/sources.py          协议 2.5
skills/crew-dev/SKILL.md, skills/crew-coordinator/SKILL.md
tests/fixtures/session-protocol/  换成 v2.5
tests/test_light_task.py
```

## 命令

```bash
python3 -m unittest discover -s tests
PYTHONPATH=tests python3 -m unittest test_light_task
```

## 代码风格

沿用现有模块：代码与注释英文，输出中文；只用标准库；外部命令只有 `git`，带超时、不经 shell。

## 测试策略

- 契约：v2.5 全部样例的一致性测试（含 6 份新样例与两条位置规则）；旧样例照旧通过；`module: null`。
- 派出：只对 `ready`；worktree、分支、登记、开工说明内容；不占模块名额；bind 后 `working`。
- 交回：发件人与状态核对；实际改动比对、多出文件、越界重叠；bug 缺复现测试的提示。
- 合并：顺序（bug → 模块 → 需求）；合入、检查失败重置退回、冲突退回；不调 gateTick；同步通知；收回。
- 升格：三种答复各自的状态与输出；hub 低于 2.5 时不经 hub。
- 端到端：一个真实临时仓库里，记任务 → 派出 → 在任务 worktree 提交 → 交回 → 批准 → 合并 → 模块收到同步通知。
- 回归：全量测试通过。

## 边界

- **始终**：派出、批准、缩小、取消、升格的决定都要用户原话；任务分支不删。
- **先问**：给轻任务设数量上限；合并顺序改动；让任务调 spec-guard。
- **绝不**：自动开会话；自动升格；任务合并后自动推送；在登记的决策收件箱支持契约 v2.5（T 前缀）之前往它发轻任务卡片（顺序：收件箱先支持 T 前缀，module-crew 才发）。

## 验收标准

1. 契约 v2.5 样例全部通过，旧样例不变；没写「模块」的消息 `module` 为 `null`。
2. `task dispatch` 只对 `ready` 生效：建好 worktree、分支 `task/t<n>`、登记 `task` 角色、开工说明含任务单原文、完整检查命令、bug 复现测试要求与 v2.5 写法样例；任务为 `dispatched`；不减少模块空位。
3. 做事的会话 `bind` 后任务为 `working`；钩子在任务 worktree 注入轻任务身份。
4. 任务的最终验收【交审】被 `review add` 记账；发件人不对或任务不在 `working` 拒收；实际改动比对写进事项，越界重叠时标出并建议升格；任务改为 `returned`。
5. 用户批准后任务进合并队列，顺序为 bug 任务、模块、需求任务；合入后任务为 `merged`、不调 gateTick、在用模块收到同步通知；检查失败重置并退回（通知带「任务」）。
6. 升格请求记账后任务为 `escalated`；答 A／B／C 分别到 `promoted`、`working`（任务单已改）、`cancelled`。
7. hub 登记协议低于 2.5 时，任务的提请批准与升格请求不生成 for-hub 正文，并提示在本会话问用户。
8. `merge cleanup T<n>` 收回 worktree、保留分支、列出待退役邮箱名。
9. 端到端测试通过；全量测试通过。

## 未决问题

- 决策收件箱什么时候升到 v2.5：之前任务的批准都在模块协调里直接问用户。
- 合并队列顺序（决策 7）是推荐值，需要用户确认。

## 文档建议

README 加「轻任务」一节（记任务 → 派出 → 交回 → 批准合并 → 升格），命令一览补 `task dispatch`／`task scope`；CHANGELOG 记入第六版。

## 0.17.0 修订（第 2 轮）

> 需求来源：用户在 mc-coord 确认「0.17.0 需求就是这四件，前提假设 A1～A5 全按推荐」（开工批准 C277）；本模块负责其中两件：
> ① 轻任务重叠判断细化与在做任务收窄预计文件；② S33 交回后重新交审。上面各节照旧有效，本节只写增改。

### 要解决的两个卡点

1. **目录把并行卡死**：T264 预计 `module_crew/__main__.py`、`tests/`，T267 预计 `module_crew/changes.py`、`commits.py`、`start.py`、`tasks.py`、`tests/`。
   现在 `tasks.clash` 把以 `/` 结尾的目录当成「目录下所有文件」，两个任务只因为都写了 `tests/` 就判重叠，T267 只能排队；
   T264 想把 `tests/` 收窄成实际要改的 `tests/test_session_handover.py`，`task scope` 又只认「升格待定」，报「不在等升格决定，不能缩小」。
2. **S33 交回后卡死**：任务交回（「交回」）后分支又多了提交（误发同步通知、做事的会话 sync 过），`merge run` 报
   「任务分支 … 在最终验收交审之后又有提交，须重新交审」（merge.py `_run`）；可 `review._add_task` 只收「在做」的任务，新的交审被拒，两边都走不动（T167、T170 当时靠把分支 reset 回交审提交解开）。

### 假设（请确认；按 A1～A5 推荐值写）

- R1（**我对「目录只和对方点名落在其中的文件比」的理解，请重点确认**）：目录条目表示「这个目录下会动一些还没点名的文件」，
  它**不再**和对方点名的文件判重叠；点名的文件之间照旧比；只有两边都写了目录、且是同一目录（或一个在另一个里面）时才判重叠。
  照这个理解，T264 收窄成 `tests/test_session_handover.py` 后，T267 的 `tests/` 和它不重叠，T267 可开。
  另一种读法（目录仍和对方点名在其中的文件判重叠，只是两个目录要完全相同才算）解不开 T264／T267，所以没采用。
- R2：放宽后漏判的风险由交回时的比对兜住：`review add` 用实际改动的文件（都是点名的）和在做的活比，撞上点名文件或同一目录照旧标「越界重叠」。
  和在用模块分支的比较也按同一规则：模块分支已改的文件是点名的，任务只写目录时不再因它判重叠（假设 4 的「只多改了没人在碰的文件」照旧）。
- R3（A4）：不加项目开关；收窄要用户原话（`--original-file`），和其他任务单改动一样。
- R4：「收窄」指新的预计文件每一条都落在原来的某一条里（同一个文件；或在原目录里的文件、子目录），且和原来不完全一样；加文件或换到原范围外不叫收窄，
  拒收并提示走升格（做事的会话停下发升格请求）。「完成标准」可以一起改，也要写（沿用现有 `--done` 必填）。
- R5：能收窄的状态是「已派出」「在做」，状态不变；「升格待定」照旧走缩小（任意新任务单、回到「在做」，不要求是收窄）。「交回」之后不收窄：工作已做完，要改就退回。
- R6：重新交审不需要用户另外同意：它只替换交审记录，旧交审与旧的合并批准作废，新的交审照常提请用户批准；用户批准仍是合并的唯一入口。

### 关键决策（增）

11. **重叠规则**（`module_crew/tasks.py`）：`clash(a, b)` 改为——两个都是文件：相同才算；两个都是目录：相同或一个在另一个里面才算；一个文件一个目录：不算。
    另加 `covers(entry, path)`（`path` 是 `entry` 本身或落在目录 `entry` 里），供「是否在任务单内」的判断用：
    `review._add_task` 算「任务单以外多改了」原来借用 `clash`，改用 `covers`，口径不变（实际文件落在预计目录里就算任务单内）。
    `overlaps`、`next_ready`、`add`、`summary`、`task show` 都经 `clash`，跟着生效，不另改。
12. **在做任务收窄**（`tasks.scope`）：任务在「已派出」「在做」时，新的预计文件必须是收窄（R4），否则拒收「这不是收窄：… 不在原来的预计文件里，加文件请走升格」；
    通过后改 `expectedFiles`、`done`，状态不变，事件动作 `narrowed`（带用户原话），生成发给做事的会话的正文（「预计文件已按用户的决定收窄」+ 新任务单 + 「超出的改动不要做，要碰别的文件先停下发升格请求」）。
    「升格待定」照旧（动作 `scoped`，回到「在做」）。其他状态报「T<号> 现在是「…」，不能缩小或收窄」。收窄后由模块协调跑 `module-crew task next` 把不再重叠的排队任务提为可开（命令已有，不改）。
13. **交回后重新交审**（`module_crew/review.py` 的 `_add_task`）：任务在「交回」时，
    先取任务分支顶端：和 `result.commit`（上次交审时记下的提交）相同就拒收「分支顶端和上次交审的提交相同（<短号>），不用重新交审」；
    合并锁正被这个任务占着（`mergelock.locked` 且 `read().unit` 是 `T<号>`）就拒收「T<号> 正在合并，等合并结束」；
    其余照「在做」时的做法记账：新的交审事项、比对实际改动、附检查账，**旧的未结交审与合并批准记为被取代**（沿用已有的 superseded 逻辑），
    任务仍为「交回」，`result` 换成新提交与新改动（事件动作 `resubmitted`）。输出写明「取代了 C<号>；需要重新提请用户批准」。
    「在做」时的行为不变；其他状态照旧拒收。
14. **skill 与 README**：`skills/crew-coordinator/SKILL.md`、`codex-skills/crew-coordinator/SKILL.md` 的轻任务一节加「在做的任务收窄预计文件」（凭用户原话、`task scope` 后跑 `task next`）
    与「合并报交审之后又有提交时，让做事的会话重新发最终验收【交审】，`review add` 取代旧交审后重新提请批准」；
    `skills/crew-dev/SKILL.md`、`codex-skills/crew-dev/SKILL.md` 的轻任务一节加「交回后分支又多了提交（如同步）：重新发最终验收【交审】」与「预计文件写目录时尽量写到具体文件」；
    README「轻任务」一节补这两点，命令一览里 `task scope` 的说明改为「升格请求选缩小后改任务单／在做的任务收窄预计文件」。

### 改哪些文件、哪些函数

| 文件 | 改什么 |
|---|---|
| `module_crew/tasks.py` | `clash` 改规则；新增 `covers`、收窄判断；`scope` 认「已派出」「在做」的收窄 |
| `module_crew/review.py` | `_add_task`：收「交回」且分支顶端已变的重新交审；多改文件的判断改用 `tasks.covers` |
| `tests/test_light_task.py` | 重叠规则、收窄、重新交审的测试（先红后绿） |
| `skills/crew-coordinator/SKILL.md`、`codex-skills/crew-coordinator/SKILL.md` | 只改轻任务相关的那几行 |
| `skills/crew-dev/SKILL.md`、`codex-skills/crew-dev/SKILL.md` | 只改「轻任务」一节 |
| `README.md` | 只改「轻任务」一节与命令一览 `task scope` 那一行 |

不改 `module_crew/__main__.py`（`task scope` 的参数不变）、`merge.py`（那条报错照旧，处理在重新交审一侧）、`changes.py`、`store.py`。
和同时在做的 crew-shared-changes 的交集只有 `README.md` 与两份 `crew-coordinator/SKILL.md`：本模块只动轻任务那几段，对方动公共变更那几段；
合入集成分支时后到的一方 `module-crew sync` 解冲突。要是模块协调认为这也不行，就把这三个文件的改动挪到对方合入之后再做。

### 范围外（本轮）

- 模块（非轻任务）交审之后又有提交的同类问题：模块走 `review.py` 的另一条路径，本轮不动。
- 自动收窄、自动重新交审；按实际改动自动改预计文件。

### 验收标准（增）

10. 重叠：`tests/` 和 `tests/a.py` 不重叠；`tests/` 和 `tests/` 重叠；`tests/` 和 `tests/fixtures/` 重叠；`a.py` 和 `a.py` 重叠；用 T264／T267 的预计文件做的测试里，
    T264 收窄成 `tests/test_session_handover.py` 后，T267 由「排队」经 `task next` 变为「可开」。
11. 交回比对：实际改了预计目录里的文件不算多改；多改的点名文件撞上别的任务点名的同一文件或同一目录时仍标「越界重叠」。
12. 收窄：「在做」「已派出」的任务凭用户原话收窄成功，状态不变、正文生成、事件 `narrowed` 带原话；加了原范围外的文件、和原来完全一样、或状态是「交回」「已合入」等时拒收；「升格待定」的缩小行为不变（现有测试照过）。
13. 重新交审：任务「交回」后分支多一个提交，新的最终验收【交审】被 `review add` 收下，旧交审与旧合并批准记为被取代、任务仍为「交回」、`result.commit` 是新提交，
    新交审批准后 `merge run` 能合入；分支顶端没变时拒收；合并锁被这个任务占着时拒收。
14. 全量测试通过（含旧称扫描）。

### 文档建议（本轮）

README「轻任务」一节补收窄与重新交审两句（见决策 14）；CHANGELOG 随发版记入 0.17.0。

## 变更记录

- 2026-10-22：「边界·绝不」写明发卡顺序——登记的决策收件箱支持契约 v2.5（T 前缀）之前，不往它发轻任务卡片（决策 6 与验收 7 的做法本来如此，代码不变）。来源：用户经总协调转达的决定「A2 不成立：决策收件箱先支持 T 前缀，module-crew 才往收件箱发轻任务卡片；把这个顺序写进 Spec。」
- 2026-10-27：加「0.17.0 修订（第 2 轮）」一节（重叠规则细化、在做任务收窄预计文件、交回后重新交审，决策 11～14、验收 10～14），评审标记改回 pending；原因：0.17.0 需求超出原范围；来源：用户在 mc-coord 原话「0.17.0 需求就是这四件，前提假设 A1～A5 全按推荐」（开工批准 C277）
