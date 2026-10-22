# Implementation Plan: crew-task-ledger

<!-- spec-guard: review approved -->

> 依据：`spec/crew-task-ledger.md`（用户 2026-10-22 批准）。任务清单：`tasks/crew-task-ledger/todo.md`。

## Overview

按「记录与编号 → 重叠判断 → 排队与取消 → 命令行 → status 与文档」的顺序做。每个任务先写失败的测试，看到红再实现到绿，单独在 `main` 本地提交，不推送。
不改钩子、不改绑定，短验证不受影响；本模块不发版。

## Architecture Decisions

- **新文件 `module_crew/tasks.py`**：`add`、`overlaps`、`advance`、`next_ready`、`cancel`、`summary`，都只经 `store` 事务写，只读 `git`。
- **记录**：`store.KINDS` 加 `task`；`store` 写入时校验任务记录（类型、状态、`expectedFiles` 非空且每项是不含 `..` 的相对路径、`causedBy` 形如 `T<n>`／`C<n>`）。
  编号用 `tx.allocate_number()`。
- **状态转换表**：`TRANSITIONS = {"queued": {"ready", "cancelled"}, "ready": {"queued", "dispatched", "cancelled"}, "dispatched": {"working", "cancelled", "escalated"},
  "working": {"returned", "escalated", "cancelled"}, "returned": {"merged", "working", "escalated", "cancelled"}, "escalated": {"working", "promoted", "cancelled"}}`；
  `merged`／`promoted`／`cancelled` 是终态。`advance` 不在表里就抛 `TaskRefused`。`ready` 回 `queued` 留给 `task next` 发现新冲突时用。
- **重叠**：`_clash(a, b)`：相同，或一方以 `/` 结尾且另一方以它开头。来源一：状态在 `dispatched`／`working`／`returned`／`escalated` 的任务的 `expectedFiles`
  加 `result.files`（有的话）；来源二：状态库里在用的模块会话，`git diff --name-only <集成分支>...<模块分支>`（带超时；分支不存在就跳过并在输出里说明）。
  `ready` 的任务也算占位（已经批准可开，还没派出），避免两条都被提成可开。
- **排队**：`next_ready` 按 `(type != "bug", number)` 排序逐条看，已不重叠的提为 `ready`，并把它加入占位再看下一条。
- **编号显示**：`refs.task(n) -> "T<n>"`；`refs.parse` 正则加 `Tt`；`task` 子命令用 `refs.parse` 后再核对指向 `task` 记录。
- **status**：`probe.summarize_store` 加 `tasks`：`{"active": [...], "queued": [...], "recent": [最近 5 条终态]}`；`__main__` 显示「任务」段。

## 影响面

新增：`module_crew/tasks.py`、`tests/test_task_ledger.py`。
修改：`module_crew/store.py`、`module_crew/refs.py`、`module_crew/probe.py`、`module_crew/__main__.py`、`skills/crew-coordinator/SKILL.md`、`README.md`、
可能还有断言 `refs.parse` 报错文案或 `status --json` 字段集合的旧测试。不新增依赖，不改契约、钩子、`interface.json`、版本号（随第六版一起发）。

## Task List

- [ ] Task 1：`task` 记录、校验、编号与 T 前缀；没有模块协调时拒绝（Spec 验收 1、9）
  - 文件：`module_crew/store.py`、`module_crew/refs.py`、`module_crew/tasks.py`、`tests/test_task_ledger.py`
- [ ] Task 2：重叠判断——在做任务、`ready` 占位与模块分支已改文件；已合入与取消的不算（Spec 验收 2、3）
  - 文件：`module_crew/tasks.py`、测试
- [ ] Task 3：状态转换表、`task next` 排队提升、`task cancel`（Spec 验收 4、5、6）
  - 文件：`module_crew/tasks.py`、测试

### Checkpoint 1（report）：记账与排队就位，相关测试通过，记入 todo 后继续

- [ ] Task 4：`task add/list/show/next/cancel` 命令行与 `--json`；接管、清空交接后任务不变（Spec 验收 8）
  - 文件：`module_crew/__main__.py`、测试
- [ ] Task 5：`status` 任务段（文字与 `--json`，只读）（Spec 验收 7）
  - 文件：`module_crew/probe.py`、`module_crew/__main__.py`、测试
- [ ] Task 6：crew-coordinator skill「记任务与看排队」、README 命令一览、全量测试与旧称扫描（Spec 验收 10）
  - 文件：`skills/crew-coordinator/SKILL.md`、`README.md`、`tests/test_skills.py`（如需要）

### Checkpoint 2（gate）：最终验收

- [ ] 回告：完成情况发给总协调（local_d7434023）

## Risks

| 风险 | 影响 | 缓解 |
|---|---|---|
| 模块还没改到的文件判断不了 | 轻任务和模块到合并时才冲突 | 输出照实提示；合并队列的完整检查兜底 |
| `git diff` 在模块分支很多时变慢 | `task add` 慢 | 每个分支一次 `--name-only`，带超时；超时就跳过并说明 |
| `refs.parse` 放宽到 T 后，别处把 T 号当成 C 号 | 号指错记录 | 各命令解析后都核对记录种类；测试覆盖 |
