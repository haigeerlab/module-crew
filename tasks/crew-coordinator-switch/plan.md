# Implementation Plan: crew-coordinator-switch

<!-- spec-guard: review approved -->

> 依据：`spec/crew-coordinator-switch.md`（用户 2026-10-22 批准）。任务清单：`tasks/crew-coordinator-switch/todo.md`。

## Overview

先告诉总协调要改钩子与绑定（只在本地 `main`，不发版、不升级本机，短验证不受影响），再按「体检 → 升级与关闭 → 钩子安静与提醒 → 清空交接 → status → 文档」的顺序做。
每个任务先写失败的测试，再实现到全绿，单独在 `main` 本地提交，不推送。

## Architecture Decisions

- **体检**：`probe` 新增检查项 `spec-guard-enabled`（项目根 `.agent/config.json` 存在）。`spec-guard` 检查项另带一个机器可读的原因码 `no-capability-map`（`/map` 退出码 3），
  供 `coordinator up` 判断「只因没有能力图」；`status` 的显示与退出码规则不变（新项也算 blocker）。
- **升级与关闭**：新文件 `module_crew/coordinator.py`，`up(project, short, original)` 与 `down(project, original)` 返回 `(code, lines)`。
  `up` 的配置写法复用 `start._settings`（简称校验、集成分支、`crewDir`），`maxModules` 用 `DEFAULT_MAX`（改为 2）；登记沿用 `start.prepare` 里的会话记录形状，绑定写 `hostSession` 并在事件里带原话。
  `down` 把协调登记记为 `retired`（`SESSION_STATUSES` 已有）并去掉 `hostSession`。`start.prepare` 已有「有在用协调就不再登记」，不改逻辑，只补测试。
- **状态库**：`KINDS` 加 `sighting`、`handover`；`store.transaction(actor, wait=None)` 加可选等锁上限（`LOCK_NB` 轮询，到时抛 `StoreBusy`），只有钩子传 `wait=2`，其余调用行为不变。
- **钩子分流**：新增 `hooks.active_coordinator(db)`（`status: active` 的协调登记与其集成 checkout）。没有它 → 任何会话、任何事件都输出空。有它但还没绑定（接管后、bind 前）→ 集成 checkout 里的陌生会话照旧得到现在的 bind 提示，不写 `sighting`、不发提醒（Spec 决策 5 只对已绑定的协调会话）。
  陌生会话：模块 worktree 里沿用现在的 dev 提示；其余目录（集成 checkout、仓库别处）在 `SessionStart` 写 `sighting`，第一次写入才注入提醒（Spec 决策 6 原文），集成 checkout 里另带接管办法。
  协调会话的 `UserPromptSubmit`：有 `told: false` 的 `sighting` 就加一句并把它们改成 `told: true`。所有写入包在 `try` 里，`StoreBusy`／`OSError` 一律安静。
- **清空交接**：`hooks.json` 加 `SessionEnd` → `module-crew hook session-end`。已绑定会话 `reason == "clear"` → 写 `handover`（登记名、旧编号、`cwd`、时间）。
  `SessionStart` 且 `source == "clear"`：找同 `cwd`、30 秒内、未关闭的 `handover`，改绑定为新编号（事件 `rebound-after-clear`），关闭交接记录，再按角色注入并加「刚清空过」一句。超过 5 分钟的交接记录在下次读时记为作废。
  判断时间用 `store.now()` 与记录里的时间比较；测试里通过参数注入「现在」。
- **status**：`probe` 的汇总多「协调会话」与「没登记的会话」两段，`--json` 同名两个字段。

## 影响面

新增：`module_crew/coordinator.py`、`tests/test_coordinator_switch.py`。
修改：`module_crew/probe.py`、`module_crew/store.py`、`module_crew/hooks.py`、`module_crew/start.py`（`DEFAULT_MAX`）、`module_crew/__main__.py`（`coordinator up/down`、`hook session-end`）、`hooks/hooks.json`、
`skills/crew-coordinator/SKILL.md`、`README.md`、`CHANGELOG.md`、`.claude-plugin/plugin.json`（版本 0.10.0）；断言旧陌生提示文案、`DEFAULT_MAX`、检查项清单的旧测试按新行为改。
不新增依赖，不改契约与 `interface.json`，不涉及界面。

## Task List

- [ ] Task 0：告诉总协调——本模块要改钩子（新增 SessionEnd、钩子开始少量写状态库）与绑定（清空后自动转绑），只在本地 `main` 提交，不打标签、不升级本机，短验证不受影响；发版前再告诉一次
- [ ] Task 1：体检新增 `spec-guard-enabled`；`spec-guard` 项带 `no-capability-map` 原因码
  - 验收：Spec 验收 2（缺 `.agent/config.json`）
  - 文件：`module_crew/probe.py`、`tests/test_coordinator_switch.py`、受影响的 probe 测试
- [ ] Task 2：`coordinator up`／`down`、`DEFAULT_MAX` 改 2、`start prepare` 衔接
  - 验收：Spec 验收 1、2、3、4、10
  - 文件：`module_crew/coordinator.py`、`module_crew/start.py`、`module_crew/__main__.py`、测试
- [ ] Task 3：钩子安静与一次性提醒——`active_coordinator`、`sighting` 写入与等锁上限、陌生提示新文案、协调会话的告知
  - 验收：Spec 验收 5、6、7、9
  - 文件：`module_crew/hooks.py`、`module_crew/store.py`、`tests/test_coordinator_switch.py`、`tests/test_hooks.py`、`tests/test_routing.py`

### Checkpoint 1（report）：开关与提醒就位，全量测试通过，记入 todo 后继续

- [ ] Task 4：`SessionEnd` 钩子与清空交接（协调与模块会话），按实测的事件顺序喂载荷
  - 验收：Spec 验收 8、9
  - 文件：`hooks/hooks.json`、`module_crew/hooks.py`、`module_crew/__main__.py`、测试
- [ ] Task 5：`status` 两个新段（文字与 `--json`）
  - 验收：Spec 验收 11
  - 文件：`module_crew/probe.py`、测试
- [ ] Task 6：`crew-coordinator` skill 的触发说明与升级提示、README「开始使用」、CHANGELOG 第六版、版本 0.10.0、全量测试与旧称扫描
  - 验收：Spec 验收 12
  - 文件：`skills/crew-coordinator/SKILL.md`、`README.md`、`CHANGELOG.md`、`.claude-plugin/plugin.json`、`tests/test_skills.py`

### Checkpoint 2（gate）：实地验证前停下问你

  - 要做的事：在桌面版里对一个装了本地 0.10.0 的临时协调会话做一次 `/clear`，看身份是否接上（Spec 验收 13）。
  - 为什么停：要在桌面版开一个测试会话并清空它，需要你同意；做不了就记「未实测」与原因。

- [ ] Task 7：实地 `/clear` 验证，结果写进 todo

### Checkpoint 3（gate）：最终验收

- [ ] 回告：完成情况发给总协调（local_d7434023）

## Risks

| 风险 | 影响 | 缓解 |
|---|---|---|
| 钩子写状态库时锁冲突 | 钩子变慢或卡住对话 | 只钩子用 2 秒等锁上限，超时安静；测试占住锁验证 |
| 清空交接误认别的会话 | 身份被别的会话拿走 | 只认同 `cwd`、30 秒内、`source: clear` 的相邻事件；其余一律不交接 |
| 改了陌生提示文案，旧测试与演练脚本依赖旧文案 | 测试红、演练执行看不懂 | 旧测试按新文案改；模块 worktree 的提示保持原文 |
| 桌面版清空的事件顺序与命令行版不同 | 交接不生效 | Checkpoint 2 实地验证；不生效就退回手动 bind（现状） |
