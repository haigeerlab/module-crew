# Implementation Plan: crew-light-task

<!-- spec-guard: review approved -->

> 依据：`spec/crew-light-task.md`（用户 2026-10-22 批准，合并顺序 bug → 模块 → 需求）。任务清单：`tasks/crew-light-task/todo.md`。

## Overview

先把契约钉到 v2.5（其余改动都要用「任务」字段），再按「登记角色与钩子 → 派出 → 交回 → 合并 → 升格 → 端到端 → 文档」的顺序做。
每个任务先写失败的测试、看到红再实现到绿，单独在 `main` 本地提交，不推送、不发版。本机已是 0.10.0，本模块的改动在下次发版前不影响本机与短验证。

## Architecture Decisions

- **契约 v2.5**：从 session-protocol 仓 `566f0de` 复制 `fixtures/` 到 `tests/fixtures/session-protocol/v2.5/`（带 `SOURCE` 与 `SHA256SUMS`），一致性测试 `PINNED` 加 v2.5、`FIXTURES` 指向 v2.5，
  v2.2～v2.4 照旧跑。`protocol.py`：四种消息认选填「任务」（`T<号>`），按 v2.5 位置规则解析与生成；问题代码先 `bad-task-ref` 再 `module-task-both`；`contract()` 缺「模块」时给 `module: None`。
  `sources.PROTOCOLS` 加 `2.5`，`hub_protocol` 默认仍按 2.4。
- **角色 `task`**：`store.ROLES` 加 `task`；`_validate_session` 对 `task` 角色要求 `task`（正整数）与绝对路径 `worktree`，同一任务只能有一个在用登记。
  `start` 的名额只数 `dev`（`_active_devs` 已按 role 过滤，补测试锁住）。`hooks.detect` 在登记的任务 worktree 里返回 `Role("task", name, None, db)` 并带任务号，
  `session_start`／`prompt_line` 注入「你是 T<n> 的轻任务会话」与阶段（取任务状态）；`stranger_line` 对任务 worktree 给 bind 提示。`_home_of` 认 `task` 角色。
- **派出**：`tasks.dispatch(db, project, n, host)`：校验 `ready` 与配置已定（`crewDir`、`integrationBranch`、简称），`git worktree add -b task/t<n> <crewDir>/task-t<n> <集成分支>`，
  登记 `<简称>-t<n>`，开工说明写进 `bodies/`，`permissions.follow`，任务 `advance` 到 `dispatched`。`bind` 成功且登记是 `task` 角色时，`advance` 到 `working`。
- **交回**：`review.add` 解析到「任务」时走任务分支：核对发件人是 `assignee`、任务 `working`；`git diff --name-only <集成分支>...task/t<n>`；多出文件与 `tasks.overlaps(..., exclude=n)` 的结果写进交审事项
  `extraFiles`／`overlapExtra`；bug 缺「复现测试」字样加提示行；任务 `advance` 到 `returned` 并记 `result.files`。不检查 spec-guard 的必备文件（任务没有 Spec）。
  `review batch`／`for-hub` 对任务事项写「任务」；hub 协议 < 2.5 时 `for-hub` 跳过任务事项，并在输出里写「在本会话直接问用户」。
- **合并**：合并批准事项带 `task` 或 `module`；`merge.queue` 排序键 `(0, 号)`＝bug 任务、`(1, Build order 位置)`＝模块、`(2, 号)`＝需求任务。
  `merge.run` 对任务：分支 `task/t<n>`、不调 `_tick`、合入后 `tasks.advance(merged)`；退回通知按 v2.5 在最后一行写「任务」；`no_sync` 同时排除在合并或已合并的任务会话。
  `merge cleanup` 接受 `T<n>`。
- **升格**：`inbox.add` 收到带「任务」的【等待用户】时记账并 `advance(escalated)`；`answer` 对这类事项按选项 A／B／C 处理（A：`promoted` + 提示 add-module；B：提示 `task scope`；C：`cancelled` + 提示 cleanup）。
  `tasks.scope(db, n, expect, done, original)`：只对 `escalated`，改任务单后 `advance(working)`，生成发给做事的会话的缩小通知正文。

## 影响面

修改：`module_crew/protocol.py`、`store.py`、`start.py`、`hooks.py`、`tasks.py`、`review.py`、`merge.py`、`inbox.py`（及 `answer` 所在处）、`sources.py`、`__main__.py`、
`skills/crew-dev/SKILL.md`、`skills/crew-coordinator/SKILL.md`、`README.md`、`CHANGELOG.md`；新增 `tests/test_light_task.py`、`tests/fixtures/session-protocol/v2.5/`；
修改一致性测试与少量断言合并队列顺序、角色集合的旧测试。不新增依赖，不改 `interface.json` 与版本号（随第六版发）。

## Task List

- [ ] Task 1：契约钉到 v2.5（样例、一致性测试、解析与生成「任务」、两个问题代码、`module: null`、协议 2.5 登记）（Spec 验收 1）
- [ ] Task 2：`task` 登记角色与校验、名额只数模块、钩子认任务 worktree（Spec 验收 3 的钩子部分）
- [ ] Task 3：`task dispatch` 与开工说明；`bind` 后 `working`（Spec 验收 2、3）

### Checkpoint 1（report）：契约与派出就位，相关测试通过，记入 todo 后继续

- [ ] Task 4：交回记账、实际改动比对、越界重叠、提请批准与 hub 低于 2.5 的分流（Spec 验收 4、7）
- [ ] Task 5：合并队列顺序、任务合并与退回、不调 gateTick、同步通知、`merge cleanup T<n>`（Spec 验收 5、8）
- [ ] Task 6：升格请求记账、答复 A／B／C、`task scope`（Spec 验收 6）

### Checkpoint 2（report）：整条轻流程的单元测试通过，记入 todo 后继续

- [ ] Task 7：端到端测试——临时仓库里记任务 → 派出 → 任务 worktree 提交 → 交回 → 批准 → 合并 → 在用模块收到同步通知（Spec 验收 9）
- [ ] Task 8：`crew-dev`「轻任务」一节、`crew-coordinator`「派出、交回、回滚」、README「轻任务」与 CHANGELOG、全量测试与旧称扫描（Spec 验收 9）

### Checkpoint 3（gate）：最终验收

- [ ] 回告：完成情况发给总协调（local_d7434023）；契约 v2.5 已钉住的结果告诉契约负责人（local_a9d06942）

## Risks

| 风险 | 影响 | 缓解 |
|---|---|---|
| 契约解析器改动牵连所有消息 | 旧消息被误判 | v2.2～v2.4 样例照旧全跑；新字段只在出现时生效 |
| 合并队列加入任务后排序变化 | 模块合并顺序被打乱 | 模块之间仍按 Build order；单测锁住三段顺序 |
| 任务角色进钩子分流 | 模块或协调被误判为任务 | `detect` 先按 worktree 路径精确匹配；回归 test_hooks、test_routing、test_coordinator_switch |
| 改动面大、上下文长 | 漏改 | 每个任务单独提交，检查点各跑一次相关测试，最后全量 |

## 0.17.0 返工说明（2026-10-27）

为什么返工：LIVE-SAAS 现场问题与 0.16.1 期间暴露的流程卡点，用户在 mc-coord 确认 0.17.0 做这几件（见 todo「0.17.0 修订」一节）。超出原范围，Plan 改回 pending，由模块会话按修订后的 Spec 补写本节的任务分解后交审。

依据：`spec/crew-light-task.md`「0.17.0 修订（第 2 轮）」（用户 2026-10-27 批准，C281；原话「C281 A，README 与 crew-coordinator skill 两边照常各改各的段落」）。

### 架构决定

- **重叠规则**（决策 11）：`tasks.clash` 改成「文件对文件相同才算；目录对目录相同或包含才算；文件对目录不算」；新增 `tasks.covers(entry, path)`。
  `review._add_task` 算多改文件改用 `covers`（口径不变）。`overlaps`／`next_ready`／`add`／`summary` 不改代码，经 `clash` 生效。
- **收窄**（决策 12）：`tasks.scope` 按状态分两路——「升格待定」照旧（`scoped`，回到在做）；「已派出」「在做」走收窄：新列表每条都要被原列表某条 `covers`、且集合不同，
  否则 `TaskRefused`；写 `expectedFiles`、`done`，状态不变，事件 `narrowed` 带原话，生成「已收窄」正文。命令行参数与 `__main__.py` 不变。
- **重新交审**（决策 13）：`review._add_task` 的状态门改为「在做」或「交回」；「交回」时分支顶端等于 `result.commit` 拒收，`mergelock.locked` 且 `read()['unit'] == T<n>` 拒收；
  其余共用现有记账与 superseded 逻辑，最后「交回」不走 `advance`，在同一事务里只更新 `result`（事件 `resubmitted`），输出加「需要重新提请用户批准」。
- **文档**（决策 14）：两份 crew-coordinator、两份 crew-dev 只改轻任务段；README 只改「轻任务」一节与命令一览 `task scope` 一行。

### 任务

- [ ] Task R1：重叠规则与 `covers`（Spec 验收 10 的规则部分、11）——测试先红后绿
- [ ] Task R2：在做任务收窄，含 T264／T267 场景（Spec 验收 10 的场景部分、12）——测试先红后绿
- Checkpoint R1（report）：`test_light_task` 与 `test_task_ledger` 等相关测试全过，记入 todo 后继续
- [ ] Task R3：交回后重新交审（Spec 验收 13）——测试先红后绿，含新交审批准后 `merge run` 合入
- [ ] Task R4：skill 与 README 的轻任务段；全量测试（后台跑，约 1800～3000 秒）与旧称扫描（Spec 验收 14）
- Checkpoint R2（gate）：最终验收

### 影响面

修改：`module_crew/tasks.py`、`spec/crew-task-ledger.md`（仅 Q1 选 A 时）、`module_crew/review.py`、`tests/test_light_task.py`、`tests/test_task_ledger.py`（`test_directory_contains`、`test_next_bug_first_and_one_of_two`、`test_status_sections` 三处按旧规则断言目录包含文件算重叠，按新规则改）、`skills/crew-coordinator/SKILL.md`、`codex-skills/crew-coordinator/SKILL.md`、
`skills/crew-dev/SKILL.md`、`codex-skills/crew-dev/SKILL.md`、`README.md`。不新增依赖，不改 `__main__.py`、`merge.py`、`changes.py`、`store.py`、版本号与 CHANGELOG（随发版）。

### 未决问题

- Q1：`spec/crew-task-ledger.md` 决策 4 写的是「一条是另一条所在的目录（`src/` 与 `src/a.ts`）算重叠」，本轮 Spec（C281）改了这条规则。
  A（推荐）：Task R1 里一并把它的决策 4 与验收那条改成新规则，在它的「变更记录」追加一行（来源 C281），改动差异随最终验收附上，用户批准最终验收即同时批准修订后的 crew-task-ledger Spec，再用 `review-mark` 重新记 approved；
  B：不动它，只在本模块 Spec 写明取代——两份 Spec 会长期说法不一。

### 风险

| 风险 | 影响 | 缓解 |
|---|---|---|
| 和已批准的 `spec/crew-task-ledger.md` 决策 4（「目录包含文件算重叠」）及验收「目录包含」矛盾 | 两份 Spec 说法不一 | 未决问题 Q1：推荐改 crew-task-ledger 决策 4 与那条验收并追加变更记录，差异随最终验收附上、一并批准后用 review-mark 重新记 approved |
| 放宽目录规则后漏判重叠 | 两个任务改到同一文件 | 交回时按实际文件比对仍标越界重叠（验收 11）；skill 提示预计文件尽量写到具体文件 |
| 旧测试按旧规则断言目录重叠 | 全量测试红 | R1 先跑 `grep clash\|overlaps tests/` 找出旧断言，按新规则改并在交审里列出 |
| 重新交审把正在合并的批准作废 | 合并中途状态错乱 | 合并锁被该任务占着时拒收（验收 13） |
| 与 crew-shared-changes 同改 README、crew-coordinator skill | 合并冲突 | 只改轻任务段；后合入的一方 `module-crew sync` 解冲突（用户 C281 同意） |

## 变更记录

- 2026-10-27：追加「0.17.0 返工说明」，评审标记 approved 改回 pending；原因：0.17.0 修订超出原范围；来源：用户在 mc-coord 原话「0.17.0 需求就是这四件，前提假设 A1～A5 全按推荐」
- 2026-10-27：「0.17.0 返工说明」补任务分解（Task R1～R4、两个检查点、影响面、风险），todo 同步细化并勾 REV-SPEC；原因：Spec 修订已获批；来源：用户在 mc-coord 原话「C281 A，README 与 crew-coordinator skill 两边照常各改各的段落」
