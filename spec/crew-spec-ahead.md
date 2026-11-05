# Spec: crew-spec-ahead

<!-- spec-guard: review approved 415719aa9b6c -->

> 能力图模块 `crew-spec-ahead`。需求来源：接缝 S60（live-saas-backoffice 想让用户点名的模块在依赖没做完时先写 Spec），用户在 mc-coord 已定取舍四条，批准开会话（批准事项 C457）。
> 依赖 `crew-start`（`start plan`／`start prepare`、开工说明、名额、`_held` 与同批依赖检查）、`crew-review-batch`（`review approve` 生成开工类【协调通知】）；
> 另用到 `crew-declared-scope`（开关 `declaredScope` 下的依赖挡住）、`crew-codex-offload`（`_start_todo` 决定开工通知写法）、`crew-merge`（`merge run` 输出）、`crew-codex-host`（Codex 开工说明）。
> 现状取自 0.22.2 源码（`start.py`、`review.py`、`offload.py`、`merge.py`、`__main__.py` 的 `status`）。标「新」的是写 Spec 时补的实现取舍，请重点审。

## 目标

用户点名一个依赖还没做完的模块时，模块协调可以先把它开起来，只写 Spec 与 Plan：

- `start prepare` 凭用户原话接受「依赖未完成」的模块，照常占名额；同一次点名的模块之间有依赖也可以一起开；
- 开工说明写明「这是提前开工：只写 Spec 与 Plan，依赖合入前不会收到开工通知」；
- Spec、Plan 照常交审批准；Plan 批准时依赖还没合入，`review approve` 不发开工通知，模块会话停在原地；
- 依赖都合入后，`status` 与 `merge run` 提示「X 的依赖已就位，可以发开工通知」，模块协调问用户一次，用户同意后用新命令发出开工通知。

第一个用户是 LIVE-SAAS 后台（live-saas-backoffice）。

## 范围

**范围内**

1. `start prepare`：放宽「依赖未完成」这一条（关键决策 1），会话登记记下 `specAhead`。
2. 开工说明：提前开工的模块多写一段限定说明（关键决策 3）；Claude 与 Codex 宿主都写。
3. `review approve`：提前开工的模块 Plan 批准时依赖未就位，不发开工通知，输出写明（关键决策 4）。
4. 新命令 `start kickoff <模块> (--original <原话> | --original-file <文件>)`：依赖就位后凭用户原话发开工通知（关键决策 5）。
5. 提示：`status`（「会话与待办」一节）与 `merge run`（合入成功后）列出依赖已就位、等发开工通知的模块（关键决策 6）。
6. `declaredScope` 打开时：提前开工的模块不受「和在用模块有依赖关系」挡住，同批有依赖也放行（关键决策 2）。
7. 文档：crew-coordinator skill（Claude 版与 Codex 版）「开工」一节补「提前开工」；crew-dev skill（两份）补一句 Plan 批准后不来开工通知就停住；`docs/guide.md`、`docs/commands.md`（`start kickoff`）、README／README.en 功能清单；CHANGELOG 与版本号随 0.23.0 发版由模块协调写。

**范围外**

- 改 spec-guard（`/map` 的 `startable`、`missingDeps` 不变）；依赖 S61。
- `start plan` 主动提议提前开工的模块。
- 依赖模块的 Spec 之后被修改时提醒本模块（本模块不做）。
- 放宽名额、已有在用会话、worktree／分支已存在、退回串行、probe 阻塞等其他挡住条件。
- 改契约 session-protocol（开工通知仍是现有的开工类【协调通知】）。

## 假设（请逐条核对）

用户在 mc-coord 已定的取舍：

1. **可写到 Spec 和 Plan**，两份都可以交审、批准；Plan 批准后依赖未合入就不发开工通知，模块会话停住。
2. **这类会话占多模块名额**（后台 3 个只开 2 个也可以）。
3. **依赖都合入后**，`status` 与 `merge run` 提示「X 的依赖已就位，可以发开工通知」，由模块协调问用户一次再发，**不自动发**。
4. **同一次点名的模块之间有依赖也可以一起开**；打开了 `declaredScope` 的项目也放宽这一条。

协调提出、用户未反对的假设：

5. **只在用户原话点名时这样开**：`start plan` 不主动提议提前开工的模块。
6. **只放宽「依赖未完成」这一条**：名额、已有会话、worktree 已存在、分支已存在、退回串行、probe 阻塞等挡住条件照旧。
7. **依赖指能力图的 depends-on**，被依赖的模块至少在能力图里（不要求已开会话、已写 Spec）。
8. **开工说明写明只写 Spec 和 Plan**。
9. **依赖模块的 Spec 之后改了不自动提醒**（本模块不做）。
10. **只改 module-crew**，不改 spec-guard，不依赖 S61。
11. **Codex 宿主同样适用**。
12. **发版 0.23.0**。

写 Spec 时补的假设（新）：

13. 「依赖未完成」指 `/map --json` 里该模块状态为 `not_ready`（`missingDeps` 非空）。状态为 `blocked`（等被挂起的模块）、`suspended`、`in_progress`、`done` 的不按提前开工放行，照旧拒绝或走原有重开路径。
14. 「依赖就位」指该模块能力图上的每个依赖：`/map` 状态为 `done`，或在 crew 里已合入（合并批准关为 `merged`，与 `_merged_modules` 同口径）。
15. 自治档位不影响「问用户一次」：任何档位下提前开工模块的开工通知都只由 `start kickoff` 凭原话发。

## 关键决策与取舍（请重点审）

1. **（新）`start prepare` 不加新参数，按模块状态自动认出提前开工。** 校验里模块不在 `startable.modules` 时，先看重开（现有），再看是否 `not_ready`：是就记入 `proposal.specAhead`，不报「不在可开工列表」。
   用户原话就是点名；协调 skill 写明只在用户原话点名了这个模块时才这样开。
   取舍：加 `--spec-ahead` 开关更显式，但协调多记一个参数、用户原话已是唯一依据，所以不加；代价是协调可能在用户没点名时误开——由 skill 约束和输出里醒目的一行
   「<模块>：提前开工（依赖 <列表> 未完成），只写 Spec 与 Plan」兜住，开工批准事项另记 `specAhead: [模块…]`，可查。
2. **（新）`declaredScope` 打开时的两处放宽只对提前开工的模块生效。** `_held`（和在用模块有依赖关系就等它合入）对 `specAhead` 模块不挡；同批「<a> 和 <b> 有依赖关系，不能同时开」在两者之一是 `specAhead` 时不挡。
   都是普通可开工模块之间的依赖照旧挡（它们会同时构建）。理由：提前开工的模块在依赖合入前不构建，碰不到公共文件，不会和依赖抢声明范围。
   开工通知发出时依赖已合入，上游不再「在用」；下游若也是提前开工的模块，它在本模块合入前同样不构建。所以 `start kickoff` 不再重查 `_held`。
3. **开工说明的限定段**：普通「这一步只做」行之后、「收到开工类【协调通知】之前不要开始构建」之前，加两行：
   「这是提前开工：依赖 <列表> 还没合入。只写 Spec 与 Plan、照常交审；Plan 批准后不会马上收到开工通知，停在原地等，不要构建，也不用为此发【等待其他会话】。」
   「依赖合入后模块协调会问用户，再发开工通知；收到后先 module-crew sync 拿到依赖的代码再构建。」评审节奏（separate／combined）照项目配置；Codex 开工说明在此基础上照旧附 `codex_lines`。
4. **`review approve` 的开工通知闸**：模块 Spec 与 Plan 都已批准、本次批了 Plan 时，若该模块在用会话带 `specAhead` 且依赖未就位，不生成开工通知，输出
   「<模块>：提前开工的模块，依赖 <未就位列表> 还没合入，没有发开工通知；依赖就位后 status 与 merge run 会提示，问用户一次再运行 start kickoff <模块>」。
   【用户答复】照常生成（模块知道 Plan 已批）。依赖在 Plan 批准时已经就位的，照今天直接发开工通知（不必再问一次：用户批 Plan 本身就是开工批准，与普通模块一致）。
5. **（新）新命令 `start kickoff`**，参照 `offload decline` 补发开工通知的做法：
   - 校验：模块有在用的 `specAhead` 会话；Spec 与 Plan 都已批准（取最近一次含 Plan 的批准事项）；依赖都已就位；还没发过（会话登记 `kickoff` 为空）；原话非空。任一不过退出码 3，什么都不写。
   - 落地：记一条已答事项（`kind: "start-kickoff"`，原话、模块、依据的批准事项号）；开工通知「依据」写 `start_basis(批准事项)` 加「依赖 <列表> 已合入，用户 C<本事项> 同意开工」；
     「要你做什么」经 `_start_todo`（额度外包开关打开时照外包规则，条件不满足时同样不发并提示 `offload decline`）；会话登记写 `kickoff: <事项号>`。
   - 输出发送项（收件人、正文路径），模块协调照它 `bridge_send`。
   取舍：也可以让 `review approve` 在依赖就位后重跑时补发，但那要重复批准一次；单独命令更清楚地对应「问用户一次」。
6. **提示**：`status` 的「会话与待办」每个依赖已就位、未发开工通知且 Plan 已批准的提前开工模块一行
   「<模块> 的依赖已就位，可以发开工通知：问用户一次，同意后 module-crew start kickoff <模块> --original-file <原话文件>」；依赖未就位的一行「<模块> 提前开工，等 <列表> 合入」。
   `merge run` 合入成功后，对这次合入让依赖变为就位的提前开工模块输出同样的「依赖已就位」行；Plan 还没批的只在 `status` 里显示「依赖已就位，Plan 批准后直接发开工通知」。
   `status --json` 在 `store` 下加 `specAhead: [{module, missing, kickoffReady, kickoff}]`。
7. **（新）`review batch` 不改**：提前开工模块的依赖核对照旧可能显示「依赖未就绪」，作为给用户的提示保留；协调 skill 写明这是预期的，不挡批准。

## 接口约定

### 记录

```json
// session（dev）新增字段
{"role": "dev", "module": "b", "specAhead": {"missing": ["a"], "since": 812}, "kickoff": null}
// item kind=start 新增字段
{"kind": "start", "modules": ["a", "b"], "specAhead": ["b"]}
// item kind=start-kickoff
{"state": "closed", "kind": "start-kickoff", "closedReason": "answered", "module": "b", "approval": 830,
 "answer": {"original": "...", "answeredAt": "..."}}
```

### 命令

```bash
bin/module-crew start prepare <模块 id>… (--original <原话> | --original-file <文件>) [...]   # 不变，放宽依赖未完成
bin/module-crew start kickoff <模块 id> (--original <原话> | --original-file <文件>) [--json]
```

- `start kickoff`：`0` 已生成开工通知（或外包条件不满足、按 `_start_todo` 不发并提示，此时不记 `kickoff`、退出码 3）；`3` 校验不过，什么都没写；`2` 参数错。

## 项目结构

```text
module_crew/start.py               validate 认 specAhead、_held 与同批依赖放宽、开工说明限定段、kickoff()、spec_ahead_rows()
module_crew/review.py              开工通知闸
module_crew/merge.py               合入后输出「依赖已就位」
module_crew/__main__.py            start kickoff 子命令；status 文字与 --json
skills/crew-coordinator/SKILL.md   「开工」补提前开工
codex-skills/…/crew-coordinator    同上（Codex 版）
skills/crew-dev/SKILL.md           Plan 批准后不来开工通知就停住
codex-skills/…/crew-dev            同上
docs/guide.md、docs/commands.md、README.md、README.en.md
tests/test_spec_ahead.py
```

## 命令

```bash
python3 -m unittest discover -s tests -v
```

## 代码风格

沿用前几个模块；能力图与依赖一律取 `probe.run()` 的 `/map --json`，不另读 spec-guard；状态走 `store` 事务；开工通知正文走 `protocol.render_coordination_notice`。

## 测试策略

- 用 crew-start 的插件夹具：能力图 a → b（b 依赖 a），a 可开工、b `not_ready`；每个测试建临时仓库。
- 开关 `declaredScope` 打开与关闭各跑一遍同批开 a、b 与「a 在用时开 b」。
- 走完整链路：`prepare a b` → b 交 Spec、Plan → `review approve`（无开工通知）→ 夹具把 a 改为合入 → `status`／`merge run` 出提示 → `start kickoff b` → 开工通知可被 `protocol.parse` 判为合格。
- 外包开关打开时 `start kickoff` 走 `_start_todo`。

## 边界

- **始终**：只放宽「依赖未完成」；开工通知只凭用户原话发；先校验后落地。
- **先问**：用户原话没点名的模块提前开；在依赖未就位时发开工通知。
- **绝不**：自动发提前开工模块的开工通知；改 spec-guard；推送。

## 验收标准

1. 能力图 a → b、a 可开工：`start prepare b --original "先开 b 写 Spec"` 退出码 0；会话登记带 `specAhead.missing = ["a"]`；开工批准事项带 `specAhead: ["b"]`；输出含「b：提前开工（依赖 a 未完成），只写 Spec 与 Plan」。
2. b 的开工说明含限定段两行（依赖 a、只写 Spec 与 Plan、不会马上收到开工通知、收到后先 sync），其余与普通开工说明一致；宿主为 Codex 时同样含限定段并附 Codex 段。
3. 照旧拒绝且什么都不写：b 状态为 `blocked`（a 挂起）；名额已满；b 已有在用会话；b 的 worktree 目录或分支已存在；运行配置为串行。
4. `start plan` 不提议 b（`not_ready`），原因照旧写「等 a」。
5. `prepare a b` 同一次开：`declaredScope` 关与开时都退出码 0；开关打开时两个都是普通可开工模块且有依赖的照旧拒绝（回归）。
6. `declaredScope` 打开、a 已有在用会话：`prepare b` 退出码 0（不再报「和在用的 a 有依赖关系」）；普通可开工模块与在用模块有依赖时照旧挡（回归）。
7. b 的 Spec 与 Plan 批准、a 未合入：`review approve` 生成【用户答复】，不生成给 b 的开工通知，输出含「依赖 a 还没合入，没有发开工通知」。
8. b 的 Plan 批准时 a 已合入：`review approve` 照今天发开工通知。
9. a 未合入：`status` 显示「b 提前开工，等 a 合入」；`start kickoff b` 退出码 3、状态库不变。
10. a 合入（`merge run` 成功）：`merge run` 输出与 `status` 都含「b 的依赖已就位，可以发开工通知」；`status --json` 的 `specAhead` 可解析且 `kickoffReady` 为真。
11. `start kickoff b --original "可以开工"`：退出码 0；记 `kind: "start-kickoff"` 已答事项；生成开工通知（依据含批准事项号与本事项号，可被 `protocol.parse` 判为合格）；会话登记记 `kickoff`；之后 `status` 不再提示，再跑一次退出码 3。
12. 外包开关打开、条件不满足：`start kickoff b` 不发开工通知、不记 `kickoff`、退出码 3，输出提示 `offload decline`。
13. 协调 skill（两份）「开工」一节写明：只在用户原话点名时提前开、`review batch` 的「依赖未就绪」是预期、依赖就位时问用户一次再 `start kickoff`；crew-dev（两份）写明 Plan 批准后没来开工通知就停住、不发【等待其他会话】。
14. 全部单元测试通过。

## 未决问题

- spec-guard 对提前开工的模块是否照常写批准标记（`/spec-guard:review-mark`、`reviewMark` 入口）与显示阶段，未用真实版本验证；
  构建第一个 Task 先用本机 spec-guard 0.85.2 在临时仓库实测。若它拒绝给 `not_ready` 模块写 approved，停下发【等待其他会话】交模块协调（那需要改 spec-guard，属 S61 范围）。

## 文档建议

- `docs/guide.md`「开工」一节加「提前开工（依赖没做完先写 Spec）」：何时用、限定、依赖就位后的 `start kickoff`。
- README／README.en 功能清单加一行；`docs/commands.md` 加 `start kickoff`。
- 无其他。

## 变更记录

- 2026-11-01：范围第 7 条与项目结构去掉 CHANGELOG（改为随 0.23.0 发版由模块协调写，与前几个模块一致），文档补 `docs/commands.md`（新命令 `start kickoff` 要进命令一览）。原因：写 Plan 时核对发版惯例（crew-final-accept-split 范围外、crew-live-rehost 文档建议都写 CHANGELOG 随发版写）；来源：本会话写 Plan 时发现，随 Plan 交审复审。
- 2026-11-04：`start kickoff` 加 `--plan-revision C<号>` 与 `--already-sent`：C 号是本模块在提前开工之后批准的 Plan 且有用户原话时，依赖未合入也记账并生成开工通知（依据写「依赖 X 未合入，按已批 Plan 修订 C<号> 不等依赖」），C 号不合格退出码 3；`--already-sent` 只补记手工已发的开工、不生成通知。原因：依赖未合入就一律拒绝，已批准的 Plan 修订（不等依赖）无法记账，手工发出的开工也补记不了；来源：live-saas-backoffice 报告 SEAMS S78（ecosystem-lead 转来），用户批准方案甲，轻任务 T480。
- 2026-11-05：`start kickoff` 加 `--answered-review`（须与 `--plan-revision` 同用）：C 号是本模块在提前开工之后、被 `answer` 关掉的 Plan 交审（kind review、node plan、closedReason answered）且有答复原话时也放行，输出原样列出当时记下的答复原话供模块协调与用户核对，通知依据写「按用户已答复的 Plan 交审 C<号> 不等依赖」；不带此参数时这类 C 号仍退出码 3，并提示可加此参数。原因：Plan 修订的交审被 `answer` 关掉、没有 `review approve` 的批准记录，`--plan-revision` 只认批准事项而报「不是批准事项」；来源：live-saas-backoffice 报告（SEAMS S81，S78 的补充），用户批准随 0.23.2 补上，轻任务 T524。
