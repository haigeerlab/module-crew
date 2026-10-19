<!-- spec-guard: review approved -->
# Implementation Plan: crew-onboarding

> 依据：`spec/crew-onboarding.md`（已批准）。任务清单：`tasks/crew-onboarding/todo.md`。

## Overview

先做 `inbox add` 的骨架（发件人核对、解析、拒收不写），再依次接【等待用户】的记账与取代、等待单与关单、【撤回】与重复提交，
然后做 `answer`，最后写两份 skill。每个任务先写失败的测试，再实现到全绿，单独提交。

## Architecture Decisions

- `module_crew/inbox.py` 只有两个入口：`add(db, text, sender, relay_id) -> Outcome`、`answer(db, number, original, option) -> Reply`；
  全部状态改动在一个 `store` 事务里完成，任何拒收在写之前判断，拒收时事务里不调写方法（crew-store 保证不改文件）。
- `Outcome` 带：类型、退出码、新编号、关掉的编号、没对上的编号、要转告的原句、问题代码；CLI 只负责打印与退出码。
- 编号查找 `_find(records, sender, n)`：先查键 `str(n)` 且 `from == sender`，再查 `relayId == n` 且 `from == sender`。
- 重复提交判定：同种记录里已有 `from == sender` 且 `relayId == relay_id` 的；【已恢复】【撤回】没有自己的记录，在事件 `data` 里记 `relayId`，用 `store.events` 查重。
- `answer` 的选项原文写作「字母：方案文字」，与契约样例 `user-reply/single` 一致；`source_relay_id` 取事项的 `relayId`。
- 测试辅助：`tests/helpers.py` 加 `seed_sessions(db)`，写入一个协调会话与两个模块会话（一个已退役）。

## 影响面

新增：`module_crew/inbox.py`、`skills/crew-coordinator/SKILL.md`、`skills/crew-dev/SKILL.md`、`tests/test_inbox.py`、`tests/test_answer.py`、`tests/test_skills.py`。
修改：`module_crew/__main__.py`（两个子命令）、`tests/helpers.py`。不涉及界面。

## Task List

### Phase 1：收件记账

- [ ] Task 1：`inbox add` 骨架——发件人核对、解析、拒收不写、【交审】【公共变更请求】退出码 4（验收 5、6）
- [ ] Task 2：【等待用户】记账与默认取代、显式取代、并行（验收 1、2）
- [ ] Task 3：等待单、结束行关单、【已恢复】、【撤回】、重复提交（验收 3、4、7）

### Checkpoint 1（report）

- [ ] 全部测试全绿

### Phase 2：答复与 skill

- [ ] Task 4：`answer`（验收 8、9、10）
- [ ] Task 5：两份 skill（验收 11）

### Checkpoint 2（gate）：模块最终验收

- [ ] 全部测试全绿；逐条对照 Spec 的 11 条验收标准，写明各由哪个测试覆盖
- [ ] 在对话里列出本模块实际改动的文件（新增、修改、删除与行数），并贴出两份 skill 全文供审
- [ ] 本 Plan 获批即授权：每个任务完成后在 `main` 做一次本地提交；不推送

## Risks and Mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| 结束行编号既可能是状态库编号也可能是邮箱号，两者数值撞上 | 中 | 先按状态库编号且同一发件人找；测试覆盖两者同号的情况 |
| skill 写得太长、会话不照做 | 中 | 每份控制在一屏要点内，命令与退出码用表格；最终验收贴全文交你审 |
| 原话经命令行传入被 shell 改写 | 中 | 提供 `--original-file`；测试多行与特殊字符 |

- 2026-10-19：加两项任务（0.5.0，R21 MC-2：skill 措辞；契约部分等 SP-1）。来源同上。
