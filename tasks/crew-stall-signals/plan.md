# Implementation Plan: crew-stall-signals

<!-- spec-guard: review approved -->

> 依据：`spec/crew-stall-signals.md`（用户 2026-10-19 批准，指纹 02a28c5161a1）。任务清单：`tasks/crew-stall-signals/todo.md`。

## Overview

给 `sessions --json` 每行加五个只读事实字段（`startedAt`、`commits`、`asks`、`returns`、`waitUser`），再把其中两项写进人看的 `sessions` 与 `status`。
先做提交事实（要碰 git），再做从状态库数出来的三项，最后做人看的输出与文档。每个任务先写失败的测试，再实现到全绿，单独在 `main` 本地提交。

## Architecture Decisions

- **新文件 `module_crew/stall.py`**：放 `commit_facts(worktree, integration_branch)`、`started_at(events, name)`、`asks(items, module)`、`returns(items, module)`、`wait_user(items, name)` 五个纯读函数；
  `failure.sessions()` 调它们拼字段。不放进 `commits.py`——那里管的是 module-crew 自己做提交的说明与钩子输出，职责不同。
- **git 调用**：`git -C <worktree> rev-list --count <集成分支>..HEAD` 与 `git -C <worktree> log -1 --format=%H%x00%cI <集成分支>..HEAD`；用现有子进程写法（`subprocess.run`，`capture_output`，不抛异常），
  返回码非 0 或 worktree 不是目录时给 `error`（取 stderr 第一行，没有就写「worktree 不存在」）。集成分支名取运行配置 `integrationBranch`，读不到写「运行配置没有集成分支」。
- **开工时间**：事件日志里 `type == "session.registered"` 且 `key == <会话名>` 的最后一条的 `at`。
- **「问过你」**：遍历 `kind == "review"` 且 `module` 相符的事项；被任一 `hub-batch` 的 `reviews` 列出、或 `closedReason == "answered"` 就计数；
  `lastAt` 取进提请批准的 `hub-batch` 事件时间与答复时间 `answer.answeredAt` 中较晚的一个。节点按 Spec 定的顺序 `spec`、`plan`、`interface`、`final` 排（`stall.py` 里写死这个顺序；不借用 `review.NODE_RANK`，它把接口排在 Plan 前面，是交审排序用的）。
- **退回与等待用户**：`merge-approval` 且 `closedReason == "returned"`；`wait-user` 且 `from == <会话名>`，`decide` 取 `decide` 字段第一行。时间取对应事件的 `at`。
- `ref` 一律用 `refs.py` 的现有写法（`C<号>`）；W 前缀属于 crew-glossary-rename，本模块不改。

## 影响面

新增：`module_crew/stall.py`、`tests/test_stall_signals.py`。修改：`module_crew/failure.py`（`sessions`、`render_sessions`）、`module_crew/probe.py`（status 模块行）、
`spec/crew-hub-bridge.md`（契约一节一句话＋变更记录）、`README.md` 第 121 行。不改状态库格式、契约、`interface.json`（版本号在 crew-glossary-rename 收尾时随 0.4.0 一起升）。不涉及界面。

## Task List

### Phase 1：事实字段

- [ ] Task 1：提交事实与开工时间——`stall.commit_facts`、`stall.started_at`，`sessions --json` 加 `startedAt`、`commits`（验收 1、2、3）
- [ ] Task 2：问过你、合并退回、等待用户——`stall.asks`、`returns`、`wait_user`，`sessions --json` 加三个字段（验收 4、5、6、7）

### Checkpoint 1（report）：新字段齐全；crew-hub-bridge 现有 sessions 契约测试原样通过、状态库读不到仍退出 2（验收 8），记入 todo 后继续

### Phase 2：人看的输出与文档

- [ ] Task 3：`module-crew sessions` 加「最近提交」「问过你」两行、`status` 模块行加「最近提交 X 前」「同一节点最多问过你 N 次」；`spec/crew-hub-bridge.md` 契约一节加一句并记变更记录；README 第 121 行补新字段（验收 9）

### Checkpoint 2（gate）：模块最终验收

- [ ] 全量测试全绿（验收 10）；10 条验收逐条对应测试名与结果；列出实际改动文件（新增、修改、行数，取自 git）与提交号
- [ ] 本 Plan 获批即授权：每个任务完成后在 `main` 本地提交；不推送；不升版本号、不冻结、不动 `module-crew-release/`；最终验收通过后直接写 crew-host-permissions 的 Spec 交审

## Risks and Mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| 模块很多时每个模块两次 git 调用让 `sessions --json` 变慢 | 低 | 决策收件箱几分钟读一次、模块个位数；测试里不计时，最终验收时报实测耗时 |
| 时区：提交时间与状态库时间格式不同 | 低 | `%cI` 本身是 ISO 8601 带时区；测试断言可被 `datetime.fromisoformat` 解析 |
| 「问过你」漏算没配决策收件箱时还没答的那次 | 已接受 | Spec 关键决策 3 写明，不新增记录 |
| 动到已批准的 crew-hub-bridge Spec | 低 | 只追加一句与变更记录，不改原有条文；最终验收附这处差异 |

## Open Questions

无（Spec 的未决问题「接管后开工时间不改」按暂定做）。
