# Spec: crew-takeover-approve

<!-- spec-guard: review approved 8590623c437c -->

> 能力图模块 `crew-takeover-approve`。需求来源：接缝 S101，已批合并方案 plugin-ecosystem `research/2026-11-21-自动接管合并方案.md`（bfce091，用户 2026-11-21「按推荐批准」）
> 第 2 节 module-crew 一行与第 3 节 Q1、Q5、Q6、Q7、Q8、Q12；方向文档 `research/2026-11-21-自动接管方向.md` 第二节第 3、4 条。开会话依据：用户批准事项 C605。
> 依赖 `crew-autonomy-tier`（本模块把它退役）、`crew-review-nearby`（审查者、【审查结论】、返工轮次）、`crew-check-ledger`（检查账，本模块只读不改）；另用到 `crew-review-batch`（`review approve` 落地与开工通知）、`crew-declared-scope`（`declared.enabled`）。
> 上游：spec-guard 0.91.0（interface 1.15）与 delegate 接口 1.5，写 Spec 时都**还没发版**，接口形状按假设 1、2 写，构建要等它们发版、以真实接口为准（见「上游依赖」）。
> 现状取自 0.23.6 源码（`autonomy.py`、`review.py`、`declared.py`、`start.py`、`merge.py`、`checks.py`、`__main__.py`）。标「新」的是写 Spec 时补的实现取舍，请重点审。

## 目标

项目在 spec-guard 里设了接管档位后，module-crew 按档位决定 Spec、Plan 由谁批，并让每一处都看得出是谁批的：

- **看得清**：`status`、`tier`、开工说明、交审事项、给用户的批量交审都写明这个模块的 Spec、Plan、合并三项各是「人批」还是「Codex 放行」；判为重要需求、强制人批的写原因。
- **Codex 放行**：Spec 或 Plan 勾了「Codex 审过就算」时，模块的【交审】不送用户，由模块协调交 Codex 审；Codex 的结论接进现有的审查者机制：有阻断意见就自动返工（最多 2 轮），没有就由 module-crew 落地、写 spec-guard 的 `codex-approved` 标记、发后续通知；Codex 不可用一律停下等用户，**绝不**退回 Claude 自审。
- **分开记账**：Codex 放行记成单独一类批准，和用户批准分开计数、分开显示。
- **批准人不同就分开批**：同一模块 Spec、Plan 一个人批、一个 Codex 放行时，自动按 separate 交审。
- **出事收窄**：现有四类出事与 `tier degrade` 改调 spec-guard 的「只许收窄」入口，按「先撤合并、再 Plan、最后 Spec」一次降一格；恢复仍要用户原话、经 spec-guard 写。
- **退役 autonomyTier**：module-crew 不再读 `autonomyTier`，旧值不映射；它原来顺带打开的评审节奏、声明范围、收尾汇总三项，改为各自独立的开关保留。

没设接管档位（spec-guard 报「不接管」）时，一切照今天：每项人批。

## 范围

**范围内**

1. **读档位**：`module_crew/takeover.py`（新）按 spec-guard interface 1.15 读项目 `takeover` 与每个模块生效的三项（Spec、Plan、合并），含「强制人批」与原因（假设 1，决策 1）。
2. **显示**：`status`、`tier`、`start plan`／开工说明、`review list`／批量交审、交审事项登记行写明每项批准方式（决策 2）。
3. **Codex 审查接进审查者机制**：新命令 `review codex C<n>`（给出这一次要跑的 `/delegate:review` 命令）与 `review codex-note C<n> --report <文件>`（读审查报告、按阻断／建议判定、返工或放行）（决策 3～6）。
4. **Codex 放行的落地与记账**：复用 `review approve` 的落地路径，写 `codex-approved` 标记，记成 `codex-approval` 事项（决策 5、7）。
5. **Codex 不可用**：停下、生成【等待用户】草稿（决策 6）。
6. **批准人不同时自动分开批**：开工说明与 `review batch` 的评审节奏（决策 8）。
7. **出事收窄**：`autonomy.incident` 四个出口与 `tier degrade` 改调 spec-guard 的收窄入口；`tier restore` 改为指引（决策 9、10）。
8. **autonomyTier 退役**：不读 `autonomyTier`、不再用 `config/main.autonomy` 的降档上限与升档建议；三个开关独立保留（决策 11）。
9. **协议**：Codex 只放行 Spec（Plan 还没写）时要告诉模块会话「Spec 已放行、写 Plan」，需要 session-protocol 给【协调通知】新增类型「放行」（决策 12，按记忆规则先向契约提需求、经用户批准）。
10. **skill 与文档**：`crew-coordinator`、`crew-dev`（Claude 与 Codex 各一份）、README。

**范围外**

- 合并第一段（勾了「合并：自动」时自动 `merge run`、最终验收凭 `codex-approved` 验收标记放行）：归同批模块 `crew-takeover-merge`。本模块只**显示**合并一项是人合还是自动合，最终验收照今天要用户答复。
- 推 batch 分支、合远端 PR、撤回检测、两个计数：归 autopilot。
- 接管档位的存储、校验、写入、重要需求判定、`codex-approved` 标记的格式与 `/build` 怎么认它：归 spec-guard 0.91.0；module-crew 不写 `.agent/config.json`。
- 阻断／建议的判据：autopilot 起草、delegate 与 autopilot 确认；module-crew 只读报告里的 `severity`。
- 能力图：永远人批，本模块不碰。
- 人工审查者（lead）的现有机制、`REWORK_LIMIT = 3`：照旧，不改。
- 改模块会话的停点：三种必停情况、`gate` 检查点照旧。

## 上游依赖（构建要等）

| 上游 | 版本 | 本模块用到 | 未发版时 |
|---|---|---|---|
| spec-guard | 0.91.0，interface 1.15 | `takeover`／`moduleTakeover` 的读法（每模块生效三项、强制人批原因）；`reviewMark` 的 `codex-approved` 状态；只许收窄的写入口 | Spec、Plan 照常交审；构建停在 Plan 的第一个 `gate`，发【等待其他会话】等它发版 |
| delegate | 接口 1.5 | 审查报告每条发现的 `severity: blocking \| suggestion`（缺字段按 blocking）；没有结论就报失败；`--previous-report` 复审对照上一轮；报告 `scope.fingerprint`（1.4 已有） | 同上 |
| session-protocol | 新增【协调通知】类型「放行」（决策 12） | Codex 只放行 Spec 时通知模块会话 | 提需求经用户批准、契约发版后再构建这一项；其余项不等它 |

读不到 1.15、读不到 1.5 时（假设 3）一律照「不接管」做：全部人批，不报错。

## 上游实测（Checkpoint 0，2026-11-22）

本机装了 spec-guard 0.91.0（interface 1.15）与 delegate 0.10.0（接口 1.5），按真实接口修订如下；与下文假设、决策不一致处以本节为准。

1. **读档位**：每个模块生效的四项从 `map_view.py --json` 每个模块的 `takeover` 读：`{"spec", "plan", "merge", "release", "source", "widerThanProject", "narrowed"}`（`release` 只显示，不由本模块处理）。
   module-crew 已在 `probe.run` 里读这份 `/map --json`，`takeover.py` 直接用它，不另起子进程；项目档位取 `project_config.py show --format json` 里 key 为 `takeover` 的一项（预设名或自定义对象）。
   强制人批：`important.reasons` 非空时 Spec 一律人批（原因照抄，如 `multi-module`）；Plan 的「预先声明」有任何一行不是「无」时 Plan 一律人批（spec-guard codex-approval Q6，用户选 A）。
2. **审查报告**：`/delegate:review` 标准输出的 JSON 存成文件。没有结论 = `execution_status` 不是 `completed`，或 `review_outcome` 不是 `findings`／`no_findings_in_scope`，或 `backend` 不是 `codex`；`findings[].severity` 缺省按 `blocking`。
   报告与文件靠 `scope.files` 里每个文件内容的 sha256 绑定（不用 `blob-pairs-v1`）。复审带 `--previous-report`，阻断项是否解决看 `recheck.items`，新问题在 `findings`。
3. **`review codex` 给的命令**：`/delegate:review --backend codex --repo <模块 worktree> --paths <交审文件> [--spec spec/<模块>.md]（审 Plan 时带）[--previous-report <上一轮报告>] <任务说明>`，
   读模块 worktree 的 HEAD；模块协调把标准输出存到 `review codex` 指定的文件（状态库目录下 `codex/C<n>-r<轮>.json`）。`codex-note` 用 `scope.files` 的 sha256 对交审提交里的内容逐文件核对（取代决策 4 的指纹比对）。
4. **轮次记在文件里**：spec-guard 自己按文件「外部审查意见」一节里的轮次行计数，两轮阻断后不再接受 `codex-reviewed`。所以有阻断时，返工通知让模块会话**先**在自己的 worktree 跑
   `/spec-guard:review-mark --target <spec|plan> --state codex-reviewed --review <报告> --confirm`（记下这一轮），再按阻断意见改、提交、重新交审；module-crew 的 `CODEX_REWORK_LIMIT = 2` 与 spec-guard 的上限一致，两边都挡。
5. **放行写标记**：落地到集成 checkout 后跑 `reviewMark --target <spec|plan> --state codex-approved --review <报告> --confirm`；spec-guard 会再核一次报告与文件、追加这一轮的轮次行。`--target both` 对 Codex 不可用，Spec、Plan 各写一次。
   spec-guard 拒绝（退出 2）时 module-crew 还原集成 checkout、退出码 4，原因照抄。
6. **收窄**：调 `takeoverNarrow`：`project_config.py narrow --project <集成 checkout> [--module <模块>] --source module-crew --reason <一行> --confirm`；顺序（合并 → Plan → 不接管，自定义按 release、merge、plan、spec 取第一个非人批项）由 spec-guard 定。
   它改 `.agent/config.json`，module-crew 随即在集成分支单独提交（提交信息写原因），按 `crew-unqueued-commits` 记为 module-crew 自己的提交。已是最严时 spec-guard 什么都不写、退出 0，module-crew 不输出收窄行。
7. **`tier --preflight`**：核对 spec-guard ≥ 0.91.0 且接口 1.15 有 `takeover`、`takeoverNarrow`，delegate 接口 ≥ 1.5（`review.report.severity`、`recheck`）；任一不满足退出码 3。



1. **（新）spec-guard 1.15 的读法**（已按发版实测改，以「上游实测」一节为准）：interface.json 新增 `takeover` 一项，按 `autonomyTier` 的写法给 `readFrom`；module-crew 只认两种读法：
   项目档位取 `project_config.py show --format json` 里 key 为 `takeover` 的一项；每个模块生效的三项取 `map_view.py --json` 每个模块的 `takeover`：
   `{"spec": "human"|"codex", "plan": "human"|"codex", "merge": "human"|"auto", "source": "...", "forcedHuman": [{"item": "spec", "reason": "新模块"}...]}`。
   字段名以 spec-guard 发版为准，构建时照真实接口改这一节与夹具，改动随最终验收复审（变更记录写明）。
2. **（新）delegate 1.5 的报告**（已按发版实测改，以「上游实测」一节为准）：`/delegate:review` 的 JSON 报告（`schemaVersion` 不变或升 2）每条发现带 `severity`；`status` 不是「完成」（权限拒绝、空／坏输出、部分覆盖、达限、失败）都算「没有结论」；`scope.fingerprint` 绑定审过的内容。
3. **读不到就是不接管**：spec-guard 低于 0.91.0、接口没有 `takeover`、命令跑不成、输出缺项，一律按三项人批，`tier`、`status` 写一行原因（同 `crew-autonomy-tier` 假设 2 的安全限制：固定参数、带超时、不经 shell、脚本在安装目录内）。在集成 checkout 读（同 `crew-autonomy-tier` 假设 3）。
4. **「两轮」的口径**：Codex 第一次审有阻断 → 返工第 1 轮 → 复审仍有阻断 → 返工第 2 轮 → 再复审仍有阻断 → 停下交用户。即最多返工 2 次、最多审 3 次。复审带 `--previous-report <上一轮报告>`。
5. **建议意见不返工**：只有建议、没有阻断就放行；建议原样附进放行通知，模块会话在写 Plan、构建时自己决定吸收与否（同今天「吸收遗留建议」）。方向文档「建议由 Claude 自己决定并写一句理由留档」由模块会话在 Plan 或提交里写，module-crew 不检查。
6. **谁跑 Codex**：模块协调（Claude 会话）按 `review codex` 给出的命令用 Bash 后台跑 `/delegate:review --backend codex`，跑完把报告路径交给 `review codex-note`；module-crew 自己不调 Codex，也不判断报告以外的东西。
7. **重要需求以 spec-guard 判定为准**：spec-guard 判为重要（`/map --json` 的 `important.reasons` 非空）的 Spec，不管勾选怎么写都按人批；module-crew 不自判新模块、跨模块、高风险路径。
8. **Codex 放行不是用户批准**：不写 `approved` 标记、不发【用户答复】、不进「用户批准事项」的编号说法；对用户说「Codex 放行」。

## 关键决策与取舍（请重点审）

1. **（新）新文件 `module_crew/takeover.py`**（细节按「上游实测」一节修订）：
   `project(db, project) -> Setting`（`value`：`none`／`plan`／`merge`／`custom`，`source`，`usable`，`reason`）；
   `module(db, project, module_id) -> Items`（`spec`、`plan`、`merge` 三项的生效值，`forced`：`{item: reason}`，`usable`、`reason`）；
   `approver(db, project, module_id, node) -> "human" | "codex"`（`node` 为 `spec`／`plan`；`interface` 按 Spec 算；`final` 永远 `human`，留给 `crew-takeover-merge`）。同一进程读一次缓存，键含 `.agent/config.json` 的修改时间（同 `autonomy.read`）。
2. **（新）显示的写法**：一个模块一行「批准方式：Spec <人批|Codex 放行>、Plan <人批|Codex 放行>、合并 <人合|自动合>」，强制人批写「Spec 人批（重要需求：<原因>）」；档位来源写在 `tier` 首行。
   - `status`：开了接管（不是 `none` 或有模块单独设）时多一段「接管档位」：项目档位一行，在用模块各一行，Codex 放行计数一行（决策 7）；没开时一字不变。
   - 开工说明：在「交审节奏」那行后加批准方式一行，并写「Codex 放行的节点，【交审】照常发给模块协调，结论由 Codex 给出」。
   - 交审登记行（`review add` 输出）：Codex 放行的节点写「已记为交审事项 C<n>（… Codex 放行：下一步 review codex C<n>）」，不提示问用户。
   - 批量交审（`review batch`、给决策收件箱的卡片）：Codex 放行的事项**不进**给用户的批次；批次末尾加一行「另有 k 项由 Codex 审查中／已放行：…」（只是告知）。
3. **（新）Codex 审查接进审查者机制，用虚拟审查者 `codex`**（细节按「上游实测」一节修订）：不经 `source add` 登记、不走邮箱；`review add` 判定节点为 Codex 放行时，在交审事项上记 `sentTo: ["codex"]`、`reviewer: "codex"`、`sentAt`，`review_state` 照旧得出「审查中」。
   `review codex C<n>` 只读，输出一行可直接执行的 `/delegate:review --backend codex --base <集成分支顶端> --paths <交审文件> [--previous-report <上一轮报告>] <任务说明>`，任务说明固定写：按 spec-guard Spec／Plan 的要求审这份文件，阻断意见限于「照这份文件做会做错或做不成」。
   `review codex-note C<n> --report <json>` 把报告转成和【审查结论】同样的一行记录（`from: "codex"`、`verdict`、`changes` 取阻断项、`suggestions` 取建议项、`report`、`fingerprint`），之后走 `note` 里同一段返工逻辑，只是上限取 `CODEX_REWORK_LIMIT = 2`（假设 4），超限时记 `overLimit`、生成【等待用户】草稿（选项：A 用户来批这一版／B 照阻断意见再改一轮），**不**挂降档（AI 定不了交人是正常流程，不是出事）。
4. **（新）报告与交审内容要对得上**（细节按「上游实测」一节修订）：`codex-note` 核对报告 `scope.fingerprint` 覆盖的文件就是交审事项的文件、内容等于交审提交里的内容（逐文件 `git show <commit>:<path>` 比对），对不上拒收、退出码 3，提示重跑 `review codex`；防止「审的是旧版本」。
5. **（新）放行时复用 `review approve` 的落地路径**（细节按「上游实测」一节修订）：抽出 `_land(project, picked, mark_state, record)`：`review approve` 传 `approved` 与用户原话，Codex 放行传 `codex-approved` 与报告摘要（报告路径、指纹、轮次、建议条数）。
   集成分支提交信息写「Codex 放行事项 C<k>：放行 <模块> 的 <节点>」；回给模块会话的不是【用户答复】，而是：Spec 与 Plan 都已批准（任一方批的都算）时发开工类【协调通知】（「依据」写 Codex 放行事项号）；只放行了 Spec 时发「放行」类【协调通知】（决策 12）。
   开工通知的其余写法（提前开工、外包、`_start_todo`）全部照旧。
6. **（新）Codex 不可用一律停**：`codex-note` 读到「没有结论」（报告缺失、坏 JSON、`status` 非完成、部分覆盖）时不记结论，退出码 5，输出一份【等待用户】草稿：「Codex 审查没跑成：<原因>」，选项 A 等 Codex 恢复后重跑 `review codex C<n>`（推荐）／B 这一项这次改由用户批（之后照人批流程 `review approve`）。模块协调照今天的【等待用户】流程转给用户。
   `review approve` 对 `reviewer: "codex"` 的事项：没有用户选 B 的答复记录时拒绝（退出码 3，提示「这一项是 Codex 放行，先 review codex」），选 B 后照人批走，事项记 `reviewer: "human"`、`fallback: "codex-unavailable"`。没有任何路径让 Claude 自己的判断替代 Codex 结论。
7. **（新）分开记账**：Codex 放行记成事项 `kind: "codex-approval"`（字段同 `review-approval`，`answer` 换成 `codex: {report, fingerprint, rounds, suggestions}`），事件 `item.codex-approved`；`_approved_nodes`、`start_basis` 认它与 `review-approval` 两种；
   `status` 的接管一段写「Codex 放行：Spec a 次、Plan b 次；其中返工后才放行 c 次；超限交用户 d 次」；`status --json` 的 `store.takeover` 给同样的数。用户批准的说法、编号、统计一处都不变。
8. **（新）批准人不同就分开批**：`start.review_cadence` 加模块参数：该模块 Spec 与 Plan 的批准方 `approver` 不同时返回 `separate`（来源写「Spec、Plan 批准人不同，自动分开批」），相同时照 spec-guard 的 `reviewCadence`。开工说明与 `review batch` 都走它。
9. **（新）出事收窄改调 spec-guard**（细节按「上游实测」一节修订）：`autonomy.incident(db, project, kind, ref, reason)` 的签名与四个出口（`merge.py` 两处、`review.py` 的 `rework-over-limit`、`checks.py` 的基线失败）不动，内部改为：
   读生效档位；三项全是人批就什么都不做；否则调 spec-guard 收窄入口，按「合并 → Plan → Spec」取消最前面一个勾（预设档：接管到合并 → 只接管 Plan → 不接管），一次一格。
   作用对象：出事能归到模块（前三类）时，该模块单独设过 `moduleTakeover` 就收窄那个模块，同时收窄项目档；基线失败只收窄项目档。同一 `kind:ref` 只降一次（`incidentKeys` 照旧记在 `config/main`，只是去重用）。
   输出一行「接管档位已从 <原> 收窄到 <新>：<原因>。马上告诉用户；恢复要用户原话，经 /spec-guard:config 写」；收窄入口调用失败时输出「没能收窄（<原因>）：请告诉用户，由用户决定是否用 /spec-guard:config 调低」，不影响调用方。
10. **`tier degrade` 参数不变**：`--reason`、`--ref` 照旧，内部走决策 9 的同一路径（`kind: external`）；退出码照旧（0 已降或无需降、2 降档失败、3 参数错）。
    `tier restore` 退役为指引：不论参数，退出码 3，输出「放宽档位要用户原话、一次升一档，用 /spec-guard:config 写（module-crew 不再存降档上限）」。
11. **（新）autonomyTier 退役与三个开关**：module-crew 不再调用 `autonomyTier.readFrom`，`config/main.autonomy` 里的 `cap`、`seen`、`suggestedFor` 不再读（记录保留、只增不改）；升档建议（`evidence`、`suggestion`、`merge run` 合入后的建议行）随之去掉。三个开关独立：
    - 评审节奏：照旧只读 spec-guard 的 `reviewCadence`；不再有「降档上限压到 strict 时改 separate」这条。
    - 声明范围：`declared.enabled` 只认 `declaredScope` 的 `on`／`off`，没设就是关（回到 `crew-declared-scope` 原样）。
    - 收尾汇总：新开关 `config/main.digest`（`on`／`off`，默认关），用 `module-crew config --digest on|off --original-file <原话>` 写；`tier digest` 命令本身不变、照样只读可跑，开关只决定 skill 是否要求「这几类消息不逐条告诉用户、收尾时汇总」。
    迁移提示：spec-guard 报 `autonomyTier` 不是 `strict`（旧值还在）时，`tier`、`status` 写一行「autonomyTier 已退役、不再生效（旧值 <值> 不映射为接管档位）：要接管用 /spec-guard:config 设 takeover；原来顺带打开的评审节奏、声明范围、收尾汇总请分别设」，只提示一次以上，不自动写任何开关。
12. **（新）协议新增「放行」类【协调通知】**：separate 节奏下 Codex 放行 Spec 后，要告诉模块会话「Spec 已放行，写 Plan 交审」，今天这件事靠【用户答复】，但 Codex 放行不能发【用户答复】（假设 8）。
    提议 session-protocol v2.9：【协调通知】新增类型「放行」，「依据」必须有放行事项编号，「要你做什么」写下一步；`crew-dev` 写明模块会话认它和认【用户答复】一样（只限它点名的节点），发件人仍须是在用模块协调。
    按项目规则先向契约提需求、经用户批准再改本仓库；契约没发版前，构建可先做其余各项，这一项排在 Plan 最后、单独 `gate`。

## 接口约定

### 命令

```bash
bin/module-crew tier [--json]                                   # 只读：接管档位（项目与在用模块）、Codex 放行计数、autonomyTier 退役提示
bin/module-crew tier --preflight                                # 只读：写 takeover 之前核对 spec-guard ≥ 0.91.0、接口 1.15 有 takeover
bin/module-crew tier degrade --reason <文字> --ref <标识>        # 参数不变：调 spec-guard 收窄入口
bin/module-crew tier restore …                                  # 退役：只输出指引，退出码 3
bin/module-crew tier digest [--json] [--mark-told]              # 不变
bin/module-crew review codex C<n>                               # 只读：给出这一轮的 /delegate:review 命令
bin/module-crew review codex-note C<n> --report <json 文件>     # 记 Codex 结论：返工、放行或交用户
bin/module-crew config --digest on|off (--original <原话> | --original-file <文件>)
```

- `review codex`：`0` 给出命令；`3` 这项不是 Codex 放行、已关闭或已超限。
- `review codex-note`：`0` 已记（返工已发／已放行）；`3` 拒收（报告与交审对不上、事项不对）；`4` 落地失败（同 `review approve`，已还原集成 checkout）；`5` 没有结论或超限，输出【等待用户】草稿。
- `tier --json`：`{"takeover": {"value", "source", "usable", "reason"}, "modules": [{"module", "spec", "plan", "merge", "forced": {...}}], "codex": {"spec", "plan", "reworked", "overLimit"}, "retiredTier": str|null, "lastIncident": {...}|null}`。

### Python 入口

```python
takeover.approver(db, project, module_id, node) -> "human" | "codex"
takeover.module(db, project, module_id) -> Items
autonomy.incident(db, project, kind, ref, reason="") -> str | None      # 签名不变，内部改调 spec-guard
```

`autonomy.effective` 退役：现有调用方（`declared.enabled`、`start.cadence_info`）改为不调用；`crew-codex-offload` 没有用它（已核对 `offload.py`）。

### 记录（只增不改）

```json
// 交审事项（review）新增字段
{"reviewer": "codex", "sentTo": ["codex"], "sentAt": "...", "codexReports": ["<路径>"], "fallback": null}
// Codex 放行事项
{"state": "closed", "kind": "codex-approval", "closedReason": "answered", "reviews": [123], "baselineCommit": "...",
 "codex": {"report": "<路径>", "fingerprint": "...", "rounds": 2, "suggestions": 3}}
// config/main 新字段
{"digest": "on"}
```

事件动作：`item.codex-sent`、`item.codex-noted`、`item.codex-approved`、`item.codex-unavailable`；`config.takeover-narrowed`（收窄成功，含 spec-guard 返回的前后档位）。

## 项目结构

```text
module_crew/takeover.py          新：读接管档位、每模块三项、批准方、收窄入口调用
module_crew/autonomy.py          incident／degrade 改调 takeover 的收窄；退役 read/effective/cap/evidence/suggestion/restore；保留 digest
module_crew/review.py            add：Codex 节点记 reviewer；codex／codex-note；抽出 _land 供 approve 与放行共用；_approved_nodes 认 codex-approval
module_crew/start.py             review_cadence 加模块参数（决策 8）；去掉降档上限分支；开工说明批准方式一行
module_crew/declared.py          enabled：只认显式开关（决策 11）
module_crew/merge.py             去掉合入后的升档建议行
module_crew/probe.py             status：store.takeover 替代 store.autonomy
module_crew/protocol.py          认【协调通知】类型「放行」（契约发版后）
module_crew/__main__.py          review codex／codex-note、config --digest、tier 各子命令、status 一段
skills/crew-coordinator/SKILL.md、codex-skills/crew-coordinator/SKILL.md
skills/crew-dev/SKILL.md、codex-skills/crew-dev/SKILL.md
README.md
tests/test_takeover_approve.py   新；tests/test_autonomy_tier.py 按退役改写
```

## 命令

```bash
python3 -m unittest discover -s tests
PYTHONPATH=tests python3 -m unittest test_takeover_approve
```

## 代码风格

沿用现有模块：代码与注释英文，输出中文；只用标准库；spec-guard 调用带超时、参数列表、不经 shell，入口一律经 interface.json 取。

## 测试策略

- 假 spec-guard 夹具：1.15（`takeover` 各档、模块单独设、`forcedHuman`、收窄入口记下被调用的参数）；1.14（只有 `autonomyTier`，值 `relaxed`）；读法写法不同；脚本跑不成。
- 假 delegate 报告夹具：只有建议；有阻断；缺 `severity`；`status` 失败；指纹对不上。
- 复用 `crew-review-nearby`、`crew-autonomy-tier` 的测试基类（模块会话、集成 checkout）。
- 不接管：现有测试原样通过（`test_autonomy_tier` 中依赖档位的用例按退役改写，改写清单随最终验收列出）。

## 边界

- **始终**：读不到档位按人批；Codex 不可用就停下等用户；Codex 放行与用户批准分开记、分开说；收窄立刻告诉用户；module-crew 不写 `.agent/config.json`。
- **先问**：放宽档位（用户原话，经 `/spec-guard:config`）；Codex 超限或不可用时这一项改由用户批；改协议（契约需求经用户批准）。
- **绝不**：Claude 自审代替 Codex；把 Codex 放行说成或记成用户批准；自动放宽档位；能力图交给 Codex；把判为重要需求的 Spec 交给 Codex。

## 验收标准

1. 不接管（含读不到 1.15）：全量测试通过；`status`、`start plan`、开工说明、`review add`／`batch`／`approve`、`merge run` 的输出与改前相同（autonomyTier 相关的行除外，见 11）；`tier` 写原因。
2. 读档位：1.15 夹具的四种项目档、模块单独设、`forcedHuman` 都读对；读不到的三种情况按人批并写原因。
3. 显示：`status`、`tier`、开工说明、交审登记行写出每项批准方式；强制人批写原因；Codex 放行的事项不进给用户的批次，批次末尾有告知行。
4. Codex 返工：有阻断 → 发返工通知（轮次 1、2）；第 3 次审仍有阻断 → 不再返工，退出码 5，草稿选项 A／B；缺 `severity` 按阻断；只有建议 → 放行，建议附进通知。复审命令带 `--previous-report`。
5. 放行：写 `codex-approved` 标记（夹具记下调用参数）、集成分支提交信息写「Codex 放行事项」、记 `codex-approval`；Spec 与 Plan 都批了发开工通知；只放了 Spec 发「放行」通知（契约发版后）；没有【用户答复】发出。
6. 对得上：报告指纹或内容与交审提交不同 → 退出码 3、不记。
7. Codex 不可用：报告缺失／坏／失败／部分覆盖 → 退出码 5、不记结论；`review approve` 对 Codex 项没有用户选 B 时拒绝，选 B 后照人批落地并记 `fallback`。
8. 分开批：Spec 人批、Plan Codex（及反过来）时开工说明与 `review batch` 都是 separate，即使 `reviewCadence=combined`。
9. 收窄：四类出事各自按「合并 → Plan → Spec」降一格（夹具看收窄入口收到的参数）；全人批时不调；同一事项只降一次；`tier degrade` 参数与退出码不变；`tier restore` 退出码 3 并给指引；归到模块且模块单独设过时模块与项目都收窄。
10. 记账：`status --json` 的 `store.takeover` 与 `tier --json` 的 `codex` 计数正确；用户批准的计数不受影响。
11. 退役：spec-guard 报 `autonomyTier: relaxed` 时，开工说明、`review batch`、`declared.enabled` 都不受它影响，`tier`、`status` 有迁移提示；`declaredScope` 没设时 `declared.enabled` 为假；`config --digest` 没原话退出码 3、有原话写入。
12. skill：`crew-coordinator`（两份）写明 Codex 放行的完整步骤（`review codex` → 后台跑 → `codex-note` → 按退出码处理）、Codex 不可用照草稿问用户、收窄马上告诉用户、放宽经 `/spec-guard:config`、收尾汇总看 `digest` 开关；`crew-dev`（两份）写明认「放行」通知、Codex 返工照普通返工处理、停点不变。
13. 实测：spec-guard 0.91.0 与 delegate 1.5 发版后，本机真跑一次 `takeover` 读取与一次 `/delegate:review` 报告进 `codex-note`，结果写进最终验收。

## 并行边界

- 独占：`module_crew/takeover.py`、`tests/test_takeover_approve.py`
- 公共：测试资源

## 并行说明

本模块和 `crew-takeover-merge` 同批：本模块先合入定形，`crew-takeover-merge` 排在后面、依赖本模块，`module-crew sync` 后在它之上改这些共享文件：`module_crew/review.py`（`_land`）、`module_crew/merge.py`、`module_crew/__main__.py`、`module_crew/probe.py`、
`skills/crew-coordinator/SKILL.md`、`codex-skills/crew-coordinator/SKILL.md`、`skills/crew-dev/SKILL.md`、`codex-skills/crew-dev/SKILL.md`、`README.md`。`crew-takeover-merge` 读 `takeover.module(...).merge` 与 `codex-approval` 的记账口径。
session-protocol 契约的改动（决策 12 的「放行」类型）经契约需求流程，不在本仓库改。

## 未决问题

- 收窄的作用对象（决策 9）：这一版「归到模块就模块与项目一起收窄」偏严；若用户希望只收窄出事的模块，改成只动 `moduleTakeover`。
- spec-guard 1.15 的真实字段名、收窄入口的参数（是否接受 `--module`）以发版为准；和这里不同时在构建中改、随最终验收复审。
- 「放行」通知要不要也给人批的 Spec 用（统一说法），这一版不动人批路径。

## 文档建议

README 的「自治档位」一节改写为「接管档位」：三项各由谁批、Codex 放行怎么走、Codex 不可用会怎样、出事收窄顺序、恢复要原话；写明 autonomyTier 已退役与三个开关怎么分别设；「命令一览」补 `review codex`、`review codex-note`、`config --digest`，标 `tier restore` 退役。CHANGELOG 随发版写。

## 变更记录

- 2026-11-22：「并行边界」去掉「共享：」一行，共享文件清单与契约的说明挪到紧跟其后的新节「并行说明」；「公共」行只留类别「测试资源」；内容范围不变。原因：spec-guard verify-artifacts 只认「独占」「公共」两种行，「共享」行与带说明的公共行判为 unknown-line；来源：用户 2026-11-21 在 mc-coord 会话答复「批草案并改边界」（mc-coord 转达 #21948、#21951），随最终验收附 Spec 差异一并复审。
- 2026-11-22：新增「上游实测」一节，按 spec-guard 0.91.0（interface 1.15）与 delegate 0.10.0（接口 1.5）的真实接口修订假设 1、2、7 与决策 1、3、4、5、9（读法改用 `/map --json` 每模块 `takeover`，强制人批取 `important.reasons` 与 Plan 预先声明，报告按 `scope.files` 的 sha256 绑定，阻断轮次由模块会话用 `review-mark --state codex-reviewed` 记进文件，放行用 `codex-approved --review`，收窄调 `takeoverNarrow` 并由 module-crew 提交 `.agent/config.json`）；目标与范围不变。原因：Plan Checkpoint 0 要求发版后按真实接口改；来源：本模块构建 Checkpoint 0，随最终验收附 Spec 差异复审。
- 2026-11-22：构建 Task 4、5 时补三处实现取舍：① 新增 `review codex-fallback C<n> (--original|--original-file)`，用户选「这一项改由自己批」（Codex 不可用或两轮仍阻断）时凭原话把交审改回人批，之后照 `review approve`／`review answer`（决策 6 原写「选 B 后照人批走」，没写入口）；② Codex 返工通知的审查编号写 `R-<第几次审>`，交审事项的审查记录 `from` 为 `codex`；③ 批准标记命令认 spec-guard 1.1 与 1.15 两种占位符写法，`[--review <report file>]` 只在 Codex 放行时展开——装上 0.91.0 后旧写法会让 `review approve` 与合并时记 Spec 修订批准都失败（已告知 mc-coord #21999）。原因与来源：本模块构建 Task 4、5，随最终验收附 Spec 差异复审。
