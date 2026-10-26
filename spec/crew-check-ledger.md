# Spec: crew-check-ledger

<!-- spec-guard: review pending -->

> 能力图模块 `crew-check-ledger`（第十版第 2 个）。需求来源：已批方案 plugin-ecosystem `proposals/2026-10-24-S32-并行流畅与额度外包.md`（612634c，用户 2026-10-24 批准「按推荐批准」）第二节 module-crew 第 3、4 条，第三节守门；
> 方案第五节决定 3：快检查命令由项目自己写成脚本。开会话依据：用户批准事项 C201。
> 依赖 `crew-merge`（合并队列与完整检查）、`crew-background-checks`（合并锁、后台运行）、`crew-light-task`（bug 任务）。标「新」的是写 Spec 时补的实现取舍，请重点审。

## 目标

多模块并行时，同步与核验类提交占了大头（LIVE-SAAS canvas 61%），同一基线失败被各模块重复记录（11 次）。这一版把两种检查分开、把检查结果交给工具记账：

- 平时（同步后、提前落地前、自测）只跑项目写好的**快检查**（只跑受影响部分）；**完整检查只在合并队列里跑**。
- 按**树哈希**记下「这棵树跑过哪条检查、结果如何」，同一棵树不重跑；模块会话不再自己写、提交证据文件，最终验收直接引用检查账。
- 集成基线在后台只跑一次完整检查、记一次账；基线红了自动建一个「修基线」的 bug 任务，不再让每个模块各记一遍。

全部行为在项目开关 `checkLedger` 打开后才生效；开关默认关，凭用户原话打开。没打开的项目和今天完全一样。

## 范围

**范围内**

- 项目配置新增 `quickCheckCommand`（快检查命令）与开关 `checkLedger`（`on`／`off`，没有即 `off`），经 `config set` 写入，要用户原话。
- 状态库新增记录种类 `check`（检查账），按「树哈希 + 检查种类」记结果。
- 新命令 `module-crew check quick|baseline|show|list`。
- 开关打开后：`merge run` 的完整检查结果记账；同步、落地、恢复、轻任务开工等通知里的「跑完整检查」改为「跑快检查」；`change land` 提交前先跑快检查；
  最终验收【交审】记账时自动附上那棵树的检查账；基线红了自动建修基线的 bug 任务。
- `status` 显示开关、集成基线的检查账状态。
- `crew-dev`、`crew-coordinator` 两个 skill 补开关打开后的做法。

**范围外**

- module-crew 按改动文件推断「受影响部分」（方案决定 3：由项目脚本负责）。
- 合并队列里跳过完整检查（守门：合并队列里一定跑完整检查，见关键决策 4）。
- 自治档位 `relaxed` 把快检查、记账类通知改为收尾汇总（crew-autonomy-tier；本模块只提供 `check list --json` 供它读）。
- Codex 模块协调的分离运行（`check baseline` 不做 `--detach`，Codex 模块协调前台跑；见未决问题）。
- 声明目录内公共文件直接改与自动落地（crew-declared-scope）；本模块只在 `change land` 提交前插一步快检查，自动落地走 `change land` 时自然带上。

## 假设（请逐条确认）

1. **一个开关管全部**：`checkLedger: on` 同时打开「两种检查分开」「检查记账」「基线后台检查与自动建修基线任务」三件事，不再细分开关。打开前必须已有 `checkCommand`（完整检查）和 `quickCheckCommand`。
2. **快检查命令由项目写成脚本**（例如 `pnpm check:affected`），module-crew 只负责在干净的树上运行它、记账；「受影响」相对什么由脚本自己定（通常相对集成分支）。
3. **快检查沿用 S30「不经 shell 执行」**：`shlex.split` 成参数列表运行，写入时拒绝含 shell 运算符的命令（同 `checkCommand` 的规则与提示）；超时沿用 `checkTimeout`。
4. **只给干净的树记账**：工作区有未提交改动或未跟踪文件（不含被忽略的）时不跑、不记，树哈希取 `HEAD^{tree}`；`change land` 取暂存区的树（`git write-tree`）。
5. **自动建的修基线任务以打开开关时的用户原话为依据**：任务记录的「用户原话」写「（自动建立）依据项目开关 checkLedger 打开时的用户原话：<原话>」。派出照现有轻任务流程，不自动派。
6. 本模块不依赖 spec-guard 的新接口（declaredScope、autonomyTier 都不读），所以没有「读不到新接口」的情况；开关没打开或配置不全时一律照今天做。
7. 旧版 module-crew 读到 `check` 记录会当成「不认识的行」跳过并警告（与 `sighting`、`task`、`handover` 新增时相同），不会损坏状态库；固定入口只跑一个版本，正常不会碰到。

## 关键决策与取舍（请重点审）

1. **（新）检查账的键与内容**：记录种类 `check`，键 `<树哈希>.<quick|full>`；内容
   `{"tree", "kind", "command", "result": "pass"|"fail", "exitCode", "tail"（输出最后 40 行）, "commit", "where"（worktree 或集成 checkout 路径）, "by"（会话名或 merge-run／baseline）, "startedAt", "seconds", "inheritedFrom"（见决策 5，平时为 null）}`。
   同一个键再记一次覆盖当前值，历史留在事件日志里。**超时、跑不起来（退出码 126／127、找不到程序）不记账**，只报出原因，下次照常再跑。
2. **（新）「同一棵树不重跑」的判定**：同一个键已有记录、且记录里的 `command` 等于当前配置的命令，就直接报出记录的结果（通过退出码 0、失败退出码 5），不再运行；
   快检查时，这棵树已有**通过**的完整检查也算满足。命令改过就当没跑过。要强制重跑加 `--rerun`（环境修好、怀疑偶发失败时），重跑结果覆盖旧记录。
3. **（新）`check quick` 在哪能跑**：模块 worktree、轻任务 worktree（登记过的会话）里；集成 checkout 里只经 `change land` 跑。退出码：`0` 通过（新跑或已记）、`5` 失败、`3` 拒绝（开关没开、没有 `quickCheckCommand`、工作区不干净、不在登记过的 worktree）、`4` 超时或跑不起来（不记账）。
   失败时若集成基线的完整检查记录是红的，输出多一行「集成基线 <短哈希> 的完整检查也是红的（修基线任务 T<号>）：先看失败是不是来自基线，是就不用另记、照常继续」。
4. **合并队列照旧每次都跑完整检查**：`merge run` 不因检查账跳过完整检查（守门「合并队列里一定跑完整检查」；合并出来的树几乎总是新的，跳过也省不了多少）。只是开关打开后，跑完把结果（通过或失败）记进检查账，`by` 写 `merge-run`。
5. **（新）合并后的勾选、批准标记提交继承检查账**：`merge run` 合入通过后还会做勾选最终验收（改 `tasks/<模块>/todo.md`）、记修订后 Spec 的批准（改 `spec/<模块>.md` 标记行）两种提交，集成分支顶端的树因此不是跑过检查的那棵。
   开关打开时，`merge run` 在这两步之后给顶端的树另记一条完整检查「通过」，`inheritedFrom` 写合并提交的树；只在这两步确实只改了这两个文件时这样记，否则不记（基线会显示「没跑过」，由 `check baseline` 补跑）。
   取舍：项目检查若会检查 Markdown 格式，这两处改动理论上可能让检查变红；但它们由 spec-guard 生成、格式固定，补跑一次完整检查的代价（几分钟到半小时）更不划算。
6. **（新）基线检查 `check baseline`**：只在模块协调会话里跑，在集成 checkout 上对集成分支顶端的树跑完整检查并记账（`by: baseline`）；已有记录就不重跑（决策 2，`--rerun` 例外）。
   跑之前拿合并锁（`crew-background-checks`，锁记录写「基线检查」而不是合并批准事项号），跑的时候合并和别的写集成 checkout 的命令被挡住（退出码 6），反过来合并在跑时它也退出码 6。
   由模块协调用 Bash 的后台运行启动（与 `merge run` 相同），不自己起子进程。什么时候跑：`status` 显示「集成基线 <短哈希>：完整检查没跑过」时（`change land`、不经队列的提交、刚开工之后），`change land`、`unqueued` 的输出也提示一句。
   合并队列合入后有决策 5 的记录，不用再跑。退出码：`0` 通过、`5` 失败、`3` 拒绝（开关没开、不是模块协调、集成 checkout 不干净）、`4` 超时或跑不起来、`6` 合并锁被占。
7. **（新）基线红了自动建修基线任务，只建一次**：`check baseline` 失败（新跑出来的失败，不是读到的旧记录）时，用 `tasks.add` 建一个 bug 任务：
   标题「修基线：集成分支 <短哈希> 完整检查失败」，做什么写退出码与 FAIL／ERROR 开头的行（最多 5 行，同 `merge run` 的退回通知），完成标准写「集成分支上完整检查通过」，
   预计改的文件取「上一个完整检查通过的基线提交」到当前顶端之间改过的文件；检查账里没有通过过的基线时**不自动建**，输出「没有可比的绿基线，请用户说明要修哪些文件后用 task add 建任务」。
   任务记录多一个字段 `baseline: {"tree", "commit"}`。已有一个没结束（不是 merged、cancelled、promoted）的修基线任务时不再建，输出它的编号；同一棵树读到旧的失败记录时也不再建。
   任务照现有规则排队（预计文件与在做的模块重叠就 `queued`），派出照现有轻任务流程。
8. **（新）通知措辞跟着开关走**：`sync.STEP` 后面接的「跑完整检查后继续」集中成一个函数，开关打开时改为「跑 `module-crew check quick`（快检查）后继续」。
   用到的地方：合并后的同步基线通知（`merge._close_merged`）、公共变更落地后的同步通知（`changes.land`）、挂起恢复时的补同步（`failure`）、不经队列提交后的同步通知（`unqueued.notify`）、`sync` 合并完的最后一行、轻任务开工说明里的交回条件（`tasks.render_kickoff`）。
9. **（新）`change land` 提交前先跑快检查**：开关打开时，`git add` 清单文件后用 `git write-tree` 取暂存区的树，在集成 checkout 上跑快检查（同决策 2 的判定，记账 `by: change-land`）；
   失败或跑不起来就不提交、文件保持暂存、退出码 5（失败）或 4（跑不起来），输出失败行，请求保持打开，交用户决定（修好后再 `change land`，或用户同意后加 `--skip-quick-check --original-file` 跳过，跳过也记进请求记录）。
10. **（新）最终验收引用检查账，不写证据文件**：开关打开时，`review add` 收到最终验收【交审】（模块和轻任务都算）后，按交审提交的树查检查账，把查到的快检查、完整检查记录（键与结果）记进交审事项的 `checks`，
    `review show` 与 `review batch` 显示一行「检查账：快检查 通过（树 <短哈希>）」；查不到时显示「检查账：这棵树没跑过快检查」并在 `review add` 的输出里提醒，**不拒收**。
    `crew-dev` skill 写明：开关打开后，「验收结果」里测试类条目写「见检查账（树 <短哈希>，快检查通过）」，不再提交测试输出、证据文件。
11. **配置写入**：`config set --quick-check-command "<命令>"`、`config set --check-ledger on|off`，都要 `--original`／`--original-file`。
    快检查命令照 `checkCommand` 的 S30 规则校验；打开开关时缺 `checkCommand` 或 `quickCheckCommand` 就拒绝（退出码 3，说明先设哪个）。关掉开关不删检查账，只是不再用。

### 要改 `module_crew/merge.py` 的哪几处（供模块协调排开工顺序）

- `_run_check`：返回原因不变；开关打开时把结果记进检查账（通过、失败都记；超时与跑不起来不记）。
- `_run`：合入通过、勾选与批准标记提交之后，按决策 5 给顶端的树记继承的完整检查记录。
- `_close_merged`：同步基线通知的「要你做什么」改用决策 8 的函数。
- 不改 `_check_config`、`_SHELL_OPS`、`run`、`_hand_off` 与合并锁的用法；快检查命令的校验在新文件里复用 `_SHELL_OPS`。

其他会碰的现有文件：`store.py`（`KINDS` 加 `check`）、`mergelock.py`（锁记录可写「基线检查」）、`sync.py`、`changes.py`（`land`）、`failure.py`、`unqueued.py`、`tasks.py`（`render_kickoff`）、
`review.py`（`add`、`_add_task`、`show`、`batch` 的显示）、`probe.py`（`status`）、`__main__.py`。其中 `changes.land` 与 `review.py` 的最终验收显示，crew-declared-scope 也可能改。

## 接口约定

### 配置（`config` 记录 `main`）

```json
{"checkCommand": "python3 -m unittest discover -s tests", "checkTimeout": 1800,
 "quickCheckCommand": "scripts/check-affected", "checkLedger": "on"}
```

### 检查账（记录种类 `check`）

```json
// key: "<tree>.quick" | "<tree>.full"
{"tree": "<40 位>", "kind": "quick", "command": "scripts/check-affected", "result": "pass", "exitCode": 0,
 "tail": "...", "commit": "<跑时的提交，change land 时为 null>", "where": "/path/to/worktree", "by": "shop-b",
 "startedAt": "...", "seconds": 42, "inheritedFrom": null}
```

### 任务记录

修基线任务多 `"baseline": {"tree": "...", "commit": "..."}`；其他字段不变。

### 命令

```bash
bin/module-crew config set [--quick-check-command "<命令>"] [--check-ledger on|off] (--original <原话> | --original-file <文件>)
bin/module-crew check quick [--rerun]                 # 模块或轻任务 worktree 里
bin/module-crew check baseline [--rerun]              # 模块协调，放后台跑
bin/module-crew check show [<提交>] [--json]          # 只读：这个提交的树有哪些检查记录，默认 HEAD
bin/module-crew check list [--limit N] [--json]       # 只读：最近的检查账，最新在前
bin/module-crew change land <C号> [--skip-quick-check] …   # 跳过要原话
```

- `status --json` 的 `store` 多 `checks`：`null`（开关没开）或 `{"ledger": "on", "quickCheckCommand", "baseline": {"commit", "tree", "full": "pass"|"fail"|null, "inherited": bool}, "baselineTask": <号或 null>}`。
- 退出码：`0` 通过、`3` 拒绝、`4` 超时或跑不起来、`5` 检查失败、`6` 合并锁被占（只 `check baseline`）。

## 项目结构

```text
module_crew/checks.py         新：检查账读写、跑检查、快检查、基线检查、建修基线任务、通知措辞
module_crew/merge.py          _run_check、_run、_close_merged（见上）
module_crew/store.py          KINDS 加 check
module_crew/mergelock.py      锁记录可写基线检查
module_crew/sync.py, changes.py, failure.py, unqueued.py, tasks.py, review.py, probe.py, __main__.py
skills/crew-dev/SKILL.md, skills/crew-coordinator/SKILL.md
tests/test_check_ledger.py    新
```

## 命令

```bash
python3 -m unittest discover -s tests
PYTHONPATH=tests python3 -m unittest test_check_ledger
```

## 代码风格

沿用现有模块：代码与注释英文，输出中文；只用标准库；外部命令参数列表、带超时、不经 shell；git 状态读取用 `--no-optional-locks`。

## 测试策略

- 复用 crew-merge／crew-light-task 的测试基类（b、c 两个模块会话、集成 checkout）；快检查、完整检查用临时目录里的小脚本（按文件是否存在决定成败，记下被调用次数以验证「不重跑」）。
- 开关关着：所有现有测试原样通过，通知措辞、`merge run`、`change land`、`review add` 的输出不变，状态库里没有 `check` 记录。
- 并发：基线检查跑着时另起进程跑 `merge run`，退出码 6，反之亦然。

## 边界

- **始终**：开关默认关、凭用户原话开关；合并队列里每次都跑完整检查；只给干净的树记账；检查命令不经 shell。
- **先问**：打开或关掉开关；改快检查命令；`change land` 跳过快检查；派出自动建的修基线任务（照现有派出规则）。
- **绝不**：凭检查账跳过合并队列里的完整检查；给不干净的工作区记账；超时或跑不起来记成通过或失败；同一次基线失败建两个修基线任务；删除检查账记录。

## 验收标准

1. 开关关着（默认）：全量测试原样通过；`sync`、`merge run`、`change land`、`unqueued --notify`、`resume`、`task dispatch`、`review add` 的输出与通知措辞和今天一致；状态库没有 `check` 记录；`check quick`、`check baseline` 退出码 3 并说明开关没开。
2. `config set --check-ledger on` 缺 `quickCheckCommand` 或 `checkCommand` 时退出码 3、配置不变；`--quick-check-command` 含 shell 运算符时被拒、提示改写法；没给原话时被拒；写入后 `status` 显示开关与命令。
3. `check quick` 在干净的模块 worktree 里跑快检查并记账（键 `<树>.quick`，结果、命令、会话名正确）；同一棵树再跑不调用脚本、报出记录的结果；`--rerun` 重新调用并覆盖；改了快检查命令后重新跑；这棵树已有通过的完整检查时不跑。
4. `check quick` 工作区有未提交改动或未跟踪文件时退出码 3、不记账；脚本失败退出码 5 且记为 fail；超时或找不到程序退出码 4 且不记账。
5. 开关打开时 `merge run` 照常跑完整检查（脚本被调用），结果记账（`by: merge-run`）；通过后勾选提交之后的顶端树有一条 `inheritedFrom` 指向合并树的完整检查通过记录；合并后多出别的文件改动时不记继承记录。
6. 开关打开时，合并后的同步基线通知、`change land` 的同步通知、`unqueued --notify`、恢复时的补同步、`sync` 最后一行、轻任务开工说明都写「跑 `module-crew check quick`」，都能被 `protocol.parse` 判为合格。
7. `check baseline`：在集成分支顶端的树跑完整检查并记账（`by: baseline`）；已有记录不重跑；不是模块协调时退出码 3；合并锁被占时退出码 6；它跑着时 `merge run` 退出码 6。
8. 基线失败且检查账里有过通过的基线：自动建一个 bug 任务（标题、做什么含失败行、预计文件为两次基线之间改过的文件、`baseline` 字段、原话写明依据开关）；再跑一次（读到旧记录）或在新的红基线上再跑，都不再建第二个，输出已有任务编号；没有通过过的基线时不建、输出提示。
9. `check quick` 失败、且集成基线完整检查是红的时，输出带修基线任务编号的那一行。
10. `change land` 开关打开时：快检查通过才提交并记账；失败时不提交、文件保持暂存、退出码 5、请求仍开着；`--skip-quick-check` 没有原话被拒，有原话时跳过并记进请求记录。
11. 最终验收【交审】（模块与轻任务）：`review add` 把交审树的检查账记进 `checks`，`review show`／`review batch` 显示「检查账」一行；查不到时提醒但照常收下。
12. `status` 显示「集成基线 <短哈希>：完整检查 通过／失败／没跑过」与修基线任务编号；`--json` 有 `checks`。`check show`、`check list --json` 列出记录。
13. 两个 skill：`crew-dev` 写明开关打开后同步后跑 `check quick`、最终验收引用检查账、不提交证据文件；`crew-coordinator` 写明设开关要用户原话、`check baseline` 放后台跑、红基线的修基线任务怎么处理。
14. 全量测试通过。

## 未决问题

- Codex 模块协调没法用 Bash 后台运行 `check baseline`（`merge run` 有 `--detach`）：这一版前台跑；用下来嫌慢再照 `merge run` 加 `--detach`。
- 方案第一节第 5 条的四个数在 LIVE-SAAS 下一轮量（livesaas-lead），本模块只负责让「同一基线失败重复记录」可以从检查账和任务记录里数出来。

## 文档建议

README「命令一览」补 `check quick|baseline|show|list` 与 `config set --quick-check-command／--check-ledger`；「一次完整流程」补一段「打开检查记账后：平时快检查、合并跑完整检查、基线红了自动建修基线任务」。CHANGELOG 随发版写。
