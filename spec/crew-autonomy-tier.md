# Spec: crew-autonomy-tier

<!-- spec-guard: review pending -->

> 能力图模块 `crew-autonomy-tier`（第十版第 3 个）。需求来源：接缝 S32，已批方案 plugin-ecosystem `proposals/2026-10-24-S32-并行流畅与额度外包.md`（612634c，用户 2026-10-24「按推荐批准」）
> 第二节 module-crew 第 5 条（自治档位、升档建议、出事降档）与 spec-guard 第 2、3 条（`autonomyTier` 配置项、底线）；第三节守门：开关默认关、凭用户原话开，读不到新接口照今天问用户。开会话依据：用户批准事项 C230。
> 依赖 `crew-declared-scope`（`declared.enabled`、声明范围处理公共文件）、`crew-check-ledger`（检查账、`check list --json`、基线检查）；上游 spec-guard 0.85.0（interface 1.11）的 `autonomyTier`。
> 标「新」的是写 Spec 时补的实现取舍，请重点审。

## 目标

项目在 spec-guard 的 `.agent/config.json` 里设了 `autonomyTier` 后，module-crew 按档位放开三件事，并替用户盯着档位合不合适：

- `strict`：今天的做法，什么都不变。
- `standard`：Spec 和 Plan 一起交审；Plan「预先声明」名单内的公共文件按 `crew-declared-scope` 处理（直接改、合并时一并审、确需提前进集成分支的自动落地事后汇总）。
- `relaxed`：在 `standard` 的基础上，同步、快检查、记账类的消息不再逐条告诉用户，只在收尾时汇总一次。
- 工具从状态库算证据，最近几个模块连续达标就建议升一档，用户一句话确认才升；出事自动降一档并马上告诉用户。

任何档位都不低于 spec-guard 共享检查点规则「自治档位与底线」：能力图、Spec（可以和 Plan 一起批）、最终验收要用户批；测试改不红、Spec 没覆盖的决策、高风险不可逆改动这三种情况必停。
没设档位、或读不到 spec-guard 的新接口时，一切和今天一样。

## 范围

**范围内**

1. **读档位**：新文件 `module_crew/autonomy.py` 按 interface.json 的 `autonomyTier.readFrom` 调用 spec-guard，取值与来源；读不到一律当 `strict` 并写明原因。
2. **写入前提核对**：`module-crew tier --preflight` 确认本机 spec-guard ≥ 0.85.0 且接口有 `autonomyTier`，不满足时退出码 3、说明为什么现在不能写。写入本身由模块协调用 `/spec-guard:config` 做，要用户原话（决策 2）。
3. **生效档位** = spec-guard 里设的档位，再受 module-crew 记下的「降档上限」约束（决策 3）。
4. **standard 的两项效果**：评审节奏与声明范围（决策 4、5）。
5. **relaxed 的收尾汇总**：新命令 `module-crew tier digest [--json] [--mark-told]`（决策 6）。
6. **升档建议**：按状态库证据算，显示在 `tier`、`status` 与 `merge run` 合入后的输出里（决策 7）。
7. **出事降档**：四类事件自动降一档、记账、输出要马上告诉用户的一行（决策 8）；降档后恢复要用户原话（`tier restore`）。
8. **`status` 显示档位一段**。
9. **skill 与文档**：`crew-coordinator`、`crew-dev`（Claude 与 Codex 各一份）、README。

**范围外**

- 改 spec-guard：`autonomyTier`、`reviewCadence` 的存储、校验、`--confirm` 流程都照 spec-guard 的；module-crew 不直接写 `.agent/config.json`，也不调用没在 interface.json 声明的 `project_config.py set`。
- 声明范围本身的判定与提前落地（`crew-declared-scope`）、检查账与基线检查本身（`crew-check-ledger`）：本模块只读它们、在它们的出口挂降档。
- 额度外包（`crew-codex-offload`）：本模块不定义它在各档的行为；它要按档位放开时，读本模块的 `autonomy.effective`。
- 档位影响模块会话自己的停点：三种必停情况、`gate` 检查点照旧，模块会话不读档位。
- 决策收件箱、session-protocol 的消息格式：不新增消息类型、不改字段。

## 假设（请逐条确认）

1. **（新）档位本身就是开关**：spec-guard 里没设 `autonomyTier`（来源 `default`）时，module-crew 的所有新行为都不出现——包括升档建议；用户亲口要求、模块协调用 `/spec-guard:config` 写入任一档（含显式写 `strict`）后才算打开。
   不另设 module-crew 自己的开关，免得两个键说法不一。显式写 `strict` 的效果只有一个：开始给升档建议。
2. **读法照 interface.json**：`readFrom` 写的是一段文字而不是命令数组，module-crew 只认它以 `python3 -B hooks/project_config.py show --project <project-root> --format json` 开头这一种写法，按这个固定参数列表运行（带超时、不经 shell、脚本必须在 spec-guard 安装目录内，同 `probe.safe_command` 的安全限制）；
   写法变了、接口没有 `autonomyTier`、命令跑不成、输出里没有这一项，一律读作 `strict`，原因写给看的人（「读不到档位：<原因>，按 strict」）。值不合法时 spec-guard 自己报 `strict`、来源 `default (config invalid)`，照收。
3. **在哪个 checkout 读**：`.agent/config.json` 入库，各分支可能不同；module-crew 一律在集成 checkout（`integrationBranch` 所在的 checkout）读，以集成分支为准。模块 worktree 里不读档位。
4. **写入后要提交**：`/spec-guard:config` 只改集成 checkout 的工作区。模块协调写入后立刻把 `.agent/config.json` 单独提交（提交信息带用户原话），这条提交按 `crew-unqueued-commits` 算「不经合并队列的提交」照常处理；各模块下次同步时拿到。
5. **（新）「出事」的四类**：① `merge run` 因模块的原因退回（完整检查失败或冲突，`returnKind: module`；检查环境的退回不算）；② 用户撤销合并批准（`merge revoke`）；③ 返工满 3 次（`rework-over-limit`）；④ `check baseline` 新跑出的基线失败（读到旧记录不算）。
   用户在交审时答「退回」不算出事（那是正常评审），只算进升档证据。
6. **（新）升档证据的口径**：只看「当前档位开始以后」合入的模块（轻任务不算）。「开始」= module-crew 最近一次看到生效档位变化的时刻（决策 3 记的事件）。每个模块的四个数：
   合并退回次数（`returnKind: module`）、撤销批准次数、返工轮次（`rework-sent` 次数）、用户退回次数（交审事项以 `closedReason: answered` 关闭）。
   **达标** = 合并退回 0、撤销 0、返工 ≤ 1、用户退回 0；**连续 3 个模块达标**就建议升一档。3 与 1 写成常量，以后要调再改。
7. **底线是检查项，不是可选项**：任何档位下 `review approve` 仍要用户原话、最终验收仍要用户答复、开工说明仍写「收到开工类【协调通知】之前不要开始构建」、`【等待用户】` 照常立刻转给用户；relaxed 收进汇总的只有决策 6 列的几类消息。项目规则更严时以项目为准（例如项目没设 `reviewCadence=combined`，standard 也照 separate 交审，见决策 4）。

## 关键决策与取舍（请重点审）

1. **（新）读档位的入口放在新文件 `module_crew/autonomy.py`**：`read(project) -> Tier`，`Tier` 有 `value`（`strict`／`standard`／`relaxed`）、`source`（spec-guard 报的来源）、`usable`、`reason`；
   `effective(db, project) -> Effective`，有 `configured`（`Tier`）、`cap`（降档上限或 `None`）、`value`（两者取低）、`explicit`（来源不是 `default`，即假设 1 的开关）；同一进程内读一次就缓存。
2. **（新）写入走 spec-guard，module-crew 只做写入前核对**：`module-crew tier --preflight` 核对三件事：Claude 的插件安装记录里 spec-guard 版本 ≥ 0.85.0；它的 interface.json 有 `autonomyTier`；
   状态库登记过 Codex 会话（`codex-desktop`）时另起一行「Codex 那边的 spec-guard 版本 module-crew 查不到：0.67.1 及更早会把整份配置判无效，请用户确认 Codex 也装了 0.85.0 以上」（只提醒、不拒）。
   前两项不满足退出码 3。crew-coordinator skill 写明：用户要设或改档位时，先跑 `tier --preflight`，通过后在回复里引用用户原话，用 `/spec-guard:config` 写 `autonomyTier`；
   要设成 `standard` 或 `relaxed` 时同一句原话里一并写 `reviewCadence=combined`（spec-guard 不联动它）；写完照假设 4 提交。
3. **（新）降档上限记在 module-crew 的状态库**：自动降档不能写 spec-guard（写入要用户原话），所以 module-crew 记 `config/autonomy`：`{"cap": "standard", "capFor": "relaxed", "incident": {...}, "seen": "relaxed", "toldSeq": 123}`。
   - `cap` 生效时，生效档位 = min(设的档位, `cap`)；`capFor` 记降档时设的是哪一档。之后设的档位改了（≠ `capFor`，说明用户又说了新的话），`cap` 自动清掉并记一条事件，以用户最新的话为准。
   - `seen` 是 module-crew 最近一次看到的生效档位；每次读到和它不同就更新并记事件 `tier-seen`，作为升档证据的起点（假设 6）。
   - 恢复：`module-crew tier restore --original-file <原话文件>` 把 `cap` 往上抬一档（抬到设的档位就清掉），要用户原话，记进事件；没有 `cap` 时退出码 3，提示「要升到设的档位以上，用 /spec-guard:config」。
4. **（新）standard 的评审节奏**：module-crew **不替** spec-guard 改 `reviewCadence`，只读它（`start.cadence_info` 照旧）。生效档位 ≥ standard 而 `reviewCadence` 不是 `combined` 时，`tier` 与 `status` 写一行
   「档位 standard 要 Spec 与 Plan 一起审，但 reviewCadence 是 separate：请用户确认后用 /spec-guard:config 设成 combined」，开工说明与 `review batch` 照 separate（宁严勿松）。
   反过来，`cap` 把生效档位压到 strict 而 `reviewCadence` 是 `combined` 时，`start.review_cadence` 返回 `separate`（开工说明写 separate、`review batch` 不合并 Spec 与 Plan）；没有 `cap` 时完全照 spec-guard 的 `reviewCadence`，和今天一样。
5. **（新）standard 的声明范围：派生，不替用户写开关**：`declared.enabled(db)` 改为：`declaredScope` 是 `on` → 开；是 `off`（用户明说过关）→ 关；**没设过**时，生效档位 ≥ standard → 开。
   不在切档时写 `declaredScope` 键——否则降档时要再写一次，而关开关按 `crew-declared-scope` 也要用户原话。用户显式设过的开关永远优先。`crew-declared-scope` 的「读不到声明照今天问用户」照旧生效。
6. **（新）relaxed 的收尾汇总**：`tier digest` 从事件日志里取 `toldSeq` 之后的这几类，按模块分组列出、给一段可以直接给用户看的汇总正文：
   - 同步：合入后发出的同步基线通知（几条、发给谁）、公共变更落地后的同步通知、模块 `module-crew sync` 的结果；
   - 快检查与记账：检查账新增的记录（快检查／完整检查、通过／失败、树短号，取自 `check list --json`）；
   - 不经合并队列的提交（`crew-unqueued-commits` 记下的）；提前落地（`change landed` 里还没汇总的，`--mark-told` 时一并标记）。
   `--mark-told` 把 `toldSeq` 推到当前最新事件号（只是记账，不要原话）。退出码：`0` 有内容、`3` 没有。
   crew-coordinator skill 写明：生效档位是 relaxed 时，这几类消息不再逐条告诉用户；**给用户发批量交审、最终验收，或 `merge cleanup` 本批收尾时**，先 `tier digest`，把正文写进那条消息，再 `--mark-told`。
   降档通知、`【等待用户】`、基线变红建的修基线任务、权限弹窗、任何要用户决定的事**不进汇总**，照常立刻告诉用户。生效档位低于 relaxed 时 `tier digest` 照样能跑（只读），但 skill 不要求用它。
7. **（新）升档建议**：`tier` 与 `status` 在假设 1 的开关打开、生效档位不是 relaxed、且满足假设 6 时写
   「可以建议升到 <下一档>：最近 3 个模块（a、b、c）合并退回 0、撤销 0、返工 ≤ 1、用户退回 0」；`merge run` 合入后满足时在输出末尾加同一行。
   这只是建议：skill 写明把它转告用户、用户一句话确认后，没有 `cap` 的照决策 2 写 spec-guard，有 `cap` 的用 `tier restore`。同一个起点只建议一次（记 `suggestedAt`），用户不理就不再重复，直到证据起点变了。
8. **（新）出事降档**：假设 5 的四个出口各调一次 `autonomy.incident(db, project, kind, detail)`。生效档位是 strict 时什么都不做；否则把 `cap` 设成低一档，记事件 `tier-lowered`（含原因、事项号），
   返回一行「自治档位已从 <原档> 降到 <新档>：<原因>。马上告诉用户；恢复要用户原话（module-crew tier restore）」，由调用它的命令原样输出。同一次 `merge run`、同一个事项只降一次。
   挂钩的位置（供模块协调排写码先后）：
   - `module_crew/merge.py`：`_run` 退回分支（`returnKind == "module"` 时）、`revoke` 成功后；
   - `module_crew/review.py`：`note` 里记 `rework-over-limit` 之后；
   - `module_crew/checks.py`：`baseline` 新跑出失败、调用 `fix_task` 的地方。
9. **`status` 的档位一段**：只在开关打开（假设 1）或有 `cap` 时显示：「自治档位：设的 <值>（<来源>），生效 <值>」，有 `cap` 加「（<日期> 因 <原因> 降档，恢复要用户原话）」，再跟决策 4 的提示、决策 7 的建议。`status --json` 的 `store` 多 `autonomy`：`null` 或 `{"configured", "source", "cap", "effective", "suggest": <档或 null>, "evidence": [...]}`。读不到档位时写「读不到档位：<原因>，按 strict」。

## 接口约定

### 命令

```bash
bin/module-crew tier [--json]                              # 只读：设的档位、来源、降档上限、生效档位、证据、建议
bin/module-crew tier --preflight                           # 只读：写入 autonomyTier 之前核对 spec-guard 版本与接口
bin/module-crew tier restore (--original <原话> | --original-file <文件>)
bin/module-crew tier digest [--json] [--mark-told]
```

- `tier`：`0`。`--json`：`{"configured": {"value", "source", "usable", "reason"}, "explicit": bool, "cap": str|null, "effective": str, "cadence": str, "cadenceHint": str|null, "evidence": [{"module", "returned", "revoked", "rework", "userReturned", "ok": bool}], "suggest": str|null}`。
- `tier --preflight`：`0` 可以写；`3` 不能写（原因逐条）。
- `tier restore`：`0` 抬了一档；`2` 参数错；`3` 原话为空或没有 `cap`。
- `tier digest`：`0` 有内容；`3` 没有。

### Python 入口（供 crew-codex-offload 等后续模块读）

```python
autonomy.effective(db, project) -> Effective     # value: "strict" | "standard" | "relaxed"
autonomy.incident(db, project, kind, detail) -> str | None   # kind: "merge-returned" | "revoked" | "rework-over-limit" | "baseline-red"
```

### 记录（只增不改）

```json
// config/autonomy（新键，config 种类已有）
{"cap": "standard", "capFor": "relaxed", "incident": {"kind": "merge-returned", "item": 231, "at": "..."},
 "seen": "standard", "seenAt": "...", "suggestedAt": null, "toldSeq": 0}
```

事件动作：`tier-seen`、`tier-lowered`、`tier-restored`、`tier-cap-cleared`、`tier-suggested`、`digest-told`。

## 项目结构

```text
module_crew/autonomy.py          新：读档位、生效档位、降档上限、证据与建议、digest
module_crew/declared.py          enabled()：没设开关时看生效档位（决策 5）
module_crew/start.py             cadence_info／review_cadence：cap 压到 strict 时返回 separate（决策 4）
module_crew/merge.py             _run 退回分支、revoke 之后挂 incident；合入后输出升档建议（决策 7、8）
module_crew/review.py            note：rework-over-limit 之后挂 incident
module_crew/checks.py            baseline：新跑出的失败挂 incident
module_crew/probe.py             status：store.autonomy
module_crew/__main__.py          tier 子命令；status 显示档位一段
skills/crew-coordinator/SKILL.md、codex-skills/crew-coordinator/SKILL.md
skills/crew-dev/SKILL.md、codex-skills/crew-dev/SKILL.md
README.md
tests/test_autonomy_tier.py
```

不改：`module_crew/changes.py`、`module_crew/present.py`、`module_crew/unqueued.py`、`module_crew/protocol.py`、`module_crew/store.py`（`config` 种类已有，不加新种类）。

## 命令

```bash
python3 -m unittest discover -s tests
PYTHONPATH=tests python3 -m unittest test_autonomy_tier
```

## 代码风格

沿用现有模块：代码与注释英文，输出中文；只用标准库；spec-guard 调用带超时、参数列表、不经 shell，入口一律经 interface.json 取。

## 测试策略

- 假 spec-guard 夹具：一份声明 1.11、`autonomyTier.readFrom` 指向小脚本（按环境变量返回 `strict`／`standard`／`relaxed`、来源 `default`／`.agent/config.json`／`default (config invalid)`）；一份只有 1.10；一份 `readFrom` 写法不同；一份脚本跑不成。
- 复用 `crew-declared-scope`、`crew-check-ledger` 的测试基类（b、c 两个模块会话、集成 checkout）。
- 档位没设（来源 `default`）：现有测试原样通过，`status`、`merge run`、`start`、`review batch` 输出逐字不变，状态库没有 `config/autonomy`。
- 降档：分别造出四类事件，档位 relaxed → standard → strict，strict 再出事不变；改设的档位后 `cap` 清掉。
- 证据：造 3 个合入的模块（其中一个返工 2 次），看建议出现与不出现。

## 边界

- **始终**：读不到档位就当 strict；降档立刻告诉用户；任何档位都守住底线；module-crew 不直接写 `.agent/config.json`。
- **先问**：设或改档位（用户原话，经 `/spec-guard:config`）；恢复降档（`tier restore` 要原话）；`reviewCadence` 跟档位不一致时改不改。
- **绝不**：自动升档；替用户写 `autonomyTier`、`reviewCadence`、`declaredScope`；把要用户决定的事收进汇总；因档位跳过任何用户批准或合并队列里的完整检查。

## 验收标准

1. 档位没设：全量测试原样通过；`status`、`start plan`、开工说明、`review batch`、`merge run`、`change add` 的输出与改前逐字相同；没有 `config/autonomy` 记录；`tier` 写「档位没设（spec-guard 默认 strict），module-crew 照今天做」。
2. 读档位：1.11 夹具三种值与三种来源都读对；1.10、`readFrom` 写法不同、脚本跑不成三种情况都读作 strict 且 `reason` 写明原因；`default (config invalid)` 读作 strict。
3. `tier --preflight`：spec-guard 0.85.0 夹具退出码 0；0.84.2 或接口没有 `autonomyTier` 退出码 3 并写原因；登记过 Codex 会话时多一行提醒、退出码不变。
4. standard（`reviewCadence=combined`）：开工说明写 combined、`review batch` 合并同一模块的 Spec 与 Plan；`declaredScope` 没设时 `declared.enabled` 为真、`change add` 走名单内分类；`declaredScope: off` 时为假。
   standard 而 `reviewCadence=separate`：照 separate，`tier`、`status` 有提示行。
5. relaxed：`tier digest` 列出 `toldSeq` 之后的同步通知、检查账记录、不经队列的提交、未汇总的提前落地，按模块分组并给汇总正文；`--mark-told` 后再跑退出码 3；降档、【等待用户】、修基线任务不在汇总里。
6. 降档：四类事件各自把 relaxed 降到 standard（再一次到 strict），输出带「马上告诉用户」那一行、记 `tier-lowered`；strict 时不变、无输出；同一事项只降一次；检查环境的退回与读到旧基线失败记录不降。
   `cap` 压到 strict 且 `reviewCadence=combined` 时开工说明写 separate。
7. 恢复与清除：`tier restore` 没原话或没 `cap` 退出码 3；有原话时抬一档并记原话；设的档位改了之后 `cap` 自动清掉并记事件。
8. 升档建议：开关打开、档位开始后连续 3 个合入模块达标时，`tier`、`status`、`merge run` 合入输出写建议；有一个返工 2 次就不写；档位没设时不写；同一起点只记一次 `tier-suggested`。
9. 底线：relaxed 下 `review approve` 没原话仍被拒、开工说明仍有「收到开工类【协调通知】之前不要开始构建」、最终验收仍要 `review answer`；有测试逐条断言。
10. skill：`crew-coordinator`（两份）写明设档位的步骤（先 `tier --preflight`、引用原话、`/spec-guard:config` 同时设 `reviewCadence`、写完提交）、relaxed 时何时跑 `tier digest`、降档马上告诉用户、升档只建议不自动、`tier restore` 要原话；
    `crew-dev`（两份）写明档位不改变模块会话的停点：三种必停情况与 `gate` 检查点照旧。
11. 全量测试通过（后台跑）；本机 spec-guard 0.85.0 实测一次 `project_config.py show` 读档位，结果写进最终验收。

## 并行边界

- 独占：`module_crew/autonomy.py`、`tests/test_autonomy_tier.py`
- 共享（和 `crew-codex-offload` 可能同时改，改不同段落）：`module_crew/merge.py`（`_run` 退回分支、`revoke`、合入后的输出行）、`module_crew/__main__.py`（新增 `tier` 子命令、`status` 一段）、`module_crew/probe.py`（`status` 的 `store`）、
  `module_crew/declared.py`（`enabled`）、`module_crew/start.py`（`cadence_info`／`review_cadence`）、`module_crew/review.py`（`note`）、`module_crew/checks.py`（`baseline`）、两份 `crew-coordinator` skill、两份 `crew-dev` skill、README
- 公共：测试资源

## 并行说明

本模块对 `merge.py`、`review.py`、`checks.py` 都只在已有分支里加一行调用和一行输出，不改合并、返工、检查本身的逻辑。和 `crew-codex-offload` 最可能碰到的是 `merge.py`、`__main__.py`、`probe.py` 的 `status` 与两份 `crew-coordinator` skill；
若它也要在合入后的输出或 `status` 里加段落，先合入的一方定位置，后合入的一方 `module-crew sync` 后接在后面。

## 未决问题

- 「收尾」的时机这一版取「批量交审、最终验收、`merge cleanup` 本批收尾」三处；LIVE-SAAS 下一轮用下来嫌汇总太晚或太碎再调。
- 升档门槛（连续 3 个、返工 ≤ 1）是先定的常量，要等 LIVE-SAAS 下一轮的数（方案第一节第 5 条）再校准。

## 文档建议

README 加一小节「自治档位」：三档各放开什么、怎么设（先 `tier --preflight`、`/spec-guard:config` 同时设 `reviewCadence`）、升档建议与出事降档、底线；「命令一览」补 `tier` 四种用法。CHANGELOG 随发版写。
