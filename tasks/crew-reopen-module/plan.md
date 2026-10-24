# Implementation Plan: crew-reopen-module

<!-- spec-guard: review approved -->

> 依据：`spec/crew-reopen-module.md`（用户 2026-10-24 批准，事项 C68，「C68 A；Q1 接受；Q2 点名即开工」）。任务清单：`tasks/crew-reopen-module/todo.md`。
> 未决问题已定：Q1 接受假设 2 的判据（看 `progress`、`firstTickAt`，不看 `review`）；Q2 Spec、Plan 都还是 `approved` 时点名重开即开工，不等开工通知。

## Overview

先在状态库加 `reopen` 字段与「本轮起算号」，再做 `start prepare` 的重开：判据与分支校验 → 落地（快进、worktree、`-r<轮次>` 登记）→ 开工说明「重开修订」一段 → `start plan` 的原因。
然后让按模块查历史的地方只看本轮，用一个端到端测试把重开 → 交审 → 合并 → 收回走一遍，最后写 skill、README，跑全量测试。
每个任务先写失败的测试、看到红再实现到绿，单独在模块分支本地提交，不推送、不发版；合入集成分支用 `module-crew sync`。

**开工时机**：`start.py`（T62）、`merge.py`／`review.py`（T60）、`README.md`（T55、T61）正被轻任务改。构建等这四个都合进 main、收到开工类【协调通知】后才开始，
开工第一步 `module-crew sync`，之后在新 main 上改；下面「影响面」里写的函数名以合入后的代码为准，名字变了按新代码找对应位置，不改做法。

## Architecture Decisions

- **本轮起算号（Spec 决策 3、4）**：`store` 加 `round_since(sessions, module) -> int`：该模块在用 `dev` 登记有 `reopen` 时返回 `reopen.since`，否则 `0`。
  各处「按模块查事项」的过滤加一个条件 `int(key) > since`；`since == 0` 时条件恒真，没重开过的模块行为逐字不变（已有测试作回归）。
  `store` 的会话校验认 `reopen`：`round` 为 ≥2 的整数、`since` 为 ≥1 的整数、`review` 为含 `spec`、`plan` 两个字符串的对象；`item` 的 `reopened` 为字符串列表。
- **可重开判据（决策 1，Q1）**：`start._reopenable(map_module, db) -> str | None`：返回「差哪一条」的原因，满足时返回 `None`。
  `validate` 对不在 `startable.modules` 的模块调它：满足则记入 `reopen` 清单，否则拒绝原因写「不在可开工列表，也不能按重开处理：<差哪一条>」。
  旧一轮 `dev` 会话仍在用 → 「旧会话 <邮箱名> 还在用，先 merge cleanup <id>」。
- **分支校验与落地（决策 2）**：校验阶段对重开的模块判定 `created`／`fast-forward`／拒绝：
  没有 `refs/heads/<id>` → `created`；`merge-base --is-ancestor <id> <集成分支>` 成立 → `fast-forward`；不成立 → 拒绝并用 `rev-list --count <集成分支>..<id>` 写多出的提交数；
  `worktree list --porcelain` 里该分支已被检出 → 拒绝。落地时 `fast-forward` 先 `git branch -f <id> <集成分支>` 再 `git worktree add <路径> <id>`，`created` 与新模块同一条命令。
  `branch -f` 失败按中途失败（退出码 4）处理，与 `worktree add` 失败同一出口。
- **登记与轮次（决策 3，假设 6）**：轮次 = 状态库里 `role == "dev"` 且 `module == id` 的登记条数（含退役）+ 1，最小 2；邮箱名 `<简称>-<id>-r<轮次>`。
  `reopen = {"round", "since": <开工批准事项号>, "review": {"spec", "plan"}}`，`review` 取校验时 `/map` 的值。开工批准事项加 `reopened`（只有重开的模块时才写这个键）。
- **开工说明（决策 5，Q2）**：`render_kickoff` 加可选参数 `reopen: dict | None`；为 `None` 时输出逐字不变。有值时在「这一步只做」前插「重开修订」一段，并按 `review` 选三种写法之一；
  两项都 `approved` 时「这一步只做」换成「先 module-crew sync…不用等开工通知」，且不输出「收到开工类【协调通知】之前不要开始构建」一行。Codex 宿主的附加段照旧拼在后面。
- **`start plan` 的原因（决策 6）**：`_why_not` 在 `status == "in_progress"` 分支先套 `_reopenable`，满足时写「已重开（第 <轮次> 轮待开），要用户点名：start prepare <id>」。
- **只看本轮（决策 4）**：改动点（以合入 T60、T62 后的代码为准）：
  - `start`：`_merged_modules`／`_counted_devs`／`_why_not` 的「已合入」只算本轮之后的合并批准；
  - `hooks._stage`：交审、批准、合并批准都只算本轮之后；`reopen.review` 两项 `approved` 时把 `spec`、`plan` 视为已批（阶段从构建起算）；
  - `merge`：`no_sync`、`_cleanup`（已合入判定）、补勾最终验收（取最近一次 merged）只算本轮；
  - `review`：`_approved_nodes`、`_rounds`、`_previous_commit`／`_last_changes` 按模块查的部分只算本轮；
  - `stall`：退回计数只算本轮。
  每处只加过滤条件，不改结构；测出别的按模块查的地方被旧记录误判，同样处理并在 todo 里记下。

## 影响面

新增：`tests/test_reopen_module.py`。
修改：`module_crew/store.py`、`start.py`、`hooks.py`、`merge.py`、`review.py`、`stall.py`、`skills/crew-coordinator/SKILL.md`、`codex-skills/crew-coordinator/SKILL.md`、`skills/crew-dev/SKILL.md`、`README.md`。
skill 的断言写在 `tests/test_reopen_module.py` 里（不改 `tests/test_skills.py`，守住并行边界）。用 `tests/helpers.py` 现有的 `set_map` 等夹具造 `/map`，预计不改公共文件；真要改先发【公共变更请求】。
不新增依赖；不改契约、`interface.json`、版本号。

## Task List

- [ ] Task 1：状态库认 `reopen` 与 `reopened`，加 `round_since`（Spec 接口约定·状态库）
- [ ] Task 2：`prepare` 校验——可重开判据、旧会话未收回、旧分支非祖先或已检出时退出码 3 且什么都不写（Spec 验收 2 拒绝部分、3）
- [ ] Task 3：`prepare` 落地——快进或新切、worktree、`-r<轮次>` 登记、开工批准事项 `reopened`、输出与 `--json`；与新模块同次开时新模块逐字不变（Spec 验收 1、2 新切部分、4、8）
- [ ] Task 4：开工说明「重开修订」一段与三种 `review` 写法（Spec 验收 5）
- [ ] Task 5：`start plan` 不提议、原因写「已重开…要用户点名」（Spec 验收 7）

### Checkpoint 1（report）：重开能开出来，开工说明与 plan 输出对，相关测试与已有 start 测试通过，记入 todo 后继续

- [ ] Task 6：只看本轮——`start` 名额与已合入、`hooks` 阶段、`merge` 的 `no_sync`／`cleanup`／补勾、`review` 已批节点与轮次、`stall` 退回计数（Spec 验收 6 单元部分）
- [ ] Task 7：端到端——重开 → 新会话 bind → 阶段 → 最终验收交审 → 批准 → `merge run` → `merge cleanup` 退役 `-r2`，每步不被旧一轮记录误判（Spec 验收 6）

### Checkpoint 2（report）：命令层做完，全量测试通过，记入 todo 后继续

- [ ] Task 8：skill 与 README——`crew-coordinator` 两份「开工」一节加重开做法、`crew-dev` 加「重开修订只做新加的未勾项」、README 加「修订已完成的模块」（Spec 验收 9）
- [ ] Task 9：同步集成分支（`module-crew sync`）后全量测试（Spec 验收 10）

### Checkpoint 3（gate）：最终验收

- [ ] 回告：ecosystem-lead（S18 的 module-crew 一侧已就位：`start prepare` 点名重开），经 mc-coord 转

## 风险与对策

| 风险 | 影响 | 对策 |
|---|---|---|
| T60、T62 合入后函数结构变了 | 决策 4 的改动点对不上 | 开工先 sync，按新代码找对应位置；只加过滤条件，不改结构 |
| 漏掉某个按模块查的地方 | 重开模块在某一步被当成已合入 | Task 7 端到端逐步断言；发现即补并记入 todo |
| `git branch -f` 被权限规则拦 | 快进做不了 | 发【等待用户】去会话操作；不改用别的写法绕过 |
| `/map` 实际字段与夹具不符（`progress`、`firstTickAt`） | 判据在真实项目里不成立 | 写 Spec 时已用真实 `/map --json` 核对过这几个字段；最终验收前再用真实 spec-guard 跑一次 `start plan` 看原因行 |

## 变更记录
