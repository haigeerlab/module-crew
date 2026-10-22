<!-- spec-guard: review approved ce10f668804e -->

# Spec: crew-session-handover

> 能力图模块 `crew-session-handover`（第七版第 2 个）。需求来源：`docs/requirements-record.md` 第 16 节第 12 条及其补充（spec-guard 负责人试用观测 O9 与清空后不注入，用户 2026-10-22 确认）。
> 依赖 `crew-coordinator-switch`（模块协调的登记与 bind）、`crew-recovery-hooks`（钩子注入、清空交接）、`crew-background-checks`（写命令的集中守门）。标「新」的是写 Spec 时补的实现取舍，请重点审。

## 目标

模块协调换会话时身份要接得上、也只能有一个会话以模块协调身份动手：

- 用户知道怎么「重开」才不丢身份；
- 新开的会话（哪怕在别的目录）能经用户同意直接接手，旧会话随即失效；
- 已登记的会话不论在哪个目录，钩子都告诉它「你是谁、命令入口是什么」；
- 不是登记的那个会话，运行模块协调的写命令会被拒。

## 范围

**范围内**

1. 钩子按会话编号认身份：SessionStart 与每轮一行，先看本会话编号是否登记在某个在用会话上；登记了就按那个角色注入（含命令入口），不再要求当前目录是登记目录。目录不一致时多一行写明两边目录。
2. 跨目录接管：`module-crew bind <邮箱名> --takeover --original-file <原话文件>` 在新会话里一步完成接管：记下用户原话、把登记改绑到本会话、记下旧会话编号；不要求在登记目录里运行（同一个仓库内即可）。
3. 旧会话失效提示：被接管的旧会话再发消息时，每轮一行改为「本会话已被 <新会话> 接管，不要再以 <邮箱名> 的身份执行 module-crew 写命令」。
4. 写命令核对调用者：模块协调的写命令在动手前比对调用者的会话编号与模块协调登记的会话编号，不同就拒绝（退出码 7），并写明怎么接管。
5. `status` 标出本会话：「会话与待办」里调用者自己那一条后面写「← 本会话」；调用者没有登记、而项目有已绑定的模块协调时，多一行说明「本会话不是登记的模块协调 <邮箱名>，要接手用 bind --takeover」。
6. 写明怎么重开：README 与 crew-coordinator skill 写「升级或要重开时，在原会话里 `/clear`，或退出应用再打开；不要新开会话；已经新开了就用 `bind --takeover`」。

**范围外**

- 判断宿主里的会话「是否还活着」：module-crew 拿不到宿主的会话列表（见假设 3），不做「同一角色两个活着的会话」检测；双写的风险由第 4 条从根上挡住。
- 模块会话、轻任务会话的跨目录接管：它们照旧在自己的 worktree 里接管（原有 `takeover` + `bind`），本模块只让钩子按会话编号认出它们。
- 自动关掉或归档旧会话。

## 假设

1. 命令进程里的 `CLAUDE_CODE_SESSION_ID`（Codex 为 `CODEX_THREAD_ID`）与钩子收到的 `session_id` 是同一个编号（`bind` 已依赖这一点）。
2. 读不到会话编号的调用（用户自己在终端里运行）视为用户本人在操作，写命令不拦。
3. 宿主不向插件提供「哪些会话还在运行」；module-crew 只知道登记、清空交接与钩子目击记录。
4. 接管只发生在同一个仓库（同一个 git 公共目录）里。

## 关键决策与取舍（请重点审）

1. **（新）身份按会话编号认，目录只作提示**：钩子先查「本会话编号登记在哪个在用会话上」，找到就用那条登记的角色出提示，找不到才退回原来的按目录判断（陌生会话的提醒照旧）。
   目录不一致时加一行「本会话在 <当前目录>，<邮箱名> 登记的目录是 <登记目录>：module-crew 命令在本仓库任一目录都能运行，改文件的事到登记目录做」。
2. **（新）接管一步完成、只给模块协调**：`bind --takeover` 要用户原话，只用于模块协调；在同一仓库任一目录可运行。它把 `hostSession` 换成本会话，在登记上追加 `previousSessions`（旧会话编号与时间），
   事件 `session.taken-over` 记原话、旧编号、新编号。原有两步做法（`takeover` 后 `bind`）保留不变。
3. **（新）写命令守门放在命令分派处**：和合并锁守门（crew-background-checks）一样集中在 `__main__`。「模块协调的写命令」= 除以下之外的所有子命令：
   只读命令（`status`、`sessions`、`review batch`／`show`、`task list`／`show`／`next`、`unqueued` 不带 `--notify`、`permissions plan`、`start plan`、`protocol`、`source list`、`map`），
   模块与轻任务会话自己用的（`bind`、`sync`、`host-check`），以及 `hook`。只在三者同时成立时拒绝：项目有在用的模块协调、它登记了会话编号、调用者读得到会话编号且不同。
   拒绝时退出码 7，输出「本会话不是登记的模块协调 <邮箱名>：……要接手，请用户同意后运行 module-crew bind <邮箱名> --takeover --original-file <原话文件>」，什么都不写。
4. **（新）不做「两个活着的会话」检测，改为标出本会话**（与需求第 12 条原文「status 报阻塞」不同，用户已接受）：module-crew 无从知道宿主里哪个会话还开着，按钩子目击时间猜会误报（普通会话路过也会被目击）。
   写命令已经只认登记的会话，第二个会话动不了集成分支；`status` 改为标出「← 本会话」，调用者不是登记的模块协调时写明，并给出接管命令。
5. **旧会话的一行提示读登记上的 `previousSessions`**，不翻事件日志，保持钩子快（每轮一行仍只读文件）。

## 接口约定

```bash
module-crew bind <邮箱名> --takeover --original-file <原话文件>   # 新会话接手模块协调（同一仓库任一目录）
```

- 退出码：写命令被会话核对挡住 `7`；`bind --takeover` 用于非模块协调登记、原话为空 `3`。
- 状态库：会话登记新增可选字段 `previousSessions: [{"sessionId", "at"}]`；事件 `session.taken-over` 的 data 增加 `oldSessionId`、`newSessionId`。
- `status --json` 的 `store.sessions[]` 增加 `self: bool`；`store` 增加 `selfIsCoordinator: bool | null`（读不到会话编号时为 null）。

## 项目结构

```text
module_crew/hooks.py       按会话编号认身份；session_start 接受登记；旧会话提示；bind --takeover
module_crew/store.py       previousSessions 校验
module_crew/__main__.py    写命令会话守门、bind --takeover、status「← 本会话」
module_crew/probe.py       sessions[].self 与 selfIsCoordinator
skills/crew-coordinator/SKILL.md、README.md
tests/test_session_handover.py
```

## 命令

```bash
python3 -m unittest discover -s tests
PYTHONPATH=tests python3 -m unittest test_session_handover
```

## 代码风格

沿用现有模块：代码与注释英文，输出中文；只用标准库；钩子只读文件（接管与守门不在钩子里写）。

## 测试策略

- 钩子：模块协调登记在集成 checkout，会话在另一个 worktree 里启动、压缩、清空（清空走桌面版交接）→ 注入模块协调提示、命令入口与两边目录一行；模块会话同理；未登记的会话照旧按目录。
- 接管：别的 worktree 里 `bind --takeover` 成功、登记改绑、`previousSessions` 有旧编号、事件齐全；没有原话、目标不是模块协调时退出码 3 且不写。
- 旧会话：接管后旧会话编号的每轮一行是失效提示；SessionStart 不再注入模块协调提示。
- 守门：设好会话编号环境变量，登记的会话跑写命令照常；别的会话跑 `merge run`、`change land`、`review approve`、`task dispatch`、`start prepare` 等退出码 7、状态库不变；
  只读与模块侧命令照常；读不到会话编号时不拦；模块协调没登记会话编号时不拦。
- status：本会话那一条带「← 本会话」；非登记会话多一行说明；`--json` 有 `self`、`selfIsCoordinator`。
- 回归：全量测试通过；钩子耗时不变。

## 边界

- **始终**：接管要用户原话；守门拒绝时什么都不写；钩子只读。
- **先问**：自动归档或关掉旧会话；把跨目录接管放开给模块会话、轻任务会话；按钩子目击时间推断会话是否活着。
- **绝不**：不经用户原话改绑登记；读不到会话编号时替用户拒绝；在钩子里写登记。

## 验收标准

1. 模块协调登记在集成 checkout、本会话在别的目录：SessionStart（启动、压缩、清空）注入「本会话是模块协调 <邮箱名>」的提示与命令入口，并有一行写明两边目录；每轮一行照常。模块会话在别的目录时同理。未登记的会话行为不变。
2. `bind <邮箱名> --takeover --original-file` 在同一仓库的别的 worktree 里成功：登记改绑到本会话、`previousSessions` 记下旧编号、事件带原话与新旧编号；原话为空或目标不是模块协调时退出码 3、不写。
3. 被接管的旧会话：每轮一行是「已被接管，不要再以 <邮箱名> 的身份执行写命令」；SessionStart 不再注入模块协调提示。
4. 调用者会话编号与登记不同：模块协调的写命令（至少 `merge run`、`merge approve`、`change land`、`review approve`、`review add`、`inbox add`、`task dispatch`、`start prepare`、`coordinator down`）退出码 7、状态库与集成分支不变，输出含接管命令；
   只读命令、`bind`、`sync`、`host-check`、`hook` 照常；读不到会话编号、或模块协调没登记会话编号时不拦。
5. `status`：本会话那一条带「← 本会话」；调用者不是登记的模块协调时多一行说明与接管命令；`--json` 有 `sessions[].self` 与 `selfIsCoordinator`。
6. README 与 crew-coordinator skill 写明重开的做法（原会话 `/clear` 或重启应用、不新开；新开了用 `bind --takeover`）。
7. 全量测试通过；钩子单次耗时与改前同一量级。

## 未决问题

- 无。关键决策 4（不做「两个活着的会话」检测，改为写命令只认登记的会话、status 标出本会话）用户 2026-10-22 批准 Spec 时接受。

## 文档建议

README「出状况时怎么办」加「换会话（重开、接管）」一条；「命令一览」补 `bind --takeover`。CHANGELOG 随发版写。
