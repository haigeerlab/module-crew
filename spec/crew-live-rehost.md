# Spec: crew-live-rehost

<!-- spec-guard: review approved dea5825450a2 -->

> 能力图模块 `crew-live-rehost`（第十版）。需求来源：接缝 S55，用户在 mc-coord 会话确认需求七条，批准开会话（批准事项 C410）。
> 依赖 `crew-host-handover`（空档换宿主、`hostHandover`、`bind --takeover` 认宿主、交接说明）、`crew-recovery-hooks`（钩子按角色注入、`takeover` 记同意）、
> `crew-host-permissions`（按宿主写规则、只追加、`follow`）；另用到 `crew-session-handover`（写命令会话守门、`previousSessions`）、
> `crew-failure`（`resume_kit` 恢复说明）、`crew-codex-offload`（外包状态）、`crew-background-checks`（合并锁）。
> 现状取自 0.21.0 源码（`handover.py`、`hooks.py`、`store.py`、`permissions.py`、`failure.py`、`offload.py`）。标「新」的是写 Spec 时补的实现取舍，请重点审。

## 目标

一批没做完、模块协调和模块会话都在 Codex 上时，用户能在 Claude Code 里把这一批整体接过来，不需要旧 Codex 模块协调配合：

- 用户在集成 checkout 新开一个 Claude 会话（尚未登记），说「把这批从 Codex 迁到 Claude」；
- 这个会话跑 `coordinator rehost --check` 给用户看要迁什么、哪些会挡住，用户凭确认码说一句原话，再跑 `coordinator rehost --to claude`；
- 一步改完：模块协调与所有在用会话登记为 Claude，旧会话失效，按 Claude 写权限规则，逐个生成恢复说明（未提交改动原样列出）；发起的会话成为模块协调；
- 新模块协调按恢复说明为每个模块会话、轻任务会话开 Claude 会话；每个迁来的会话第一步对照已批 Spec、Plan 盘点，经模块协调交用户，用户点头前不写代码。

第一个用户是 LIVE-SAAS 前端（Codex 上 1 个模块协调、4 个模块会话、2 个轻任务会话，未结公共变更请求 6 条、等待记录 18 条）。

## 范围

**范围内**

1. `coordinator rehost --check`（只读）：列出要迁的登记、挡住的条件、每个 worktree 的未提交改动，给出确认码。
2. `coordinator rehost --to claude --code <确认码> --original-file <原话文件>`：核对 → 改登记 → 旧会话失效 → 写 Claude 权限规则 → 生成恢复说明 → 输出迁移说明。
3. 写命令会话守门为 `rehost --to` 开一个窄口（关键决策 2），其余写命令守门不变。
4. 旧会话失效：旧 Codex 会话的会话编号移进 `previousSessions`；module-crew 的模块侧写命令认出被迁走的旧会话就拒绝（关键决策 5）。
5. 恢复说明（模块会话与轻任务会话各一份）：接管同一邮箱名、`bind`、迁移时的快照（HEAD、未提交改动）、盘点要求。
6. 盘点闸：迁来的会话在钩子里显示「迁来待盘点」；`rehost show` 对照快照与现在；用户点头后模块协调运行 `rehost release` 解除。
7. `coordinator rehost --undo`：迁来的会话一个都还没 `bind` 前，可凭原话撤回（关键决策 7）。
8. 钩子：集成 checkout 里的陌生 Claude 会话、模块协调登记在 Codex 时，提示可以 `rehost --check`。
9. 文档：`docs/guide.md`「换宿主」一节补「批次内迁到 Claude」；README／README.en 功能清单；crew-coordinator skill（Claude 版）加「接手 Codex 上没做完的一批」一节；crew-dev skill 加「迁来之后」一节。

**范围外**

- Claude→Codex 方向的批次内迁移；只迁部分会话（例如只迁模块协调）；Claude 协调与 Codex 模块混搭时只迁模块。
- 合并进行中、外包未结时的迁移（直接拒绝，不提供强制）。
- 替用户停掉、归档 Codex 里的旧会话（用户在 Codex 里亲手做）；替用户决定未提交改动的去留。
- 改 agent-relay、decision-inbox、spec-guard；改契约 session-protocol。
- 迁移后自动打开额度外包（迁来的模块照旧自己做完，不中途换，沿用 crew-dev「额度外包」一节）。

## 假设（请逐条确认）

1. **前提**：状态库里在用的模块协调登记为 `codex-desktop`（经 `coordinator handover --to codex` 换过去，所以带 `hostHandover`）；本批所有在用的模块会话、轻任务会话也登记为 `codex-desktop`（crew-host-handover 假设 7）。
   模块协调登记为 Claude 时 `rehost` 拒绝（那是空档 `handover` 或普通 `bind --takeover` 的事）。
2. **发起的会话**：用户在 Claude 桌面版新开的会话，工作目录是集成 checkout（不用 worktree），本会话还没有登记成任何会话。module-crew 从 `CLAUDE_CODE_SESSION_ID` 认出它是 Claude 会话。
   用户在终端直接运行（读不到会话编号）也放行，这时模块协调不绑会话，之后用 `bind --takeover` 绑。
3. **旧会话由用户在 Codex 里亲手停下并归档**，module-crew 判断不了 Codex 线程停没停（与 crew-host-handover 假设 4 同）；迁移说明第一步就是这件事，`--to` 前要用户在原话里说「已停」。
4. **未结事项按邮箱名记**：事项（C）、公共变更请求、等待记录（W）、交审、轻任务、决策收件箱的待决事项都挂在邮箱名上，邮箱名不变就原样有效，`rehost` 不改它们。
   agent-relay 里没读的消息也按邮箱名存着，新会话接管名字后照常读到。
5. **接管邮箱名要用户同意**：每个新 Claude 会话 `bridge_register {agent:<邮箱名>, takeover:true, wake:"auto"}`；这次 `rehost` 的原话就是用户对全部这些接管的同意（恢复说明写明）。
   agent-relay 对 Codex 持有者会提示「无法确认之前的 Codex 会话是否已停」，用户已在原话里确认停了就继续。
6. **权限规则只追加**：给集成 checkout 和每个模块 worktree 追加 Claude 规则，原有的 Codex 规则留着；写法、git 忽略要求沿用 crew-host-permissions。项目从没 `permissions apply` 过时不写，迁移说明提示可以凭原话 apply。
7. **本机 Claude Code 已装 module-crew、agent-relay、spec-guard**：固定入口读的就是 Claude 的插件安装记录（crew-codex-coordinator 假设 4），所以 module-crew 一定在；spec-guard 找不到时挡住（模块会话离不开它），agent-relay 由发起的会话自己调一次 `bridge_agents` 确认。
8. **盘点用现有消息**：迁来的会话把盘点结果作为【等待用户】「类型：中途检查点」发给模块协调（契约 v2.3 已有），不新增消息类型、不改契约。
9. 契约不改；验收以夹具测试为主；实地在 LIVE-SAAS 迁移前先在 crew-rehearsal 演练一次（经用户同意才开始）。

## 关键决策与取舍（请重点审）

1. **（新）挡住条件固定为一张清单**，`--check` 与 `--to` 用同一份，每项「满足／不满足＋原因」：
   - `coordinator-host`：在用的模块协调登记为 `codex-desktop`；
   - `all-codex`：在用的模块会话、轻任务会话都登记为 `codex-desktop`（有 Claude 的就列出，不迁混搭）；
   - `merge`：合并锁没被持有（`merge run --detach` 在 Codex 后台跑着也算持有）；
   - `offload`：没有处于 `running`／`needs-input`／`stopped`／`timeout` 的外包记录；
   - `spec-guard`：本机 Claude 能找到 spec-guard（沿用 offload／autonomy 定位 spec-guard 的做法）；
   - `caller`：调用者是 Claude 会话或终端，且没有绑到任何登记上（已是某个模块会话的会话不能发起）；
   - `cwd`：当前目录在集成 checkout 内（真实路径比较）。
   **不挡**：已批准未合并的事项、未结的事项／请求／等待记录、`queued`～`escalated` 的轻任务——它们按邮箱名原样迁过去（假设 4）。决策收件箱侧 module-crew 看不全，`--check` 照 handover 的写法提示一行。
2. **（新）守门只为 `rehost --to` 开一个窄口**：`_session_guard` 平时拒绝「有会话编号但不是绑定的模块协调」的调用（退出码 7）。`coordinator rehost --to` 改为自己核对：
   调用者是 Claude 会话（有 `CLAUDE_CODE_SESSION_ID`）且登记的模块协调在 Codex、调用者未绑定任何登记、当前目录在集成 checkout——全满足才放行，否则退出码 7、什么都不写。
   Codex 会话（只有 `CODEX_THREAD_ID`）一律拒绝（它若是旧协调，应当用旧协调自己的命令；若不是，就不该迁）。`--check` 只读，任何会话可跑。
3. **（新）原话怎么核实：确认码绑住预览的那一刻**。`--check` 按状态算一个 6 位确认码：对「模块协调与要迁的登记（名字、宿主、绑定的会话编号）、每个 worktree 的 HEAD 与未提交文件清单、合并锁、外包状态」取哈希。
   不写状态库（`--check` 保持只读）。`--to` 重新算一遍：`--code` 对不上 → 退出码 3「预览之后状态变了，请重新 --check 给用户看」；原话里不含这个确认码 → 退出码 3。
   这样挡住三种误用：别的会话转来的话（不含当前确认码）、会话自己拿旧预览开工（状态变了码就变）、没给用户看预览就执行。
   **局限照实写进 skill**：module-crew 分不清原话文件是用户打的还是会话写的，这一点和别的凭原话的命令一样；确认码只保证用户看过的就是要执行的。
   原话还必须写明旧会话已停（含「已停」或「停了」），否则退出码 3，提示先请用户在 Codex 里停下并归档 7 个旧会话。
4. **（新）`--to claude` 在一个事务里做完，任一前置失败什么都不写**：
   ① 核对：清单全满足、确认码与原话；
   ② 改登记：模块协调与每个在用的模块会话、轻任务会话 `host` 改为 `claude-desktop`；原 `hostSession` 移进 `previousSessions`（带 `reason: "rehost"`），`hostSession` 清掉；
     每条加 `rehost: {from: "codex-desktop", at, original, batch: <迁移号>, snapshot: {head, dirty: [...]}, inventory: "pending"}`（模块协调没有 `snapshot` 与 `inventory`）；
     模块协调的 `hostHandover` 换成 `{from: "codex-desktop", to: "claude-desktop", at, original, pending: false}`，store 校验照旧满足；
     调用者有会话编号时，同一事务把它绑成模块协调（事件 `session.rehosted` 带原话、旧会话编号、新会话编号）；
   ③ 写权限：已 apply 过时，对集成 checkout 和每个 worktree 走 `permissions.follow`，写失败不回滚登记，迁移说明里逐个标出；
   ④ 说明：每个模块会话、轻任务会话生成一份恢复说明（存为正文，给出编号），再生成一份迁移说明，打印并存到 `rehost-guide/<时间>.md`（状态库目录内，不进仓库）。
5. **（新）旧会话失效分三层，旧会话没停时各管一段**：
   - 模块协调的写命令：旧 Codex 协调的会话编号已不在 `hostSession`，守门照旧退出码 7；
   - 模块侧写命令（`sync`、`check quick`、`offload start|settle|resume|takeover`、`bind` 这些任何会话可跑的写命令）：调用者的会话编号出现在某条登记的 `previousSessions` 且 `reason` 为 `rehost` 时，退出码 7，说明「本会话已被迁到 Claude，停手」；只读命令照常；
   - git 提交与文件改动 module-crew 拦不住（Codex 没有钩子）：靠快照兜底——新会话第一步 `rehost show` 对照迁移时的 HEAD 与未提交文件，不一致就停下报给模块协调，按「旧会话没停」处理（由用户去 Codex 停掉它，再决定那些改动留不留）。
   agent-relay 侧：新会话接管名字后，旧 Codex 线程每轮重新注册（不带 takeover）会被拒，收不到新消息。
6. **（新）盘点闸**：
   - 钩子在迁来的模块会话、轻任务会话里，`rehost.inventory` 为 `pending` 时档位显示「迁来待盘点：先跑 rehost show、对照已批 Spec 与 Plan 盘点，经模块协调交用户；用户点头前不写代码」，排在其他档位前面；
   - `rehost show [<邮箱名>]`（只读）：快照与现在的 HEAD、未提交文件对比；该模块已批的 Spec、Plan 路径与批准标记；todo 勾到哪；快照以来的提交；
   - 盘点结果作为【等待用户】「类型：中途检查点」发给模块协调，要点写「做对的」「要返工的」「未提交改动：<文件> 留／丢」（每个文件一行）；
   - 用户答复到了，模块协调运行 `rehost release <邮箱名> --original-file <答复原话>`，`inventory` 改为 `released`，钩子恢复原档位；
   - 用户选「丢」的未提交改动：模块会话用 `git stash push -u -m "rehost-<邮箱名>"` 收起（找得回来），不删文件。
   module-crew 不阻止盘点期间写代码（拦不住编辑），靠钩子与 skill 约束；模块协调的 `review add` 对盘点未解除的模块拒绝记最终验收交审（退出码 3），防止跳过盘点直接收尾。
7. **（新）撤回只在没人接手前**：`coordinator rehost --undo --original-file` 只在这一批迁来的模块会话、轻任务会话还没有一个 `bind` 过时可用：
   登记恢复为 `codex-desktop`、`hostSession` 从 `previousSessions` 取回、去掉 `rehost` 字段与本次的 `hostHandover`；权限规则不撤（只追加）；恢复说明留着不删。
   有会话已经 `bind` 了就拒绝（退出码 3），因为它可能已经动了 worktree；那时要回 Codex 只能等将来的 Claude→Codex 批次内迁移（范围外）。
   另一个选择是完全不提供撤回，请用户定（未决问题 1）。
8. **迁移说明的步骤**（每步「去哪个会话／做什么／做完的样子」，沿用 handover 的写法）：
   ① Codex（ChatGPT 应用）：用户亲手停下并归档旧的模块协调与全部模块会话、轻任务会话（逐个列名字）——`--to` 之前已做，说明里复述以便核对；
   ② 本会话（新模块协调）：`bridge_register {agent:<协调邮箱名>, takeover:true, wake:"auto"}`、加载 crew-coordinator skill、跑 `status`；
   ③ 本会话：按 crew-coordinator 的开会话做法，为每个迁来的会话开一个 Claude 会话，工作目录选它原来的 worktree（不新建 worktree），首条消息贴它的恢复说明（给出正文编号与路径）；
   ④ 每个新会话：接管邮箱名、`bind`、`rehost show`、盘点、发【等待用户】；
   ⑤ 模块协调：把盘点逐个交用户（经决策收件箱，照常），收到答复后 `rehost release`；
   ⑥ 权限：哪些 checkout 写上了 Claude 规则，哪些没写上与原因；建议开会话后跑 `permissions verify` 实测。
9. **恢复说明**复用 `failure.resume_kit` 的骨架，迁移时另加：本次迁移的原话即接管同意；`bridge_register` 带 `takeover:true, wake:"auto"`；`bind <邮箱名>`；
   快照（HEAD 短号、未提交文件逐行，最多 50 行、多的写「另有 N 个」）；「第一步盘点，用户点头前不写代码」；轻任务会话额外写任务号与任务单位置。不再带 Codex 段。

## 接口约定

```bash
module-crew coordinator rehost --check [--json]                                                   # 只读：清单、要迁的登记、未提交改动、确认码
module-crew coordinator rehost --to claude --code <确认码> (--original <原话> | --original-file <文件>) [--json]
module-crew coordinator rehost --undo (--original <原话> | --original-file <文件>)
module-crew rehost show [<邮箱名>] [--json]                                                        # 只读：快照与现在对比、已批 Spec/Plan、todo 进度
module-crew rehost release <邮箱名> (--original <原话> | --original-file <文件>)                    # 模块协调：用户点头后解除盘点闸
```

- `rehost --check`：全满足 `0`，有不满足 `3`，不在 module-crew 仓库 `2`。`--json`：`{"ready", "code", "from": "codex-desktop", "to": "claude-desktop", "checks": [{"id","ok","reason"}], "sessions": [{"name","role","module","task","worktree","head","dirty"}]}`；不满足时 `code` 为 `null`。
- `rehost --to`：`0` 完成；`3` 清单不满足、确认码不符、原话为空或不含确认码或没说已停——都什么都不写；`7` 调用者不是可以发起的会话（关键决策 2）。
- `rehost --undo`：`0` 完成；`3` 没有可撤回的迁移、已有会话 bind、原话为空；`7` 不是登记的模块协调。
- `rehost release`：`0` 完成；`3` 该会话没有待盘点的迁移、原话为空；`7` 守门（沿用）。
- 状态库：会话登记加可选 `rehost`（见关键决策 4）；`previousSessions` 项可带 `reason`；事件 `session.rehosted`、`session.rehost-undone`、`session.rehost-released`；
  `status --json` 的 `store` 加 `rehostPending: [<邮箱名>]`（只增不改）。

## 项目结构

```text
module_crew/rehost.py           新增：挡住清单、确认码、迁移事务、撤回、show、release、迁移说明文字
module_crew/__main__.py         coordinator rehost 与 rehost 子命令接入（同 coordinator handover 的接法）；_session_guard 的窄口与「被迁走的旧会话」拒绝
module_crew/hooks.py            迁来待盘点档位；陌生 Claude 会话在协调登记于 Codex 时的提示
module_crew/store.py            rehost 字段与 previousSessions.reason 校验
module_crew/failure.py          resume_kit 接受迁移附加段（模块会话与轻任务会话）
module_crew/review.py           最终验收交审对盘点未解除的模块拒绝
module_crew/probe.py            status 显示待盘点
skills/crew-coordinator/SKILL.md、skills/crew-dev/SKILL.md、docs/guide.md、README.md、README.en.md
tests/test_live_rehost.py       新增
```

## 命令

```bash
python3 -m unittest discover -s tests
PYTHONPATH=tests python3 -m unittest test_live_rehost
```

## 代码风格

沿用现有模块：代码与注释英文，输出中文；只用标准库；外部命令只有 `git`，带超时、不经 shell；写入前核对、凭用户原话写；
module-crew 不发消息、不替用户点弹窗、不停或归档会话、不改全局配置、不删文件；钩子保持只读。

## 测试策略

- 夹具：用 handover 把协调换到 Codex，再登记 2 个 Codex 模块会话（一个 worktree 有未提交改动与未跟踪文件）、1 个 Codex 轻任务会话、若干未结事项／请求／等待记录。
- 清单：逐项造出不满足（协调在 Claude、混一个 Claude 模块会话、合并锁、running 外包、找不到 spec-guard、调用者已绑定、目录不在集成 checkout），`--check` 各报对应项、退出码 3、无确认码。
- 确认码：同一状态两次 `--check` 码相同；改一个文件、加一个提交、绑定变化后码变；`--to` 码不符、原话不含码、原话没说已停时退出码 3 且状态库与文件不变。
- 守门：Codex 会话调用 `--to` 退出码 7；已绑模块会话调用退出码 7；未绑 Claude 会话放行；终端（无编号）放行且协调不绑。
- 迁移结果：所有登记 `claude-desktop`、旧编号进 `previousSessions`（`reason: rehost`）、`hostSession` 清掉、调用者绑成协调、事件含原话；
  未结事项／请求／等待记录逐字不变；Claude 规则文件写上、Codex 规则留着；恢复说明含接管写法、`bind`、快照里的未提交文件、盘点要求；迁移说明每步三项。
- 旧会话：用旧 Codex 编号跑 `sync`、`check quick`、`offload start`、`bind` 退出码 7；跑 `status` 照常。
- 盘点闸：钩子档位为「迁来待盘点」；`rehost show` 报出快照之后的新提交与新改动；`review add` 最终验收退出码 3；`release` 后钩子恢复、`review add` 放行。
- 撤回：未 bind 时恢复原登记逐字一致；有一个 bind 后退出码 3。
- 回归：全量测试通过；`coordinator handover`、`bind --takeover` 行为不变。

## 边界

- **总是**：要用户原话且含当前确认码；挡住就什么都不写；邮箱名不变；权限规则只追加；未提交改动原样保留、列给用户。
- **先问**：放宽挡住条件（如合并进行中也迁）；只迁部分会话；迁移后自动打开外包；在盘点期间放行最终验收。
- **从不**：替用户停、归档 Codex 会话；删除或回滚 worktree 里的改动；改未结事项、请求、等待记录的内容；改契约；在 worktree 或集成 checkout 写 AGENTS.md／CLAUDE.md。

## 验收标准

1. 清单任一不满足：`rehost --check` 列出该项与原因、退出码 3、不给确认码；`rehost --to` 退出码 3、状态库与所有 checkout 文件不变。全满足时 `--check` 退出码 0、给出确认码、`--json` 可解析并列出每个会话的 HEAD 与未提交文件。
2. 确认码：状态不变时稳定；worktree 改动、提交、绑定任一变化后改变；`--to` 码不符、原话不含确认码、原话没说旧会话已停时退出码 3、不写。
3. 守门：未绑定的 Claude 会话在集成 checkout 里可以运行 `rehost --to`；Codex 会话、已绑定任何登记的会话、目录不在集成 checkout 时退出码 7、不写；其他写命令的守门行为与改前相同。
4. `rehost --to claude` 后：模块协调与全部在用的模块会话、轻任务会话登记为 `claude-desktop`，旧会话编号在 `previousSessions` 且带 `reason: rehost`，调用者绑为模块协调（终端运行时不绑）；
   未结事项、公共变更请求、等待记录、轻任务记录逐字不变；事件 `session.rehosted` 含原话。
5. 已 apply 过权限：集成 checkout 与每个模块 worktree 得到 Claude 规则、原有 Codex 规则不变；某个没被 git 忽略时迁移照常完成、迁移说明标出原因。没 apply 过：不写规则、迁移说明提示可以 apply。
6. 每个迁来的模块会话、轻任务会话各有一份恢复说明：含 `takeover:true, wake:"auto"`、`bind <邮箱名>`、快照 HEAD 与未提交文件（原样列出）、「先盘点，用户点头前不写代码」，不含 Codex 段；迁移说明存进状态库目录，每步有「去哪个会话／做什么／做完的样子」。
7. 旧会话失效：以旧 Codex 会话编号运行模块侧写命令（`sync`、`check quick`、`offload start`、`bind`）退出码 7 并说明已被迁走；只读命令照常。
8. 盘点闸：迁来会话的钩子档位为「迁来待盘点」；`rehost show` 报出快照之后多出的提交与改动；盘点未解除时最终验收交审退出码 3；`rehost release` 后档位与交审恢复正常。
9. 撤回：没有会话 bind 时 `--undo` 让登记恢复到迁移前（逐字比较）；有会话 bind 后退出码 3、不写。
10. 钩子：集成 checkout 里未登记的 Claude 会话、模块协调登记在 Codex 时，提示一行可以 `coordinator rehost --check`；协调在 Claude 时提示与改前相同。
11. 文档：`docs/guide.md`「换宿主」一节有「批次内迁到 Claude」（何时能迁、确认码、旧会话要用户亲手停、盘点、撤回与局限）；README／README.en 功能清单列出；crew-coordinator skill 有「接手 Codex 上没做完的一批」、crew-dev skill 有「迁来之后」。
12. 全量测试通过。实地：经用户同意在 crew-rehearsal 演练一次 Codex→Claude 批次内迁移（含一个有未提交改动的模块），再用于 LIVE-SAAS；做不了写「宿主未实测」与原因。

## 未决问题

1. 关键决策 7（撤回只在没人 bind 前）是推荐值；另一个选择是完全不提供撤回，迁错了只能人工修状态库。
2. 原话里「已停」的判断用关键词（「已停」「停了」），可能漏判写法不同的原话；另一个选择是要求单独的 `--old-sessions-stopped` 开关，由会话在用户明说后加。
3. 用户选「丢」的未提交改动按决策 6 用带标签的 stash 收起；stash 在所有 worktree 间共用，另一个选择是提交到一个 `rehost-wip/<模块>` 分支。

## 文档建议

`docs/guide.md`「换宿主」一节补「批次内迁到 Claude」；README／README.en 功能清单加一项、命令一览补 `coordinator rehost` 与 `rehost show|release`；CHANGELOG 随发版写。
回告：发版后告诉 mc-coord（转用户）LIVE-SAAS 可以按迁移说明迁；随最终验收列出。
