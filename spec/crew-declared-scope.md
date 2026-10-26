# Spec: crew-declared-scope

<!-- spec-guard: review approved e5b1cec77663 -->

> 能力图模块 `crew-declared-scope`（第十版第 1 个）。需求来源：接缝 S32（并入 S29），已批方案 plugin-ecosystem `proposals/2026-10-24-S32-并行流畅与额度外包.md`（612634c，用户 2026-10-24「按推荐批准」）
> 第二节 module-crew 第 1、2 条：声明目录内的公共文件模块直接改、默认合并时才进集成分支、名单内确需提前进的自动落地事后汇总、有依赖关系的模块不同时开；第三节守门：开关默认关、凭用户原话开，读不到新接口照今天问用户。
> 依赖 `crew-merge`（合并、同步基线的收件人规则）、`crew-review-display`（最终验收四张表）、`crew-start`（开工提议与 `prepare`）；上游 spec-guard 0.85.0（interface 1.11）的 `declaredScope`。
> 标「新」的是写 Spec 时补的实现取舍，请重点审。

## 目标

项目打开开关后，模块 Plan 的「预先声明」一节里列过的公共文件，模块会话在自己的分支里直接改，不再发【公共变更请求】、不再由模块协调代改；
这些文件随模块一起在最终验收时单列一节审一次，默认等合并时才进集成分支。确实要提前进集成分支的，名单内的文件由模块协调从模块分支取过来自动落地、事后汇总给用户；
名单外的文件照今天发请求。开关打开后，有依赖关系的模块不同时开工。没打开开关、或读不到 spec-guard 的新接口时，一切和今天一样。

## 范围

**范围内**

1. **项目开关** `declaredScope`（运行配置 `config/main`，取值 `on`／`off`，没设过等于 `off`）：`config set --declared-scope on|off` 凭用户原话写入。
2. **读声明**：新函数按 interface.json 的 `declaredScope` 入口调用 spec-guard（安全限制同 `/map`），把结果归成「可用」或「不可用 + 原因」两种。
3. **模块会话自查**：新命令 `module-crew scope [<文件>…] [--json]`（只读，在模块 worktree 里跑），逐个文件答「名单内：直接改」或「名单外：发【公共变更请求】」。
4. **开工说明**：开关打开时「全局约束」一行改写成名单内直接改、名单外发请求（决策 6）。
5. **提前落地**：`change add` 认出「文件全在名单内」的请求，标成提前落地、不打「要问用户」；`change land <C号> --from-module` 从模块分支取这些文件在集成分支单独提交、照常通知各模块同步，并记一条待汇总（决策 3、4）。
6. **事后汇总**：新命令 `change landed [--json]` 列出还没汇总给用户的自动落地，`--mark-told` 记为已汇总（决策 5）。
7. **最终验收单列一节**：`review batch` 的最终验收在「改了哪些文件」里加一节「声明内公共文件」，列名单内被改的文件、行数与是否已提前落地；新增依赖表标出声明外的依赖（决策 7）。
8. **有依赖关系的模块不同时开**：开关打开时，`start plan` 不提议、`start prepare` 拒绝和在用模块（含重开的）有依赖关系的模块（决策 8）。
9. **skill 与文档**：`crew-dev`、`crew-coordinator`（Claude 与 Codex 各两份）、README。

**范围外**

- 改 spec-guard 的「预先声明」写法或判定（`planApproved` 等只读取）；自己解析 Plan 的预先声明一节。
- 两种检查（快检查）、检查记账：归 `crew-check-ledger`。提前落地后照今天的做法通知各模块同步，同步后跑什么检查不在本模块定。
- 自治档位：归 `crew-autonomy-tier`。本模块只提供开关，档位以后按自己的规则替用户开关它。
- 用钩子拦截模块会话改名单外的文件（今天「不改公共文件」也只是 skill 规则，不拦截）。
- 删除文件、改对外契约、安全例外：spec-guard 规定不能预先声明，照今天发请求。
- 改合并本身（`merge run` 的合并、检查、退回、同步规则）：`module_crew/merge.py` **不改**，只调用它已有的 `no_sync`、`commit_timeout`。

## 假设（请逐条确认）

1. **（新）「名单内」的判据**：文件路径等于 `publicPaths`、`configs`、`patches` 里的一项，或落在 `publicPaths` 里以 `/` 结尾的目录下。`dependencies`（`包名@范围`）不让任何文件变成名单内：
   要改 `package.json`、锁文件来加依赖，这两个文件本身也得写进声明（通常写在「质量与工作区配置」）；`dependencies` 只用来在最终验收里核对新增的依赖有没有声明过（决策 7）。
2. **声明只在 `planApproved` 为 `true` 时算数**：Plan 批准后又改过（spec-guard 报 `false`）、`declared` 为 `false`、退出码 4（格式错）、装的 spec-guard 低于 1.11、命令跑不成——一律当「没有声明」，
   照今天发请求、问用户，并把原因写给看的人（「声明不可用：<原因>」）。不猜、不部分采信。
3. **在哪个 checkout 读**：模块会话的 `scope` 在自己的 worktree 读（看到的是同步进来的已批 Plan，自己改过 Plan 就会读到 `planApproved: false`）；
   模块协调这边（`change add`、`change land`、最终验收、开工判断）在集成 checkout 读，以集成分支上已批准的 Plan 为准。
4. **提前落地只在模块会话发了【公共变更请求】时发生**：开关打开后，模块会话对名单内的文件平时不发请求；只有确实要让集成分支提前带上（例如别的在用模块马上要用）时才发，
   契约的【公共变更请求】字段不变，不新增消息类型，所以不用先改 session-protocol。
5. **请求里有一个文件在名单外，整条请求照今天处理**（提示、问用户、协调会话在集成 checkout 改）；输出里写明哪几个在名单内，方便让模块拆成两条。
6. **「冲突」提示照旧要问用户**：另一条未处理请求也改同一个文件时，即使全在名单内也不自动落地。两个模块的声明里都有同一个公共文件、各自在分支里改，合并时的冲突照 `crew-merge` 的冲突退回处理，本模块不另管。
7. **「有依赖关系」按能力图的 `dependsOn` 算，上下游都算、按传递闭包**：spec-guard 的 `startable` 本来就要求依赖全部做完，所以新模块平时就不会和它的上游同开；
   本模块补上的是重开的模块（`crew-reopen-module`）和兜底核对：已合入（有关闭为 merged 的本轮合并批准）的模块不算「在用」。
8. **每条新行为都只在开关打开时生效**；开关 `off` 时 `scope` 命令照样能跑，但首行写明「开关没开：公共文件一律发【公共变更请求】」，其余输出逐字与今天相同。

## 关键决策与取舍（请重点审）

1. **（新）开关凭用户原话写，命令不判断档位**：`config set --declared-scope on --original-file <文件>`，和 `--commit-prefix`、`--check-timeout` 同一个入口、同一个事务，事件里记原话。
   打开时先读一次 spec-guard：低于 1.11 照样写入，但输出警告「spec-guard 低于 1.11，读不到声明，打开后仍照今天的做法」。以后 `crew-autonomy-tier` 切档时写同一个键。
2. **（新）读声明的入口放在新文件 `module_crew/declared.py`**：`read(project, module) -> Declared`，`Declared` 有 `usable`、`reason`、`paths`（三类路径）、`dependencies`、`approvedCommit`；
   `inside(path) -> bool` 按假设 1 判；`enabled(db) -> bool` 读开关。调用走 `probe.find_plugin`／`read_interface`／`safe_command`，参数列表、带超时、不经 shell，和 `scopeOverlap` 的调用方式相同。
3. **（新）`change add` 的分类**：开关打开、声明可用、清单里每个文件都在名单内、没有 `conflict:` 提示时，请求记 `declared: true`（另记读到的 `approvedCommit`），
   输出写「名单内：提前落地，不用问用户；用 change land C<号> --from-module」，**不**再写「要问用户」；锁文件等原有提示照旧记下，但不再触发问用户。其余情况记 `declared: false`，行为与今天相同；
   开关打开但声明不可用时多一行「声明不可用：<原因>，照今天处理」。
4. **（新）`change land <C号> --from-module`**：只接受 `declared: true` 的请求。取请求方模块分支当时的顶端提交，在集成 checkout 里用 `git checkout <提交> -- <清单文件>` 取出这些文件，
   随后走 `land` 现有的核对（集成 checkout 只有清单内的改动）、提交、关请求、发同步基线通知；请求另记 `fromModule: {"commit": <模块提交>}`。
   拒绝（退出码 3，什么都不改）：请求不是 `declared: true`；集成 checkout 落地前就有改动；清单里有文件在模块分支上不存在（删除不能预先声明）；落地前再读一次声明，已不可用或文件已不在名单内。
   提交信息写「公共变更请求 C<号>（<发件人>）提前落地：<改什么>」。这样模块协调不用到临时目录里拼候选文件、算 SHA。
5. **（新）事后汇总**：每次 `--from-module` 落地在请求上记 `toldUser: false`。`change landed` 只读列出 `toldUser` 为 `false` 的自动落地（请求号、模块、文件、提交号、时间），
   并给一段可直接给用户看的汇总正文；`change landed --mark-told <C号>…` 记为已汇总（不要原话：只是记账，不是批准）。crew-coordinator skill 写明：每次给用户发批量交审或最终验收前先看 `change landed`，
   有就把汇总写进那条消息，再 `--mark-told`。
6. **开工说明的「全局约束」一行**（`render_kickoff`）：开关打开时改为
   「全局约束：Plan「预先声明」名单内的公共文件直接在本分支改（`module-crew scope <文件>` 可查）；名单外的不改，要改发【公共变更请求】；被挡住发【等待其他会话】；发出前 module-crew protocol check。」
   开关关闭时逐字不变。Plan 还没批准时名单是空的，所以写 Spec、Plan 阶段的行为不变。
7. **（新）最终验收的「声明内公共文件」一节**（`present.final_tables`／`table_lines`）：开关打开时，从「文档」「代码」两张表里把名单内的文件挪出来，放进紧跟其后的一节「声明内公共文件：」，
   每行「- <新增／修改> <路径>（+a −d）」，已提前落地的加「，已提前落地 C<号>（<提交短号>）」；没有写「- 无」。声明不可用时这一节写「声明不可用：<原因>，名单内外没有区分」，文件留在原表。
   「新增依赖」表在开关打开且声明可用时，不在 `dependencies` 里的包加「（未声明）」。`--json` 的 `display` 加 `declared: {"state": "ok"|"unavailable"|"off", "reason", "files": [...]}`。开关关闭时输出逐字不变。
8. **（新）有依赖关系的模块不同时开**（`start.plan`、`start.validate`、`_why_not`）：开关打开时，取 `/map --json` 各模块的 `dependsOn` 算上下游闭包；
   在用模块 = 状态库 `dev` 登记 `status: active`、本轮未合入的模块（挂起的也算）。要开的模块和任一在用模块互为上下游时：`plan` 不提议它，原因写「和在用的 <模块> 有依赖关系，等它合入再开」；
   `prepare` 拒绝（退出码 3，什么都不写）。同一次 `prepare` 里要开的几个模块之间互为上下游也拒绝。开关关闭时不做这项核对。

## 接口约定

### 命令

```bash
bin/module-crew config set --declared-scope on|off (--original <原话> | --original-file <文件>)
bin/module-crew scope [<文件>…] [--json]                          # 只读，在模块 worktree 里跑
bin/module-crew change land <编号> --from-module [--original <原话> | --original-file <文件>]
bin/module-crew change landed [--json] [--mark-told <编号>…]
```

- `config set`：退出码不变（`0` 写入、`2` 参数错、`3` 原话为空）；可以和 `--commit-prefix`、`--check-timeout` 一起给。
- `scope`：`0` 读成（含开关没开、声明不可用两种，原因写在首行）；`2` 不在登记过的模块 worktree 里。`--json`：`{"switch": "on"|"off", "usable": bool, "reason": str|null, "module", "approvedCommit", "paths": {...}, "dependencies": [...], "files": [{"path", "inside": bool}]}`。
- `change add`：退出码不变；输出多「名单内：提前落地…」或「声明不可用…」一行。
- `change land --from-module`：`0` 成功（输出同 `land`，另有一行「提前落地，记入待汇总」）；`3` 见决策 4；`4` 提交失败（同 `land`）。不带 `--from-module` 时行为不变。
- `change landed`：`0` 有待汇总；`3` 没有。`--mark-told` 给的编号不是待汇总的自动落地时退出码 3、什么都不写。

### 记录（只增不改）

```json
// config/main
{"declaredScope": "on"}
// request：新增可选字段
{"declared": true, "declaredCommit": "<读到的 approvedCommit>", "fromModule": {"commit": "<模块分支提交>"}, "toldUser": false}
```

## 项目结构

```text
module_crew/declared.py          新：读 declaredScope、名单内判据、开关
module_crew/changes.py           add 的分类；land 加 from_module；landed 列表与 mark_told
module_crew/present.py           final_tables、table_lines：声明内公共文件一节、未声明依赖
module_crew/start.py             plan、validate、_why_not：依赖关系核对；render_kickoff：全局约束一行
module_crew/__main__.py          config set --declared-scope；scope 子命令；change land --from-module；change landed
skills/crew-dev/SKILL.md、codex-skills/crew-dev/SKILL.md
skills/crew-coordinator/SKILL.md、codex-skills/crew-coordinator/SKILL.md
README.md
tests/test_declared_scope.py
```

不改：`module_crew/merge.py`、`module_crew/review.py`（`review batch` 已经调用 `present.final_tables`／`table_lines`，本模块只改这两个函数）、`module_crew/protocol.py`。

## 命令

```bash
python3 -m unittest discover -s tests
PYTHONPATH=tests python3 -m unittest test_declared_scope
```

## 代码风格

沿用现有模块：代码与注释英文，输出中文；只用标准库；git 与 spec-guard 调用带超时、参数列表、不经 shell；spec-guard 入口一律经 interface.json 取。

## 测试策略

- 假 spec-guard（测试里放一份声明 1.11、`declaredScope` 指向小脚本的插件夹具）返回四种结果：可用、`planApproved: false`、`declared: false`、退出码 4；另一份只声明 1.10。
- 每个测试建临时仓库与模块 worktree（复用 crew-review-batch 的测试基类，b、c 两个模块会话），名单内写 `config/app.json` 与目录 `shared/`。
- 开关：没设、`off`、`on` 三种下跑 `change add`、`start plan`、开工说明、最终验收，`off` 与没设时与改前输出逐字相同。
- 提前落地：模块分支改 `shared/x.ts` 并提交 → `change add` → `land --from-module` → 集成分支多一个只含该文件的提交、内容等于模块分支、各模块收到同步通知 → `change landed` 列出 → `--mark-told` 后不再列。
- 依赖：能力图 a ← b（b 依赖 a）；a 重开在用时 b 不被提议、`prepare b` 被拒；开关关时不拒。
- 回归：全量测试通过。

## 边界

- **始终**：只在开关打开且声明可用时改变行为；读不到就照今天问用户；名单内外的判定只看 spec-guard 给的清单。
- **先问**：打开或关闭开关（要用户原话）；名单外或混合的请求；有冲突提示的请求。
- **绝不**：自己解析 Plan 的预先声明一节；声明不可用时部分采信；自动落地名单外的文件；改合并、检查与退回规则。

## 验收标准

1. `config set --declared-scope on --original "打开声明范围"`：`config/main.declaredScope == "on"`，事件记原话；原话为空退出码 3；spec-guard 只有 1.10 时照样写入并输出警告。
2. 开关没设或 `off`：`change add`、`change land`、`start plan`、`start prepare`、开工说明、`review batch` 的输出与改前逐字相同（用改前的输出做对照）。
3. `scope`（开关 `on`、声明可用）：`config/app.json`、`shared/a/b.ts` 答名单内，`package.json`（没声明）答名单外；`planApproved: false`、`declared: false`、退出码 4、spec-guard 1.10 四种情况首行都是「声明不可用：<原因>」且每个文件都答名单外；开关 `off` 时首行写明开关没开。
4. 开关 `on`：开工说明的「全局约束」一行是决策 6 的写法；`off` 时与改前相同。
5. `change add`：全在名单内、没冲突的请求记 `declared: true`，输出「名单内：提前落地」且没有「要问用户」；混合请求记 `declared: false`、输出列出名单内的文件、照旧按提示问用户；另一条未处理请求改同一文件时 `declared: false`；声明不可用时多「声明不可用」一行。
6. `change land --from-module`：集成分支多一个提交，只含清单文件，内容等于模块分支顶端的版本，提交信息含「提前落地」与请求号；请求关为 `landed` 并记 `fromModule.commit`、`toldUser: false`；
   请求方收到带「回复：#N」的同步基线通知、其他在用模块各收到一条，正文都被 `protocol.parse` 判为合格。
7. `land --from-module` 拒绝且什么都不改（退出码 3）：请求不是 `declared: true`；集成 checkout 有改动；清单文件在模块分支上不存在；落地前声明已不可用。
8. `change landed` 列出未汇总的自动落地与可给用户看的汇总正文；`--mark-told C<号>` 后不再列出；没有时退出码 3；编号不对时退出码 3、不写。
9. 最终验收（开关 `on`、声明可用）：名单内被改的文件只出现在「声明内公共文件」一节，提前落地过的带请求号与提交短号；没有时写「- 无」；
   声明外的新增依赖带「（未声明）」；声明不可用时这一节写原因、文件留在原表；`--json` 的 `display.declared` 三种 `state` 都对。
10. 依赖（开关 `on`）：b 依赖 a、a 有在用会话时 `start plan` 不提议 b 且原因含「和在用的 a 有依赖关系」，`prepare b` 退出码 3 且什么都不写；a 本轮已合入后不再挡；同一次 `prepare a b` 被拒；开关 `off` 时不做这项核对。
11. skill：`crew-dev`（两份）写明开关打开时先 `module-crew scope <文件>`，名单内直接改、名单外发请求、确需提前进集成分支才对名单内文件发请求；
    `crew-coordinator`（两份）的「公共变更请求」一节写明名单内请求用 `change land --from-module`、不问用户，交审前看 `change landed` 并写进给用户的消息；开关要用户原话。
12. 全量测试通过；本机 spec-guard 0.85.0 实测一次 `declaredScope`（一个带「预先声明」一节、已批准的 Plan），结果写进最终验收。

## 并行边界

- 独占：`module_crew/declared.py`、`module_crew/changes.py`、`module_crew/present.py`、`module_crew/start.py`、`module_crew/__main__.py`、`skills/crew-dev/SKILL.md`、`codex-skills/crew-dev/SKILL.md`、`skills/crew-coordinator/SKILL.md`、`codex-skills/crew-coordinator/SKILL.md`、`README.md`、`tests/test_declared_scope.py`
- 公共：测试资源

## 并行说明

`module_crew/merge.py` 不在独占里：本模块不改它（见「范围外」）。和 `crew-check-ledger` 可能同时改的是 `__main__.py`（各加子命令，不同段落）、两份 `crew-coordinator` skill 与 README。

## 未决问题

- 无。

## 文档建议

README「公共文件怎么改」一小节补开关打开后的做法（名单内直接改、提前落地、事后汇总），「一次完整流程」的最终验收一步写明多一节「声明内公共文件」。CHANGELOG 随发版写。
