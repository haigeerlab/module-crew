# Spec: crew-task-ledger

<!-- spec-guard: review approved 8f7a86542d4a -->

> 能力图模块 `crew-task-ledger`（第六版第 2 个）。需求来源：`docs/requirements-record.md` 第 14 节第 3、6、8 条与「这一版不做」（用户 2026-10-22 确认）。
> 依赖 `crew-store`、`crew-coordinator-switch`（有在用的模块协调才能记任务）。标「新」的是写 Spec 时补的实现取舍，请重点审。

## 目标

让模块协调把派出去的每一件轻任务（单个需求或 bug）记进状态库，不靠对话记忆：任务单写了什么、派给谁、在哪个 worktree 和分支、
做到哪一步、结果如何、由哪个任务带进来。压缩、清空或换会话后，`status` 能重建这份清单；新任务的预计文件和在做的活重叠时排队，bug 排前。

本模块只管**记账与排队**；开 worktree、开会话、交回、合并、升格由下一个模块 crew-light-task 做，它按本模块的状态转换写记录。

## 范围

**范围内**

- 状态库新记录种类 `task`，编号与 C、W 共用一个计数器，对人显示 `T<号>`（契约 v2.5 的 T 前缀）。
- 命令：`task add`（写任务单、判断能不能开）、`task list`、`task show`、`task cancel`、`task next`（排队里现在能开的）。
- 重叠判断：新任务的预计文件 vs 在做的任务的预计文件、在用模块分支已改的文件。
- 排队顺序：bug 在前，同类按编号。
- `status` 显示任务段；`takeover` 后任务照旧（记录按邮箱名挂，不随会话编号变）。
- `refs.parse` 认 `T15`。

**范围外**

- 开 worktree、开会话、交回、进合并队列、升格、回滚（crew-light-task）。
- 并发上限：轻任务不设总数上限（需求记录第 14 节第 8 条）。
- 读 spec-guard 的任何东西（轻流程不调 spec-guard）。

## 假设（来自需求记录第 14 节）

1. 只有模块协调记任务；没有在用的模块协调时 `task add` 拒绝。
2. 任务单三项必填：做什么、预计改哪些文件、做到什么程度算完；类型 `feature` 或 `bug`。
3. 预计文件重叠就排队，不重叠可以同时开；宁可保守。
4. bug 排在需求前面；不打断正在做的。
5. 「由哪个任务带进来」记在 bug 任务上（`T<号>` 或模块合并的 `C<号>`），供以后看哪类活容易出问题。
6. 记任务要用户原话（用户在模块协调里说了这件事）；别的会话报来的 bug，由模块协调整理后仍要用户明说「做」才记。

## 关键决策与取舍（请重点审）

1. **（新）编号共用计数器**：`task` 用 `tx.allocate_number()`，与 C、W 不会撞号；存整数，对外一律 `T<号>`。`refs.parse` 接受 `T15`、`C15`、`W15`、`15`，
   但 `task` 命令只认指向 `task` 记录的号。
2. **任务记录**（键为号）：
   `{"type": "feature"|"bug", "title", "what", "expectedFiles": [..], "done", "state", "causedBy": "T<n>"|"C<n>"|null,
   "assignee": null|"<邮箱名>", "worktree": null|"<绝对路径>", "branch": null|"<分支>", "result": null|{..}, "original", "createdAt"}`。
   `expectedFiles` 每项是仓库内的相对路径；以 `/` 结尾表示整个目录。不允许绝对路径、`..`、空列表。
3. **状态**：`queued`（排队）→ `ready`（可以开）→ `dispatched`（已派出）→ `working`（在做）→ `returned`（交回）→ `merged`（已合入）；
   另有 `escalated`（升格请求待用户决定）、`promoted`（已升格为模块）、`cancelled`（取消）。本模块只实现 `queued`／`ready`／`cancelled`
   与 `task next` 把 `queued` 提为 `ready`；其余转换的函数先写好、加校验（只许合法转换），由 crew-light-task 调用。
   `dispatched`／`working`／`returned`／`escalated` 统称**在做**，参与重叠判断。
4. **（新）重叠怎么判断**：两组路径有重叠 = 有两个点名的文件完全相同，或有两个目录相同、或一个在另一个里面（`src/` 与 `src/ui/`）；目录不和点名的文件判重叠（`src/` 与 `src/a.ts` 不算，目录表示还没点名的文件，0.17.0 起）。拿新任务的 `expectedFiles` 去比：
   - 在做的任务的 `expectedFiles`，以及它交回时报的实际改动文件（有的话）；
   - 每个在用模块分支相对集成分支已经改过的文件（`git diff --name-only <集成分支>...<模块分支>`）。
   模块还没改到的文件判断不了，这一点写进 `task add` 的输出（「模块 X 还在开发，以后可能碰到同样的文件」）。不读 spec-guard 的模块边界。
5. **排队与可开**：`task add` 时不重叠 → `ready`，重叠 → `queued` 并写明和谁、哪些文件重叠。`task next` 按「bug 在前、同类按号」列出排队里
   现在已不重叠的，并把它们提为 `ready`；两条排队任务彼此重叠时只提前面那条。轻任务不设数量上限。
6. **取消**：`task cancel T<n> --original-file`，只对还没合入的任务；记 `cancelled` 与原话；已派出的任务，提示模块协调告诉做事的会话停下（发消息归 crew-light-task）。
7. **status**：新增「任务」段：在做的（编号、类型、标题、状态、派给谁）、排队的（编号、和谁重叠）、最近 5 条已合入或取消的；`--json` 有 `tasks` 字段。
   `status` 只读，不调整排队。
8. **接管**：任务的 `assignee` 是邮箱名，`takeover`／`bind`／清空交接只换会话编号，不动任务；模块协调换了会话，任务清单原样在状态库里。

## 接口约定

```bash
module-crew task add --type feature|bug --title <标题> --what <做什么> --expect <路径>[,<路径>…] --done <完成标准> \
                     [--caused-by T<n>|C<n>] --original-file <原话文件> [--json]
module-crew task list [--all] [--json]
module-crew task show T<n> [--json]
module-crew task next [--json]
module-crew task cancel T<n> --original-file <原话文件>
```

退出码：`0` 成功；`3` 被拒（没有模块协调、字段不合规、号不对、状态不允许）；`2` 参数错。

Python：`tasks.add(db, project, ...) -> (number, state, overlaps)`、`tasks.overlaps(db, project, files, exclude=None)`、
`tasks.advance(db, number, new_state, **fields)`（校验合法转换）、`tasks.next_ready(db, project)`。

事件：`task.added`、`task.queued`、`task.ready`、`task.cancelled`，以及 crew-light-task 将用的 `task.dispatched` 等。

## 项目结构

```text
module_crew/tasks.py            新
module_crew/refs.py             认 T 前缀，加 task(n) 显示
module_crew/store.py            KINDS 加 task；记录校验
module_crew/probe.py            status 任务段
module_crew/__main__.py         task 子命令、status 显示
skills/crew-coordinator/SKILL.md  记任务与看排队的规矩
tests/test_task_ledger.py
```

## 命令

```bash
python3 -m unittest discover -s tests
PYTHONPATH=tests python3 -m unittest test_task_ledger
```

## 代码风格

沿用现有模块：代码与注释英文，输出中文；只用标准库；外部命令只有 `git`，带超时、不经 shell。

## 测试策略

- 记录：必填项、非法路径（绝对、`..`、空）、类型、原话；没有模块协调拒绝；编号与 C、W 共用计数器；`T` 前缀显示与解析。
- 重叠：相同文件、相同或嵌套的目录、目录与其中点名的文件不算、无重叠；在做任务与模块分支已改文件两种来源；已合入、取消的任务不参与。
- 排队：bug 在前；`task next` 提升已不重叠的、两条排队互相重叠只提前一条；`status` 只读不改排队。
- 状态转换：合法转换通过，非法转换拒绝。
- 接管：`takeover` 后任务不变。
- 回归：全量测试通过。

## 边界

- **始终**：记、取消任务要用户原话；`status` 只读。
- **先问**：给任务设数量上限；用 spec-guard 的模块边界判断重叠。
- **绝不**：自动开会话或 worktree（归 crew-light-task）；自动取消或升格任务。

## 验收标准

1. 有模块协调时 `task add` 记下任务，编号显示为 `T<号>`，与 C、W 不撞号；没有模块协调时拒绝；缺必填项、路径非法、没给原话各拒绝。
2. 预计文件和在做的任务或在用模块分支已改文件重叠时记为 `queued`，输出写明和谁、哪些文件；不重叠记为 `ready`，并提示模块还没改到的文件判断不了。
3. 已合入、取消的任务不参与重叠判断。
4. `task next` 按 bug 在前、同类按号，把已不重叠的排队任务提为 `ready`；两条排队任务互相重叠时只提前一条。
5. `task cancel` 只对没合入的任务生效，记原话；对已合入的拒绝。
6. 非法状态转换（例如 `queued` 直接到 `merged`）被拒。
7. `status` 显示任务段（在做、排队、最近完成），`--json` 有 `tasks`；运行 `status` 不改任何任务。
8. `takeover` 与清空交接后任务记录不变。
9. bug 可记 `causedBy`（`T<号>` 或 `C<号>`），格式不对拒绝。
10. 全量测试通过。

## 未决问题

- 模块还没改到的文件判断不了：要更早发现冲突，需要模块声明预计改动的范围；这一版只提示，不做。

## 文档建议

README「命令一览」加 `task` 一行；「一次完整流程」后加一小节「轻任务」，crew-light-task 做完后再补全流程。

## 变更记录

- 2026-10-27：决策 4 与测试策略「重叠」一条改为目录只和目录比（相同或嵌套才算），不再和点名的文件判重叠；原因：轻任务只因都写 `tests/` 就无法并行（T264／T267）；来源：用户批准 crew-light-task 0.17.0 修订 Spec（C281）与 Plan 的 Q1 A（C287）
