# Implementation Plan: crew-live-rehost

<!-- spec-guard: review pending -->

> 依据：`spec/crew-live-rehost.md`（用户 2026-10-30 批准，事项 C412／C413，原话「批准，未决都选 A」）。任务清单：`tasks/crew-live-rehost/todo.md`。
> 未决问题的选择：Q1 A（没人 bind 前可撤回）、Q2 A（原话关键词「已停／停了」）、Q3 A（「丢」的未提交改动用带标签的 stash 收起）——都与 Spec 正文的推荐值一致，Spec 不用改。

## Overview

先给状态库加 `rehost` 字段与 `previousSessions.reason` 的校验，再做只读的挡住清单与确认码（`coordinator rehost --check`），然后做 `--to claude` 本身（守门窄口、一个事务改登记、权限跟随、恢复说明、迁移说明）。
接着做旧会话失效（模块侧写命令认出被迁走的旧会话）、盘点闸（钩子档位、`rehost show`、`rehost release`、最终验收交审拦截）、撤回与钩子提示，最后改文档、同步后跑全量测试。
每个任务先写失败的测试、看到红再实现到绿，单独在模块分支本地提交，不推送、不发版；合入集成分支用 `module-crew sync`。

## Architecture Decisions

- **新文件 `module_crew/rehost.py`**（沿用 `handover.py` 的结构与 `Check` 数据类）：
  - `readiness(db, project, cwd, caller) -> list[Check]`：Spec 关键决策 1 的七项（`coordinator-host`、`all-codex`、`merge`、`offload`、`spec-guard`、`caller`、`cwd`）。
    `merge` 用 `mergelock.read`；`offload` 读 `offload` 记录的 `state`；`spec-guard` 用 `probe.find_plugin("spec-guard", project)`；`caller` 用 `hooks.registration_of`；`cwd` 用真实路径比较集成 checkout（`probe._checkout_of`）。
  - `snapshot(rec) -> {head, dirty}`：worktree 的 `git rev-parse HEAD` 与 `git status --porcelain=v1 -uall`（带超时、不经 shell），dirty 原样保存全部行，输出时最多列 50 行。
  - `confirm_code(db, sessions, snapshots, lock, offloads) -> str`：对规范化 JSON 取 sha256，转成 6 位大写字母数字（去掉易混的 0/O/1/I）。只读、不存。
  - `rehost(project, original, code, session_id, cwd) -> (code, lines)`：前置全过才在一个事务里改所有登记（关键决策 4 ②），随后 `permissions.follow` 逐个 checkout、生成恢复说明与迁移说明。
  - `undo(project, original, session_id)`、`show(db, name=None)`、`release(db, name, original)`。
  - 原话核对：非空、含确认码、含「已停」或「停了」（Q2 A）。
- **store**：`_validate_session` 加可选 `rehost`：`from` 为 `codex-desktop`、`at` 字符串、`original` 非空、`batch` 正整数；dev／task 另要 `snapshot{head, dirty: list}` 与 `inventory` 取 `pending`／`released`。
  `previousSessions` 项可带 `reason`（字符串）。模块协调的 `hostHandover` 改写为 `{from: codex-desktop, to: claude-desktop, …, pending: false}`，现有校验照旧通过。迁移号用 `tx.allocate_number()`。
- **守门（`__main__._session_guard`）**：
  - `("coordinator", "rehost")` 带 `--check` 走只读豁免；带 `--to` 时跳过通用守门，改由 `rehost.may_start(...)` 核对关键决策 2 的四条，不满足退出码 7；`--undo` 照常受守门（要绑定的模块协调）。
  - 新增「被迁走的旧会话」拒绝：调用者编号出现在任一登记的 `previousSessions` 且 `reason == "rehost"` 时，`_ANY_SESSION` 里的写命令（`sync`、`check quick`、`offload start|settle|resume|takeover`、`bind`）退出码 7；只读命令不受影响。放在通用豁免之前判断。
  - `("rehost", "show")` 只读，任何会话可跑；`("rehost", "release")` 是模块协调的写命令，照常受守门。
- **恢复说明（`failure.py`）**：`resume_kit(db, module, extra=None)` 加可选附加段；新增 `task_kit(db, number, extra)` 给轻任务会话（结构同 `resume_kit`，取任务单位置）。迁移附加段由 `rehost.kit_lines(name, rec)` 生成，内容见 Spec 关键决策 9；登记已改为 Claude，所以自然不带 Codex 段。
- **迁移说明**：`rehost.guide(...)` 复用 `handover._step` 的三项格式，存到 `<状态库目录>/rehost-guide/<时间>.md`，原话另存 `<时间>-original.txt`（供新会话 `bridge_register`／`bind` 引用）。
- **盘点闸**：
  - `hooks._stage` 之前判断：会话登记 `rehost.inventory == "pending"` 时档位为「迁来待盘点：……」（模块会话与轻任务会话都加；轻任务走 `_task_stage` 前同样判断）；
  - `review.add`：最终验收节点、该模块（或轻任务）的会话 `rehost.inventory == "pending"` 时退出码 3，说法「迁来的会话还没盘点完（rehost release 之后才收最终验收）」；Spec、Plan 交审不拦；
  - `probe.summarize_store` 的 `store` 加 `rehostPending`，`status` 文字多一行「迁来待盘点：<邮箱名>…」。
- **钩子陌生会话提示**：`hooks.stranger_line` 对集成 checkout、模块协调登记为 `codex-desktop`、本会话是 Claude（钩子负载里有 `session_id`、环境变量有 `CLAUDE_CODE_SESSION_ID`）时，改为提示「模块协调登记在 Codex；要把这一批迁到 Claude，请用户在本会话明说后先运行 module-crew coordinator rehost --check」。只读，不加子进程。

## 影响面

新增：`module_crew/rehost.py`、`tests/test_live_rehost.py`。
修改：`module_crew/store.py`、`__main__.py`、`hooks.py`、`failure.py`、`review.py`、`probe.py`、`permissions.py`（只在需要时给 `follow` 加按 worktree 循环的调用口，不改规则内容）、
`skills/crew-coordinator/SKILL.md`、`skills/crew-dev/SKILL.md`、`docs/guide.md`、`README.md`、`README.en.md`，以及按需调整断言的已有测试。
不新增依赖，不改契约、`interface.json`、版本号、CHANGELOG（随发版由模块协调写）；不改公共文件。

## Task List

- [ ] Task 1：store 校验 `rehost` 字段与 `previousSessions.reason`（Spec 验收 4 的状态库部分）——验证：新测试先红后绿；`test_store`、`test_host_handover`、`test_session_handover` 照常通过
- [ ] Task 2：`rehost.readiness`、快照与确认码，`coordinator rehost --check`（含 `--json`、只读豁免）（Spec 验收 1、2 的确认码部分）——验证：七项逐项不满足各报对应项、退出码 3、无确认码；状态不变码稳定，改文件、加提交、改绑定后码变
- [ ] Task 3：`coordinator rehost --to claude`：守门窄口、原话与确认码核对、一个事务改全部登记、调用者绑为模块协调、事件 `session.rehosted`（Spec 验收 2、3、4）——验证：Codex 会话／已绑会话／目录不对退出码 7；码不符／原话缺码／没说已停退出码 3 且状态库逐字不变；成功后登记、`previousSessions`、未结事项逐字不变；终端运行时协调不绑
- [ ] Task 4：权限跟随全部 checkout、恢复说明（模块会话与轻任务会话）、迁移说明（Spec 验收 5、6）——验证：已 apply 时 Claude 规则写上、Codex 规则文件逐字不变；没被忽略时照常完成并标出；没 apply 时提示；恢复说明含 `takeover:true, wake:"auto"`、`bind`、快照与盘点要求、不含 Codex 段；迁移说明每步三项并存进状态库目录

### Checkpoint 1（report）：迁移本身走通，`test_live_rehost` 与相关已有测试通过，记入 todo 后继续

- [ ] Task 5：旧会话失效：被迁走的旧会话编号跑模块侧写命令退出码 7（Spec 验收 7）——验证：旧编号跑 `sync`、`check quick`、`offload start`、`bind` 退出码 7，跑 `status`、`sessions` 照常；其他会话的守门结果与改前相同
- [ ] Task 6：盘点闸：钩子档位、`rehost show`、`rehost release`、`review add` 最终验收拦截、`status` 的待盘点（Spec 验收 8）——验证：钩子输出「迁来待盘点」；`show` 报出快照之后的新提交与新改动；未解除时最终验收交审退出码 3、Spec／Plan 交审不拦；`release` 后档位与交审恢复
- [ ] Task 7：`coordinator rehost --undo`（Spec 验收 9，Q1 A）——验证：没人 bind 时登记逐字恢复到迁移前；有一个 bind 后退出码 3、不写
- [ ] Task 8：钩子陌生 Claude 会话提示（Spec 验收 10）——验证：协调在 Codex 时提示 `rehost --check`；协调在 Claude 时输出与改前逐字相同；`hooks.py` 仍不 import `subprocess`

### Checkpoint 2（report）：命令层做完，全量测试通过，记入 todo 后继续

- [ ] Task 9：文档与技能：`docs/guide.md`「换宿主」补「批次内迁到 Claude」、README／README.en 功能清单与命令一览、crew-coordinator「接手 Codex 上没做完的一批」、crew-dev「迁来之后」（Spec 验收 11）——验证：文档断言测试先红后绿；`test_docs`、`test_skills`、`test_readme_hosts` 照常通过
- [ ] Task 10：`module-crew sync` 后全量测试（Spec 验收 12 的测试部分）——验证：`python3 -m unittest discover -s tests` 全部通过

### Checkpoint 3（gate）：实地演练要不要现在做

- 停下发【等待用户】「类型：中途检查点」：问用户是否同意在 crew-rehearsal 演练一次 Codex→Claude 批次内迁移（要用户在 Codex 里开协调与模块会话、亲手停下归档）；
  同意就按用户给的安排做并把结果写进最终验收；不同意就在最终验收里写「宿主未实测」与原因。

### Checkpoint 4（gate）：最终验收

- [ ] 回告：发版后告诉 mc-coord（转用户）LIVE-SAAS 可以按迁移说明迁（随最终验收列出）

## 风险与对策

- **守门改动波及面大**：`_session_guard` 是所有命令的入口。对策：新判断只在「调用者编号在 `previousSessions` 且 `reason == rehost`」或「`coordinator rehost --to`」时生效，其余路径不动；Task 5 跑 `test_session_handover`、`test_coordinator_switch`、`test_routing` 回归。
- **确认码不稳定**：`git status` 顺序、时间戳会让码抖动。对策：只取排序后的文件行与 HEAD，不放时间；测试里连续两次 `--check` 断言相同。
- **一次事务写多条登记**：任一校验失败整个事务回滚。对策：先在内存里组好所有新登记并逐条过 `_validate_session`，再进事务；测试覆盖中途失败时状态库逐字不变。
- **旧 Codex 会话在迁移后还在改 worktree**：module-crew 拦不住。对策：快照与 `rehost show` 对比，恢复说明与 crew-dev 写明对不上就停下报告。
- **轻任务恢复说明此前没有**：`resume_kit` 只服务模块会话。对策：新增 `task_kit`，结构与 `resume_kit` 一致，单独测试。

## 中途会停下来问你的地方

- Checkpoint 1、2（report）：记入 todo 后继续，不停。
- Checkpoint 3（gate）：实地演练做不做，要用户决定（要用户在 Codex 里亲手操作）。
- Checkpoint 4（gate）：最终验收。
- 另外遇到 crew-dev 的三种必停情况（测试改不红、Spec 没覆盖的决策、高风险不可逆改动）照停。

## 未决问题

- 无（Spec 的三个未决问题用户已选 A）。
