# Implementation Plan: crew-unqueued-commits

<!-- spec-guard: review approved -->

> 依据：`spec/crew-unqueued-commits.md`（用户 2026-10-22 批准）。任务清单：`tasks/crew-unqueued-commits/todo.md`。

## Overview

先做「认得点」的记录与更新（四处自己的提交、升级与开工），再做 `unqueued` 只读列出与 `--notify`，然后接进 `merge run` 与 `status`，最后改 skill 与 README。
每个任务先写失败的测试、看到红再实现到绿，单独在 `main` 本地提交，不推送、不发版。

## Architecture Decisions

- **新文件 `module_crew/unqueued.py`**：`seen(db)`、`mark(tx, checkout, source)`（把认得点设为 checkout 的 HEAD，写事件 `integration-seen`）、`find(db, project) -> Found`（认得点、顶端、提交列表、`missing_seen`、`not_in_history`）、
  `notify(db, project) -> list[send]`（同步基线通知，收件人规则复用 `merge.no_sync` 与 merge 里给在做任务发通知的同一段逻辑，抽成 `merge.sync_targets(tx)`）。
- **更新认得点**：`merge.run` 合并成功（含勾选提交之后）、`merge.tick`、`changes.land`、`review.approve` 的提交成功后，在各自的事务里调 `unqueued.mark`；`coordinator.up` 与 `start.prepare` 第一次写配置时设认得点。
  检查失败重置后不更新（顶端回到合并前，认得点本来就在那里）。
- **列提交**：`git rev-list --first-parent <seen>..<integrationBranch>`，再用一次 `git log --no-walk --format=%h%x00%an%x00%cI%x00%s` 取短号、作者、时间、标题；时间按 0.10.1 的 `_iso` 规则处理。
  认得点不是集成分支的祖先（`merge-base --is-ancestor` 失败）时 `not_in_history`，只列顶端一个提交。
- **merge run**：合并前调 `find`，有提交就 `notify` 并 `mark`（来源 `merge-run`），输出列出；然后照常合并。
- **status**：`probe.summarize_store` 加 `unqueued: {"count", "seen", "head", "missingSeen"}`（只读，不写库）；`__main__` 显示一行。
- **命令**：`module-crew unqueued [--json] [--notify]`，退出码按 Spec。

## 影响面

新增：`module_crew/unqueued.py`、`tests/test_unqueued.py`。修改：`merge.py`、`changes.py`、`review.py`、`coordinator.py`、`start.py`、`probe.py`、`__main__.py`、`skills/crew-coordinator/SKILL.md`、`README.md`。
不新增依赖，不改契约、钩子、`interface.json`、版本号。

## Task List

- [ ] Task 1：认得点——`unqueued.mark`，升级、开工时设定；四处自己的提交之后更新（Spec 验收 1）
- [ ] Task 2：`unqueued` 只读列出、退出码、认得点不在历史里的提示（Spec 验收 2、6）
- [ ] Task 3：`unqueued --notify`——收件人规则抽成 `merge.sync_targets`、通知、推进认得点（Spec 验收 3）

### Checkpoint 1（report）：发现与通知就位，相关测试通过，记入 todo 后继续

- [ ] Task 4：`merge run` 合并前检查并通知（Spec 验收 4）
- [ ] Task 5：`status` 一行与旧项目没有认得点时的提示（Spec 验收 5）
- [ ] Task 6：crew-coordinator skill、README「出状况时怎么办」与命令一览、全量测试与旧称扫描（Spec 验收 7）

### Checkpoint 2（gate）：最终验收

- [ ] 回告：完成情况发给总协调（local_d7434023）

## Risks

| 风险 | 影响 | 缓解 |
|---|---|---|
| 漏掉某处自己的提交没更新认得点 | 自己的提交被报成不经队列 | Task 1 对四处各写一个测试；`unqueued` 输出带提交标题，误报一眼可见 |
| 抽 `merge.sync_targets` 改动合并后的通知 | 收件人变化 | 先用现有合并测试锁住收件人，再抽函数 |
| 认得点写入与提交不在同一事务 | 中途失败时认得点落后 | 落后只会多报一次，不会漏报；照实输出 |
