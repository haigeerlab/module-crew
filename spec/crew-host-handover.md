# Spec: crew-host-handover

<!-- spec-guard: review approved 76d918e70127 -->

> 能力图模块 `crew-host-handover`（第八版）。需求来源：插件生态接缝 S13 修订版，用户 2026-10-23 在 ecosystem-lead 会话确认
> 「只在空档整体来回换宿主，不做模块中途换」，2026-10-23 在 mc-coord 会话批准插入能力图（批准事项 C13）。
> 宿主事实取自 decision-inbox `docs/host-differences.md`（H1–H5、H7、H8、H10–H12、H23、H25）。
> 依赖 `crew-codex-host`（Codex 模块会话、`host-check`）、`crew-host-permissions`（权限规则写入与跟随）、`crew-light-task`（`task dispatch`）、
> `crew-session-handover`（`bind --takeover`、写命令会话守门）。标「新」的是写 Spec 时补的实现取舍，请重点审。

## 目标

一个项目的多模块并行开发（模块协调 + 模块会话 + 轻任务会话）能在一批收尾后的空档里，整体从 Claude Code 换到 Codex，或从 Codex 换回 Claude Code：

- 一批收尾时模块协调告诉用户「已收尾，具备换宿主的条件」；
- 用户说换，`module-crew coordinator handover --to codex|claude` 核对收尾条件、改模块协调登记的宿主、按新宿主写集成 checkout 的权限规则，生成逐步交接说明；
- 交接说明每一步写清去哪个会话、点什么、贴什么，用户照做即可完成身份交接与开新协调会话；
- 之后 `start prepare` 开模块、`task dispatch` 派任务默认用模块协调所在的宿主。

换不换、换到哪边由用户决定；module-crew 不看额度、不自动换。

## 范围

**范围内**

1. 收尾提示：最后一个在用的模块会话或轻任务会话收回后，`merge cleanup` 输出一行「本批已收尾，具备换宿主的条件」；`status` 在满足条件时显示同一行。
2. `coordinator handover --check`（只读）：逐条报收尾条件是否满足。
3. `coordinator handover --to codex|claude --original-file <原话文件>`：核对条件 → 改登记宿主 → 写集成 checkout 的权限规则 → 记事件 → 输出并保存交接说明。
4. `bind <邮箱名> --takeover` 认新宿主：调用者的宿主（看环境变量 `CODEX_THREAD_ID`／`CLAUDE_CODE_SESSION_ID`）必须与登记的宿主一致。
5. 状态库放开「模块协调只能是 claude-desktop」：模块协调可以登记为 `codex-desktop`，但只能经 `handover` 改过去。
6. 宿主跟随：`start prepare` 与 `task dispatch` 的 `--host` 默认取模块协调的宿主；模块协调在 Codex 时拒绝 `--host claude`。
   `task dispatch --host codex` 的开工说明加 Codex 段（与 `start prepare --host codex` 同一套文字）。
7. `permissions` 的集成 checkout 跟随模块协调宿主：Codex 时写 `.codex/rules/module-crew.rules` 并报项目信任状态。
8. 文档：README「换宿主」一节；crew-coordinator skill 加「空档换宿主」一节（Claude 版，含收尾时怎么告诉用户、怎么带用户走交接说明）。

**范围外**

- 模块做到一半换宿主；协调与模块长期混搭两边（只保留现有的「Claude 协调 + Codex 模块会话」）；Codex 协调叫醒 Claude 模块会话。
- 自动看额度、自动换宿主。
- **模块协调在 Codex 上真正跑起来**（Codex 版 crew-coordinator skill、合并长检查与提权、Codex 侧定位插件）：这是另一个待定模块 B。
  本模块只做交接本身；B 发版前，`handover --to codex` 拒绝执行（关键决策 6）。
- 改 agent-relay、decision-inbox；改契约。

## 假设（请逐条确认）

1. **何时能换**：只在空档——没有在用的模块会话与轻任务会话、没有排队或进行中的合并、没有待用户批的事项（module-crew 侧未结的待决、交审、公共变更请求、等待记录都为空）。任一不满足就拒绝，不提供「强制」。
2. **谁运行 `handover`**：原宿主上在用的模块协调会话（写命令守门照常认它）。原会话已经没了时，用户自己在终端运行（读不到会话编号，守门不拦，沿用 crew-session-handover 假设 2）。
3. **登记宿主在 `handover` 时就改**，`hostSession` 保留原会话，直到新宿主会话 `bind --takeover` 才改绑；这段时间原会话仍能运行写命令（守门只看会话编号），交接说明第一步就是让它停手。
4. **新宿主会话要先停掉原会话，再接管邮箱名**：Claude→Codex 时 agent-relay 拒绝接管仍在运行的 Claude 会话（holder-still-running），所以先归档或停掉原 Claude 会话；
   Codex→Claude 时 agent-relay 判断不了 Codex 线程是否停了，交接说明要用户确认已停（不再在那个线程里发话）后再接管。
5. **Codex 协调每轮重新注册**（H25、H3）：交接说明与之后的 Codex 协调规矩写明「每轮开始先用自己的线程 id `bridge_register`（不带 takeover）」。module-crew 没有 Codex 钩子可注入（H8），这句只能写进说明与 skill。
6. **用户接受的代价**：Codex 上写状态库、提交、合并都在 `.git` 里，要用户点提权（H11）；模块会话要用户手动在 Codex 里开；ChatGPT 应用重启后要逐个点开（H2）。审批照旧在该端模块协调会话里由用户亲口批（H10）。
7. **混搭边界**：模块协调在 Claude 时，`--host codex` 照旧允许（crew-codex-host）；模块协调在 Codex 时只允许 Codex 模块与轻任务会话（Codex 叫不醒停掉的 Claude 会话，H4）。
8. **邮箱名不变**：模块协调换宿主后仍用原邮箱名（如 `mc-coord`），决策收件箱与别的插件不用改登记；只在 agent-relay 里接管。
9. **权限规则只加不撤**：换到 Codex 时给集成 checkout 追加 Codex 规则，原有 Claude 规则保留（换回来时直接可用）；规则的写法、只追加、要被 git 忽略等约束沿用 crew-host-permissions。
10. **B 未发版前不让换到 Codex**（关键决策 6）：换过去也只能靠交接说明里的命令清单做事，容易出错；换回 Claude 方向不受此限。
11. 契约不改；验收以夹具测试为主，实地来回换一次放进演练、经用户同意才开始（Claude→Codex 方向要等 B）。

## 关键决策与取舍（请重点审）

1. **（新）收尾条件固定为一张清单**，`--check` 与 `handover` 用同一份，每项给「满足／不满足＋原因」：
   - `sessions`：没有 `status: active` 的 `dev`、`task` 会话登记；
   - `tasks`：没有处于 `dispatched`／`working`／`returned`／`escalated` 的任务（`queued`／`ready` 可以留着，换过去后用新宿主派）；
   - `merge`：合并锁没被持有，没有已批准未合并的事项；
   - `pending`：module-crew 记账的待决事项（`item`）、公共变更请求（`request`）、等待记录都没有未结的；
   - `clear-handover`：没有未取走的清空交接记录（`handover`）。
   决策收件箱里另有的待决事项 module-crew 看不全，`--check` 输出一行「决策收件箱侧请模块协调用 decision-inbox 的 waits 再看一眼」，不作为拒绝条件。
2. **（新）`handover` 一次做完四件事，任一前置失败就什么都不写**：
   ① 核对：收尾条件、原话非空、`--to` 与当前宿主不同、调用者是登记的模块协调（或读不到会话编号）；
   ② 改登记：模块协调的 `host` 改为目标宿主，加 `hostHandover: {from, to, at, original}`，事件 `coordinator.handover`；
   ③ 写权限：项目已 `permissions apply` 过时，按目标宿主给集成 checkout 追加规则（Codex：`.codex/rules/module-crew.rules`；Claude：`.claude/settings.local.json`），沿用 crew-host-permissions 的合并写入与记录；写失败不回滚登记，交接说明里标出「权限规则没写上：<原因>」；
   ④ 说明：生成交接说明，打印并存到状态库目录 `handover-guide/<时间>.md`（git 目录内，不进仓库）。
3. **（新）交接说明逐步写，每步固定三项「去哪个会话」「做什么（点什么／贴什么）」「做完的样子」**：
   - Claude→Codex：① 原 Claude 协调会话停手，用户在侧栏归档它；② 在 Codex 新建任务，工作目录选集成 checkout，贴下面整段开场文字；
     ③ 开场文字让 Codex 线程：`bridge_register {agent:<邮箱名>, takeover:true, wake:{app:"codex", sessionId:<CODEX_THREAD_ID>}}`（被拒 holder-still-running 就回到第①步）、
     运行 `<固定入口> bind <邮箱名> --takeover --original-file <原话文件>`（会弹提权，用户在该线程批准）、加载 Codex 版 crew-coordinator skill、跑 `status`；
     ④ 用户在 Codex 里信任项目（规则才生效，H8 同类限制，只提示不代改）；⑤ 之后每轮开头重新 `bridge_register`（不带 takeover）。
   - Codex→Claude：① 原 Codex 协调线程停手，用户确认不再在那个线程里发话；② 在 Claude 桌面版新开会话，目录选集成 checkout，贴开场文字；
     ③ 开场文字让新会话：`bridge_register {agent:<邮箱名>, takeover:true, wake:"auto"}`、`module-crew bind <邮箱名> --takeover --original-file <原话文件>`、加载 crew-coordinator skill、跑 `status`。
   - 两个方向都附「下一批怎么开」：`start prepare` 默认用新宿主，Codex 模块会话要用户手动开任务（沿用 crew-codex-host 的做法）。
   - 交接说明里的 `takeover` 需要用户同意，说明写明「这一步就是用户同意的接管，原话即本次 handover 的原话」。
4. **（新）`bind --takeover` 加宿主核对**：调用者有 `CODEX_THREAD_ID` 视为 Codex，有 `CLAUDE_CODE_SESSION_ID` 视为 Claude；与登记的 `host` 不一致时退出码 3，提示「先在原会话运行 coordinator handover --to <宿主>」。
   接管成功后清掉 `hostHandover` 的进行中标记（保留在事件里），`status` 不再显示「交接中」。
5. **（新）宿主跟随只改默认值**：`start prepare`、`task dispatch` 的 `--host` 不写时取模块协调的 `host`；写了按写的，但模块协调在 Codex 时 `--host claude` 退出码 2、什么都不写。
   `task dispatch` 现在只支持 Claude；本模块给它加 `--host codex`，开工说明复用 `start.codex_lines`（host-check、提权、带 host 注册、重新注册、先跑 status）。Codex 版 crew-dev skill 补「轻任务」一节（与 Claude 版同一套规矩）。
6. **（新）`--to codex` 以 Codex 版 crew-coordinator skill 存在为前提**：插件里没有 `codex-skills/crew-coordinator/SKILL.md` 时，`handover --to codex` 与 `--check --to codex` 报「Codex 版模块协调规矩还没发版（待定模块 B）」，退出码 3、什么都不写。
   B 发版后这条自然放开，本模块不用再改。`--to claude` 不受影响。
7. **store 校验改法**：`role: coordinator` 允许 `host: codex-desktop`；`coordinator up` 仍只登记 `claude-desktop`（新项目从 Claude 起步，改宿主只走 `handover`）。这是对 crew-codex-host 验收 4 的修订，随本 Spec 交审。
8. **收尾提示放在会变成空档的那一刻与 `status`**：`merge cleanup <模块|T号>` 收回后若收尾条件全满足，输出一行「本批已收尾，具备换宿主的条件：要换到 <另一边> 请用户明说，再运行 coordinator handover --to <宿主>」；
   `status` 在条件满足且有过合并时显示同一行。只提示，不建议换不换。

## 接口约定

```bash
module-crew coordinator handover --check [--to codex|claude] [--json]                 # 只读：收尾条件清单
module-crew coordinator handover --to codex|claude (--original <原话> | --original-file <文件>) [--json]
module-crew bind <邮箱名> --takeover --original-file <原话文件>                         # 增加宿主核对
module-crew start prepare … [--host claude|codex]                                     # 默认跟随模块协调
module-crew task dispatch T<n> [--host claude|codex] [--json]                          # 新增 codex；默认跟随模块协调
```

- `handover --check`：条件全满足 `0`，有不满足 `3`，不在 module-crew 仓库 `2`。`--json`：`{"ready": bool, "from", "to", "checks": [{"id", "ok", "reason"}]}`。
- `handover --to`：`0` 完成；`3` 条件不满足、原话为空、目标与当前相同、`--to codex` 而 B 未发版——都什么都不写；`7` 写命令会话守门（沿用）。
- 状态库：模块协调登记加可选 `hostHandover: {"from", "to", "at", "original", "pending": bool}`；事件 `coordinator.handover`；`status --json` 的 `store` 加 `coordinatorHost` 与 `handoverReady: bool`。
- `sessions --json` 已有 `host` 字段，不改结构。

## 项目结构

```text
module_crew/handover.py          新增：收尾条件、handover、交接说明文字
module_crew/coordinator.py       handover 子命令接入
module_crew/hooks.py             bind --takeover 的宿主核对、清 pending
module_crew/store.py             coordinator 允许 codex-desktop；hostHandover 校验
module_crew/start.py, tasks.py   --host 默认跟随；task dispatch 的 Codex 段
module_crew/permissions.py       集成 checkout 跟随模块协调宿主
module_crew/merge.py, probe.py   收尾提示、status 字段
module_crew/__main__.py          子命令与参数
skills/crew-coordinator/SKILL.md、codex-skills/crew-dev/SKILL.md、README.md
tests/test_host_handover.py      新增
```

## 命令

```bash
python3 -m unittest discover -s tests
PYTHONPATH=tests python3 -m unittest test_host_handover
```

## 代码风格

沿用现有模块：代码与注释英文，输出中文；只用标准库；外部命令只有 `git`，带超时、不经 shell；写入前核对、凭用户原话写；module-crew 不发消息、不替用户点弹窗、不改全局配置。

## 测试策略

- 收尾条件：夹具仓库里逐项造出不满足（在用模块会话、working 任务、合并锁、已批未合、未结待决／请求／等待、未取走的清空交接），`--check` 各报对应项、退出码 3；全清后退出码 0。
- `handover --to claude`（夹具先把协调登记成 Codex）与 `--to codex`（夹具放一份假的 Codex 版 crew-coordinator skill）：登记宿主、`hostHandover`、事件、权限规则文件、交接说明文件与关键句；
  条件不满足、原话空、目标相同、B 未发版时退出码 3 且状态库与文件不变。
- `bind --takeover`：宿主一致成功并清 pending；不一致退出码 3、不写。
- 宿主跟随：协调在 Codex 时 `start prepare`、`task dispatch` 默认 Codex、`--host claude` 退出码 2；协调在 Claude 时行为与改前逐字相同。
- 收尾提示：`merge cleanup` 收回最后一个模块后出现那一行，还有在用会话时不出现；`status` 同理。
- 回归：全量测试通过；`coordinator up` 仍只登记 Claude。

## 边界

- **总是**：换宿主要用户原话；条件不满足什么都不写；权限规则只追加；邮箱名不变。
- **先问**：放宽收尾条件（如允许留着待决事项换）；模块协调在 Codex 时放行 Claude 模块会话；`coordinator up` 直接登记为 Codex。
- **从不**：模块做到一半换宿主；自动看额度或自动换；替用户点提权、信任项目或归档会话；在 worktree 或集成 checkout 写 AGENTS.md／CLAUDE.md；Codex 协调去叫醒 Claude 会话。

## 验收标准

1. 收尾条件任一不满足：`handover --check` 列出该项与原因、退出码 3；`handover --to` 退出码 3、状态库与集成 checkout 文件都不变。全满足时 `--check` 退出码 0、`--json` 可解析。
2. `handover --to claude`（协调原在 Codex）：登记 `host` 为 `claude-desktop`、`hostHandover.pending` 为真、事件含原话；已 apply 过权限时集成 checkout 的 Claude 规则齐全；交接说明含停原线程并确认、`takeover:true, wake:"auto"`、`bind --takeover`、加载 crew-coordinator，每步有「去哪个会话／做什么／做完的样子」，并存到状态库目录。
3. `handover --to codex`：没有 Codex 版 crew-coordinator skill 时退出码 3、什么都不写、输出提到待定模块 B；有时登记改为 `codex-desktop`、集成 checkout 得到 `.codex/rules/module-crew.rules` 并报信任状态、交接说明含归档原 Claude 会话、`wake:{app:"codex", sessionId:<CODEX_THREAD_ID>}` 接管、提权、信任项目、每轮重新注册。
4. 原话为空、`--to` 与当前宿主相同：退出码 3、不写。不是登记的模块协调会话运行：退出码 7（沿用守门）。
5. `bind --takeover`：调用者宿主与登记一致时成功、`hostHandover.pending` 清掉；不一致时退出码 3、提示先在原会话运行 handover、不写。
6. 协调在 Codex：`start prepare`、`task dispatch` 不带 `--host` 时登记为 `codex-desktop`、开工说明带 Codex 段；`--host claude` 退出码 2、不写。协调在 Claude：两条命令的行为与改前逐字相同。
7. `task dispatch --host codex`：开工说明含 host-check 绝对路径、提权、带 host 注册、重新注册、先跑 status；Codex 版 crew-dev 有「轻任务」一节。
8. `coordinator up` 仍只登记 `claude-desktop`；store 接受 `codex-desktop` 的模块协调登记。
9. `merge cleanup` 收回最后一个在用会话后输出「本批已收尾，具备换宿主的条件」；还有在用会话时不出现；`status` 与 `status --json`（`handoverReady`、`coordinatorHost`）一致。
10. README 有「换宿主」一节；crew-coordinator skill 有「空档换宿主」一节（收尾怎么告诉用户、换不换由用户定、带用户走交接说明、`takeover` 前先停原会话）。
11. 全量测试通过。实地：演练里经用户同意做一次 Codex→Claude 或 Claude→Codex（后者要 B 已发版）；做不了写「宿主未实测」与原因。

## 未决问题

- 关键决策 6（B 未发版前拒绝 `--to codex`）是推荐值：另一个选择是放行但在交接说明里警告，请用户定。
- Codex 线程里 `bind --takeover` 写状态库要提权，一次提权是否覆盖后续写命令：要在演练里实测，说明按「每次都可能要批」写。

## 文档建议

README 加「换宿主（空档）」一节：什么时候能换、`handover --check`／`--to`、交接说明怎么用、代价（提权、手动开会话、重启后逐个点开）；命令一览补 `coordinator handover`。
CHANGELOG 随发版写。回告：发版后告诉 ecosystem-lead S13 的模块 A 已就位、`--to codex` 等模块 B；随最终验收列出。
