# Implementation Plan: crew-session-handover

<!-- spec-guard: review pending -->

> 依据：`spec/crew-session-handover.md`（用户 2026-10-22 批准，含关键决策 4）。任务清单：`tasks/crew-session-handover/todo.md`。

## Overview

先让钩子按会话编号认出登记的角色（不论目录），再做一步接管与旧会话的失效提示，然后在命令分派处加会话守门，接着 `status` 标出本会话，最后改 README 与 skill、跑全量与钩子耗时。
每个任务先写失败的测试、看到红再实现到绿，单独在 `main` 本地提交，不推送、不发版。

## Architecture Decisions

- **按会话编号找登记**：`hooks.registration_of(db, sid) -> (name, rec) | None`（在用登记里 `hostSession.sessionId == sid`），`hooks.role_of(db, name, rec) -> Role`（按登记的 role／module／task 组装，不看目录）。
  `session_start`、`prompt_line` 改为接受 `Role`（原来按 `cwd` 的调用改成先 `detect(cwd)` 再传入，行为不变）；`_text_for` 先按会话编号找，找到就用它，找不到才走原来的 `detect(cwd)` + `matches` 路径。
  目录不一致（`cwd` 不在 `_home_of(rec)` 里）时，SessionStart 多一行写明两边目录。
- **一步接管**：`hooks.bind(..., takeover=False)`；`takeover=True` 时只认 `role == "coordinator"`、要原话、跳过目录核对（同一个 git 公共目录已由 `open_store(cwd)` 保证），在一个事务里把 `hostSession` 换成本会话、
  把旧 `hostSession.sessionId`（有的话）追加进 `previousSessions`（最多留 20 条）、事件 `session.taken-over` 记 `original`、`oldSessionId`、`newSessionId`。`store` 校验 `previousSessions` 是列表、每项有字符串 `sessionId` 与 `at`。
- **旧会话提示**：`_text_for` 找不到登记时，再查有没有登记的 `previousSessions` 含本会话编号；有就 SessionStart 与每轮都只出一行失效提示（不出角色提示、不出陌生会话提醒）。
- **会话守门**：`__main__` 在合并锁守门旁边加 `_session_guard(args)`：豁免集合（只读、模块侧、`hook`、`bind`、`coordinator up` 在没有在用模块协调时）之外的子命令，
  当「有在用模块协调 + 它登记了会话编号 + `own_session_id()` 读得到且不同」时打印原因与接管命令、返回 7。豁免集合写成一张表，测试逐项核对。
- **status 本会话**：`probe.summarize_store` 的 `sessions[]` 加 `self`（`hostSession.sessionId == own_session_id()`），`store` 加 `selfIsCoordinator`（读不到编号为 None）；`__main__` 打印「← 本会话」与非登记会话的一行说明。

## 影响面

新增：`tests/test_session_handover.py`。修改：`module_crew/hooks.py`、`store.py`、`__main__.py`、`probe.py`、`skills/crew-coordinator/SKILL.md`、`README.md`，以及按需调整断言的已有测试。
不新增依赖，不改契约、`interface.json`、版本号；钩子仍只读文件。

## Task List

- [ ] Task 1：钩子按会话编号认身份，别的目录也注入角色提示与命令入口、写明两边目录（Spec 验收 1）
- [ ] Task 2：`bind --takeover` 一步接管（含 `previousSessions` 与事件）（Spec 验收 2）
- [ ] Task 3：被接管的旧会话只收到失效提示（Spec 验收 3）

### Checkpoint 1（report）：身份与接管就位，相关测试通过，记入 todo 后继续

- [ ] Task 4：写命令会话守门，退出码 7，豁免表逐项核对（Spec 验收 4）
- [ ] Task 5：`status` 的「← 本会话」、非登记会话说明与 `--json` 字段（Spec 验收 5）
- [ ] Task 6：README「换会话」与命令一览、crew-coordinator skill 重开做法、全量测试与钩子耗时（Spec 验收 6、7）

### Checkpoint 2（gate）：最终验收

- [ ] 回告：完成情况发给总协调（local_d7434023）；O9 的修法告诉 spec-guard 负责人（local_0a689563）
