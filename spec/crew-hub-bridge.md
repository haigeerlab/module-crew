<!-- spec-guard: review approved f085b058524f -->
# Spec: crew-hub-bridge

> 能力图模块 `crew-hub-bridge`。需求来源：LIVE-SAAS 接入方案，用户决定 11、28、29（`~/Documents/haigeerlab/livesaas-integration/USER-DECISIONS-2026-10-18.md`），
> 接缝分析 `JOINT-SEAM-CHECK.md` 第五节（S4、S5、协调会话规则）与第六节（decision-inbox 的只读出口需求）。用户 2026-10-18 在本会话确认范围与 11 条假设。
> 契约：session-protocol v1.7（1e14a49；v1.6 81720ba 新增「转自」与【负责人转交】，v1.7 写明【取代 #N】只认枢纽事项号）。

## 目标

让 module-crew 的协调会话能接在收件枢纽后面工作：用户在收件枢纽里给出的决定、或指定负责人转交的决定，经校验后可以作为 module-crew 各命令的批准来源，
并能从枢纽事项号查到对应的 crew 编号；协调会话能把一批交审合成一条交给枢纽的【等待用户】；decision-inbox 等外部插件能从一个稳定的只读出口读到各模块会话的状态。

## 范围

**范围内**

- `module_crew/sources.py` 与命令 `module-crew source add|list|map`；批准命令新增来源参数。
- `module-crew review note`（审查行）与 `review batch --for-hub`（交枢纽正文）。
- `sessions --json` 契约化；插件根目录 `interface.json`。
- 两份 skill 的措辞与协调会话规则。

**范围外**

- 跨线协作补强：外部线回复入账、显示「在等谁」、外部交付通知（用户决定 27：第一波不做）。
- 「是否在忙」：decision-inbox 自己从 agent-relay 读。
- 强制「先审再批」：审查行只提醒不拦截。
- 契约 v1.6 条文本身（契约负责人起草、用户批）。

## 假设（用户 2026-10-18 已确认）

1. 模块 `crew-hub-bridge` 追加到能力图末尾，依赖 crew-review-batch、crew-merge、crew-failure。
2. 批准来源三种：`self`（用户在协调会话亲手输入，默认）、`hub`（收件枢纽转来的【用户答复】）、`lead`（指定负责人带事项号与原话转交）；后两种的发件人先由用户在协调会话亲手登记（`source add`），未登记不认。
3. 所有批准命令新增 `--source <邮箱名> --source-item <H> --source-relay-id <消息号>`；来源非 `self` 时 `--original-file` 放对方消息全文，用契约解析核对，不合就拒绝、什么都不写；`lead` 的格式按 v1.6。
4. 每条批准记来源、H、对方消息号；一个 H 可对应多个 crew 编号；`source map` 双向查。
5. `review note` 记审查会话的【审查结论】，`review batch` 每条显示审查行，没有显示「未审查」；只提醒不强制。
6. `review batch --for-hub` 生成合格的【等待用户】正文。
7. 只读出口：`sessions --json` 加 schemaVersion 与固定字段（stage 枚举 + stageText）；读不到退出码 2、原因写 stderr；`interface.json`；字段只增不改。
8. 协调会话把枢纽答复转给模块：现有【用户答复】加来源，转完输出发给枢纽的【已恢复】「结束：#H」；按 v1.6 对照。
9. skill 措辞（crew-coordinator 第 13、25、56、122 行）与协调会话规则（含用户决定 29）。
10. 依赖 v1.6 的部分（第 3 条 hub／lead 解析、第 8 条）发版前只写 Spec；其余先做。
11. 不做跨线补强与忙闲状态。

## 关键决策与取舍（请重点审）

1. **来源登记是一张白名单，只能由用户亲手开**：`source add <邮箱名> --kind hub|lead --original-file <用户原话>` 写运行配置 `sources`（`{name, kind, addedAt, original}`），
   `source remove` 同样要原话。批准命令只认白名单里的名字；`self` 不用登记。这样「别的会话转来的话不算」这条底线不变，只是多了用户亲自指定的可信转达者。
2. **来源不是 `self` 时，原话取自对方消息、不由协调会话转写**：命令把 `--original-file` 当作对方消息全文，用 `protocol.parse` 解析，
   核对类型（hub 为【用户答复】，lead 为【负责人转交】owner-handoff）、事项号等于 `--source-item`；记下的「用户原话」是解析出的字段，不是协调会话自己写的；lead 另记「来自」短名与「转交范围」。
   任何一项对不上：退出码 3，状态库与 git 都不变。
3. **对照记在每条批准上，不另建表**：批准记录的 `answer` 增加 `source: {name, kind, item, relayId}`（`self` 时为 `{kind: "self"}`）。`source map H` 遍历记录列出所有带这个 H 的 crew 编号与节点；
   `source map #N` 反查 N 的来源。不新增记录种类，状态库格式只加字段。
4. **审查行只读审查结论、不判断**：`review note <交审编号> --from <审查会话> --file <消息>` 要求发件人在白名单里（kind `lead`）、消息是合格的【审查结论】、
   「审查编号」或要点里能对上这个交审；记在交审事项的 `reviews` 列表。`review batch` 显示「审查：<会话> <结论首行>」或「未审查」。批准不检查有没有审查。
5. **交枢纽的正文由命令生成，不手写**：`review batch --for-hub [--parallel-with <H>]` 输出一条【等待用户】正文文件：「要你决定」写批准哪几条交审；要点逐条写模块、节点、要点首行与审查行；
   选项「推荐 A：全部批准」「B：只批准部分（请写编号）」「C：都退回修改」；需要时加【与 #H 并行】标记；生成后自检 `protocol.parse` 合格才写出。
6. **只读出口的 stage 枚举由现有四档推出**：`spec-plan`（写 Spec 与 Plan）、`build`（已批准可构建）、`returned`（最近一次最终验收被退回、待重交）、`wait-merge`（等合并）、`merged`（已合入）；
   `stageText` 沿用钩子的中文句子。挂起不是档位，单独在 `suspended` 字段给原因。
7. **interface.json 只登记对外出口**：`{"interface": "1.0", "plugin": "module-crew", "version": <plugin.json 的版本>, "contract": <CONTRACT_VERSION>, "sessions": {"command": ["bin/module-crew", "sessions", "--json"], "schemaVersion": 1}}`；
   一致性测试保证 version、contract 与代码一致。

8. **转给模块的答复按 v1.6 写**（2026-10-18 修订）：带来源批准时，给模块的【用户答复】写「事项：#H（你的原消息 #M、#M2）」与「转自：收件枢纽，消息 #R」或「转自：<短名>（负责人转交），消息 #R」，
   lead 时照抄「转交范围」；同一收件人的几条交审合成一份（一个 #H 涉及几个模块就各发一份）。命令同时输出给来源的【已恢复】「结束：#H」，协调会话在这个 #H 涉及的模块都转完后再发。
9. **评审标记只认两种批准**（2026-10-18 修订）：用户在协调会话亲手批准、或已登记收件枢纽（hub）转来的【用户答复】时，`review approve` 照常写标记并提交，
   hub 来源的提交说明写「用户批准事项 #N（收件枢纽事项 #H）：…」；**负责人转交（lead）的 Spec／Plan 批准只记账**：记一条 `kind: "lead-record"` 的已答事项（来源、用户原话、交审编号），
   不写标记、不提交、不发【用户答复】与开工通知，交审事项保持未关；输出写明原因并提醒请用户在本会话或经收件枢纽再批准一次。`merge approve` 不写标记，带 lead 来源照旧。


## 接口约定

### 命令

```bash
bin/module-crew source add <邮箱名> --kind hub|lead (--original <原话> | --original-file <文件>)
bin/module-crew source remove <邮箱名> (--original <原话> | --original-file <文件>)
bin/module-crew source list [--json]
bin/module-crew source map (<H> | '#<crew 编号>') [--json]
bin/module-crew review note <交审编号> --from <审查会话> --file <消息文件>
bin/module-crew review batch --for-hub [--parallel-with <H>]
# 批准命令（review approve/answer、merge approve/cleanup/push/tick、start prepare、change land/answer、suspend、serial、takeover、ticket close）新增：
#   [--source <邮箱名> --source-item <H> --source-relay-id <消息号>]
bin/module-crew sessions --json
```

- `source add/remove`：`0` 成功；`3` 原话为空、名字已在／不在白名单、kind 不合法。
- 批准命令带 `--source`：来源未登记、消息不合格、类型或事项号对不上 → `3`，什么都不写；不带 `--source` 时行为与现在完全相同（`self`）。
- `review note`：`0` 记下；`3` 发件人未登记为 lead、消息不是合格的【审查结论】、对不上交审。
- `review batch --for-hub`：输出正文文件路径；`0` 有未答交审；`3` 没有。
- `sessions --json`：`0`；读不到（不在仓库、未建库、状态库损坏）→ `2`，stderr 一行原因，stdout 为空。

### sessions --json（对外契约，只增不改）

```json
{"schemaVersion": 1,
 "sessions": [{"module": "b", "relayName": "shop-b", "worktree": "/abs/path",
               "stage": "build", "stageText": "Spec 与 Plan 已批准，可以构建；做完发最终验收【交审】",
               "suspended": null, "lastActivity": "2026-10-18T12:00:00+08:00"}]}
```

`relayName` 即会话登记名（agent-relay 邮箱名）。`lastActivity` 没有记录时为 null。另外保留现有字段（`openTickets`、`openItems`、`ago`）作为非契约字段。

### interface.json（插件根目录）

见关键决策 7。

## 项目结构

```text
module_crew/sources.py             来源白名单、来源校验、对照查询
module_crew/review.py              review note、batch --for-hub、approve 接来源
module_crew/merge.py / start.py / changes.py / failure.py / inbox.py / hooks.py   批准入口接来源（共用 sources.check）
module_crew/__main__.py            source 子命令、--source 参数、sessions --json 契约
interface.json
skills/crew-coordinator/SKILL.md   措辞与「接入收件枢纽」一节
skills/crew-dev/SKILL.md           收到转来答复的核对（按 v1.6）
tests/test_sources.py、tests/test_hub_output.py
```

## 命令

```bash
python3 -m unittest discover -s tests -v
```

## 代码风格

沿用前几个模块；来源校验集中在 `sources.check(db, source, item, relay_id, text) -> SourceInfo`，各批准入口只调用它，不各写一套。

## 测试策略

- 白名单：增删要原话；未登记来源被拒；`self` 路径的现有测试全部不变（回归）。
- hub 来源：用 v1.6 样例（发版前用 v1.5 的【用户答复】样例模拟 hub 路径）构造消息，核对事项号、原话原样记录；一个 H 批准两个交审，`source map` 双向查。
- 审查行：合格【审查结论】记下并在 batch 显示；未登记、不合格、对不上被拒。
- `--for-hub` 生成的正文 `protocol.parse` 合格，含审查行与【与 #H 并行】。
- 只读出口：字段齐全、stage 枚举覆盖五档、未建库退出码 2 且 stdout 为空、1 秒内返回；interface.json 与 plugin.json、CONTRACT_VERSION 一致。

## 边界

- **始终**：来源白名单只能由用户原话增删；非 `self` 来源的原话取自对方消息解析结果；出口字段只增不改。
- **先问**：把审查行改为强制；让未登记的会话成为来源；改出口已有字段。
- **绝不**：把协调会话自己写的话当作枢纽或负责人的答复；在出口里写状态库；绕过契约解析接受转交。

## 验收标准

1. `source add live-saas-hub --kind hub --original "登记收件枢纽"`：白名单有它；无原话、重复、kind 不合法退出码 3；`source remove` 同理；`source list` 列出。
2. 不带 `--source` 的所有批准命令行为与现在一致（现有测试全部通过）。
3. `review approve 4 5 --source live-saas-hub --source-item 120 --source-relay-id 6001 --original-file <hub 消息>`：合格时两条批准都记 `source: {name, kind: hub, item: 120, relayId: 6001}`，用户原话取自消息；来源未登记、消息不合格、事项号不符时退出码 3、状态库与 git 不变。
4. `source map 120` 列出 #4、#5 及其模块与节点；`source map '#4'` 给出来源 120 与 live-saas-hub。
5. `lead` 来源：合格的【负责人转交】被接受，记下来自短名与转交范围；拿【用户答复】冒充 lead、拿【负责人转交】冒充 hub 都退出码 3。
6. `review note 4 --from live-saas-arch-review --file <审查结论>`：记下并在 `review batch` 显示审查行；没有审查的显示「未审查」；未登记、不合格、对不上退出码 3。
7. `review batch --for-hub`：正文 `protocol.parse` 判为合格的【等待用户】，含每条交审的模块、节点、要点首行、审查行与三个选项；`--parallel-with 118` 时带【与 #118 并行】。
8. `sessions --json`：`schemaVersion` 为 1，每个在用模块会话有契约字段；五种 stage 各构造一次；挂起时 `suspended` 为原因；未建库时退出码 2、stderr 一行原因、stdout 为空；单次 1 秒内。
9. `interface.json` 合法，`version` 等于 plugin.json、`contract` 等于 `CONTRACT_VERSION`，`sessions.command` 能运行。
10. 转交枢纽答复：带来源批准时，给模块的【用户答复】按 v1.6 带「转自」（hub 或负责人转交）、列出该收件人的全部原消息号（同一收件人合成一份）、lead 时带「转交范围」；并输出发给来源的【已恢复】「结束：#H」；两者都 `protocol.parse` 合格；不带来源时答复写法不变。crew-dev skill 写明认「转自」答复的核对。
11. skill：crew-coordinator 第 13、25、56、122 行改为「用户的决定只有两种来源」的措辞；新增「接入收件枢纽」一节，含只向枢纽交【等待用户】、合批、一对多、转完立刻结束 #H、一个模块一张外部等待单、【答复告知】只记录、醒来先 `status`、可直连 API 与后台线做技术核对与已批范围交付确认（新工作先经枢纽请用户批）、长检查用后台运行。
11. `review approve 4 --source <lead> …`：退出码 0，集成分支不变、没有评审标记，交审 #4 仍为 open，记一条 lead-record（含来源与原话），没有要发送的消息，输出含「只记账」；之后用户在本会话亲手 `review approve 4` 照常成功。
12. 带 hub 来源批准：集成分支提交说明含「收件枢纽事项 #120」；用户在本会话亲手批准时提交说明不含「收件枢纽」。


## 未决问题

- 无（v1.6／v1.7 已对照，见变更记录）。

## 文档建议

README 增加「接入收件枢纽」一节：登记来源、带来源批准、合批交枢纽、只读出口与 interface.json。

## 变更记录

- 2026-10-18：按 session-protocol v1.6（81720ba）、v1.7（1e14a49）定稿对照：契约版本改为 v1.7；lead 来源改为接受【负责人转交】并记短名与转交范围；新增关键决策 8（转给模块的答复按 v1.6 带「转自」、同一收件人合成一份、输出【已恢复】）；验收 3、5、10 由「按 v1.6 对照」改为具体写法；未决问题清空。原因：契约负责人发布 v1.6、v1.7；来源：用户批准的契约版本，随本模块最终验收复审。
- 2026-10-18：新增关键决策 9（评审标记只认用户亲手与 hub 转来的批准；lead 来源的 Spec／Plan 批准只记账；hub 来源提交说明写 #H），增加验收 11、12。原因：spec-guard 0.70.0 不认负责人转交、要求记 #H，冻结版 0.1.0 对 lead 也写标记；来源：用户 2026-10-18 确认 0.1.1 范围；spec-guard 0.70.0（PR haigeerlab/spec-guard-plugin#352）最终措辞：负责人转交不算写标记的来源，收件枢纽转来的批准写标记时在提交说明记 #H。
