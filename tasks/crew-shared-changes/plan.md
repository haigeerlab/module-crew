<!-- spec-guard: review pending -->
# Implementation Plan: crew-shared-changes

> 依据：`spec/crew-shared-changes.md`（已批准）。任务清单：`tasks/crew-shared-changes/todo.md`。

## Overview

先做 `change add`（记账、等待单、分流提示、查重）与只读的 `change list`，再做 `change answer`，然后是 `change land`（核对、提交、通知），
最后接命令行与 skill。每个任务先写失败的测试，再实现到全绿，单独提交。

## Architecture Decisions

- `module_crew/changes.py` 入口：`add(db, text, sender, relay_id)`、`pending(db)`、`answer(db, number, original)`、`land(project, number, original=None)`；
  复用 `inbox` 的 `Outcome`／`AnswerRefused`／`Reply`，查重沿用事件 `data.relayId` 的写法。
- 分流提示 `hints_for(files, others)` 是纯函数，规则按 Spec 关键决策 4 写成模块级常量。
- 等待单与请求在同一事务里写：先分配等待单编号写 `ticket`，再写 `request` 并记下等待单编号；`waitingFor` 填协调会话的邮箱名（取状态库在用 `coordinator`）。
- `land` 的核对：`git -C <集成 checkout> status --porcelain --untracked-files=all`，逐行取路径（含改名的新旧两侧），全部须在清单内且至少一条。
- 通知正文：`protocol.render_coordination_notice("sync-baseline", ...)`；给请求方的在前面加 `回复：#<relayId>\n` 后用 `protocol.parse` 自检。

## 影响面

新增：`module_crew/changes.py`、`tests/test_changes.py`。
修改：`module_crew/__main__.py`（`change` 子命令）、`skills/crew-coordinator/SKILL.md`、`tests/test_skills.py`。
测试会在临时仓库的集成分支上真实提交；不涉及界面。

## Task List

### Phase 1：记账

- [ ] Task 1：`change add` 与 `change list`（验收 1、2、3、4）
- [ ] Task 2：`change answer`（验收 8）

### Checkpoint 1（report）

- [ ] 全部测试全绿

### Phase 2：落地与命令

- [ ] Task 3：`change land`（验收 5、6、7）
- [ ] Task 4：命令行与协调会话 skill（验收 9）

### Checkpoint 2（gate）：模块最终验收

- [ ] 全部测试全绿；逐条对照 Spec 的 9 条验收标准，写明各由哪个测试覆盖
- [ ] 在对话里列出本模块实际改动的文件（新增、修改、删除与行数），并贴出 skill 改动
- [ ] 本 Plan 获批即授权：每个任务完成后在 `main` 做一次本地提交；测试只在临时仓库的集成分支上提交；不推送

## Risks and Mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| `git status --porcelain` 的改名、带空格路径解析错 | 中 | 用 `-z` 输出解析；测试含改名与带空格路径 |
| 分流规则漏掉某种锁文件 | 低 | 只是提示，最终由协调会话判断；规则只增不改，漏了补 |

## 0.17.0 返工说明（2026-10-27）

为什么返工：LIVE-SAAS 现场问题与 0.16.1 期间暴露的流程卡点，用户在 mc-coord 确认 0.17.0 做这几件（见 todo「0.17.0 修订」一节）。超出原范围，Plan 改回 pending，由模块会话按修订后的 Spec 补写本节的任务分解后交审。

## 变更记录

- 2026-10-27：追加「0.17.0 返工说明」，评审标记 approved 改回 pending；原因：0.17.0 修订超出原范围；来源：用户在 mc-coord 原话「0.17.0 需求就是这四件，前提假设 A1～A5 全按推荐」
