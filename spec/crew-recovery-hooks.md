<!-- spec-guard: review pending -->
# Spec: crew-recovery-hooks

> 能力图模块 `crew-recovery-hooks`。需求来源：`docs/requirements-record.md` 第 7 节（恢复五原则；钩子在启动／恢复／压缩及每轮按角色注入；换会话需用户同意 `takeover` 邮箱名一次）、
> B7（宿主：挂起与叫醒、插件更新需新会话、钩子信任）。假设见下文，用户 2026-10-18 已确认。

## 目标

会话被压缩、恢复或换成新会话后，不靠对话记忆也知道「我是谁、该做什么、先核对什么」：插件钩子按角色从状态库生成简短提示，
压缩后要求先核对再动手；换会话时由用户同意一次接管同一个邮箱名，状态库记下这次接管。

## 范围

**范围内**

- `hooks/hooks.json`（SessionStart：startup／resume／compact；UserPromptSubmit）与 `module_crew/hooks.py`、命令 `module-crew hook <事件>`。
- 角色判断、提示文字、压缩后的核对提示。
- 命令 `module-crew takeover <邮箱名> --original-file`。

**范围外**

- 真正向 agent-relay 注册（新会话自己调用）；钩子信任（README 安装说明）。
- 停止钩子、定时巡视（第一版不做）；写角色标记（crew-start 负责）。

## 假设（用户 2026-10-18 已确认）

1. `hooks/hooks.json` 注册 SessionStart（启动、恢复、压缩）与 UserPromptSubmit，统一调 `bin/module-crew hook <事件>` 输出 `additionalContext`；不属于 module-crew 的会话静默（无输出、退出码 0）。
2. 角色：当前 checkout 有角色标记时以标记为准（见关键决策 6）；没有标记时，当前目录是在用模块会话登记的 worktree → 模块会话，是集成分支所在 checkout 且有在用协调会话 → 协调会话。
3. 模块会话注入：模块、邮箱名、协调会话名、当前该做什么（从状态库推出）、自己未关的等待单、crew-dev 规则提醒；协调会话注入：事项／请求／等待单／合并队列计数、先跑 `status`、看「等待审批」。
4. 压缩事件另加：先跑 `module-crew status`、读未完成事项，以状态库为准，不按压缩前记忆重做。
5. 完整提示只在 SessionStart；UserPromptSubmit 每轮一行；钩子只读状态库，不跑 probe 与 `/map`，目标 0.2 秒内；出错静默退出码 0。
6. `takeover <邮箱名> --original-file` 经用户同意：记同意，输出新会话重新注册同一名字的做法；会话登记不变，只追加接管事件。
7. 钩子信任写进 README，本模块不管。

## 关键决策与取舍（请重点审）

1. **模块会话「当前该做什么」只有四档，按状态库推出**：
   - 该模块有 `answered` 的 Spec 与 Plan 交审且都属于某个 `review-approval` → 「已批准，可以构建；做完发最终验收【交审】」；
   - 有 `open` 的 `merge-approval` → 「最终验收已批准，等协调会话合并」；
   - 有 `closedReason: "merged"` 的 `merge-approval` → 「已合入集成分支，停止开发，等收回」；
   - 以上都不是 → 「写 Spec 与 Plan、发【交审】，收到开工通知之前不要构建」。
   最近一次 `merge-approval` 是 `returned` 时，第一档后面加「上次最终验收被退回：<原因首行>」。
2. **路径比较用真实路径**：当前目录与登记的 worktree、集成 checkout 都先 `os.path.realpath` 再比，子目录也算（在 worktree 的子目录里开会话照样识别）。
   集成 checkout 用 `git worktree list --porcelain` 找（读 git 元数据，不跑 probe）。
3. **钩子永不挡对话**：`hook` 子命令捕获一切异常；任何错误都只输出空、退出码 0；`hooks.json` 里的 shell 外壳也 `|| true; exit 0`。
4. **每轮一行的内容**：模块会话 `module-crew：你是 <模块> 的模块会话（<邮箱名>），当前：<档位短语>`；协调会话 `module-crew：协调会话；未关 事项 N／请求 N／等待单 N／待合并 N`。
5. **接管只记同意、不改登记**：`takeover` 要求邮箱名是状态库里在用的会话；记一条该会话的事件（`session.taken-over`，带原话与时间），记录内容不变；
   输出写明新会话应「用同一个名字 `bridge_register`，按 agent-relay 的提示传接管／恢复参数，`wake: "auto"`」。

6. **角色以 spec-guard 角色标记为准**（2026-10-18 修订）：从当前目录向上找到 checkout 根（含 `.git` 的目录），按 interface 1.1 `checkoutRole.marker` 读该 checkout 自己 git 目录下的 `spec-guard/role`
   （`.git` 是目录就读 `.git/spec-guard/role`；是 `gitdir:` 文件就读所指目录下的；只读文件，不跑子进程）。内容只认一行 `module <id>` 或 `coordinator`：
   - `module <id>` 且状态库有该模块的在用模块会话 → 模块会话（不再要求路径与登记一致，worktree 换了位置也认）；
   - `coordinator` 且状态库有在用协调会话 → 协调会话；
   - 有标记但状态库对不上（模块已退役、没有协调会话）→ 静默，不退回按路径判断；
   - 没有标记、标记不合法（多行、超长、链接、不认识的内容）→ 按原来的路径规则判断（兼容 spec-guard 0.67 与未开 `moduleConcurrency` 的项目）。
7. **钩子给出本会话该用的命令入口**（2026-10-22 新增，0.11.1）：SessionStart（启动、恢复、压缩、清空）的完整提示，对模块协调、模块会话、轻任务会话都多一行「module-crew 命令入口：`<本次运行的插件目录>/bin/module-crew`（版本 <插件版本>）；用这一行，不用记忆、开工背景或别的会话给的路径」。插件目录取钩子自己运行的那份 module-crew（宿主按当前加载的插件调起钩子），版本取它旁边 `.claude-plugin/plugin.json` 的 `version`，读不出写「版本未知」。每次重开、压缩、清空都会重新给，插件升级后会话自然换到新路径。crew-coordinator、crew-dev 两份 skill 与模块会话、轻任务会话的开工说明同步改为「命令入口以钩子注入的那一行为准，不要把带版本号的绝对路径记进记忆、开工背景或转给别的会话」。每轮一行（UserPromptSubmit）不加这一行。


## 接口约定

### hooks.json（要点）

```json
{"hooks": {
  "SessionStart": [{"hooks": [{"type": "command", "command": "ROOT=\"${PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-}}\"; BIN=\"$ROOT/bin/module-crew\"; if [ -n \"$ROOT\" ] && [ -x \"$BIN\" ]; then \"$BIN\" hook session-start || true; fi; exit 0"}]}],
  "UserPromptSubmit": [{"hooks": [{"type": "command", "command": "…\"$BIN\" hook prompt…"}]}]
}}
```

SessionStart 的事件来源（startup／resume／compact）从钩子标准输入的 JSON `source` 字段读；读不到按 startup。

### 输出

```json
{"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": "<中文提示>"}}
```

不属于 module-crew 时什么都不输出。

### 命令

```bash
bin/module-crew hook session-start|prompt      # 读标准输入的钩子 JSON；只读；永远退出码 0
bin/module-crew takeover <邮箱名> (--original <原话> | --original-file <文件>)   # 0 成功；3 不是在用会话或原话为空
```

## 项目结构

```text
hooks/hooks.json
module_crew/hooks.py
module_crew/__main__.py       加 hook、takeover
tests/test_hooks.py
```

## 命令

```bash
python3 -m unittest discover -s tests -v
```

## 代码风格

沿用前几个模块；`hooks.py` 只 import `store`（和标准库），不 import `probe`、`start` 等会跑子进程的模块（测试扫描断言）。

## 测试策略

- 复用 crew-merge 的测试基类，在不同目录（模块 worktree 及其子目录、集成 checkout、无关目录、没建库的仓库）以子进程方式运行 `bin/module-crew hook ...`，喂入钩子 JSON，检查输出。
- 四档状态各构造一次；压缩事件检查核对提示；耗时断言在 1 秒内（宽松，防 CI 抖动），并记录实测值。
- 人为弄坏状态库（非法 `meta.json`）时仍退出码 0 且无输出。

## 边界

- **始终**：只读；静默失败；提示简短。
- **先问**：给不属于 module-crew 的会话注入任何内容；在钩子里写文件或跑子进程（git 元数据读取除外）。
- **绝不**：挡住对话（非零退出或报错输出）；替会话注册邮箱。

## 验收标准

1. 无关目录、没建库的仓库、未登记的 checkout：`hook session-start` 与 `hook prompt` 都无输出、退出码 0。
2. 模块 worktree（及其子目录）：SessionStart 输出含模块 id、邮箱名、协调会话名、当前档位、自己未关的等待单编号、「crew-dev」；UserPromptSubmit 只输出一行。
3. 四档状态分别构造：写 Spec 等批准／已批准可以构建／等合并／已合入，各输出对应短语；上次被退回时附原因首行。
4. 集成 checkout：SessionStart 输出协调会话提示，含四类计数、`module-crew status`、「等待审批」；UserPromptSubmit 一行。
5. 事件来源为 compact 时，额外含「先跑 `module-crew status`」「以状态库为准」「不按压缩前的记忆重做」。
6. `meta.json` 损坏或任意异常：无输出、退出码 0；单次运行耗时 1 秒以内（记录实测值）。
7. `hooks.json` 合法，两个事件都调用 `bin/module-crew hook`，外壳带 `|| true` 与 `exit 0`；`hooks.py` 不 import `probe`／`start`／`review`／`merge`／`subprocess`。
8. `takeover shop-b --original "让新会话接管"`：记一条 `session.taken-over` 事件（原话、时间），会话记录不变，输出重新注册的做法；不在用的名字或原话为空时退出码 3。
9. 角色标记：worktree 标记为 `module b` 时按 b 的模块会话注入（含 worktree 被移到别处、登记路径对不上的情况）；集成 checkout 标记为 `coordinator` 时按协调会话注入；
   标记为 `module x`（没有在用会话）时静默；没有标记或标记不合法时结果与修订前相同；仍不 import `subprocess`。

10. 最终验收已交审、还没批准（有未关的 node 为 final 的交审）：档位为「最终验收已交审（交审事项 #N），等用户批准；不要重做或重发」；只读出口的 `stage` 仍为 `build`，只改 `stageText`。
11. 模块协调、模块会话、轻任务会话的 SessionStart 输出（启动、压缩、清空三种来源）都含「module-crew 命令入口：<插件目录>/bin/module-crew（版本 X）」，路径与版本取自运行钩子的那份插件；`plugin.json` 读不出时写「版本未知」、其余照常；陌生会话的提醒与每轮一行不含这一行。两份 skill 与两种开工说明不再写插件目录的具体路径，写明以钩子注入的为准。


## 未决问题

- 无（角色标记按 interface 1.1 定稿接入；0.68.0 发版后在第 7 关用真实版本再核一次）。

## 文档建议

README 的安装说明写「首次使用需在 Claude Code 里信任 module-crew 的钩子；插件更新后要开新会话才生效」。

## 变更记录

- 2026-10-18：角色判断改为以 spec-guard 角色标记为准（关键决策 6、验收 9），没有标记时保留原路径规则；删去对应未决问题。原因：interface 1.1 定稿 `checkoutRole`（标记位置 `git rev-parse --git-path spec-guard/role`、取值 `module <id>`／`coordinator`）；来源：spec-guard 负责人通知 interface.json 1.1 定稿（spec-guard 分支 `claude/module-concurrency` 提交 6231abc，0.68.0 未发版），用户 2026-10-18 复审批准。
- 2026-10-18：新增「最终验收已交审、等批准」档位（只读出口 stage 枚举不变，仍报 build），增加验收 10。原因：试点问题 J（恢复说明在已交最终验收时仍写「可以构建」）；来源：第二轮试点（`docs/pilot-report.md` 第二轮一节），用户 2026-10-18 批准修法。
- 2026-10-22：新增关键决策 7 与验收 11：SessionStart 的完整提示注入本次运行的插件目录下的命令入口与版本，skill 与开工说明改为以它为准、不记带版本号的路径；发 0.11.1。原因：模块协调第一次把「插件目录下的 bin/module-crew」解析成 `module-crew-release/v0.10.0/…` 记进记忆并抄进开工背景，之后升级、清空都没换，0.10.1～0.11.0 的修复没生效（spec-guard 负责人报告 O8）；来源：用户 2026-10-22 批准并进 0.11.1（「2 并进」），本修订待复审。
