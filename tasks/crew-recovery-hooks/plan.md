<!-- spec-guard: review approved -->
# Implementation Plan: crew-recovery-hooks

> 依据：`spec/crew-recovery-hooks.md`（已批准）。任务清单：`tasks/crew-recovery-hooks/todo.md`。

## Overview

先做角色判断（纯读文件与状态库），再做模块会话与协调会话的提示文字（含四档状态与压缩核对），然后接 `hook` 子命令与 `hooks.json`，
最后做 `takeover`。每个任务先写失败的测试，再实现到全绿，单独提交。

## Architecture Decisions

- `module_crew/hooks.py`：`detect(cwd) -> Role | None`、`session_start(cwd, source) -> str | None`、`prompt_line(cwd) -> str | None`、`takeover(db, name, original)`。
- 角色判断不跑子进程：状态库位置用 `store.store_path`（它内部调一次 `git rev-parse`，这是唯一的子进程）；集成 checkout 通过读 git 元数据找——
  主 checkout = 公共 git 目录的上一级，分支取 `<公共目录>/HEAD`；其他 worktree 读 `<公共目录>/worktrees/*/gitdir` 与各自 `HEAD`。
- 四档状态按 Spec 关键决策 1 用状态库的 `item` 记录推出；等待单取 `ticket` 中 `from == 本会话` 且 `open` 的。
- `hook` 子命令包一层 `try/except BaseException`，任何异常都只返回 0 且无输出；标准输入 JSON 读不出就当 `{}`。

## 影响面

新增：`hooks/hooks.json`、`module_crew/hooks.py`、`tests/test_hooks.py`。修改：`module_crew/__main__.py`（`hook`、`takeover`）。不涉及界面。

## Task List

### Phase 1：角色与提示

- [ ] Task 1：角色判断与静默（验收 1，及验收 2、4 的识别部分）
- [ ] Task 2：模块会话与协调会话提示、四档状态、压缩核对（验收 2、3、4、5）

### Checkpoint 1（report）

- [ ] 全部测试全绿

### Phase 2：接入与接管

- [ ] Task 3：`hook` 子命令、`hooks.json`、异常静默与耗时（验收 6、7）
- [ ] Task 4：`takeover`（验收 8）

### Checkpoint 2（gate）：模块最终验收

- [ ] 全部测试全绿；逐条对照 Spec 的 8 条验收标准，写明各由哪个测试覆盖；附两种角色的提示样例与耗时实测值
- [ ] 在对话里列出本模块实际改动的文件（新增、修改、删除与行数）
- [ ] 本 Plan 获批即授权：每个任务完成后在 `main` 做一次本地提交；不推送

## Risks and Mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| 读 git 元数据的方式与 git 版本有出入 | 中 | 测试用真实 `git worktree add` 建的仓库；读不出就静默 |
| 钩子在无关会话里误注入 | 高 | 只在登记过的 worktree 与集成 checkout 注入；测试覆盖无关目录与未登记 checkout |
| 钩子拖慢每轮对话 | 中 | 不跑 probe／`/map`；测试记录耗时 |
