# Spec: crew-design-mark-sync

<!-- spec-guard: review pending -->

> 能力图模块 `crew-design-mark-sync`。需求来源：模块 crew-review-gates-align 的未决问题 Q1（`spec/crew-review-gates-align.md`），ecosystem-lead #23580（用户在其会话「排，下一项做」）；用户 2026-11-27 在 mc-coord 批准排期、插入与开工（「排，下一项做」「现在开始」「确认插入」），开会话依据：用户批准事项 C896。
> 上游：spec-guard 0.101.0（本机 2026-11-27 实测，`interface.json` 为 `1.28`）。技术方案标记 `reviewMark --target design` 自 interface 1.20 起有（`spec/design-review.md`），1.27 加了 `host-reviewed`、`no-reviewer`；1.28 对 design 目标没有改动（只加了 `skillLog`）。下面「现状」里 spec-guard 的行为都取自本机 0.101.0 的 `interface.json` 与 `hooks/review_mark.py`、`hooks/module_stage.py`。
> 依赖 `crew-review-batch`（`review approve` 的落地）、`crew-flow-v2`（技术方案节点、第二审查者）、`crew-review-gates-align`（没有第二审查者交用户批）。现状取自本分支源码。
> 本模块是老流程模块（不带流程标记）：Spec → Plan → todo。改的是 module-crew 对**别的**新流程模块的处理，本仓库自己的模块不受影响。

## 目标

module-crew 把新流程模块的技术方案落地到集成分支时，按 spec-guard 定的写法同时写技术方案标记，让集成分支上 `/map --json` 的 `designApproval.status` 与 module-crew 自己记的结果一致：用户批了、第二审查者放行了，就显示 `approved`（`approvedBy` 分别为 `user`、`reviewer`），不再一直停在 `pending-review`。
autopilot-hub 模块 8 的汇报读这个字段，读到的应当是真实状态。写哪个状态、带哪些参数一律以 spec-guard 为准，module-crew 不自己判断技术方案过没过。

## 现状

- `module_crew/review.py:1523` 起 `_approve` 落地循环：节点不在 `MARK_TARGET`（只有 spec、interface、plan）时 `continue`，注释「crew-flow-v2: spec-guard records no mark for a design (yet)」。所以技术方案无论由用户批（`review approve`）、由第二审查者放行（`review codex-note` → `_approve(codex={..., "design": True})`）还是免审放行（`review add` → `_approve(codex={"skip": ...})`），都只把 `tasks/<id>/design.md`、`regression.md` 写进集成分支并提交，不跑 `reviewMark`。
- `module_crew/review.py:1361` `_mark_fill`／`mark_args`：已认 interface 1.27 的 `<spec|plan|both|acceptance|design|overall>` 与含 `reviewer-approved` 等的状态占位符；`[--review <report file>]` 只在给了报告时展开，`[--blocking <N>]`、`[--reason <one line>]` 一律跳过。
- `module_crew/takeover.py:769` `codex_note`：技术方案报告没有阻断 → 报告存到状态库 `codex/C<n>-r<轮>.json` 后调 `_approve` 放行；有阻断 → 返工（返工通知写「按第二审查者的阻断意见改技术方案与回归」，模块**不跑** review-mark，crew-flow-v2 决策 7 与 crew-dev「第二审查者的返工」）；两轮仍有阻断、没有审查者（`reviewer.selection == "none"`）、审查跑不成 → 交用户（`codex-fallback` 后 `review approve`）。
- `module_crew/takeover.py:162` `_design`：spec-guard 的 `designApproval.status == "not-required"` 时判为免审（`skip`）。
- spec-guard（0.101.0）`designApproval` 只看 `tasks/<id>/design.md` 里的批准标记与轮次行：
  - 标记 `approved` → `approved`／`user`；
  - 标记 `reviewer-approved` 且生效档位 `takeover.design == reviewer` → `approved`／`reviewer`；
  - 不用审且档位是 reviewer → `not-required`（不看标记）；
  - 没有标记、没有轮次 → `pending-review`（就是今天一直显示的值）。
- spec-guard `reviewMark --target design` 的状态（interface 1.20／1.27）：
  - `approved`：用户的批准，不带 `--review`／`--blocking`／`--reason`；写批准标记，绑定去掉「外部审查意见」一节后的摘要。
  - `reviewer-approved --review <delegate --profile design 的 JSON>`：报告须是对磁盘上这份 design.md 的 design-v1 审查、没有阻断（否则 `design-blocking`／`report-invalid` 拒绝）；写一行轮次与 `reviewer-approved` 标记。
  - `reviewer-reviewed --review <报告>`：只记一轮（有阻断，或报告 `selection none` 记为 unreviewed），标记留 pending。
  - `host-reviewed --blocking N`、`no-reviewer`：宿主子会话审、没有审查者，不带报告；`--reason` 只给 `--target spec` 用。
  - 第二轮在有阻断的上一轮之后须带复核（`design-recheck-missing`）；两轮都有阻断后不再收审查者状态（`design-rounds-exhausted`），交用户 `approved`。

## 范围

**范围内**

1. `review approve`（用户批）落地技术方案时，在集成分支所在的 checkout 上跑 `reviewMark --target design --state approved --confirm`（决策 1）。
2. 第二审查者放行（`codex-note` 无阻断）落地时，跑 `reviewMark --target design --state reviewer-approved --review <这一轮存下的报告> --confirm`（决策 2）。
3. 免审放行：不写标记，照今天（决策 3）。
4. 写标记失败时照今天 Spec 的失败处理：停下、还原集成分支；放行路径记「已放行但落地失败」交用户（决策 5）。
5. 装的 spec-guard 的 `reviewMark` 不认 `--target design` 时照今天落地、不写标记，并多报一行原因（决策 6）。
6. 文字：crew-coordinator 两份 skill（如有说「不写技术方案标记」或需补一句的地方）、`CHANGELOG.md`；`spec/crew-flow-v2.md` 末尾「变更记录」补一行（决策 7）。
7. 测试：落地用户批、第二审查者放行、免审三条路径各验标记与参数；失败还原；低版本兜底；变异测试。

**范围外**

- 返工中间那几轮（有阻断的第一轮）写进模块分支的 design.md：不做（决策 4）。crew-flow-v2 决策 7 与 crew-dev「返工不跑 review-mark」保持不变。
- 技术方案在构建中被改过（集成分支上已批、模块分支又改了 design.md）：合并后 spec-guard 会显示 `revised`。今天 Spec 有 `specRevised` 与 `merge run` 补记批准，技术方案没有。另成一项，见未决问题 Q1。
- 本版之前已经落地、没有标记的技术方案补写标记：不自动补，见未决问题 Q2。
- 技术方案要不要审、谁批、过没过：归 spec-guard（`designApproval`、`takeover.design`）与第二审查者（delegate），module-crew 不判。
- 冻结中的 Codex 代批（Spec、Plan）、契约（session-protocol）、`interface.json`：不变。

## 关键决策与取舍（请重点审）

1. **用户批：`--state approved`，不带 `--review`／`--blocking`／`--reason`。** 适用于所有由用户批的技术方案：档位 `takeover.design == human`；第二审查者两轮仍有阻断后用户批；没有第二审查者（`selection none`）后用户批；审查跑不成、放行后落地失败，用户改由自己批。spec-guard 对这些情形都写「the user approves it with --state approved」，`approved` 不检查之前有没有轮次行。
   落地顺序照今天：先把 `design.md`、`regression.md` 写进集成分支 checkout，再跑 `reviewMark`，再提交（标记和文件在同一个提交里）。
2. **第二审查者放行：`--state reviewer-approved --review <报告>`。** 报告用 `codex_note` 已存进状态库的那份（`codex/C<n>-r<轮>.json`，就是判定「没有阻断」所读的同一份）。spec-guard 会再核一次报告与磁盘上的 design.md 对得上、没有阻断；对不上就按决策 5 处理，module-crew 不放宽。
   同厂商审查不另做处理：报告里的 `reviewer.same_vendor` 由 spec-guard 写进轮次行（`same-vendor=true`），`designApproval.sameVendor` 照它显示。
3. **免审放行：不写标记。** spec-guard 对「不用审且档位是 reviewer」的技术方案直接显示 `not-required`，不看标记；module-crew 正是读到这个值才免审放行的，再写 `approved` 反而会把它说成「用户批的」。
4. **只在落地时写，不记返工中间的轮次。** 标记与轮次行要写在被审的那份文本上，而返工时 design.md 只在模块分支上；集成分支上的 `/map` 在落地前根本读不到 design.md（显示 `pending-review` 是如实的：还没落地）。所以落地时一次写对最终状态就够 `designApproval.status` 用。
   取舍：另一种做法是返工通知让模块会话先跑 `reviewer-reviewed --review <报告>` 记下有阻断的那一轮（同今天 Spec、Plan 的 Codex 返工），这样 `designApproval.rounds` 有完整轮次。代价是改 crew-flow-v2 决策 7 与 crew-dev 两份 skill、模块会话多一步，而集成分支上的 `status` 不会因此变得更准。不选，见假设 A2。
   连带：两轮仍有阻断或没有审查者、由用户批时，只写 `approved`，不先补记最后那一轮（`reviewer-reviewed`／`no-reviewer`）。落地后 `status` 为 `approved`、`approvedBy` 为 `user`，`rounds` 为空、`reviewerVendor` 为 null。
5. **写标记失败：照今天 Spec 的处理。** 用户批：退出码 4，「C<n>（<模块>）写批准标记失败，已停下：<spec-guard 原话前 200 字>」，集成分支还原，什么都不提交。第二审查者放行：照 `codex_note` 今天的 M1-M2 报告 C 处理，记「已放行但落地失败」，交用户决定（`codex-fallback` 后 `review approve`）。
   不加针对 design 的特别提示：spec-guard 的拒绝原文已经说了原因与下一步（如 `design-blocking`、`report-invalid`）。
6. **低版本兜底：`--target` 不认 `design` 时不写标记。** `reviewMark` 的 `--target` 占位符里没有 `design` 时（module-crew 认得的写法里是 interface 1.1、1.15 两种；1.20～1.26 的占位符今天 `mark_args` 就不认、`review approve` 整体拒绝，本模块不改），照今天只落地文件，`review approve`／`codex-note` 的输出多一行「装的 spec-guard 不支持技术方案标记（要 interface 1.20），/map 的 designApproval 不会更新」。不拒绝、不停下：今天的落地行为原样保留。
7. **crew-flow-v2 变更记录补一行，不推翻它的决定。** crew-flow-v2「接口约定·写」写的是「技术方案的批准记录写法等 spec-guard `design-review` 定（预计同 `reviewMark` 新 target），本模块按它调用」，本模块就是把这句兑现；在其末尾「变更记录」补一行写明：技术方案落地时按决策 1～3 写 spec-guard 标记，来源本模块。`spec/crew-flow-v2.md` 是公共文件，按【公共变更请求】请模块协调改（或随最终验收由声明范围放行，Plan 定）。
8. **同一次批准里既有需求又有技术方案时**：先写需求的标记、再写技术方案的（按 `NODE_RANK` 排序），因为 spec-guard 判 `design-not-v2` 要读集成分支上 `spec/<id>.md` 的流程标记。

## 接口约定

- **读**：spec-guard `interface.json` 的 `reviewMark.command`（看 `--target` 占位符里有没有 `design`）。不新读 `/map` 字段。
- **写**：经 `reviewMark` 在集成分支 checkout 的 `tasks/<id>/design.md` 里写 spec-guard 的批准标记与（放行时）一行轮次；与今天写 Spec、Plan 标记同一条路，module-crew 不手写标记。
- **协议**：不变。
- **`interface.json`**：不变。

## 项目结构

- 改：`module_crew/review.py`（`_approve` 落地循环、`MARK_TARGET` 或其旁的 design 状态选择、低版本判断）；`module_crew/takeover.py` 只在需要把存下的报告路径传给 `_approve` 时动（今天已传 `report`，预计不用改）。
- 改：`CHANGELOG.md`、`spec/crew-flow-v2.md`（只追加变更记录一行）；crew-coordinator 两份 skill 有相关说法才改（Plan 时核对）。
- 改测试：`tests/test_flow_v2.py`、`tests/test_takeover_approve.py` 或新文件（Plan 定）。

## 命令

```bash
module-crew check quick
scripts/validate.sh --quick
```

## 代码风格

照仓库现有写法：标准库、Python 3.9 可运行、函数注释写来源（`crew-design-mark-sync decision N`）、给用户的文字用中文。

## 测试策略

- 夹具 spec-guard 的 `reviewMark` 记下收到的参数（仓库现有测试的做法），断言：
  - 用户批技术方案：`--target design --state approved --confirm`，没有 `--review`；
  - 第二审查者放行：`--target design --state reviewer-approved --review <状态库 codex/C<n>-r<轮>.json> --confirm`；
  - 免审放行：不调 `reviewMark`；
  - 需求与技术方案同批：需求的调用在前。
- 失败：`reviewMark` 对 design 退出 2 → 用户批退出码 4、集成分支还原；放行路径记落地失败、交用户。
- 低版本：`reviewMark.command` 占位符不含 `design` → 不调、照落地、有提示行。
- 真 spec-guard 一条：用本机 0.101.0 的 `review_mark.py` 在临时仓库里对一份新流程技术方案跑用户批与 reviewer-approved，落地后 `/map --json` 的 `designApproval.status` 为 `approved`、`approvedBy` 分别为 `user`、`reviewer`（装不到 spec-guard 时跳过并写明）。
- 变异：落地循环恢复 `continue`、放行路径改写 `approved`、免审路径也写标记，各让对应测试变红。
- 其余现有测试不改、全绿；现有断言「技术方案落地不调 reviewMark」的测试（如有）按新决定改，Plan 里点名。

## 边界

- **会做**：范围内 1～7。
- **先问再做**：返工轮次写进模块分支；给旧的技术方案补标记；改契约或 `interface.json`。
- **不做**：范围外列出的事；自己判断技术方案过没过、该谁批。

## 验收标准

- **AC1** 用户批技术方案（档位 human，或两轮阻断／没有审查者／审查跑不成后改由用户批）：落地时调 `reviewMark --target design --state approved --confirm`，标记与两份文件在同一个集成分支提交里；用真 spec-guard 时 `designApproval` 为 `approved`／`user`。
- **AC2** 第二审查者放行：调 `reviewMark --target design --state reviewer-approved --review <这一轮存下的报告> --confirm`；用真 spec-guard 时 `designApproval` 为 `approved`／`reviewer`，`sameVendor` 与报告一致。
- **AC3** 免审放行不调 `reviewMark`，其余照今天。
- **AC4** 写技术方案标记失败：用户批停下并还原集成分支（退出码 4）；放行路径记落地失败、交用户。
- **AC5** spec-guard 的 `reviewMark` 不认 `design`：照今天落地，输出有决策 6 的提示行。
- **AC6** 同批里需求标记先于技术方案标记。
- **AC7** `spec/crew-flow-v2.md` 末尾变更记录有本模块的一行；`CHANGELOG.md` 有条目。
- **AC8** 变异测试全部变红；`module-crew check quick` 通过。

## 并行边界

- 独占：`spec/crew-design-mark-sync.md`、`tasks/crew-design-mark-sync/`、`module_crew/review.py`、`module_crew/takeover.py`、`tests/test_flow_v2.py`、`tests/test_takeover_approve.py`
- 公共：`skills/`、`codex-skills/`、`CHANGELOG.md`、`spec/crew-flow-v2.md`（只追加变更记录；发【公共变更请求】）

## 并行说明

能力图上本模块排在最后、串行；挂起的 `crew-takeover-merge` 也改 `takeover.py`、`review.py`，恢复前不会同时改。

## 要你确认的假设

- **A1** 三种情形的写法照 spec-guard 0.101.0：用户批 `approved`；第二审查者放行 `reviewer-approved --review <报告>`；免审不写。没有审查者、两轮仍阻断都归「用户批」，写 `approved`。
- **A2** 只在落地到集成分支时写最终状态，不记返工中间的轮次，也不在用户批之前补记最后一轮（决策 4）；`designApproval.rounds` 对用户批的技术方案为空。hub 模块 8 只要 `status`／`approvedBy` 就够；若它还要 `rounds`、`reviewerVendor`，请在审 Spec 时说，改为补记。
- **A3** 写标记失败按今天 Spec 的失败处理（停下、还原或交用户），不另设特别流程。
- **A4** 本模块不改 crew-flow-v2 的任何已批决定，只在它的变更记录补一行说明兑现了「接口约定·写」那一句。

## 未决问题

- **Q1** 技术方案在构建中被改过：合入后集成分支上的 design.md 标记变成 `revised`，`designApproval` 显示 `revised`。Spec 今天有 `specRevised` 与 `merge run` 补记，技术方案没有。推荐：**另开一项**，由 mc-coord 记单、用户排期；不并进本模块。
- **Q2** 本版之前已经落地、没有标记的技术方案（其他项目里已开工的新流程模块）：`designApproval` 仍显示 `pending-review`。推荐：不自动补；需要时用户在集成分支 checkout 上用 `/spec-guard:review-mark --target design --state approved` 手动补（这等于用户重新批一次），发版说明里写一句。

## 文档建议

`CHANGELOG.md` 随本模块写；crew-coordinator 两份 skill 只在有「不写技术方案标记」一类说法时改，README 没有相关说法，不用改。项目没有文档基线。

## 变更记录
