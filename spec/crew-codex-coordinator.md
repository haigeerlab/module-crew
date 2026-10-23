# Spec: crew-codex-coordinator

<!-- spec-guard: review approved 5ac3af7aa37e -->

> 能力图模块 `crew-codex-coordinator`（第八版，接缝 S13 的模块 B）。需求来源：用户 2026-10-23 在 ecosystem-lead 会话同意开工模块 B，
> 同日在 mc-coord 会话批准插入能力图并开工（批准事项 C30）。S13 修订版范围：一批收尾后的空档里，模块协调与模块会话整体在 Claude Code 与 Codex 之间来回切换。
> 依赖 `crew-host-handover`（`coordinator handover`、宿主跟随、`bind --takeover` 认宿主）、`crew-codex-host`（Codex 模块会话、`host-check`、Codex 版 crew-dev）、
> `crew-command-entry`（固定入口）、`crew-background-checks`（合并锁）。
> 已有事实：阶段 0 实测（2026-10-23，Codex 桌面版 workspace-write 沙箱，探测分支 `probe/codex-s3` 的 `S3-RESULT.md`）、sg-coord（spec-guard 接口 1.10 读码）、
> agent-relay PR #154 实测、decision-inbox `docs/host-differences.md`（H1–H5、H8、H10、H11、H17、H25）。标「新」的是写 Spec 时补的实现取舍，请重点审。

## 目标

模块协调能在 Codex 桌面版上跑完一批：开模块、收发消息、记账、交审与转达批准、合并与收尾、推送。具体是：

- 插件带一份 Codex 版 `crew-coordinator` skill，写清 Codex 上没有钩子、每轮重新注册、每次醒来先跑 `status`、写 `.git` 要提权、模块会话由用户手动开；
- 写 `.git` 的命令在 Codex 沙箱里怎么提权有一套固定做法，`host-check` 能在集成 checkout 里替模块协调预检；
- 十几分钟的合并检查在 Codex 上不靠「后台跑、跑完叫醒」也能跑完、结果不丢；
- 有了这份 skill，`coordinator handover --to codex` 自然放开（crew-host-handover 关键决策 6），空档整体来回换宿主两个方向都能走通。

## 范围

**范围内**

1. Codex 版模块协调 skill：`codex-skills/crew-coordinator/SKILL.md`。与 Claude 版共同的规矩照写，Codex 特有的另起一节（见关键决策 1）。
2. 放开「模块协调只能是 claude-desktop」剩下的地方：模块协调在 Codex 时，所有协调命令照常可用；`coordinator up` 的去留见假设 3。
3. 无钩子时醒来先跑 `status`：skill 写明每轮开头的固定动作；`status` 在 Codex 里运行时多显示一行「本会话是谁」（关键决策 4）。
4. Codex 侧定位插件：module-crew、spec-guard、agent-relay 在 Codex 里怎么找到，找不到时怎么说（关键决策 5）。
5. 模块会话由用户手动开的指引：模块协调在 Codex 时，`start prepare`、`task dispatch` 输出逐步告诉用户去 Codex 开任务（沿用 crew-codex-host 的做法，补到协调 skill）。
6. 写 `.git` 的提权方案（关键决策 2）与 `host-check` 支持模块协调（关键决策 3）。
7. 合并长检查在 Codex 上的跑法：`merge run --detach` 与 `merge result`（关键决策 6）。
8. `handover --to codex` 放开：靠第 1 项的文件存在，`handover.py` 不改判断；验收里补一条端到端。
9. 文档：README「换宿主」一节补「模块协调在 Codex 上」；`.codex-plugin/plugin.json` 的描述改掉「协调会话在 Claude 桌面版」。

**范围外**

- 模块做到一半换宿主；协调与模块长期混搭两边；Codex 模块协调叫醒 Claude 模块会话（S13 修订版明确不做）。
- 自动看额度、自动换宿主。
- 改 agent-relay、decision-inbox、spec-guard；改契约。
- 在任何 checkout 写 AGENTS.md 或 Codex 钩子配置。
- 改 `module_crew/review.py`（轻任务 T26 正在改，见「并行边界」）。

## 假设（请逐条确认）

1. **只支持 Codex 桌面版**（ChatGPT 应用里的 Codex）作模块协调，不支持 Codex 命令行版；同一台 Mac。
2. **模块协调在 Codex 时，本批模块会话、轻任务会话全在 Codex**（crew-host-handover 假设 7 已定：Codex 叫不醒停掉的 Claude 会话，H4）。
3. **（新）`coordinator up` 仍只在 Claude 里升级**：一个项目第一次起模块协调照旧在 Claude 桌面版，换到 Codex 只走 `coordinator handover`。
   这样状态库校验（Codex 模块协调必须带 `hostHandover`）不用改。另一个选择是放开 `coordinator up` 在 Codex 里直接起，请用户定（未决问题 1）。
4. **module-crew 不在 Codex 的 PATH 上**，Codex 协调一律用固定入口 `<git公共目录>/module-crew/bin/module-crew`；固定入口读 Claude 的插件安装记录，
   阶段 0 已实测 Codex 沙箱里能读、`status` 体检全绿。所以本机必须装着 Claude Code 版的 module-crew（Codex 侧的 module-crew 安装只提供 skill）。
5. **Codex 沙箱不让写 `.git`**（H11，阶段 0 实测 `host-check` 报写不了 `.git/worktrees/<名>`、`git add` 因 `index.lock` 被拒）。模块协调的写命令几乎都写状态库（在 git 公共目录下），
   所以**每条 module-crew 写命令与 git 写操作都要申请在沙箱外运行**；阶段 0 那次申请没弹出要用户点的确认（像是自动审批放行，没做对照），一次批准能否覆盖之后的命令要在演练里实测。
6. **审批照旧由用户在模块协调所在的会话里亲口给**（H10）：Codex 协调把用户在本线程里说的原话写进原话文件，和 Claude 上一样；别的会话转来的话不算。
7. **Codex 线程每轮重启 MCP**（H25）、会丢联调身份（H3）：每轮开头用 `bridge_register {agent:<邮箱名>, wake:{app:"codex", sessionId:<CODEX_THREAD_ID>}}`（不带 takeover）重新注册。
8. **Codex 没有「后台跑、跑完叫醒」**：命令要么在本轮工具调用里跑完，要么脱离本轮在后台跑、下一轮再去看结果；单次工具调用的最长等待时间未实测，按「十分钟以上不可靠」设计。
9. **决策收件箱照旧在 Claude**：Codex 协调经 agent-relay 给收件枢纽发【等待用户】、收【用户答复】；收件枢纽是循环巡视的 Claude 会话，平时醒着。
   它被桌面版停掉时 Codex 协调叫不醒它（H4），skill 写明这时请用户去点开收件枢纽会话；不改 decision-inbox。
10. **spec-guard 在 Codex 里只有技能、没有斜杠命令**：模块协调用到的 sg-coord 接口（mapView、reviewMark、gateTick、scopeOverlap）只依赖 `python3` 与 `git`、不读 `~/.claude`、不判断宿主，
    由 module-crew 命令自己调用，Codex 上照样可用；reviewMark、gateTick 只写 `spec/<id>.md` 与 `tasks/<id>/`，在集成 checkout 内，不需要提权（提交那一步需要）。
    没人在 Codex 上走通过 Spec／Plan／交审／批准，列入实地验证。
11. 契约不改；验收以夹具测试为主；实地在 Codex 上跑一批、来回换一次，放进演练、经用户同意才开始。

## 关键决策与取舍（请重点审）

1. **（新）Codex 版协调 skill 单独一份，不在 Claude 版里加条件分支**（与 crew-codex-host 决策 2 同理）。结构：
   - 「Codex 特有的几件事（先读）」放最前：固定入口；每轮开头三步（重新注册 → `status` → 读收件箱）；写命令申请在沙箱外运行；
     没有钩子与压缩后不抓最近一条人工输入当任务（H17）；模块会话、轻任务会话都由用户手动开；Codex 叫不醒停掉的 Claude 会话；合并用 `--detach`；spec-guard 用技能。
   - 其余各节与 Claude 版同名同序（升级与关闭、记任务、开工、权限预配、交审与批准、公共变更请求、审查就近、合并与收尾、出状况、等待记录、空档换宿主、决策收件箱、请用户给原话、转达用户的决定）；
     凡写「SendMessage 叫醒」「Bash 后台运行」「侧栏归档」「权限模式」的地方换成 Codex 的说法，其余逐句一致。
   - `test_skills` 断言两份都含共同关键句，Codex 版另含：固定入口、每轮重新注册、先跑 `status`、沙箱外运行、`merge run --detach`、`merge result`、手动开任务、不叫醒 Claude 会话。
2. **（新）写 `.git` 的提权方案**：
   - skill 列一张「要申请在沙箱外运行」的清单：所有 module-crew 写命令（`bind`、`takeover`、`review *` 的写子命令、`merge *`、`start prepare`、`task dispatch`、`change land`、`coordinator *`、`permissions apply`、`unqueued --notify`、`resume`／`suspend`）、
     `git commit`／`merge`／`push`；只读命令（`status`、`sessions`、`review batch`、`task list`、`host-check`、`unqueued`）在沙箱里跑。
   - 沙箱拒绝后**不换写法绕过**：照实向用户申请一次，用户在本线程点批准（Codex 写「批准（Approve）」）；有「本会话一直允许」就选。
   - 集成 checkout 的 Codex 规则（crew-host-handover 已写 `.codex/rules/module-crew.rules`）放行固定入口，能否让提权自动通过由演练实测；规则不生效时照旧逐次批。
   - module-crew 自己不判断沙箱、不重试；写失败时照常报错并在原因里带「Codex 沙箱不让写 git 目录：请申请在沙箱外运行这条命令」（识别 `Operation not permitted`／`index.lock` 拒绝这两种，别的错误原样报）。
3. **（新）`host-check` 支持模块协调**：在集成 checkout 里运行时按模块协调查——这个 checkout 是集成 checkout、登记的模块协调在用、`module-crew` 版本与状态库一致、能写 git 公共目录（同现有的临时文件探测）、
   能读状态库、能找到 spec-guard（关键决策 5）、固定入口存在。输出与退出码沿用现有约定（`--json` 的 `role` 字段新增，只增不改）。交接说明（handover `--to codex`）在接管后加一步「运行 host-check」。
4. **（新）`status` 认出 Codex 里的模块协调**：调用者有 `CODEX_THREAD_ID` 且等于登记的模块协调 `hostSession` 时，首行写「本会话是模块协调 <邮箱名>（Codex）：没有钩子，以下按状态库为准」；
   有 `CODEX_THREAD_ID` 但不是登记的会话时写「本线程不是登记的模块协调，不要按模块协调行事」。这顶替 Claude 上钩子注入角色那一步。Claude 上 `status` 输出不变。
5. **（新）Codex 侧定位插件：沿用 Claude 的安装记录，不新增 Codex 来源**。理由：module-crew 自己就是经固定入口从 Claude 安装记录找到的，本机一定有 Claude 安装；阶段 0 实测 Codex 沙箱里读得到、找得到 spec-guard 0.84.1。
   `probe.find_plugin` 不改；在 Codex 里找不到 spec-guard 或 agent-relay 时，原因后面加一句「Codex 侧的插件安装 module-crew 不读：请在 Claude Code 里装同一插件」。
   另一个选择是按 sg-coord 的建议在 Claude 记录找不到时退到 `codex plugin list --available --json`（要新增外部命令 `codex`、两边版本可能不同），请用户定（未决问题 2）。
6. **（新）合并长检查：`merge run --detach` 加 `merge result`**：
   - `merge run --detach`（其余参数同 `merge run`）：做完合并前清单、拿到合并锁后，把本次合并交给一个脱离当前进程组的子进程继续跑（同一份代码、同一把锁由子进程持有），
     输出写到状态库目录 `merge-output/C<号>.log`，父进程立即返回退出码 0 与日志路径。锁、退回、冲突中止、放锁全部沿用 crew-background-checks，不另写一套。
   - 子进程结束时把退出码与结束时间写进 `merge-running.json`（原子替换，不删除），日志保留。
   - `merge result [C<号>]`（只读）：没在跑且有结果时输出与前台 `merge run` 相同的正文（通知全文）并以原退出码退出；还在跑时退出码 6、写「已跑 N 分钟」；
     `--wait <分钟>`（上限 8）在本次调用里最多等这么久，等到就按上面输出，等不到退出码 6——这是「分段等」，每次工具调用都在超时以内。
   - `status` 照旧显示正在跑的合并；跑完未读的结果显示「合并 C<号> 已结束，运行 merge result 取通知」。
   - Claude 上照旧用 Bash 后台运行 `merge run`，不用 `--detach`；`--detach` 在两边都能用，只是 skill 只要求 Codex 用。
   - 风险：Codex 沙箱或提权下脱离的子进程会不会被宿主随本轮结束杀掉，没实测。演练里先跑一次；被杀会表现为锁失效，按 crew-background-checks 的失效处理交用户，不会留下半个合并。
     实测不行时退到只用 `--wait` 分段等前台进程（未决问题 3）。
   - `merge push` 同样可能久（pre-push 钩子）且要联网：本模块只在 skill 里写「申请在沙箱外运行、前台跑」；push 也要 detach 等实测后再说。
7. **（新）开工与派任务在仓库外建 worktree**：`start prepare`、`task dispatch` 在仓库同级目录建 worktree，沙箱写不了，归入决策 2 的「沙箱外运行」清单；命令本身不改。
   模块协调在 Codex 时两条命令的输出末尾加一段「请用户去 Codex 新建任务：工作目录选 <worktree>，第一条消息贴 <开工说明文件> 全文」，每个模块一行。
8. **`handover --to codex` 放开的判断不改**：`handover.coordinator_skill_path()` 已指向 `codex-skills/crew-coordinator/SKILL.md`，文件进了插件即放开。
   交接说明的 Codex 方向补两句：接管后先跑 `host-check`；之后每轮按 Codex 版 skill 的开头三步。

## 接口约定

```bash
module-crew merge run [--check-command <命令>] [--replace-check] --detach [--json]   # 新：脱离后台跑，立即返回日志路径
module-crew merge result [C<号>] [--wait <分钟>] [--json]                            # 新：只读，取后台合并的结果
module-crew host-check [--json]                                                       # 在集成 checkout 里按模块协调查
module-crew status [--json]                                                           # Codex 里首行认出模块协调
```

- `merge run --detach`：`0` 已交给后台（输出日志路径与 C 号）；前置失败沿用 `merge run` 的退出码（3 清单不过、6 锁被占），这时不起子进程。
- `merge result`：结果就绪时退出码等于后台 `merge run` 的退出码（0／3／4／5），正文与前台一致；还在跑 `6`；没有可取的结果 `3`。`--json`：`{"approval", "unit", "running": bool, "exitCode", "finishedAt", "log", "output"}`。
- 状态库：`merge-running.json` 加可选 `exitCode`、`finishedAt`、`log`、`resultRead: bool`（只增不改）；新目录 `merge-output/`（不进事件日志、不删除）；事件 `merge.detached`、`merge.result-read`。
- `host-check --json` 加 `"role": "dev"|"task"|"coordinator"|null`；`status --json` 的 `store` 加 `codexSelf`：`null` 或 `{"name", "registered": bool}`。

## 项目结构

```text
codex-skills/crew-coordinator/SKILL.md   新增：Codex 版模块协调 skill
module_crew/merge.py                     run --detach、result
module_crew/mergelock.py                 结果字段、读结果
module_crew/hostcheck.py                 模块协调的检查项
module_crew/probe.py                     status 首行、codexSelf、找不到插件的原因补句
module_crew/start.py, tasks.py           协调在 Codex 时的「去 Codex 开任务」段
module_crew/handover.py                  交接说明 Codex 方向补两句
module_crew/__main__.py                  子命令与参数
skills/crew-coordinator/SKILL.md         「空档换宿主」改为两个方向都可用
.codex-plugin/plugin.json, README.md
tests/test_codex_coordinator.py          新增
```

## 命令

```bash
python3 -m unittest discover -s tests
PYTHONPATH=tests python3 -m unittest test_codex_coordinator
```

## 代码风格

沿用现有模块：代码与注释英文，输出中文；只用标准库；外部命令只有 `git`（脱离后台跑用 `subprocess` 起本插件自己的 `bin/module-crew`），带超时、不经 shell；状态库只写不删；module-crew 不发消息、不替用户点弹窗、不改全局配置。

## 测试策略

- skill：Codex 版协调 skill 存在，含共同关键句与 Codex 特有关键句；`.codex-plugin/plugin.json` 描述不再说协调只在 Claude。
- `handover --to codex`：夹具里放真实的 Codex 版协调 skill（不是假文件），收尾条件满足时完成、交接说明含 `host-check` 与每轮三步；回归 crew-host-handover 全部测试。
- `--detach`：检查脚本睡几秒；父进程立即返回 0、日志路径存在；跑的时候第二个 `merge run`、写命令退出码 6、`merge result` 退出码 6；跑完 `merge result` 的正文与同样输入下前台 `merge run` 逐字一致、退出码一致（成功、检查失败退回、冲突各一次）；
  `--wait` 等到与等不到各一次；子进程被杀时锁按失效处理。
- `host-check`：在集成 checkout 以模块协调身份全通过；git 公共目录只读时「能写 git 目录」不通过、原因含沙箱外运行；找不到 spec-guard 时不通过并带 Codex 补句。
- `status`：设 `CODEX_THREAD_ID` 等于／不等于登记的模块协调各一次，首行与 `codexSelf` 正确；不设时输出与改前逐字相同。
- 写失败识别：模拟 `Operation not permitted` 与 `index.lock` 拒绝，报错原因带「申请在沙箱外运行」；别的错误原样。
- 协调在 Codex 时 `start prepare`、`task dispatch` 输出含「去 Codex 新建任务」段；协调在 Claude 时逐字不变。
- 回归：全量测试通过。

## 边界

- **总是**：写命令沙箱拒绝时照实报、申请提权，不换写法绕过；合并结果不丢（日志与退出码留在状态库）；Claude 上的行为不变（逐字比较）。
- **先问**：放开 `coordinator up` 在 Codex 直接起；加 `codex` 命令行作为插件定位来源；`merge push` 也 detach；实地在 Codex 上跑一批。
- **从不**：替用户点提权、信任项目或开任务；Codex 协调叫醒 Claude 会话；在 checkout 写 AGENTS.md／钩子配置；删除状态库文件；改 `review.py`。

## 验收标准

1. `codex-skills/crew-coordinator/SKILL.md` 存在：含与 Claude 版共同的关键句；含 Codex 特有的固定入口、每轮先重新注册再 `status` 再读收件箱、写命令申请沙箱外运行、
   压缩后不抓最近一条人工输入当任务、用户手动开任务、不叫醒 Claude 会话、`merge run --detach` 与 `merge result`、spec-guard 用技能、收件枢纽停了请用户点开。
2. `handover --to codex`：插件里有这份 skill 时，收尾条件满足即完成（登记 `codex-desktop`、规则写上、交接说明含 `host-check` 与每轮三步）；`--to claude` 行为不变。
3. 模块协调登记为 `codex-desktop`（经 handover）时，`review add/approve`、`merge approve/run/cleanup/push-plan/push`、`start prepare`、`task dispatch`、`change land`、`coordinator down` 在夹具里照常可用，不因宿主被拒。
4. `merge run --detach`：父进程立即返回 0 与日志路径；跑期间锁生效（写命令退出码 6）、`merge result` 退出码 6；结束后 `merge result` 的正文与退出码和前台 `merge run` 一致（成功、退回、冲突）；
   `--wait` 等到返回结果、等不到退出码 6；子进程被杀后按失效锁处理；结果文件与日志不删除。
5. `status` 跑完未读的后台合并显示「已结束，运行 merge result 取通知」；`merge result` 读过后不再显示。
6. `host-check` 在集成 checkout 按模块协调查，全通过退出码 0、`--json` 有 `role: "coordinator"`；git 公共目录只读时该项不通过、原因含沙箱外运行，退出码 3。
7. `status` 在 Codex（`CODEX_THREAD_ID`）里首行认出或否认模块协调、`--json` 有 `codexSelf`；在 Claude 里输出逐字不变。
8. 找不到 spec-guard 或 agent-relay、调用者在 Codex 时，原因带「Codex 侧的插件安装 module-crew 不读」补句；写 git 目录被沙箱拒绝时，报错带「申请在沙箱外运行」。
9. 模块协调在 Codex 时 `start prepare`、`task dispatch` 输出含逐模块的「去 Codex 新建任务」段；在 Claude 时逐字不变。
10. README「换宿主」一节写明模块协调在 Codex 上的做法与代价（提权、手动开任务、分段等合并、重启后逐个点开）；`.codex-plugin/plugin.json` 描述已改；Claude 版 crew-coordinator「空档换宿主」不再写「`--to codex` 会被拒」。
11. 全量测试通过。实地：经用户同意在演练里做一次 Claude→Codex 换宿主、在 Codex 上合并一个模块（统计提权弹窗次数、`--detach` 子进程是否活过本轮）、再换回 Claude；做不了写「宿主未实测」与原因。

## 并行边界

- 轻任务 T26 正在改 `module_crew/review.py`（S14）。本模块写 Spec、Plan 期间不改代码；构建等 T26 合入、模块协调发开工通知后再开始，开工先 `module-crew sync`。
- 本模块**不改** `module_crew/review.py`：`review` 的写子命令在 Codex 上能否用只取决于提权（决策 2），不需要改代码；若构建中发现非改不可，停下发【等待其他会话】。
- 预计改动的文件见「项目结构」；与其他在做的模块无重叠（目前只有 T26 在做）。`README.md`、`skills/crew-coordinator/SKILL.md` 是多个模块都改过的文件，按惯例由本模块直接改、合并时冲突由 `merge run` 退回。

## 未决问题

1. 假设 3：`coordinator up` 是否放开在 Codex 里直接起模块协调（推荐不放开，S13 只要求来回换）。
2. 关键决策 5：Claude 安装记录找不到插件时，是否退到 `codex plugin list --available --json`（推荐不加：module-crew 本身就依赖 Claude 安装）。
3. 关键决策 6：`--detach` 的子进程在 Codex 里能否活过本轮、提权是否随之继承，要演练实测；不行就只用 `merge result --wait` 分段等前台合并（那时前台合并本身仍可能超过单次工具调用的时限，要另想）。
4. 单次工具调用在 Codex 里最长能等多久、一次提权批准能覆盖多少后续命令：演练实测后写进 skill。

## 文档建议

README「换宿主」一节补「模块协调在 Codex 上」：每轮开头三步、提权清单、`merge run --detach`／`merge result`、手动开任务、收件枢纽停了要点开；命令一览补 `merge result`。CHANGELOG 随发版写。
回告：发版后告诉 ecosystem-lead S13 的模块 B 已就位、`handover --to codex` 已放开、实地验证结果；随最终验收列出。
