# Spec: crew-review-rules-follow

<!-- spec-guard: review approved 1f1755fcf21f -->

> 能力图模块 `crew-review-rules-follow`。需求来源：ecosystem-lead #23377、#23442（sg-coord #23440）；用户 2026-11-27 在 mc-coord 批准排期、插入与开工（「和 blocking 一起排」「需求齐了，开工」「确认插入」），开会话依据：用户批准事项 C852。
> 上游：spec-guard 0.98.0（interface 1.26，`spec/sg-gate-flow.md`：`milestoneStop.blocking`）、0.99.0（interface 1.27，模块 5 `sg-review-rules`：重要需求的技术方案也按档位 `takeover.design` 放行）。
> 本机 2026-11-27 实测：`~/.claude/plugins/installed_plugins.json` 里 spec-guard 已是 0.99.0，`interface.json` 为 `1.27`，构建不用再等升级。
> 依赖 `crew-start`（`start plan`／`start prepare` 的停点）、`crew-flow-v2`（新流程技术方案的批准人）。现状取自本分支源码（`module_crew/start.py`、`module_crew/takeover.py`）。
> 本模块是老流程模块（不带流程标记）：Spec → Plan → todo。

## 目标

跟上 spec-guard 0.98.0／0.99.0 的两处改动：

- **里程碑停点按 `blocking` 停**：`start plan`／`start prepare` 只在 `milestoneStop.blocking` 为真时把停点当阻塞项；为假（里程碑里每个模块都用 autopilot 预设）时照常开工，只提一句。
- **重要需求的技术方案按档位走**：新流程模块的技术方案由谁批，只看 spec-guard 给的生效档位 `takeover.design`；重要需求不再由 module-crew 另外强制人批。**这推翻 `crew-flow-v2` 的一条已批决定**（目标第 3 条「重要需求的技术方案永远人批」、决策 6 的括注、决策 7 的「重要需求本来就人批，不走到这里」与假设 A3 后半句），本模块在 `spec/crew-flow-v2.md` 末尾「变更记录」补一行。

## 现状

- `module_crew/start.py:32` `milestone_stop`：`milestoneStop` 是对象且不是 `error` 就返回阻塞项「里程碑停点：…还没确认…」，不看 `blocking`；`plan()` 有阻塞项就不提议，`prepare` 退出码 3。
- `module_crew/takeover.py:169-170` `_design`：`tier == "important"` 一律返回 `("human", DESIGN_IMPORTANT)`，排在读 `designApproval`、`takeover.design` 之前。
- spec-guard interface 1.27 的 `takeover.design`：「the configured value alone: an important flow v2 requirement no longer forces human」；`designForcedBy` 从 1.27 起恒为 null（1.22～1.26 为 `important` 时表示被重要需求强制成人批）。
- spec-guard 1.22～1.26 给的 `takeover.design` 本来就已算进重要需求（「in effect」）；所以去掉 module-crew 自己的强制后，旧版 spec-guard 上的结果不变。

## 范围

**范围内**

1. `milestone_stop` 读 `blocking`（决策 1、2）。
2. `_design` 去掉对 `important` 的强制，改为读 `designForcedBy`（决策 3、4）。
3. 重要需求的技术方案碰到「没有可用的第二审查者」时的去向（决策 5）。
4. `skills/crew-coordinator/SKILL.md:273` 与 `codex-skills/crew-coordinator/SKILL.md:286` 的「技术方案谁批：重要需求人批」改为按档位；Claude 版第 67 行「里程碑停点」一句加上 `blocking`（Codex 版今天没有这一句，补上同样一句）；`spec/crew-flow-v2.md` 变更记录补一行；`CHANGELOG.md`。
5. 测试：`tests/test_start_plan.py`、`tests/test_start_prepare.py` 加 `blocking` 用例；`tests/test_flow_v2.py:292` 那条「重要需求技术方案人批」的断言按新决定改（它钉的就是被推翻的决定），另加新用例。

**范围外**

- spec-guard 1.27 的「需求文档先审一轮」（`requirementReview`）：见未决问题 Q1，用户定之前不做。
- 普通需求「没有审查者就未审放行」（crew-flow-v2 假设 A3 前半句）：不改，见未决问题 Q2。
- 里程碑的确认本身（`/spec-guard:milestone-mark`）、档位的存储与预设：归 spec-guard。
- 已在做的模块、`review approve`、`merge`、`start kickoff`、轻任务：本来就不受停点影响，照旧。

## 关键决策与取舍（请重点审）

1. **`blocking` 怎么读**：只有 `blocking is False`（JSON 的 false）时不阻塞；缺这个字段（spec-guard 低于 1.26）、为 true、或是别的值，一律按阻塞处理，与今天一致。`error: unreadable` 的停点照今天（只警告、`prepare` 拒绝），spec-guard 说错误对象不带 `blocking`。
2. **不阻塞时说什么**：`start plan` 照常提议，另起一行提示「里程碑停点：<里程碑> 还没确认（<草案文件>），按 autopilot 预设不挡开工；用户方便时用 /spec-guard:milestone-mark 确认」。这行是**提示**，不进 `warnings`（`warnings` 会让 `prepare` 拒绝），`prepare` 照常开工、开工结果里同样带这行提示。
3. **重要需求不再强制人批**：`_design` 删掉 `tier == "important"` 那一支，按 `designApproval`（免审）→ `takeover.design`（`reviewer`／`human`）→ 读不到人批的顺序判定，重要需求与普通需求走同一条路。
4. **旧版 spec-guard 上的显示**：`takeover.designForcedBy == "important"`（1.22～1.26）时返回 `("human", DESIGN_IMPORTANT)`，显示仍写「重要需求：技术方案由用户批」；1.27 起它恒为 null，不会出现。module-crew 不再按 `tier` 自己判，只照 spec-guard 给的字段。
5. **重要需求没有可用的第二审查者（新）**：今天 `codex_note` 对技术方案一律「未审放行」，因为按 crew-flow-v2 决策 7 重要需求不会走到这里；档位放开后会走到。推荐：**重要需求在 `reviewer.selection` 为 `none` 时送用户批**（不放行），给用户的【等待用户】写明「本机没有可用的第二审查者，重要需求的技术方案由你批」；普通需求照旧未审放行。理由：spec-guard 对这种情形的状态是 `unreviewed`（「the user approves it」），重要需求不该比普通需求放得更松。

## 接口约定

- **读**：`/map --json` 顶层 `milestoneStop.blocking`（1.26）；每个模块 `takeover.design`、`takeover.designForcedBy`（1.22，1.27 起恒为 null）、`designApproval.status`。
- **写**：不变。module-crew 不写 spec-guard 的文件与配置。
- **协议**：不变，不需要契约新版。
- **`interface.json`**：不变。

## 项目结构

- 改：`module_crew/start.py`（`milestone_stop` 与提议、开工结果的提示行）、`module_crew/takeover.py`（`_design`、`codex_note` 的无审查者分支）、`module_crew/present.py`（如提示行要在这里排版）。
- 改：`skills/crew-coordinator/SKILL.md`、`codex-skills/` 对应 skill、`CHANGELOG.md`、`spec/crew-flow-v2.md`（只追加变更记录一行）。
- 改测试：`tests/test_start_plan.py`、`tests/test_start_prepare.py`、`tests/test_flow_v2.py`。

## 命令

```bash
module-crew check quick
scripts/validate.sh --quick
```

## 代码风格

照仓库现有写法：标准库、Python 3.9 可运行、函数注释写来源（`crew-review-rules-follow decision N`）、给用户的文字用中文。

## 测试策略

- 停点：`blocking` 为 true、false、缺字段、非布尔四种，加 `error: unreadable`；`plan` 与 `prepare` 各一组。
- 批准人：`important` + `takeover.design` 为 `reviewer`／`human`／缺失；`designForcedBy == "important"`；`designApproval.status == "not-required"`；`normal` 回归不变。
- 无审查者：`important` 送用户、`normal` 仍未审放行。
- 变异：`blocking` 判断改成「真值」或删掉、恢复 `important` 强制、无审查者分支不分档位，各让对应测试变红。
- 其余现有测试不改、全绿。

## 边界

- **会做**：范围内 1～5。
- **先问再做**：改普通需求的无审查者去向；做 `requirementReview` 跟随；改契约或 `interface.json`。
- **不做**：范围外列出的事；自己判断哪个模块是重要需求。

## 验收标准

- **AC1** `milestoneStop.blocking` 为 false：`start plan` 照常提议并带决策 2 的提示行，`prepare` 照常开工（退出码 0）；为 true、缺字段或非布尔：与今天一致（阻塞，`prepare` 退出码 3）。
- **AC2** `milestoneStop.error == "unreadable"`：与今天一致。
- **AC3** 新流程 `important` 模块：`takeover.design=reviewer` 时技术方案交第二审查者，`human` 或读不到时送用户，`designApproval` 免审时直接放行；与 `normal` 判定相同。
- **AC4** `takeover.designForcedBy == "important"` 时送用户并显示「重要需求：技术方案由用户批」。
- **AC5** 重要需求的技术方案审查报告 `reviewer.selection == "none"`：不放行，产出送用户的【等待用户】草稿；普通需求照旧未审放行。
- **AC6** `spec/crew-flow-v2.md` 末尾变更记录有本次推翻的一行；crew-coordinator 两份 skill 的停点与批准人说法已改。
- **AC7** 变异测试全部变红；`module-crew check quick` 通过。

## 并行边界

- 独占：`spec/crew-review-rules-follow.md`、`tasks/crew-review-rules-follow/`、`module_crew/start.py`、`module_crew/takeover.py`、`module_crew/present.py`、`tests/test_start_plan.py`、`tests/test_start_prepare.py`、`tests/test_flow_v2.py`
- 公共：`skills/`、`codex-skills/`、`CHANGELOG.md`、`spec/crew-flow-v2.md`（只追加变更记录；发【公共变更请求】）

## 并行说明

能力图上本模块排在最后、串行；挂起的 `crew-takeover-merge` 也改 `takeover.py`，恢复前不会同时改。

## 要你确认的假设

- **A1** `blocking` 只有明确为 false 才不阻塞，缺字段按阻塞（兼容 spec-guard 低于 1.26）。
- **A2** 不阻塞的停点只提示、不挡 `prepare`，也不要求用户先确认里程碑。
- **A3** 批准人只看 spec-guard 给的 `takeover.design`／`designForcedBy`，module-crew 不再按 `tier` 自己强制；旧版 spec-guard 上结果不变。
- **A4** 重要需求没有可用审查者时送用户批（决策 5）。

## 未决问题

- **Q1** spec-guard 1.27 另一处改动「需求文档先审一轮」：新流程 `normal`／`important` 的需求没有审查记录（`flow.requirementReview.status == "missing"`）时，`reviewMark --target spec --state approved` 拒绝（`requirement-unreviewed`）。
  module-crew 的 `review approve` 在集成分支落地需求批准时会因此失败。这不在本模块的分配范围里。推荐：**另开一项**（模块会话交需求前先审一轮、`review add` 对缺审查记录的需求拒收并说明原因），由 mc-coord 记单、用户排期；不并进本模块。
- **Q2** 普通需求「没有审查者就未审放行」（crew-flow-v2 A3 前半句）与 spec-guard `designApproval.status = unreviewed`（「the user approves it」）、sg-review-rules 第 12 条（「记『没有审查者』，交用户批」）不一致：module-crew 放行了，spec-guard 那边仍记为待用户批。这是 crew-flow-v2 起就有的出入，不由本模块改；推荐随 Q1 一并交用户定。
- **Q3** spec-guard 0.99.0 的 `interface.json` 里 `takeover.notes` 仍写「an important requirement's design is always the user's」，与同文件 `takeover.fields.design`（1.27 起不再强制）矛盾。本模块按 `fields.design` 与 `designApproval.statusValues` 实现；推荐经 mc-coord 回告 sg-coord 改说明文字。

## 文档建议

`crew-coordinator` 两份 skill 的「里程碑停点」与「技术方案谁批」两句随本模块改（范围第 4 条）；README 没有这两处说法，不用改。项目没有文档基线。

## 变更记录
