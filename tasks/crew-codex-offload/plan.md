# Implementation Plan: crew-codex-offload

<!-- spec-guard: review pending -->

> 依据：`spec/crew-codex-offload.md`（用户 2026-10-26 批准，事项 C233「C233 A」，集成分支提交 f8fbc4e）。任务清单：`tasks/crew-codex-offload/todo.md`。

## Overview

先打底（开关、外包记录、条件核对 `ready`），再做派出（`offload start` 与任务说明）、收结果（`settle` 的四个分支），
然后续跑与重派、交还与扣下开工通知、`show`，最后改 skill、README，sync 后跑全量测试，并用本机 delegate 0.6.0 实测一次。
每个任务先写失败的测试、看到红再实现到绿，在本模块分支本地提交；不推送、不发版。每个任务都验证「开关关着时行为不变」。

## Architecture Decisions

- **新文件 `module_crew/offload.py`** 集中本模块的逻辑：`enabled(db)`、`set_switch(...)`（供 `config set` 调用）、`ready(db, project, module) -> str | None`（决策 2，返回第一条不满足的原因）、
  `delegate_interface(project)`（只读 interface.json，判 `>=1.1,<2.0` 与 `run.resume`；另报是否 ≥1.2 且 `statuses` 含 `timeout`）、
  `parse_result(text, exit_code) -> Result`（结果行、`NEED_USER:`、分成 done／needs-input／timeout／unknown）、`next_item(todo_text)`（第一个未勾项及是不是 Task）、
  `render_brief(...)`、`start`、`settle`、`resume`、`handback`、`decline`、`show`。其他文件只加一两处调用，减少和 crew-autonomy-tier 的冲突面。
- **状态库**：`store.KINDS` 加 `offload`；键是模块 id，不进 `NUMBERED`。外包的答复原话照 `start prepare --source` 的做法记来源。
- **范围核对**：经 `probe.safe_command(..., "scopeCheck", ...)` 在模块 worktree 跑 spec-guard，`--base` 用派出时记下的 `base`；`outside` 的文件再用 `declared.read(...).inside` 放行（`declared.enabled` 时）；状态 `D` 一律越界。
- **快检查与代提交**：`git add -A -- <改动文件>` 后 `git write-tree` 取树，调 `checks.check_tree(db, cfg, "quick", tree, worktree, "offload", None, False)`；通过才 `git commit`，前缀取 `commits.prefix_of(db)`。git 调用带超时、参数列表、`--no-optional-locks` 读状态。
- **review.py 只动 `approve` 里渲染开工通知的那一段**：抽成 `_start_todo(db, project, m) -> str | None`；返回 None 表示扣下开工通知（外包条件不满足），开关关着返回原文，所以关着时逐字不变。crew-autonomy-tier 改的是 `note`，不同段落。
- **不改 merge.py、probe.py**：`status` 不加外包一段（Spec 决策 12），查看走 `offload show`。
- **delegate 夹具只放 interface.json**：测试不跑 Codex；delegate 的输出由测试写成文本文件喂给 `settle`。实测放在最后一个任务，测不成照实写原因。

## 影响面

新增：`module_crew/offload.py`、`tests/test_codex_offload.py`。
修改：`store.py`（`KINDS`）、`review.py`（`approve` 的开工通知段）、`__main__.py`（`_config_set` 加 `--codex-offload`、`offload` 子命令组）、
`skills/crew-coordinator/SKILL.md`、`codex-skills/crew-coordinator/SKILL.md`、`skills/crew-dev/SKILL.md`、`codex-skills/crew-dev/SKILL.md`、`README.md`。
不新增依赖；不改契约、钩子、`interface.json`、版本号、CHANGELOG（发版时由模块协调写）。公共文件不碰。

## Task List

- [ ] Task 1：打底——`store.KINDS` 加 `offload`；`offload.enabled`；`config set --codex-offload on|off`（checkLedger 没开拒绝、没原话拒绝、条件不满足逐条警告）；`ready` 六项条件（Spec 验收 1、3）
  - 验证：六个缺项各给对应原因；全满足通过；开关写入后读回、事件记原话；全量里与 config、store 相关的回归测试仍过
- [ ] Task 2：`offload start` 与任务说明；`parse_result`（Spec 验收 5、验收 2 的 start 部分）
  - 验证：第一个未勾项是 Task 时记 `running`、任务说明含 Task 原文、三种必停、`NEED_USER:`、不提交不推送不删除，输出 `/delegate:run --write --resumable` 写法；Checkpoint 时不派；不干净、没包含批准提交、已有待处理外包时退出码 3 且不写；开关关时退出码 3
- [ ] Task 3：`settle` 的 done 分支——勾选核对、scopeCheck 范围核对（含名单内放行与删除越界）、暂存区快检查、代提交（Spec 验收 6）
  - 验证：全过时模块分支多一个提交（信息含 Task 编号与 runId）、检查账有 `by: offload`、记录回 `idle`；越界、没勾、勾了别项、快检查失败各自不提交、文件原样、退出码 5、记录 `stopped` 带原因

### Checkpoint 1（report）：派出与 done 代提交就位，本模块测试与 review、checks、declared 相关回归测试通过，记入 todo 后继续

- [ ] Task 4：`settle` 的 needs-input、timeout（1.1 与 1.2）、认不出四个分支；【等待用户】草稿（Spec 验收 7 的前半、8、9）
  - 验证：问题原文逐字相同、草稿被 `protocol.parse` 判合格；超时不调快检查脚本、不提交、输出 status 与 diff --stat 和 ABC 选项；1.2 夹具给 resume 写法、进度说明原样附上；64、其他非 0、无结果行、未知状态、输出读不出都 `stopped`、退出码 5、附最后 20 行
- [ ] Task 5：`offload resume`、`offload start --again`（Spec 验收 7 的后半、8 的后半）
  - 验证：没原话退出码 3；有原话时输出 `--resume <runId> --write` 写法、记下答复与来源；状态不对时退出码 3
- [ ] Task 6：开工通知分叉——`review._start_todo`；`offload decline`；`offload handback`（Spec 验收 4、10、验收 2 的 approve 部分）
  - 验证：开关开且条件满足时开工通知是外包写法、`protocol.parse` 合格；条件不满足时不发开工通知并输出原因；`decline` 带原话发今天的开工通知；`handback` 生成类型「恢复」的通知、记 `handed-back`、之后 `start` 不带 `--again` 被拒；开关关时 `approve` 输出与开工通知逐字不变（用改前输出对照）
- [ ] Task 7：`offload show` 与 `--json`（Spec 验收 11）

### Checkpoint 2（report）：命令全部就位，本模块测试与相关回归测试通过，记入 todo 后继续

- [ ] Task 8：四份 skill 各加一节、README 命令一览与流程一段；`module-crew sync` 合入集成分支后后台跑全量测试；本机 delegate 0.6.0 实测一次（Spec 验收 12、13）
  - 验证：全量测试通过；实测的结果行与 `settle` 输出写进最终验收，测不成照实写原因

### Checkpoint 3（gate）：最终验收

- [ ] 回告：完成情况经模块协调转告 ecosystem-lead（S32 第二节 module-crew 第 6 条已实现）

## 修订（第 2 轮，2026-10-28 重开）

改什么：按意图 `docs/intent/codex-offload-native.md`（2026-10-27 用户确认，S38）改写外包做法——由模块会话自己调用 delegate、同一个 Codex 会话从第一个 Task 做到最后一个（`--resumable` 起头、`--continue` 接续），模块协调不再代调用、代提交；接入 delegate v0.8.0（接口 1.3）的 run.continue、run.longRun、run.result、run.writeAuthorization；退出码 125 归为回收不了；needs-input 问题正文截取时去掉可能出现的 `delegate: result=<路径>` 行；新结束状态 unmarked／failed／interrupted／unreaped／empty 逐个定处理；带 `--resumable` 的长期限中止后收尾轮、长期限下回收不了（125）两项列为已知未验证。

为什么：S38 已批（2026-10-27），delegate v0.8.0 已发布（标签 v0.8.0 → 16290d0），超 540 秒实测已满足。这是改方向，超出原批准范围：Spec 先修订交审，本 Plan 改回待批准，Spec 批准后重写本节以下的任务再交审。

依据：修订后的 `spec/crew-codex-offload.md`（用户 2026-10-28 批准，事项 C306「C306 A」，集成分支提交 6a0aa58，指纹 d94a4167b4c8）。第 1 轮的 Task 1～8 已勾，不重做；下面是第 2 轮的任务（编号 R1～R8，对应 todo「第 2 轮修订」一节）。

### 第 2 轮架构决定

- **仍集中在 `module_crew/offload.py`**，在第 1 轮代码上改，不另起文件：`delegate_interface` 改读 1.3 的五项能力标记；新增 `assign`（开工时写 v2 记录与授权文件）、`classify`（归类表）、`takeover`；`start`／`settle`／`resume` 改为只在模块会话的 worktree 里跑；删掉 `handback` 与 `start_todo_offload` 的旧文案。
- **授权文件放状态库正文目录**：用 `tx.write_body` 写一次（普通文件、0600），记录里存路径与 sha256；`start`／`resume` 每次先核对 sha256，变了就拒绝。
- **身份判断**：`start`／`settle`／`resume`／`takeover` 用 `module-crew bind` 登记的当前会话（与 `review add` 相同的取法）核对是不是该模块的模块会话，`cwd` 须在它的 worktree 里。
- **结果解析分两层**：`read_outputs(stdout, stderr)` 只取结果行、`delegate: result=` 行、`NEED_USER:`／`TIME_UP:` 之后的原文；`classify(exit, line, result_file)` 按 Spec 决策 7 的表给出归类，表外一律「认不出」。结果文件只读顶层 `status`、`exitCode`、`runId`、`authorization`。
- **失败计数放记录的 `failures`**（键是 Task 原文），通过一次清空该键；第 2 次（除 125）直接记入 `claudeTasks`。自动重来的命令由 `settle` 输出，模块会话照着执行，不再经 `start`（`start` 只派下一个未勾的 Task）。
- **done 的核对与提交**沿用第 1 轮 `_settle_done` 的四步，只改提交信息与结果后的去向（记 `head`、清计数）。
- **review.py 只动 `_start_todo`**：开关关着逐字不变；开着时按 Spec 决策 3 分三种情形，条件满足时在同一事务里调 `offload.assign`。
- **测试**：在 `tests/test_codex_offload.py` 上改写；delegate 夹具加 1.3 的 interface.json（完整、各缺一项）与结果文件；第 1 轮专测 handback、1.1 超时的用例删掉或改写。

### 第 2 轮任务

- [ ] R1：`ready` 改读 delegate 1.3 能力标记；条件⑤改为「该模块会话在 Claude Code」（Spec 验收 1）
  - 验证：1.2、1.3 各缺一项（`run.continue`、`run.longRun` 或 `maxSeconds < 1800`、`run.result`、`run.writeAuthorization`、`run.resume` 没有 `timeout`）各给对应原因；spec-guard、信任两项照旧；全满足通过
- [ ] R2：开工交接——`offload.assign`、授权文件、`review._start_todo` 三种情形与新文案；读到第 1 轮旧记录时的处理（Spec 验收 2、3，验收 10 前半）
  - 验证：开关关时 `approve` 输出与开工通知逐字不变（改前输出对照）；条件满足时写 `assigned`、`version: 2` 与授权文件（含原话、模块、批准号，sha256 入记录），开工通知 `protocol.parse` 合格；模块会话在 Codex 照旧发通知并多「不外包」一行；其余不满足扣下通知；`decline` 照旧；旧记录 `start` 退出码 3
- [ ] R3：`offload start` 改由模块会话跑：首次 `--resumable`、之后 `--continue <runId>`，固定 `--strict --timeout 1800 --authorized-by`，后台运行写法；任务说明加 `DONE:` 与接续句（Spec 验收 4）
  - 验证：两种写法各一；非 Task、已退回 Claude、开工时没交给 Codex、不在模块会话、授权 sha256 变、worktree 不干净、没包含批准提交时退出码 3 且不写

#### Checkpoint R-1（report）：交接与派出就位，本模块测试与 review 相关回归通过，记入 todo 后继续

- [ ] R4：`settle` 解析与归类——结果行、`delegate: result=` 行（stdout 或 stderr）、结果文件、授权核对、归类表；needs-input 问题正文截取；timeout 分支（Spec 验收 6 前半、7、8）
  - 验证：归类表每一行与「认不出」四种情形各一个用例；问题正文有无 `delegate: result=` 行都逐字正确；超时不调快检查脚本、不提交、给进度与 ABC、退出码 5
- [ ] R5：done 核对后的去向、失败计数、自动重来命令、退回 Claude、`takeover`、`resume` 新写法（Spec 验收 5、6 后半、9）
  - 验证：done 全过提交并记 `head`；核对不过退出码 4 给 `--continue` 重来命令（任务说明含核对结果）；unmarked／failed／empty 第 1 次给另起链命令；第 2 次记入 `claudeTasks`、之后该 Task 拒派、下一个照常；125 第 2 次仍退出码 5；`takeover`、`resume` 没原话退出码 3
- [ ] R6：命令行——`settle --stderr` 必填、加 `takeover`、去掉 `handback`；`offload show` 与 `--json` 加链上 runId、退回 Claude 的 Task、旧版记录标注（Spec 验收 10 后半、11）
  - 验证：`handback` 参数错退出码 2；`show` 各列齐全

#### Checkpoint R-2（report）：命令全部就位，本模块测试与相关回归通过，记入 todo 后继续

- [ ] R7：四份 skill 的「额度外包」一节重写、README（命令一览、流程一段、「尚未验证」补两项）（Spec 验收 12）
  - 验证：skill 相关测试通过；四份内容与 Spec 决策一致
- [ ] R8：`module-crew sync` 后跑快检查与全量测试（后台）；本机 delegate 0.8.0 在临时仓库实测 `--resumable` 一个小 Task + `--continue` 第二个（Spec 验收 13）
  - 验证：全量通过；两次的结果行、结果文件状态与 `settle` 输出写进最终验收，测不成照实写原因

#### Checkpoint R-3（gate）：最终验收

- [ ] 回告：完成情况经模块协调转告 ecosystem-lead（S38 第五节第 3 步）

### 第 2 轮风险

- delegate 结果文件只用 README 列名的顶层字段；`failed`、`empty` 的退出码文档没写明，按「非 0 + 结果文件状态」判，实测时核对。
- 真实 delegate 运行要花 Codex 额度（R8 两次小运行）；测不成照实写，不阻塞最终验收。
- `handback` 去掉、`settle` 多必填参数是不兼容改动；按 Spec 假设 10 第 1 轮从没真开过。
- 决策 15 两项（`--resumable` 长期限中止后收尾轮、长期限下 125）只用夹具测，写进 README「尚未验证」。

## 变更记录

- 2026-10-28：重开模块，Plan 改回待批准，追加第 2 轮修订一节与 todo 未勾项。原因：外包做法按 S38 意图改方向、接入 delegate 接口 1.3。来源：用户本人在 mc-coord 会话（原话「开工 crew-codex-offload 修订，重开模块写 Spec 交审」）。
- 2026-10-28：Spec 修订获批（C306）后重写「修订（第 2 轮）」一节：补第 2 轮架构决定、任务 R1～R8 与三个检查点、风险。原因：按修订后的 Spec 拆任务。来源：用户本人经 mc-coord 答复「C306 A」。
