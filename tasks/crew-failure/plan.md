<!-- spec-guard: review pending -->
# Implementation Plan: crew-failure

> 依据：`spec/crew-failure.md`（已批准）。任务清单：`tasks/crew-failure/todo.md`。

## Overview

先做挂起与恢复，同时修订 crew-start 的空位计算（两者一起才能验证「挂起让出名额」）；再做只读的 `sessions` 和 `resume-kit`；
然后做退回串行与 crew-start 的拒绝；最后补跨模块互不拖累的测试、命令行和两份 skill。每个任务先写失败的测试，再实现到全绿，单独提交。

## Architecture Decisions

- `module_crew/failure.py`：`suspend(db, module, reason, original)`、`resume(db, module)`、`sessions(db) -> list[dict]`、
  `resume_kit(db, module) -> Kit`、`set_mode(db, serial, original)`；拒绝时抛 `FailureRefused`（命令行转成退出码 3），什么都不写。
- 按模块找会话：`role == "dev"`、`status == "active"`、`module` 相符的那条登记；没有就拒绝。
- `suspended` 写进会话登记（事件 `session.suspended`／`session.resumed`），`status` 不变。
- crew-start：`_active_devs` 保持原义（钩子、合并照常认挂起的会话），另加 `_counted_devs` 只数 `suspended` 为空的，
  `plan` 的空位与 `validate`／`prepare` 的名额检查改用它；配置 `mode` 为 `serial` 时，「已退回串行」作为一条阻塞项加进 `plan` 的 `blockers`、
  `validate` 的原因，沿用 crew-start 退出码 3「有阻塞／校验不过，什么都没写」的原有含义，不新增退出码。
- 「最后动静」：遍历 `store.events`，取与该会话相关（`actor` 为它，或写入的会话／请求／事项／等待单记录里 `from`／`to`／`module` 指向它）的最新事件时间；
  距今用分钟／小时／天的整数文字，不设阈值。
- 恢复说明 = `hooks.session_start(worktree, "compact")` + 换会话的做法（`takeover` 与 `bridge_register`），用 `Transaction.write_body` 存成正文。
- 退回串行与恢复并行都写配置 `main` 记录的 `mode`，事件里带用户原话。

## 影响面

新增：`module_crew/failure.py`、`tests/test_failure.py`。修改：`module_crew/start.py`、`module_crew/__main__.py`、
`skills/crew-coordinator/SKILL.md`、`skills/crew-dev/SKILL.md`、`tests/test_skills.py`、`spec/crew-start.md`（末尾变更记录）。不涉及界面。

## Task List

### Phase 1：挂起与只读视图

- [ ] Task 1：`suspend`／`resume` 与 crew-start 空位修订（验收 1、2、3，验收 9 的空位部分）
- [ ] Task 2：`sessions`（验收 4）
- [ ] Task 3：`resume-kit`（验收 5）

### Checkpoint 1（report）

- [ ] 全部测试全绿（含 crew-start 原有测试）

### Phase 2：退回串行与收尾

- [ ] Task 4：`serial` 与 crew-start 拒绝开新模块（验收 6，验收 9 的 serial 部分）
- [ ] Task 5：跨模块互不拖累测试（验收 7）
- [ ] Task 6：命令行五个子命令、两份 skill 新增章节、`spec/crew-start.md` 变更记录（验收 8、9）

### Checkpoint 2（gate）：模块最终验收

- [ ] 全部测试全绿；逐条对照 Spec 的 9 条验收标准，写明各由哪个测试覆盖；附 `sessions` 输出与恢复说明样例
- [ ] 附 `spec/crew-start.md` 变更记录，交用户复审（一次批准同时批准 crew-start 修订）
- [ ] 在对话里列出本模块实际改动的文件（新增、修改、删除与行数）
- [ ] 本 Plan 获批即授权：每个任务完成后在 `main` 做一次本地提交；不推送

## Risks and Mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| 改 crew-start 的名额计算，影响已开模块的流程 | 高 | 只换「数名额」的两处，其余仍用 `_active_devs`；crew-start、review、merge、hooks 原有测试全部重跑 |
| 「最后动静」误把别的会话的事件算进来 | 中 | 只按明确的字段匹配；测试里两个会话各自写事件，断言互不串 |
| 退回串行误挡已开模块的交审与合并 | 高 | 只在 `start plan`／`prepare` 读 `mode`；测试断言 serial 下 `review add`、`merge run` 照常 |
