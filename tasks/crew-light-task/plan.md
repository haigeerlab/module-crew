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
