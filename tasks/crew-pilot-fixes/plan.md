# Implementation Plan: crew-pilot-fixes

<!-- spec-guard: review pending -->

> 依据：`spec/crew-pilot-fixes.md`（用户 2026-10-19 批准）。任务清单：`tasks/crew-pilot-fixes/todo.md`。

## Overview

先做独立的新命令 `sync` 并改通知措辞（MC-3、MC-5），再做只读的 `review show` 并在通知里引用（MC-4），然后改撤回批准与重交审作废（MC-6），
再做模块协调自开等待记录的记账与提示（MC-7）、派活后核对弹窗的输出提醒（MC-8），最后改 README、skill、版本号并跑全量测试，交最终验收前做一次宿主实地验证。
每个任务先写失败的测试，再实现到全绿，单独在 `main` 本地提交，不推送。

## Architecture Decisions

- **`sync` 放进新文件 `module_crew/sync.py`**：`run(cwd) -> SyncResult(code, lines)`；用 `store.open_store(cwd)` 找到状态库与运行配置，
  按 `session` 记录的 `worktree` 认出当前 checkout 属于哪个在用模块会话；子进程跑 `git merge --no-edit <integrationBranch>`，
  冲突文件取 `git diff --name-only --diff-filter=U`，本模块路径（`spec/<id>.md`、`tasks/<id>/`）用 `git checkout --theirs -- <路径>` + `git add`（在子进程里跑，不经宿主规则）。
- **`review show`**：`review.show(db, number, submission=False) -> list[str]`，只读 `item` 记录的 `reviews[].text` 与 `text`；sha256 按 UTF-8 字节算，与 `_original_line` 同法。
- **重交审作废合并批准**：在 `review.add` 关旧交审（`superseded`）的同一事务里，`node == "final"` 时关掉该模块开着的 `merge-approval`（`closedReason: "superseded"`，`supersededBy: <新交审号>`）。
- **撤回不重开**：`merge.revoke` 在同一事务里看有没有同模块、同节点、编号更大的 `review` 记录；有就不改交审。
- **等待记录**：沿用现有 `ticket` 种类，新记录 `from: "coordinator"`、`to`、`about`（`#N` 或 `C<N>`）、`relayId`、`text`；
  转达答复时（`inbox.answer`、`review.answer`／`approve`、带 `--source-item` 的批准）按 `about` 匹配，生成【已恢复】正文（`protocol` 现有渲染）并关记录，放进 `sends`（`kind: "resumed"`）。
- **弹窗提醒**：`__main__.py` 里打印 `sends` 的地方统一加一行；收件人是模块会话（`session` 记录 `role == "dev"`）时才加。

## 影响面

新增：`module_crew/sync.py`、`tests/test_sync.py`、`tests/test_pilot_fixes.py`（review show、revoke、作废、wait、提醒）。
修改：`module_crew/__main__.py`（`sync`、`review show`、`wait add` 子命令、发送提醒、sessions/status 显示自开等待记录）、`module_crew/review.py`、`module_crew/merge.py`、
`module_crew/changes.py`、`module_crew/failure.py`、`module_crew/inbox.py`、`module_crew/stall.py` 或 `failure.py`（显示）、
`skills/crew-dev/SKILL.md`、`codex-skills/crew-dev/SKILL.md`、`skills/crew-coordinator/SKILL.md`、`README.md`、`tests/test_skills.py`、三处版本号。
不新增依赖，不改契约夹具，不改状态库格式（只在现有种类里加字段）。不涉及界面。

## Task List

### Phase 1：合入不弹窗（MC-3、MC-5）

- [ ] Task 1：`module-crew sync`——只在在用模块 worktree 跑；工作区不干净拒绝；无冲突合入／已是最新；本模块文件冲突自动取集成分支版本并完成合并；其他冲突列出、不中止、退出码 2；退出码 0／2／3
  - 验收：Spec 验收 1～4
  - 验证：`tests/test_sync.py` 在临时仓库造集成分支与模块 worktree，五种情况各一例
  - 文件：`module_crew/sync.py`、`module_crew/__main__.py`、`tests/test_sync.py`
- [ ] Task 2：开工、同步基线、恢复类通知改写「跑 `module-crew sync`（单独执行，不和别的命令连写）」；两份 crew-dev skill 同步改写并加「Plan 里的合入步骤写 `module-crew sync`、冲突用编辑工具解决」
  - 验收：Spec 验收 5
  - 验证：现有通知测试改断言新措辞、断言不含「git merge」，正文过 `protocol check`；`tests/test_skills.py` 断言两份 skill 的新说法
  - 文件：`module_crew/review.py`、`module_crew/merge.py`、`module_crew/changes.py`、`module_crew/failure.py`、两份 crew-dev skill、相关测试

### Checkpoint 1（report）：sync 与新措辞在临时仓库跑通，全量测试通过，记入 todo 后继续

### Phase 2：审查原文与批准账面（MC-4、MC-6）

- [ ] Task 3：`module-crew review show C<N> [--submission]`；返工通知与开工通知加「审查原文：module-crew review show C<N>」
  - 验收：Spec 验收 6、7
  - 验证：多轮审查、无结论、`--submission`、编号不对四例；sha256 与原文一致；通知过 `protocol check`
  - 文件：`module_crew/review.py`、`module_crew/__main__.py`、`tests/test_pilot_fixes.py`
- [ ] Task 4：`merge revoke` 不重开已被取代的交审；最终验收重交审时作废开着的合并批准，`merge run` 不再取它
  - 验收：Spec 验收 8、9
  - 验证：复现 X-4 序列（交审 A → 合并批准 P → 重交审 B → revoke P）；无重交审时撤回照旧重开；作废后 `merge queue` 不含 P
  - 文件：`module_crew/merge.py`、`module_crew/review.py`、`tests/test_pilot_fixes.py`

### Phase 3：等待记录与弹窗提醒（MC-7、MC-8）

- [ ] Task 5：`module-crew wait add --file --to --relay-id --about`；转达所等事项的答复时输出并生成【已恢复】（「结束：#<relayId>」）、关记录；`sessions`／`status` 显示模块协调未关的等待记录；crew-coordinator skill 写「发【等待其他会话】后立刻 wait add」
  - 验收：Spec 验收 10
  - 验证：记账、重复邮箱号、`inbox.answer` 与带 `--source-item` 的批准两条路径各触发一次、正文过 `protocol check`
  - 文件：`module_crew/inbox.py`、`module_crew/review.py`、`module_crew/__main__.py`、`skills/crew-coordinator/SKILL.md`、`tests/test_pilot_fixes.py`、`tests/test_skills.py`
- [ ] Task 6：发给模块会话的通知与答复，命令输出末尾加「发完核对 <会话名> 是否停在权限弹窗…」；crew-coordinator skill 写派活后用 agent-relay 会话列表核对、卡住报「去会话操作」
  - 验收：Spec 验收 11
  - 验证：开工、同步、返工、撤销批准、用户答复五类输出各断言一次；发给非模块会话（收件箱）时不出现
  - 文件：`module_crew/__main__.py`、`skills/crew-coordinator/SKILL.md`、`tests/test_pilot_fixes.py`、`tests/test_skills.py`

### Phase 4：文档、版本与实地验证

- [ ] Task 7：README 命令表加 `sync`、`review show`、`wait add`，开工流程改写；版本 0.6.0（`.claude-plugin/plugin.json`、`.codex-plugin/plugin.json`、`interface.json`）；全量测试与旧称扫描
  - 验收：Spec 验收 12
  - 文件：`README.md`、三处版本号

### Checkpoint 2（gate）：实地验证前停下问你

  - 要做的事：在 scratchpad 里复制一个 crew-rehearsal 的临时副本（不碰演练用的原仓库和它的 worktree），用 0.6.0 跑 `start prepare` 和 `permissions apply`，
    再开一个默认权限模式的模块会话，让它跑 `module-crew sync`（含一次本模块文件冲突），看会不会弹窗。
  - 为什么停：要新开一个会话，还要往临时副本里写权限文件。

- [ ] Task 8：实地验证（Spec 验收 13），结果写进 todo；做不了就记「宿主未验证」并写明原因

### Checkpoint 3（gate）：最终验收

## 风险

- `git checkout --theirs` 在「对方删除」这类冲突上会失败：sync 遇到就把这个文件归入「其他冲突」，交给模块解决。
- 等待记录的 `about` 只认 `#N`、`C<N>` 两种写法，模块协调写别的会被拒收，并提示正确写法。
