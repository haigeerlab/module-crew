<!-- spec-guard: review approved -->
# Implementation Plan: crew-store

> 依据：`spec/crew-store.md`（已批准，指纹 45f344b847dd）。任务清单：`tasks/crew-store/todo.md`。

## Overview

先立插件骨架和「临时 git 仓库」测试工具，再按「定位与建库 → 事务与事件日志 → 快照与重建 → 并发 → 正文 → 会话登记 → check」逐层加能力。
每个任务先写失败的测试，再实现到全绿，然后单独提交。并发与崩溃这两类高风险行为放在前半段（任务 3、4、5），尽早暴露问题。

## Architecture Decisions

- 存储逻辑全在 `module_crew/store.py`；CLI 只在 `module_crew/__main__.py` 做参数解析与中文输出；`bin/module-crew` 只是 `exec python3 -m module_crew "$@"`
  （用脚本所在目录的上一级作 `PYTHONPATH`，不依赖安装位置）。
- 定位：`git -C <cwd> rev-parse --path-format=absolute --git-common-dir`（git ≥ 2.31；本机版本在任务 2 里断言）；`open_store(cwd=None)` 可传目录，测试全部显式传临时仓库路径。
- 事务：`flock` 锁 `.lock`；进入时读整份日志算出 `next_seq`、`next_number` 与各种类的当前记录；事务内的读取看到本事务未落盘的写入；
  退出时一次性落盘——先写正文（正文内容在事务内只留在内存，提交时才写临时文件并改名到位），再追加全部事件（单次 `write` + `fsync`），最后按种类写快照。异常时只丢弃内存状态，磁盘上什么都没发生，不需要任何删除。
  （崩溃发生在正文落盘之后、事件追加之前时，会留下没有事件指向的正文文件：`check` 把它报告为「孤立正文」警告，不删除；编号仍可能被再次分配，此时 `write_body` 发现目标已存在则先把旧文件改名为 `.orphan-<时间>` 留证。）
- 日志读取：逐行解析；无法解析或 `v` 不认识的行跳过并记警告，不抛异常；末尾缺换行时下次追加先补 `\n`。
- 快照只在写事务里写，覆盖本事务写过的种类，以及读时发现落后、缺失或损坏的种类；损坏文件先改名 `.corrupt-<时间>`。
- 会话登记校验放在 `put("session", ...)` 内，对照事务内的当前全部 `session` 记录。
- 并发测试用 `multiprocessing` 的 `spawn` 上下文。

## 影响面

全部是新文件：`.claude-plugin/plugin.json`、`bin/module-crew`、`module_crew/__init__.py`、`module_crew/__main__.py`、`module_crew/store.py`、
`tests/__init__.py`、`tests/helpers.py`、`tests/test_package.py`、`tests/test_store_init.py`、`tests/test_store_tx.py`、`tests/test_store_rebuild.py`、
`tests/test_store_concurrency.py`、`tests/test_store_body.py`、`tests/test_store_session.py`、`tests/test_store_check.py`。
不改已有文件（`tasks/crew-store/todo.md` 的勾选与 `.agent/state.json` 除外）。不涉及用户可见界面，不需要 UI 验证。

## Task List

### Phase 1：骨架

- [ ] Task 1：插件骨架、临时仓库测试工具、包级静态检查（验收 14）

### Checkpoint 1（report）

- [ ] 全部测试全绿

### Phase 2：存储核心

- [ ] Task 2：定位与 `store init`（验收 1、2、3、13）
- [ ] Task 3：事务、编号、事件日志与回滚（验收 5、10）
- [ ] Task 4：快照、从日志重建、落后与损坏处理（验收 6、7、8、9）
- [ ] Task 5：多进程并发，跨主 checkout 与 worktree（验收 4）

### Checkpoint 2（report）

- [ ] 全部测试全绿；并发测试连续跑 5 次都通过

### Phase 3：正文、会话登记与排查

- [ ] Task 6：正文文件（验收 12 中 `read_body` 部分）
- [ ] Task 7：会话登记校验（验收 11）
- [ ] Task 8：`store check`（验收 3、7、9、12 中 `check` 的部分；孤立正文警告）

### Checkpoint 3（gate）：模块最终验收

- [ ] 全部测试全绿；逐条对照 Spec 的 14 条验收标准，写明各由哪个测试覆盖
- [ ] 在对话里列出本模块实际改动的文件（新增、修改、删除与行数，取自 `git diff --stat`）
- [ ] 本 Plan 获批即授权：每个任务完成后在 `main` 做一次本地提交；不授权推送、不建远端

## Risks and Mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| macOS 上 `flock` 与 `multiprocessing` 偶发失败 | 高 | 任务 5 的并发测试连续跑 5 次；用 `spawn` |
| 每次开事务读整份日志，日志变大后变慢 | 低 | 本插件规模下几百行；任务 5 里记录 1000 条时单事务耗时，超过 50ms 再议 |
| 正文改名与事件追加之间崩溃留下孤立正文 | 中 | 架构决策里的「孤立正文」报告与 `.orphan-` 留证；任务 6 构造该场景测试 |
| 测试误写真实项目的 `.git` | 高 | `tests/helpers.py` 只在 `tempfile.mkdtemp()` 下建仓库；`open_store` 测试全部显式传路径，基类断言路径在临时目录内 |
