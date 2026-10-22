# Spec: crew-light-task

<!-- spec-guard: review approved 38969d4a5fb8 -->

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
- **绝不**：自动开会话；自动升格；任务合并后自动推送。

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
