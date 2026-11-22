# Spec: crew-takeover-merge

<!-- spec-guard: review approved aca27b4a463c -->

> 能力图模块 `crew-takeover-merge`。需求来源：接缝 S101，已批合并方案 plugin-ecosystem `research/2026-11-21-自动接管合并方案.md`（bfce091，用户 2026-11-21「按推荐批准」）
> 第 2 节 module-crew 一行「合并第一段」、第 3 节 Q2、Q6、Q7、Q9、Q12，第 5 节「硬卡：module-crew 项目可直接用它的检查账」。开会话依据：用户批准事项 C618。
> 依赖 `crew-takeover-approve`（读档位 `takeover.module(...).merge`、虚拟审查者 `codex`、`review codex`／`codex-note`、`_land`、`codex-approval` 记账、收窄入口 `autonomy.incident`；
> 写 Spec 时它的 Spec 已批（C607／C608）、Plan 已批（C611），代码还没合入）、`crew-merge`（`merge approve`／`run`、退回、勾选）、`crew-final-accept-split`（`merge accept`、最终验收三种答复）；另用到 `crew-check-ledger`（检查账）。
> 上游：spec-guard 0.91.0（interface 1.15，含模块 `codex-final-acceptance`）、delegate 接口 1.5，写 Spec 时都**还没发版**；spec-guard 的读法按它 `claude/s101-takeover` 分支（5728e2db）与 `spec/usage/auto-takeover.md` U4 写，构建时以发版为准。
> 现状取自 0.23.6 源码（`merge.py`、`checks.py`、`review.py`、`autonomy.py`、`interface.json`）。标「新」的是写 Spec 时补的实现取舍，请重点审。

## 目标

勾了「合并：自动」的模块，合并第一段（合进本地集成分支、跑完整检查）不再等用户一句话；真正的最终验收（spec-guard 的 Codex 验收记录）留在 autopilot 开出的 PR 的 head 上做：

- **Codex 审最终补丁**：模块发最终验收【交审】后，由 Codex 逐条对照这个模块 Spec 的验收标准审最终补丁；有阻断意见就自动返工（最多 2 轮），没有就放行合并第一段。
- **自动合并第一段**：Codex 无阻断、且审的正是交审时的提交 X，module-crew 记一条自动放行、排进合并队列并跑 `merge run`（合进本地集成分支、完整检查照跑、勾最终验收 gate），把「合并第一段完成」连同集成分支名、合并提交、X、Codex 报告、检查账记录记进自己的合并记录。合并队列那次完整检查由 module-crew 跑，就是非作者检查。
- **给 autopilot 读**：新增只读命令输出集成分支上已完成合并第一段、还没推送的合并及其证据，写进 `interface.json`。autopilot 读它自己推 batch 分支、开 PR、在一次性克隆里重跑检查、写编排证据，再在 PR head 上调 spec-guard 记 Codex 最终验收、远端合并。
- **出事收窄**：自动合的模块在合并队列里被退回（模块原因）、被撤销批准，照 `crew-takeover-approve` 的收窄入口降档（先撤合并）。

module-crew 不写 spec-guard 的 `--target acceptance` 验收记录，不写 `~/.autopilot/evidence/`，不调 autopilot（调用方向只能是 autopilot → 插件）。推 batch 分支、开 PR、合远端 PR、撤回检测都不做（归 autopilot）。没勾「合并：自动」的模块一切照今天：最终验收由用户答复。

## 范围

**范围内**

1. **判定**：最终验收【交审】`review add` 时按 `takeover.module(...).merge` 判定这一项是「人合」还是「自动合」，自动合还要满足前提（假设 3）；不满足照人合并写明原因（决策 1）。
2. **Codex 审最终补丁**：自动合的最终验收事项交给虚拟审查者 `codex`，复用 `review codex`／`codex-note`，审查说明换成「对照 Spec 验收标准审最终补丁」，审查范围是相对集成分支的最终补丁（决策 2、3）。
3. **放行与合并第一段**：新命令 `merge auto C<n>`：核对 Codex 无阻断且绑定 X，记 `auto-release`、建合并批准、接着跑一次合并队列（决策 4）。
4. **合并第一段完成记录**：`merge run` 合入通过后，对自动合的合并批准记 `firstStage`（集成分支、合并提交、X、合并树、检查账键），`gateTick` 照今天勾（决策 5、6）。
5. **给 autopilot 的读接口**：`merge first-stage [--json]` 与 `interface.json` 新节 `firstStage`（决策 7）；字段经模块协调与 autopr-design 对过再定。
6. **出事收窄**：自动合的事项因模块原因退回、撤销批准时调收窄入口（决策 8）；Codex 不可用、超限照 `crew-takeover-approve` 停下交用户（决策 9）。
7. **显示**：`status`、`review list`／`batch`、`merge queue` 写明最终验收「人合」还是「自动合」、走到哪一步；Codex 审查中的事项不进给用户的批次（决策 10）。
8. **skill 与文档**：`crew-coordinator`、`crew-dev`（Claude 与 Codex 各一份）、`docs/guide.md`、`docs/commands.md`。

**范围外**

- spec-guard 的 Codex 最终验收记录（`review_mark --target acceptance --state codex-approved`）：要读 autopilot 编排写的 `~/.autopilot/evidence/<owner>__<repo>/<HEAD>.json`（只认 `runner: autopilot-orchestrator`），只能在 autopilot 开出的 PR head 上由 autopilot 一侧做。
- 推 batch 分支、开 PR、一次性克隆里重跑检查、写编排证据、远端合并、撤回检测、两个计数：归 autopilot（Q9）。`merge push` 照旧要用户原话。
- 读档位、Codex 审查的返工机制、`_land`、收窄入口本身：归 `crew-takeover-approve`，本模块只调用、只把节点扩到最终验收。
- 轻任务（`task/t<号>`）：没有 Spec、没有接管档位，一律人合（决策 1）。
- 跳过合并队列里的完整检查：守门不变（`crew-check-ledger` 关键决策 4）。
- 发布（spec-guard 的 `release` 一项）：第二版，不读。

## 上游依赖（构建要等）

| 上游 | 版本 | 本模块用到 | 状态 |
|---|---|---|---|
| `crew-takeover-approve` | 合入集成分支 | `takeover.module`、`reviewer: "codex"`、`review codex`／`codex-note`／`codex-fallback`、`CODEX_REWORK_LIMIT`、`codex-approval` 记录、`takeover.narrow` | 已合入 f811152（C633） |
| spec-guard | 0.91.0，interface 1.15 | `/map --json` 每模块 `takeover.merge`；`gateTick` | 本机 0.91.3 |
| delegate | 接口 1.5 | 审查报告 `findings[].severity`（缺按 blocking）、`--previous-report`、`scope.fingerprint`（`blob-pairs-v1`） | 本机 0.10.0，接口 1.5 |
| autopr-design | 合并第一段记录的读法 | `merge first-stage --json` 的字段（决策 7） | Checkpoint 3 经模块协调对 |

读不到 1.15 或 1.5 时一律照人合（同 `crew-takeover-approve` 假设 3）。

## 假设（请逐条确认）

1. **spec-guard 的最终验收记录不归 module-crew**：spec-guard 0.91.x 的 `reviewMark --target acceptance --state codex-approved --review <报告>` 对模块 HEAD 记 Codex 验收，要求本机有 autopilot 编排写的检查证据（`autopilot.check-evidence/v1`，`runner: autopilot-orchestrator`、`non_author: true`、`head_sha` 等于 HEAD），记录写在 git 目录、不进提交，最终 gate 合并后补勾。
   module-crew 本地合入时还没有 PR、也没有编排证据，所以不调它；最终验收记录由 autopilot 在 PR head 上做。module-crew 本地的「放行」只放行合并第一段，不叫最终验收。
2. **「最终提交」就是交审时的模块提交 X**：Codex 审的是 X 相对集成分支的补丁（`scope.fingerprint` 覆盖的内容等于 X 里的内容）。合并提交 M 的树等于 X 的树时（模块已同步到集成分支顶端），`merge run` 的完整检查就记在 X 的同一棵树上。
3. **自动合的前提**：除了档位 `merge: auto`、spec-guard 没把它判为强制人批之外，还要求 ① 项目开着 `checkLedger`（检查要记账，autopilot 才读得到）且设了 `checkCommand`；② 这是模块的最终验收（不是轻任务）；③ 这个模块的 Spec、Plan 都已批准（人批或 Codex 放行都算）。缺任一条照人合，`review add` 输出写原因一行。
4. **「非作者」的口径**：检查账记录的 `by` 不是这个模块登记的会话名（模块会话跑的 `check quick` 不算），且是完整检查（`full`）、结果通过、不是继承来的（`inheritedFrom` 为空）。合并队列的完整检查（`by: merge-run`）满足这一条。
5. **Codex 审最终补丁的阻断口径**：照 delegate 1.5 的 `severity`，审查说明写「对照 Spec `spec/<模块>.md` 的验收标准逐条核对最终补丁；阻断意见限于某条验收标准没做到、做错，或照这份补丁合进去会坏掉已有行为」。建议不返工，原样附进放行记录与收尾通知。
6. **返工与轮次照 `crew-takeover-approve` 假设 4**：最多返工 2 次、审 3 次；返工就是普通的最终验收返工（模块改完重新发最终验收【交审】），轮次跨「取代」累计。
7. **自动放行不是用户批准**：不发【用户答复】，不写进「用户批准事项」；对用户说「Codex 无阻断，自动合并第一段」。收尾通知照今天由 `merge run` 发。

## 关键决策与取舍（请重点审）

1. **判定放在 `takeover.approver` 的 `final` 节点**：`crew-takeover-approve` 让 `approver(..., "final")` 永远返回 `human`、留给本模块。这里改为：`final` 节点在 `takeover.module(...).merge == "auto"`、没被强制人批、满足假设 3 时返回 `codex`，否则 `human`，并给出原因（`takeover.final_reason(...)`）。
   `review add` 收到最终验收【交审】时，判为 `codex` 就照 Spec、Plan 的 Codex 放行路径记 `reviewer: "codex"`、`sentTo: ["codex"]`，输出「已记为交审事项 C<n>（最终验收，自动合：下一步 review codex C<n>）」；判为 `human` 时一字不变，档位是 `auto` 但前提不满足时多一行「合并档位是自动，但 <原因>，这次照人合」。
2. **`review codex C<n>` 对最终验收的命令**：`/delegate:review --backend codex --base <集成分支顶端与 X 的合并基点> --head <X> [--previous-report <上一轮>] <审查说明>`，审查说明照假设 5，并附 `spec/<模块>.md` 的路径要 Codex 先读验收标准一节。
   不用 `--paths`：最终补丁按提交范围审，交审文件清单不一定列全。具体参数照 delegate 0.10.0 的真实写法实现。
3. **`review codex-note C<n>` 对最终验收的结论**：有阻断照 `crew-takeover-approve` 返工；超限、没有结论退出码 5 出【等待用户】草稿，选项改为「A 用户来验收这一版（之后照今天 `merge approve`／`merge accept`／`review answer`）／B 照阻断意见再改一轮」或「A 等 Codex 恢复后重跑／B 这一次由用户验收」。
   没有阻断时**不**在这一步落地：交审事项记 `codex: {verdict: "pass", report, fingerprint, rounds, suggestions}`、状态保持 `open`，输出下一步「module-crew merge auto C<n>（放后台跑）」。理由：放行后紧接着要跑合并队列与完整检查，耗时长，要放后台、拿合并锁。
4. **新命令 `merge auto C<n>`（模块协调，放后台跑，同 `merge run` 用合并锁）**，按顺序做，任一步不过就停、不写：
   1. 事项是 `reviewer: "codex"` 的最终验收、`codex.verdict` 为 `pass`、还开着；模块分支 HEAD 仍是交审时的 X（否则退出码 3「交审之后又有提交，须重新交审」）。
   2. **绑定**：按记下的报告再核一次 `scope.fingerprint` 覆盖的内容等于 X 的内容（防止中间换了报告）。
   3. **放行**：在一个事务里把交审事项关成 `answered`（`answer` 写「Codex 无阻断，自动放行」与报告摘要，不是用户原话），记 `kind: "auto-release"` 事项（报告、指纹、X、轮次、建议条数），建合并批准（`kind: "merge-approval"`，`auto: <auto-release 编号>`，`answer.original` 写「自动放行事项 C<k>」）。
   4. **接着跑一次合并队列**：调用 `merge run` 同一段代码（`_run`，持有同一把锁）。队首是本事项就合它；队首是别的已批事项（用户批过的）就合那一个，输出写「队列里还有 C<n>，接着跑 merge run」。
   退出码：`0` 已放行且这次合并成功；`3` 前提不过（什么都没写）；`4` 合并本身失败（同 `merge run` 的 4）；`5` 放行后 `merge run` 检查失败／冲突已退回；`6` 合并锁被占。
   取舍：放行和合并分成两条命令更容易看懂，但「自动」就是用户不点、协调不另想，合成一条让模块协调只跑一个后台命令；放行记录先落盘再合并，合并失败时放行记录还在、可追溯。
5. **非作者检查就是合并队列那次完整检查（不另跑）**：`merge run` 照 `crew-check-ledger` 守门跑完整检查并记账（`by: merge-run`），满足假设 4。合并前不在模块 worktree 另跑一次：spec-guard 的最终验收只认 autopilot 编排的证据，module-crew 另跑的检查到了 PR head 也不算数，多跑一次只是翻倍耗时。
6. **合并第一段完成的记录**：`merge run` 对带 `auto` 的合并批准合入并通过检查后，在合并批准上记
   `firstStage: {"integrationBranch", "mergeCommit", "moduleCommit": <X>, "tree": <合并树>, "check": "<树>.full", "at"}`，事件 `item.first-stage`；`gateTick` 照今天勾最终验收 gate（spec-guard 的最终验收记录之后由 autopilot 在 PR head 上做，它对「已勾」的 gate 不冲突：spec-guard 规定最终 gate 合并后补勾）。
   检查失败、冲突照今天退回、不记 `firstStage`。
7. **给 autopilot 的读接口 `merge first-stage [--json]`**（只读，任何会话可跑）：
   ```json
   {"schemaVersion": 1, "integrationBranch": "main", "head": "<集成分支顶端 40 位>", "pushedUpTo": "<最近一次 push 记录的提交或 null>",
    "merges": [{"approval": 123, "module": "x", "moduleCommit": "<X>", "mergeCommit": "...", "tree": "...", "auto": true,
                "release": {"item": 124, "report": "<路径>", "fingerprint": "...", "rounds": 1, "suggestions": 2},
                "check": {"key": "<树>.full", "result": "pass", "by": "merge-run", "nonAuthor": true, "command": "...",
                          "exitCode": 0, "startedAt": "...", "seconds": 812}}]}
   ```
   `merges` 列出集成分支上 `pushedUpTo` 之后完成合并第一段的合并（人合的也列，`auto: false`、`release: null`），按合并顺序。退出码：`0` 有记录（含空列表）、`2` 参数错或不在 module-crew 项目里。
   `interface.json` 新增 `firstStage` 一节（命令、`schemaVersion`、字段说明、退出码），`interface` 升到 `1.1`。**字段是提案**：Checkpoint 3 经模块协调与 autopr-design 对一次，按对方要的改，变更记录写明。
8. **出事收窄**：自动合的事项在下列情况调 `autonomy.incident`（已改为调 spec-guard 收窄入口，按「合并 → Plan → Spec」降一格），原因写明是自动合并：
   - 自动合的合并批准在 `merge run` 里被退回、且是「模块需要修改」（`kind: auto-merge-returned`，取代原来的 `merge-returned`，不重复降）；环境问题、提交钩子拒绝不降（同今天）；
   - 自动合的合并批准被 `merge revoke` 撤销（沿用 `revoked`）。
   Codex 返工超限、Codex 不可用**不降**（交人是正常流程）。同一事项只降一次（`incidentKeys` 去重）。PR 上检查不过、远端被撤回由 autopilot 自己降。
9. **Codex 不可用、超限一律停**：没有任何路径让 Claude 自己的判断替代 Codex；用户选「这次由用户验收」后，事项记 `reviewer: "human"`、`fallback`（复用 `review codex-fallback`），之后完全照今天的最终验收（`merge approve`／`merge accept`／`review answer`），不再自动合。
   `merge approve`／`merge accept` 对 `reviewer: "codex"` 且没有 `fallback` 的最终验收拒绝（退出码 3，提示「这一项是自动合，先 review codex；Codex 不可用时照草稿问用户」）。
10. **显示与模块会话的提示**：
    - `review list`／`review show`：自动合的最终验收写「最终验收（自动合）：Codex 审查中／返工第 k 轮／Codex 无阻断，待 merge auto／已放行 C<k>」。
    - `review batch`、`--for-hub`：自动合的最终验收不进给用户的批次，末尾告知行（`crew-takeover-approve` 决策 2）把它一并列上。
    - `merge queue`：带 `auto` 的合并批准写「（自动合，放行事项 C<k>）」。
    - `status` 接管一段：多一行「自动合：已放行 a 次，其中合入 b 次、退回 c 次」；`--json` 的 `store.takeover` 多 `merge` 计数。
    - `crew-dev`：spec-guard 0.91 的阶段提示在「合并：自动」的模块到最终 gate 时会建议「交 Codex 审、等检查证据、用 review-mark 记下」；在 module-crew 项目里模块会话**不**照做，照常发最终验收【交审】，Codex 审查与合并由模块协调做。

## 接口约定

### 命令

```bash
bin/module-crew merge auto C<n>                       # 模块协调，放后台跑：核对 Codex 无阻断与绑定、放行、跑一次合并队列
bin/module-crew merge first-stage [--json]            # 只读：给 autopilot 的合并第一段记录
bin/module-crew review codex C<n>                     # 已有（crew-takeover-approve），最终验收给出按提交范围审的命令
bin/module-crew review codex-note C<n> --report <json> # 已有，最终验收无阻断时记 pass、提示 merge auto
```

### 记录（只增不改）

```json
// 交审事项（node: final）新增
{"reviewer": "codex", "sentTo": ["codex"], "codex": {"verdict": "pass", "report": "<路径>", "fingerprint": "...", "rounds": 1, "suggestions": 2}}
// 自动放行事项
{"state": "closed", "kind": "auto-release", "closedReason": "answered", "review": 123, "module": "x", "commit": "<X>",
 "codex": {"report": "<路径>", "fingerprint": "...", "rounds": 1, "suggestions": 2}}
// 合并批准新增
{"auto": 124, "firstStage": {"integrationBranch": "main", "mergeCommit": "...", "moduleCommit": "<X>", "tree": "...", "check": "<树>.full", "at": "..."}}
```

事件动作：`item.auto-released`、`item.first-stage`。

## 项目结构

```text
module_crew/takeover.py        final 节点的判定与原因（在 crew-takeover-approve 的文件上加）
module_crew/review.py          add：最终验收按判定记 reviewer；codex／codex-note 的最终验收分支；merge 类拒绝提示
module_crew/merge.py           新 auto()、first_stage()；_run 对 auto 记 firstStage；approve／accept 拒绝 codex 项；incident 的 kind
module_crew/checks.py          非作者判定（供 first-stage 用）
module_crew/probe.py           status 接管一段的自动合计数
module_crew/__main__.py        merge auto、merge first-stage
interface.json                 firstStage 一节，interface 1.1
skills/crew-coordinator/SKILL.md、codex-skills/crew-coordinator/SKILL.md
skills/crew-dev/SKILL.md、codex-skills/crew-dev/SKILL.md
docs/guide.md、docs/commands.md
tests/test_takeover_merge.py   新
```

## 命令

```bash
python3 -m unittest discover -s tests
PYTHONPATH=tests python3 -m unittest test_takeover_merge
```

## 代码风格

沿用现有模块：代码与注释英文，输出中文；只用标准库；外部命令参数列表、带超时、不经 shell；spec-guard 入口一律经 interface.json 取。

## 测试策略

- 复用 `crew-takeover-approve` 的假 spec-guard（加 `merge: auto`）与假 delegate 报告夹具；复用 `crew-merge`／`crew-check-ledger` 的测试基类（模块会话、集成 checkout、按文件决定成败的检查脚本，记下被调用次数）。
- 不接管、`merge: human`：现有测试原样通过。

## 边界

- **始终**：Codex 无阻断且绑定 X 才放行；放行记录先落盘再合并；合并队列照跑完整检查；Codex 不可用就停下等用户；Codex 验收与用户验收分开记、分开说；收窄立刻告诉用户。
- **先问**：Codex 超限或不可用时这次改由用户验收；放宽档位（用户原话，经 `/spec-guard:config`）；推送与开 PR（照旧要原话）。
- **绝不**：推 batch 分支、开 PR、合远端 PR；调 autopilot；写 `~/.autopilot/evidence/`；调 spec-guard 的 `--target acceptance`；Claude 自审代替 Codex；模块会话自己跑的检查当作非作者证据；继承来的检查记录当作非作者证据；轻任务自动合；把 Codex 验收说成或记成用户批准。

## 验收标准

1. AC1 不自动合：没设档位、`merge: human`、读不到 1.15、前提不满足（`checkLedger` 关、轻任务、Spec 或 Plan 没批）时，最终验收的 `review add`、`merge approve`、`merge run` 输出与改前相同；档位是 `auto` 但前提不满足时多那一行原因。
2. AC2 判定：`merge: auto` 且前提满足时最终验收事项记 `reviewer: "codex"`，`review add` 输出指向 `review codex`；spec-guard 报强制人批时照人合。
3. AC3 Codex 审查命令：`review codex` 对最终验收给出带 `--base <合并基点> --head <X>` 的命令，审查说明含验收标准的要求；复审带 `--previous-report`。
4. AC4 Codex 结论：有阻断 → 返工通知（第 1、2 轮）；第 3 次审仍有阻断 → 退出码 5、草稿；没有阻断 → 事项记 `codex.verdict: pass`、仍开着、输出提示 `merge auto`；报告指纹与 X 对不上 → 退出码 3。
5. AC5 放行与合并：Codex 无阻断后 `merge auto` 记 `auto-release`、建带 `auto` 的合并批准、交审事项关成 `answered`、没有【用户答复】；接着合入集成分支（`--no-ff`、完整检查照跑、记 `by: merge-run`），收尾与同步通知照今天；队首是别的事项时合那一个并提示再跑 `merge run`；模块分支在交审后又有提交、报告指纹与 X 对不上时退出码 3 且什么都不写；锁被占退出码 6。合并前不在模块 worktree 另跑检查（检查脚本只被合并队列调用一次）。
6. AC6 合并第一段记录：自动合的合并通过检查后合并批准记 `firstStage`（集成分支、合并提交、X、合并树、检查账键），`gateTick` 照今天勾；检查失败、冲突时不记；module-crew 不调 spec-guard 的 `--target acceptance`、不写 `~/.autopilot/` 下任何文件（测试用临时 HOME 核对）。
7. AC7 读接口：`merge first-stage --json` 按合并顺序列出最近一次推送之后的合并（人合 `auto: false`），自动合的带放行与检查证据，`check.nonAuthor` 按假设 4；`interface.json` 有 `firstStage` 一节且 `interface` 为 `1.1`、现有 `sessions` 一节不变。
8. AC8 收窄：自动合的事项因模块原因退回、被撤销批准时各调一次收窄入口（夹具看参数）；环境原因退回、钩子拒绝、Codex 超限或不可用时不调；同一事项只降一次。
9. AC9 显示：`review list`、`merge queue`、`status`（含 `--json`）写出自动合的进度与计数；`review batch` 不列自动合的最终验收、末尾告知行列出。
10. AC10 不可用：`merge approve`／`merge accept` 对没有 `fallback` 的自动合事项退出码 3；用户选「这次由用户验收」后照今天的最终验收走、不再 `merge auto`。
11. AC11 skill 与文档：`crew-coordinator`（两份）写明自动合的完整步骤（`review codex` → 后台跑 → `codex-note` → `merge auto` 放后台 → 按退出码处理）、推送、开 PR、最终验收记录与远端合并归 autopilot；`crew-dev`（两份）写明自动合的最终验收照常交审、Codex 返工照普通返工处理、获批后同样不勾不提交、不照 spec-guard 阶段提示自己记验收；`docs/commands.md` 有 `merge auto`、`merge first-stage`。
12. AC12 实测：本机真跑一次：一个勾了「合并：自动」的模块走完 Codex 审查（真实 `/delegate:review` 报告）→ `merge auto` → 合入 → 记 `firstStage`，`merge first-stage --json` 的输出经模块协调交 autopr-design 核对，结果写进最终验收。
13. AC13 全量测试通过。

## 并行边界

- 独占：`tests/test_takeover_merge.py`
- 公共：测试资源

## 并行说明

本模块和 `crew-takeover-approve` 同批：`crew-takeover-approve` 先合入，本模块 `module-crew sync` 后在它之上改这些共享文件：`module_crew/takeover.py`、`module_crew/review.py`、`module_crew/merge.py`、`module_crew/checks.py`、`module_crew/probe.py`、`module_crew/__main__.py`、
`skills/crew-coordinator/SKILL.md`、`codex-skills/crew-coordinator/SKILL.md`、`skills/crew-dev/SKILL.md`、`codex-skills/crew-dev/SKILL.md`、`docs/guide.md`、`docs/commands.md`、`README.md`。
另改插件对外接口 `interface.json`（加 `firstStage` 一节，决策 7），改动随本模块最终验收审。

## 未决问题

1. `merge first-stage` 的字段：Checkpoint 3 经模块协调与 autopr-design 对（决策 7）。
2. （要用户定）合并前要不要在模块 worktree 另跑一次非作者完整检查（原决策 5）：推荐**不跑**（决策 5 的理由）；若要留作 module-crew 自己的双保险，代价是自动合每次多跑一次完整检查。

## 文档建议

`docs/guide.md` 加一节「自动合（合并第一段）」：勾了「合并：自动」后最终验收怎么走（本地 Codex 审查放行合并第一段，最终验收记录在 PR head 由 autopilot 做）、Codex 不可用或超限会怎样、出事先撤合并、推送与远端合并归 autopilot；`docs/commands.md` 补 `merge auto`、`merge first-stage`；README 的接管档位一节（`crew-takeover-approve` 改写的那节）补一句合并第一段。CHANGELOG 随发版写。

## 变更记录

- 2026-11-21：「并行边界」改成每个文件写完整的仓库相对路径（`module_crew/review.py` 等，照 `spec/crew-autonomy-tier.md` 的写法），`docs/` 两个文档与 README 从「公共」移到「共享」并写全路径；内容范围不变。原因：`module-crew review batch` 对简写路径报 bad-path、spec-guard 读不了；来源：mc-coord 2026-11-21 提醒（#21930），随 Plan 交审一并复审。
- 2026-11-21：「并行边界」去掉「共享：」一行，共享文件清单与 `interface.json` 的说明挪到紧跟其后的新节「并行说明」（照 `spec/crew-autonomy-tier.md`）；「公共」行只留类别「测试资源」；内容范围不变。原因：spec-guard verify-artifacts 只认「独占」「公共」两种行，「共享」行与带说明的公共行判为 unknown-line；来源：用户 2026-11-21 在 mc-coord 会话答复「批草案并改边界」（mc-coord 转达 #21947），随最终验收附 Spec 差异一并复审。
- 2026-11-22（Checkpoint 0，按真实接口改）：spec-guard 0.91.x 的最终验收记录（`review_mark --target acceptance --state codex-approved`）要读 autopilot 编排写的 `~/.autopilot/evidence/<owner>__<repo>/<HEAD>.json`（只认 `runner: autopilot-orchestrator`），本地合入时没有 PR 也没有这份证据，原决策 7「合入后写验收标记」做不成。改为：module-crew 只放行并完成合并第一段，凭 Codex 审最终补丁无阻断且绑定 X；非作者检查就是合并队列那次完整检查（去掉原决策 5「合并前在模块 worktree 另跑」，原未决 1 随之消失）；合入后记 `firstStage`；给 autopilot 的读接口由 `check evidence` 改为 `merge first-stage`（`interface.json` 节名 `firstStage`）；最终验收记录、编排证据、推送、PR、远端合并归 autopilot。改了目标、范围、上游依赖、假设 1～4、7，决策 3～10，接口约定，AC5～AC12，边界，未决问题，文档建议。来源：autopr-design #22045、#22050（经 mc-coord #22049、#22052 告知；module-crew 不调 autopilot 的回绝照旧），spec-guard 0.91.3 `interface.json` 与 `spec/codex-final-acceptance.md`；停在 Checkpoint 0 交用户复审。
