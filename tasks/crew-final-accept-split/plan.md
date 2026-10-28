# Implementation Plan: crew-final-accept-split

<!-- spec-guard: review pending -->

> 依据：`spec/crew-final-accept-split.md`（用户 2026-10-28 批准，事项 C357，原话「C357 A；D1 A；D2 A」）。任务清单：`tasks/crew-final-accept-split/todo.md`。
> 待决已定：D1 A——决策收件箱的最终验收卡片加选项「C：只接受验收，暂不授权合并」；D2 A——已接受验收、没授权合并的模块不能 `merge cleanup`（退出码 3）。

## Overview

先做命令层：`merge accept` 与新状态 `accepted`，再让 `merge approve` 收它，然后把 `accepted` 接进各处读取（批量、同步、阶段、状态、停滞、取代、退回、收回），
接着改两条提示与决策收件箱卡片，最后改四份技能和两份文档，跑全量测试。
每个任务先写失败的测试、看到红再实现到绿，单独在模块分支本地提交；不推送、不发版；合入集成分支用 `module-crew sync`。
没有轻任务在改这些文件（T337～T339 均已合入），收到开工类【协调通知】后直接开工。

## Architecture Decisions

- **记录（Spec 接口约定）**：交审事项（`kind: review`，`node: final`）`state` 多一个取值 `accepted`，加字段
  `acceptance = {original, answeredAt, **source_field, body}`，事件 `accepted`。合并批准事项加 `acceptedBy`（接受时的 `answeredAt` 与 `body`；一次批准的为 `None`）。
  状态库若对 `state` 取值有校验，补上 `accepted`。
- **`merge.accept` / `accept_many`（决策 1、2）**：与 `approve_many` 同构，一个事务里逐个 `_accept_one`，任一拒绝整批不写。
  `_accept_one` 的拒绝：没有该交审事项、不是最终验收、`state` 不是 `open`（`accepted` 写「已接受验收，补授权合并用 merge approve」）。
  正文用 `_reply_text` 生成【用户答复】（原话照录）。CLI 的待决问题核对复用 `review.split_decisions`：`back` 走 `review.answer`，`hold` 保持未答，`missing` 退出码 3，只有 `approve` 那一组进 `accept_many`；之后照 `merge.closing_all` 发等待记录的【已恢复】。
- **`merge approve` 收 `accepted`（决策 3）**：`_approve_one` 的状态检查放宽为 `open` 或 `accepted`；`accepted` 时写 `acceptedBy`，交审事项关成 `answered`，`answer` 里加 `acceptance`（保留接受时那段）。
  CLI 层：`split_decisions` 只看 `review batch` 里的 `open` 事项，`accepted` 的编号落在 `approve` 组里，不会再被问待决问题——不用改 `split_decisions`。
- **各处读取（决策 4、5）**：
  - `review.batch` 只取 `open`：不改，`accepted` 自然不列（加测试锁住）。
  - `merge.awaiting_final` 取 `open` 或 `accepted` → `no_sync` 随之不给它发同步。
  - `review.add`：取代旧事项的条件从 `state == "open"` 改为 `open` 或 `accepted`。
  - `review.answer`：收 `accepted`（关成 `answered`，照今天退回）。
  - `hooks`：新 `STAGE_ACCEPTED = "最终验收已接受（交审事项 C{n}），用户暂未授权合并：停在当前停点，不要再提交，等授权合并或退回"`，判断放在 `STAGE_WAIT_FINAL` 之前。
  - `failure.stage_code`：`STAGE_ACCEPTED` 与 `STAGE_WAIT_FINAL` 同值（今天落在 `build`），不加枚举值。
  - `status`：在用模块那一行后加「已接受验收、待授权合并（C<号>，接受于 <时间>）」。
  - `stall`：`asks` 与 `answers` 把 `acceptance.answeredAt` 算作用户已答复。
  - `merge._cleanup`（D2 A）：模块有 `accepted` 的最终验收时退出码 3，「已接受验收、待授权合并（C<号>）：收回后合并要重新开会话，等授权合并、合入后再收」。
- **提示文字（决策 7）**：`review._approve` 对最终验收的拒绝改为点名 `merge approve`／`merge accept`／`review answer`；CLI 的 `review answer` 对最终验收多打一行提示（Spec 原文）。
- **卡片（决策 8，D1 A）**：`_hub_item` 在 `part` 含最终验收时，选项列表在 B 之后加
  「C：只接受验收，暂不授权合并」「  选了会怎样：记下验收结论，不合并、集成分支不变；之后你说一句授权合并就排进合并队列」；「你该回」不变。生成后照旧过 `protocol.parse`。
- **技能与文档（决策 9）**：四份技能按 Spec 决策 9 改；Claude 与 Codex 两版内容对应、只差宿主写法。`docs/commands.md` 的 `merge` 一节加 `merge accept`，`review answer` 一行改「要求修改（退回）」；
  `docs/guide.md` 完整流程最终验收一步与「出状况」各加一条。断言写进 `tests/test_final_accept.py`。

## 影响面

新增：`tests/test_final_accept.py`。
修改：`module_crew/merge.py`、`review.py`、`hooks.py`、`failure.py`、`stall.py`、`__main__.py`（视状态库校验另改 `store.py`）、
`skills/crew-coordinator/SKILL.md`、`codex-skills/crew-coordinator/SKILL.md`、`skills/crew-dev/SKILL.md`、`codex-skills/crew-dev/SKILL.md`、`docs/commands.md`、`docs/guide.md`。
现有测试里断言旧文字（`review approve` 的拒绝原文、技能里的旧说法）的照实改，最终验收逐条列出。
用 `tests/helpers.py` 现有夹具，预计不改公共文件；真要改先发【公共变更请求】。不新增依赖；不改契约、`interface.json`、版本号、CHANGELOG。

## Task List

- [ ] Task 1：`merge accept` 命令与 `accepted` 状态——成功、拒绝、多编号整批不写、待决问题核对、【用户答复】与【已恢复】（Spec AC1、AC3）
- [ ] Task 2：`merge approve` 收 `accepted`——`acceptedBy`、两段原话、不再问待决问题、`merge run` 照常合入（Spec AC2）

### Checkpoint 1（report）：两步批准能走通，相关测试与已有 merge、review 测试通过，记入 todo 后继续

- [ ] Task 3：各处读取——批量与 for-hub 不列、不收同步、重交审取代、`review answer` 收 `accepted`（Spec AC4、AC5）
- [ ] Task 4：阶段、状态、停滞——钩子新阶段、`sessions --json` 同值、`status` 一行、停滞不报等用户（Spec AC6）
- [ ] Task 5：`merge cleanup` 拒收已接受验收的模块（Spec AC9，D2 A）
- [ ] Task 6：提示与卡片——`review approve`／`review answer` 新提示、最终验收卡片选项 C 且过 `protocol check`、Spec／Plan 卡片不变（Spec AC7、AC8，D1 A）

### Checkpoint 2（report）：命令层做完，全量测试通过，记入 todo 后继续

- [ ] Task 7：四份技能与两份文档改写（Spec AC10、AC11）
- [ ] Task 8：`module-crew sync` 后全量测试（Spec AC12）

### Checkpoint 3（gate）：最终验收

- [ ] 回告：ecosystem-lead（S48 的 module-crew 一侧已就位：`merge accept` 与补授权合并；新版发出后转告 livesaas-fe-coord），经 mc-coord 转

## 风险与对策

| 风险 | 影响 | 对策 |
|---|---|---|
| 有别处用 `state == "open"` 判最终验收，漏接 `accepted` | 已接受的模块被当成没交审（如收到同步、被提请批准） | 开工时 `grep` 所有读 `kind == "review"` 且看 `state` 的地方逐个过；Task 3 测试覆盖同步与批量；新发现即补并记入 todo |
| 用 `state != "closed"` 计数的地方把 `accepted` 算成未关事项 | `status` 的「未关事项」多 1 | 这是 Spec 要的（事项不关闭），加测试锁住 |
| 决策收件箱读不懂选项 C | 用户选 C 后转回的原话照样是「C」 | 原话照转，模块协调按技能用 `merge accept`；卡片仍过 `protocol.parse` |
| 现有测试断言旧提示原文 | 改提示后旧测试红 | 照实改断言，最终验收列出改了哪些测试 |

## 变更记录
