# Implementation Plan: crew-stage-c-fixes

<!-- spec-guard: review pending -->

> 依据：`spec/crew-stage-c-fixes.md`（用户 2026-10-20 批准，含交审前对 MC-9 的修订）。任务清单：`tasks/crew-stage-c-fixes/todo.md`。

## Overview

先做三处代码修复（同步通知跳过、合并批准取代、worktree 内编辑放行），再升契约 v2.4 并让提请批准带「模块」，然后改 skill、README 与版本号，最后做一次实地验证。
每个任务先写失败的测试，再实现到全绿，单独在 `main` 本地提交，不推送。

## Architecture Decisions

- **MC-10**：`merge.py` 发同步基线时，`busy` 之外再跳过「有 `kind == review`、`node == final`、`state == open` 的交审」的模块；`changes.land` 同样跳过，但提出这条变更请求的模块照常收到回复（它在等这条回复）。
- **MC-11**：`merge._approve_one` 写新批准的同一事务里，关掉同模块其他开着的 `merge-approval`（`superseded`、`supersededBy`），`Approved` 带上被取代的编号供命令输出。
- **MC-13**：`permissions.claude_entries(cfg, worktree=None)`：传了模块 worktree 才加 allow `Edit(//<去掉开头斜杠的绝对路径>/**)`、deny `Edit(//…/.claude/**)`；`_checkout_plan` 对 `role == "dev"` 传入。
  `shadowed()` 只检查 Bash 示例命令，遇到 `Edit(...)` 条目跳过（不误报）。`start prepare` 走同一个 `_checkout_plan`，自动跟随。
- **MC-9**：从 session-protocol 495b475 复制整套样例到 `tests/fixtures/session-protocol/v2.4/`，一致性测试跑三套；`FIELDS["wait-user"]` 加「模块」，`contract()` 给 `module`（去首尾空格，没写为 null）；
  `CONTRACT_VERSION = "2.4"`，`interface.json` 的 `contract` 改 2.4；`sources.PROTOCOLS` 加 "2.4"，`hub_protocol` 改为取登记 hub 里的最低版本。
  `_hub_item` 在「要点」各行之后、其他字段之前写「模块：<g['module']>」（2.2、2.3 两条路径都写）；v2.2 回归夹具重新生成，测试断言新旧只差这一行。

## 影响面

修改：`module_crew/merge.py`、`module_crew/changes.py`、`module_crew/permissions.py`、`module_crew/protocol.py`、`module_crew/sources.py`、`module_crew/review.py`、`module_crew/__main__.py`（输出被取代的批准）、
三份 skill、`README.md`、`interface.json`、三处版本号。新增：`tests/fixtures/session-protocol/v2.4/`、`tests/test_stage_c.py`。修改测试：`tests/test_protocol_conformance.py`、`tests/test_permissions.py`、`tests/test_card_fields.py`、回归夹具、`tests/test_skills.py`。
会改用户项目里被 git 忽略的 `.claude/settings.local.json`（只在 `permissions apply` 凭用户原话时）。不新增依赖。不涉及界面。

## Task List

### Phase 1：少问、少弹窗

- [ ] Task 1：MC-10——`merge run`、`change land` 的同步通知跳过有开着的最终验收交审的模块（变更请求的提出方照常回复）；两份 crew-dev skill 写「最终验收被退回或答 B，改完先 `module-crew sync` 再重交」
  - 验收：Spec 验收 1
  - 验证：重放 summary 场景（b 交最终验收后 c 合并，b 不收同步通知、b 的批准照常合并）；`change land` 一例；skill 断言
  - 文件：`module_crew/merge.py`、`module_crew/changes.py`、两份 crew-dev skill、`tests/test_stage_c.py`
- [ ] Task 2：MC-11——`merge approve` 取代同模块开着的旧批准并输出一行
  - 验收：Spec 验收 2、3
  - 验证：两次批准同模块、不同模块互不影响、与 0.6.0 的重交审作废交替重放，队列里每模块至多一个
  - 文件：`module_crew/merge.py`、`module_crew/__main__.py`、`tests/test_stage_c.py`
- [ ] Task 3：MC-13——模块 worktree 放行 `Edit(//<wt>/**)`、禁止 `Edit(//<wt>/.claude/**)`；集成 checkout 不加；`remove` 能撤；`start prepare` 跟随
  - 验收：Spec 验收 4
  - 文件：`module_crew/permissions.py`、`tests/test_permissions.py`

### Checkpoint 1（report）：三处修复就位，全量测试通过，记入 todo 后继续

### Phase 2：模块字段与规则

- [ ] Task 4：MC-9——解析器升到 v2.4（「模块」字段、`module` 键、钉 v2.4 样例、三套一致性测试）；`--protocol` 加 2.4；for-hub 每条紧跟「要点」写「模块」；回归夹具更新
  - 验收：Spec 验收 7
  - 文件：`module_crew/protocol.py`、`module_crew/sources.py`、`module_crew/review.py`、`interface.json`、样例与相关测试
- [ ] Task 5：crew-coordinator skill 写 MC-12「先查后问」三步、MC-14「提请批准只发 for-hub 正文」、手写请示填「模块」；两份 crew-dev skill 写手写请示填「模块」
  - 验收：Spec 验收 6、7（skill 部分）
  - 文件：三份 skill、`tests/test_skills.py`
- [ ] Task 6：README 写 0.8.0 的变化；版本 0.8.0；全量测试与旧称扫描
  - 验收：Spec 验收 8

### Checkpoint 2（gate）：实地验证前停下问你

  - 要做的事：在 scratchpad 里复制 crew-rehearsal 的临时副本，用 0.8.0 `permissions apply`，开默认权限模式的模块会话，让它在 worktree 内 Write、Edit 各一次，再试一次编辑 `.claude/settings.local.json`。
  - 为什么停：要新开会话、往临时副本写权限文件。

- [ ] Task 7：实地验证（Spec 验收 5），结果写进 todo；做不了记「宿主未验证」并写明原因

### Checkpoint 3（gate）：最终验收

- [ ] 回告：逐项勾清单抄送接入协调（local_4f410de8），并告诉契约负责人（local_a9d06942）module-crew 已按 v2.4 写「模块」

## 风险

- 跳过同步通知后，被跳过的模块要等最终验收出结果才同步；被退回时退回通知本来就要求先同步，答 B 时靠 crew-dev skill。
- `Edit(//…/.claude/**)` 的禁止规则若宿主对设置文件另有保护，实地验证时以宿主实际行为为准，照实记录。
