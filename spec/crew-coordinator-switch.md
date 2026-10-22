# Spec: crew-coordinator-switch

<!-- spec-guard: review approved a018243b1051 -->

> 能力图模块 `crew-coordinator-switch`（第六版第 1 个）。需求来源：`docs/requirements-record.md` 第 14 节第 1、2、4、5、7、8 条（用户 2026-10-22 经拷问确认）。
> 假设见下文，均来自那一节；标「新」的是写 Spec 时补的实现取舍，请重点审。

## 目标

让「协调会话」成为按会话开关的东西：用户在某个会话里明说，这个会话才升级成本项目的协调会话；一个仓库最多一个；
没有协调会话时插件完全安静；有协调会话时，别的普通会话提醒一次、照常工作，协调会话也知道有它；
协调会话或模块会话被 `/clear` 之后身份自动接上。多模块并行的默认上限从 3 改为 2。

使用者是用户（在协调会话里说「升级为协调会话」）和后续模块（crew-task-ledger 等以「有在用的协调会话」为前提）。

## 范围

**范围内**

- 新命令 `module-crew coordinator up`：体检、建库、写运行配置、登记并绑定协调会话。
- 体检新增检查项 `spec-guard-enabled`；`up` 用自己的一组前提判断能不能升级（不要求能力图与并行开关）。
- 钩子：普通会话的一次性提醒、协调会话看到「有没登记的会话在活动」、`/clear` 后的身份交接（新增 `SessionEnd` 钩子）。
- `start prepare` 与 `up` 的衔接：已经 `up` 过就沿用那个协调会话。
- `DEFAULT_MAX` 改为 2。
- `status` 里显示协调会话是谁、在哪、有没有绑定，以及看到过几个没登记的会话。
- `crew-coordinator` skill 的触发说明与升级提示；README。

**范围外**

- 任务记录、轻流程、并行判断（crew-task-ledger、crew-light-task）。
- 发现不经队列的提交（crew-unqueued-commits）。
- 拦截普通会话的任何操作。
- 宿主侧会话标题：钩子拿不到，提醒里只写目录与分支。

## 假设（来自需求记录第 14 节）

1. 升级必须用户明说，记原话；没升级的会话插件不注入任何规矩。
2. 「一个项目」= 同一个 git 仓库（`git-common-dir` 相同，含所有 worktree）；状态库本来就在 `<git-common-dir>/module-crew/`。
3. 升级前提：git 仓库、集成基线干净、spec-guard 与 agent-relay 已装且接口版本够用、项目已启用 spec-guard（`.agent/config.json` 存在）；**不要求**能力图、`moduleConcurrency` 或 `startable`。
4. 第二个会话要升级时被拦；旧协调会话不在了，由用户明说接管（现有 `takeover` + `bind`）。
5. 普通会话提醒一次、不打断、照用户意图做；协调会话下一次回复时告诉用户。
6. `/clear` 后会话编号会变（2026-10-22 实测：先 `SessionEnd` 旧编号 `reason:"clear"`，再 `SessionStart` 新编号 `source:"clear"`，同 `cwd`，新载荷不带旧编号）；压缩与恢复不变。
7. 多模块并行默认上限 2；已写进状态库的上限不变。

## 关键决策与取舍（请重点审）

1. **升级是一条命令，由协调会话在用户明说后运行**：
   `module-crew coordinator up --short <项目简称> --original-file <原话文件>`。它做四件事，全在一个事务里：
   没库就建库；没配置就写运行配置（简称、集成分支 = 当前分支、`maxModules` 2、`crewDir`），配置已定就沿用；
   登记 `<简称>-coord` 为协调会话；把本会话的编号绑上去（带原话）。
   输出最后提示：用 agent-relay `bridge_register` 注册邮箱名 `<简称>-coord`（`wake: "auto"`），再跑 `module-crew status`。
   **不写 spec-guard 的角色标记**（`setCoordinator` 要求并行开关打开）；角色标记照旧由 `start prepare` 在真开模块时写。
2. **（新）`up` 的前提是一组固定检查项**：`git`、`agent-relay`、`spec-guard`、`spec-guard-enabled`、`baseline` 必须是 `ok`。
   其中 `spec-guard` 项若只因 `/map` 报「没有能力图」（退出码 3）而判 blocker，`up` 视为满足；`spec-guard-planning` 不看。
   新检查项 `spec-guard-enabled`：项目根有 `.agent/config.json` → ok，否则 blocker（「项目还没启用 spec-guard：先跑 /spec-guard:setup-convention」）。
   `status` 照旧显示全部检查项；`spec-guard-enabled` 在 `status` 里不满足时是 blocker（`start` 本来也需要它）。
3. **唯一性按「在用的协调登记」判断**：状态库里已有 `status: active` 的协调登记时——
   绑的就是本会话 → 「已是协调会话，没有改动」；绑的是别的会话或没绑 → 拒绝，写明那个协调会话的目录与分支，
   并说「要换成本会话，请用户明说接管：module-crew takeover <名> --original-file <原话文件>，再在本会话 bind」。
   `up` 不提供「强制」选项。
4. **（新）要能关**：`module-crew coordinator down --original-file <原话文件>`，只在**没有在用的模块会话**时可用
   （以后也包括没有未完成的任务）：把协调登记记为 `retired`、解绑，插件回到安静。有在用模块时拒绝并列出它们。
   不删状态库，历史保留；之后可以再 `up`。
5. **（新）提醒一次，靠钩子写一条「见到」记录**：现在的钩子只读。为了「只说一次」和「告诉协调会话」，
   钩子在 `SessionStart` 遇到「本仓库有在用且已绑定的协调会话，而本会话不是任何登记会话」时，
   往状态库写一条 `sighting` 记录（键为会话编号：目录、分支、首次时间），**只在这条记录第一次写入时**注入提醒；
   同一会话编号之后的启动、恢复、压缩都不再提醒。写入失败（锁、权限）就不写也不提醒，绝不挡对话。
   这是钩子第一次写状态库，所以只写这一种记录、带 2 秒锁超时。
6. **提醒文案**（注入给普通会话，要求它在第一次回复里顺带说一次、不停下来问）：

   > 提醒：这个项目已有协调会话（在 `<目录>`，分支 `<分支>`），派活、并行和合入一般由它统一安排。你在这里直接改也可以，只是这些改动不经它的合并队列，正在开发的模块要等它发现后才会收到同步通知。要交给协调会话的话，告诉我，我把要做的事整理成一段话，你贴给它就行。

   在模块 worktree 里的陌生会话保留现在的说法（「本目录属于模块 X，先 bind」），因为那多半是刚开的模块会话还没 bind。
   在集成 checkout 里的陌生会话用上面的提醒，末尾加一句接管办法（同决策 3）。
7. **协调会话怎么知道**：协调会话的每轮提示（`UserPromptSubmit`）在有**还没告诉过**的 `sighting` 时加一句
   「有 N 个没登记的会话在本项目活动：<目录>（分支 <分支>）…；请顺带告诉用户一次」，并把这些记录标为已告知。
   同样是只写这一种字段，失败就照旧不提。`status` 里列出全部 `sighting`（最近 10 条）。
8. **`/clear` 交接只认相邻的一对事件**：新增 `SessionEnd` 钩子。已绑定的会话（协调或模块）以 `reason: "clear"` 结束时，
   写一条交接记录（登记名、旧编号、`cwd`、时间）；随后 `SessionStart` 以 `source: "clear"`、**同一 `cwd`**、
   **30 秒内**到来时，把该登记的绑定改成新编号（事件 `rebound-after-clear`），并照常注入角色、加一句
   「刚清空过：先跑 module-crew status，以状态库为准」。不满足任一条件就不交接，交接记录 5 分钟后作废，
   那时会话就是陌生会话，按现有办法 `bind`（协调要原话）。协调会话的交接**不要原话**：清空是用户在那个窗口里亲手做的。
   （2026-10-22 修订，实地验证后）**桌面版另走一条路**：桌面版清空时旧进程以 `reason: "other"` 结束，新进程等下一条消息才以
   `source: "startup"` 启动，上面的配对认不出来。所以绑定时（`bind`、`coordinator up`、`start prepare`、交接后改绑）若
   `CLAUDE_CODE_ENTRYPOINT` 是 `claude-desktop`，另记 `hostSession.desktopId` = `CLAUDE_CODE_HOST_SESSION_ID`（桌面版会话编号 `local_…`，清空后不变）。
   带 `desktopId` 的已绑定会话以**任何原因**结束时都写交接记录（带 `desktopId`）；之后同一 `cwd` 的 `SessionStart`，若钩子环境里的
   `CLAUDE_CODE_HOST_SESSION_ID` 等于记录里的 `desktopId`、登记仍绑着旧编号，就改绑到新编号（不设 30 秒窗口，记录 7 天后作废）。
   旧编号又以同一编号启动（宿主把空闲会话停掉后再接上）时，交接记录关闭为「原会话回来了」。交接记录只在旧进程结束后才有，
   所以从该会话里起的命令行子进程即使继承了同一个 `CLAUDE_CODE_HOST_SESSION_ID`，也拿不走登记。
9. **默认上限改为 2**：只改 `DEFAULT_MAX`；`up` 与 `start prepare` 新写配置时用它；已存在的 `maxModules` 不动。
10. **`start prepare` 衔接**：已有在用的协调登记时沿用它（现有逻辑已如此），不再另外登记；简称与已定的不同照旧拒绝。
    没 `up` 过直接 `start prepare` 仍然可用（它本来就要用户原话），等于同时升级。
11. **skill 与安静**：项目里没有在用的协调登记时，钩子对任何会话都不输出（含没有状态库、有库但协调已 `down`）。
    「提一句可以升级」放在 `crew-coordinator` skill：用户说到派活、并行、开个会话去修，而 `status` 显示没有协调会话时，
    说一句「可以把本会话升级为协调会话，要的话告诉我」，用户明说后再 `up`。

## 接口约定

### 命令

```bash
module-crew coordinator up --short <简称> --original-file <原话文件> [--json]
module-crew coordinator down --original-file <原话文件> [--json]
module-crew hook session-end          # 新钩子入口，读 stdin 的 SessionEnd 载荷
```

退出码：`0` 成功或无改动；`3` 前提不满足或被拒（原因逐条列出）；`2` 参数错。

### 状态库

- `session` 协调登记：`status` 新增取值 `retired`（`down` 后）。
- 新记录种类 `sighting`（键：宿主会话编号）：`{"cwd", "branch", "firstSeen", "told": false|true}`。
- 新记录种类 `handover`（键：登记名）：`{"oldSessionId", "cwd", "at"}`；交接成功或作废后 `state: closed`。
- 事件：`coordinator-up`（带原话）、`coordinator-down`（带原话）、`sighted`、`sighting-told`、`rebound-after-clear`。

### 体检

新检查项 `spec-guard-enabled`（blocker）。`probe.run()` 的 `report.checks` 多这一项；`report.to_json()` 的 `schemaVersion` 不变（只加项）。

### status

多一段「协调会话」：名字、目录、分支、已绑定／未绑定、`retired` 时写「已关闭」；「没登记的会话」：数量与最近 10 条。

## 项目结构

```text
module_crew/coordinator.py   新：up / down
module_crew/hooks.py         陌生会话分流、sighting、SessionEnd 与 clear 交接
module_crew/probe.py         spec-guard-enabled 检查项；status 新段
module_crew/start.py         DEFAULT_MAX = 2
module_crew/store.py         sighting、handover 记录校验
module_crew/__main__.py      coordinator 子命令、hook session-end
hooks/hooks.json             加 SessionEnd
skills/crew-coordinator/     触发说明与升级提示
tests/test_coordinator_switch.py
```

## 命令

```bash
python3 -m unittest discover -s tests
PYTHONPATH=tests python3 -m unittest test_coordinator_switch
```

## 代码风格

沿用现有模块：代码与注释英文，输出中文；只用标准库；钩子绝不抛错、绝不挡对话。

## 测试策略

- `up`：前提逐项不满足各拒一次；只因没有能力图而 `/map` 退出码 3 时能升级；建库、写配置、登记、绑定在一个事务里；已有协调登记的三种情况（本会话、别的会话、未绑定）。
- `down`：有在用模块时拒绝；成功后钩子对所有会话安静；再 `up` 可用。
- 钩子：没有协调会话时三种目录（集成 checkout、模块 worktree、仓库别处）都不输出；有协调会话时陌生会话第一次得到提醒、写 `sighting`，同编号第二次不再提醒；锁被占时不提醒不报错；协调会话的提示带未告知的 `sighting` 并标为已告知。
- `/clear`：按实测的事件顺序喂载荷——交接成功；`cwd` 不同、超过 30 秒、`source` 不是 `clear`、没有交接记录各不交接；模块会话同样交接。
- `DEFAULT_MAX`：新项目为 2，已存的 3 不变。
- 回归：现有 494 个测试全过（部分断言 `stranger_line` 文案的测试按新文案改）。
- 实地（不入自动测试，写进验收记录）：桌面版里真做一次 `/clear`，确认协调会话的身份接上。

## 边界

- **始终**：升级、关闭、接管都要用户原话；钩子写入只限 `sighting`、`handover` 与绑定字段；写失败就安静。
- **先问**：给钩子增加别的写入；改变模块会话的陌生提示；`up` 写 spec-guard 角色标记。
- **绝不**：拦截普通会话的工具调用或提交；钩子运行体检或 `/map`；自动接管一个还绑定着别的会话的协调登记。

## 验收标准

1. 前提齐全（含只因没有能力图而 `/map` 退出码 3）时 `coordinator up` 成功：建库、配置 `maxModules` 2、登记 `<简称>-coord` 并绑定本会话、事件带原话；输出提示注册邮箱名。
2. 缺 `.agent/config.json`、agent-relay 未装、基线不干净、不在 git 仓库，各自拒绝且原因不同；没给原话拒绝。
3. 已有在用协调登记：同一会话 → 无改动；别的会话或未绑定 → 拒绝并写明对方目录、分支与接管办法。
4. `coordinator down`：有在用模块时拒绝并列出；否则登记变 `retired`、解绑；之后钩子对所有会话不输出；可再 `up`。
5. 没有在用协调登记时，钩子在任何目录、任何事件都输出空。
6. 有协调会话时，陌生会话第一次 `SessionStart` 得到决策 6 的提醒（集成 checkout 里另带接管办法），状态库多一条 `sighting`；同一编号再启动、恢复、压缩都不再提醒；模块 worktree 里的陌生会话仍是原来的 bind 提示。
7. 协调会话下一轮 `UserPromptSubmit` 的注入里列出未告知的 `sighting`，之后不再重复；`status` 列出它们。
8. 已绑定会话 `SessionEnd reason=clear` 后 30 秒内同 `cwd` 的 `SessionStart source=clear`：绑定改为新编号、事件 `rebound-after-clear`、注入角色与「刚清空过」提示；任一条件不满足不交接。
   （2026-10-22 修订）桌面版：绑定时记下 `desktopId`；带 `desktopId` 的已绑定会话以任何原因结束后，同 `cwd`、同 `CLAUDE_CODE_HOST_SESSION_ID` 的新会话启动时改绑；`desktopId` 不同、`cwd` 不同、旧进程没结束、超过 7 天各不改绑；旧编号回来时交接记录关闭。
9. 钩子写入遇到锁超时或只读目录：不输出提醒、退出码 0、对话不受影响。
10. 新项目默认上限 2；已有配置的上限不变。
11. `status` 显示协调会话段（名字、目录、分支、绑定状态）与没登记的会话段；`--json` 同样有这两段。
12. 全量测试通过。
13. 实地：桌面版协调会话 `/clear` 后身份接上（结果写进验收记录；做不了就写明「未实测」与原因）。

## 未决问题

- 桌面版 `/clear` 的钩子事件顺序是否与命令行版相同：实地那一关验证（验收标准 13）。
- 轻任务的消息格式已问契约负责人（2026-10-22），不挡本模块。

## 风险

- 钩子开始写状态库：锁冲突或写坏会影响所有会话。缓解：只写三种字段、2 秒超时、失败安静、事务写入；测试覆盖锁占用。
- 改了钩子与绑定行为，会影响正在跑的 LIVE-SAAS 短验证：开始构建前先告诉总协调，发版前再告诉一次。

## 文档建议

README「开始使用」一节改为先「升级协调会话」（`coordinator up`），再讲开模块；加一段「没升级的会话照常用，插件会提醒一次」。CHANGELOG 记第六版。

## 变更记录

- 2026-10-22：关键决策 8 与验收 8 加桌面版交接路径（绑定时记 `CLAUDE_CODE_HOST_SESSION_ID`，旧进程结束后同目录、同桌面版会话编号的新会话改绑）。原因：Checkpoint 2 实地验证发现桌面版清空的事件与命令行版不同（`SessionEnd reason:"other"`、新进程 `source:"startup"`），原方案不生效；桌面版会话进程的 `CLAUDE_CODE_HOST_SESSION_ID` 是 `local_` 编号、清空后不变。来源：用户 2026-10-22 选 A「修订 Spec 决策 8，加桌面版按 CLAUDE_CODE_HOST_SESSION_ID 的交接路径」。
