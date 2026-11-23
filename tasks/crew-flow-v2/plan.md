# Implementation Plan: crew-flow-v2

<!-- spec-guard: review pending -->

> 依据：`spec/crew-flow-v2.md`（用户 2026-11-24 批准，事项 C698「C698 批准，Q 按推荐」；批准后按 mc-coord #22376 改了并行边界写法，见 Spec 变更记录）。任务清单：`tasks/crew-flow-v2/todo.md`。

## Overview

先把「认得新模块」打底（Task 1），再按 Spec 决策顺序改交审节点合法性与过渡（Task 2）、开工判定与通知文字（Task 3）、谁批（Task 4）、交第二审查者（Task 5）、
最终验收按回归（Task 6）、显示（Task 7）。这些都按 sg-coord 已确认的 interface 1.18 形状与接口草案 v1 用夹具开发，上游没发版时走 Spec 写明的兜底。
契约 v2.10 的节点「技术方案」与多模块布局各等一个外部结论，单独排在后面（Task 8、Task 9）。最后改文档、同步、全量测试，并用真装的上游实测（Task 10）。
每个任务先写失败的测试、看到红再实现到绿，在本模块分支本地提交；不推送、不发版。每个任务都验证「老模块（`tier` 为 null）输出与 0.24.2 相同」。

## Architecture Decisions

- **一个判断入口**：新增 `module_crew/flow.py`，集中「这个模块是不是新流程、什么档位、哪些节点合法、什么时候开工、技术方案谁批」；`review.py`、`start.py`、`takeover.py`、`hooks.py`、`present.py` 只调用它。
  读 `/map --json` 沿用 `probe` 已有的读法与缓存，不新开进程。`tier` 缺字段（spec-guard 低于 1.18）一律按 null。
- **节点代码 `design`**：`review.NODE_NAME`、`NODE_RANK`（排在 interface 之后、plan 之前）、`REQUIRED_FILES`、`sources.NODES` 加 `design`；`MARK_TARGET` 暂不加（技术方案的批准标记等 spec-guard `design-review` 定，Task 4 读得到入口才写）。
- **过渡（Spec 决策 9）**：契约 v2.10 发版前，新模块（`normal`／`important`）在 Spec 已批准后再交「节点：Spec」且「文件」列的是 `design.md`、`regression.md` 时，`review add` 记为 `design` 节点；Task 8 后改认正式节点「技术方案」，过渡写法保留一个版本并提示改写。
- **开工判定**：`review._approve` 里「Spec 与 Plan 都批准」那一处（`{"spec","plan"}` 判断）改为调 `flow.ready_to_start(module, approved_nodes)`；老模块返回原判定，逐字不变。
- **上游字段以真实接口为准**：`designApproval`、`takeover.design`、`regression_view` 的字段名按接口草案 v1 写夹具；Checkpoint 4 读真装的 interface.json 核对，不同就改夹具与实现，并在 Spec「变更记录」追加一行、随最终验收复审。
- **不碰挂起模块的未完成部分**：`merge.py` 只加 `push-plan` 的联调提示（Task 9），不动自动合相关代码。

## 影响面

新增：`module_crew/flow.py`、`tests/test_flow_v2.py`、测试夹具（假 `/map --json` 五种档位、假 delegate design 报告、假 `regression_view`）。
修改：`probe.py`、`protocol.py`（Task 8）、`review.py`、`takeover.py`、`sources.py`、`start.py`、`hooks.py`、`present.py`、`merge.py`（Task 9）、`__main__.py`（如需新参数）。
公共文件（发【公共变更请求】，Task 10）：`skills/crew-coordinator/SKILL.md`、`skills/crew-dev/SKILL.md`、`codex-skills/crew-coordinator/SKILL.md`、`codex-skills/crew-dev/SKILL.md`、`README.md`、`README.en.md`、`interface.json`（`contract` 2.10）。
不新增依赖；不改 `store.py`、`checks.py`、版本号、CHANGELOG（发版时由模块协调写）。

## 构建开始时（不是 Task，开工通知到了就做）

- 经模块协调向 session-protocol 契约提需求 v2.10（用户已同意先提，C698 Q1）：【交审】新节点「技术方案」及要点固定项「现状调研、影响面、实现方案、风险与回滚、回归用例、受影响的老功能、未决问题」，
  必须列出的文件 `tasks/<id>/design.md`、`tasks/<id>/regression.md`；放行通知「依据」可写「技术方案」；【等待用户】类型「技术方案」。发【等待其他会话】给 mc-coord，结果回来前不做 Task 8。

## Task List

- [ ] Task 1：认新模块（Spec 决策 1；验收 1）
  - 做：`flow.py` 的 `tier(module)`、`is_v2(module)`、`step(module)`；`probe` 读 `/map --json` 时带上 `tier`、`step`
  - 验证：五种档位夹具读对；1.17 夹具（没有 `tier`）全部按老模块；变异：`is_v2` 恒为假时新模块用例变红
- [ ] Task 2：交审节点合法性与过渡（Spec 决策 2、3、9；验收 2、3、4 的拒收部分）
  - 做：`review add` 按档位判节点；新模块 Plan 交审拒收、bug／small 技术方案与 Plan 拒收（原因照 Spec 决策 3）；`design` 节点必须列两份文件；过渡写法认作 `design`；`sources --nodes` 认 `design`
  - 验证：三种档位 × 五种节点的拒收表逐格测；少列 `regression.md` 被拒；老模块 Plan 交审照收；变异：去掉 Plan 拒收后用例变红
- [ ] Task 3：开工判定、开工与放行通知文字（Spec 决策 4、5；验收 2、3、4 的批准部分）
  - 做：`flow.ready_to_start`；开工通知「要你做什么」改为写 Plan、todo、不交审；`start_basis` 列出技术方案节点；放行通知的下一步（Spec 放行 → 写技术方案与回归交审，技术方案放行 → 开工）；新模块不按 `combined` 合交
  - 验证：普通模块只批 Spec 不发开工、再批技术方案才发；bug 模块批 Spec 即发；技术方案批准后两份文件进集成分支；老模块开工通知逐字不变；变异：开工仍要 Plan 时用例变红

### Checkpoint 1（report）：节点与开工就位，本模块测试与交审、批量、开工、提前开工、外包回归测试通过，记入 todo 后继续

- [ ] Task 4：谁批（Spec 决策 6；验收 5）
  - 做：`takeover` 在新模块上 Spec 恒为人批（旧档位 Codex 也不例外，显示「新流程：需求永远由用户确认」）；技术方案读 `takeover.design`／`designApproval`：`human` 送用户、`reviewer` 交第二审查者、免审直接放行并发开工通知；读不到一律人批并写原因；旧 Plan 一项标「已不生效」
  - 验证：四种情形各一组；读不到字段时人批且 `status` 写「因上游未发版而人批」；老模块档位显示不变
- [ ] Task 5：交第二审查者（Spec 决策 7；验收 6）
  - 做：`review codex` 对 `design` 节点给 `/delegate:review --profile design --backend auto --author-host <宿主> --paths …design.md --paths …regression.md --spec spec/<id>.md`，第二轮加 `--previous-report`；`codex-note` 按「`recheck.items` 未解决 + 非 suggestion 的 findings」判阻断；两轮仍阻断出【等待用户】草稿；`same_vendor` 写进记录与显示；`selection=none` 普通需求记「未审」放行
  - 验证：命令逐字比对、不带 `--model`／`--effort`；两轮上限；同厂商标注；未审放行并发开工；Spec、Plan 节点的 Codex 审查（老模块）输出不变

### Checkpoint 2（report）：批准链路就位，本模块测试与接管、审查就近回归测试通过，记入 todo 后继续

- [ ] Task 6：最终验收按回归（Spec 决策 11；验收 7）
  - 做：新模块最终验收「验收结果」要有 `R<n>` 行；有 `regression_view` 时对照用例清单、列出缺的；`manual` 用例写「待用户测」不算缺
  - 验证：缺行拒收、缺某条列出、manual 不算缺、没有 `regression_view` 时只查有 `R<n>`；老模块最终验收照旧
- [ ] Task 7：显示（Spec 决策 4、10；验收 9）
  - 做：钩子「当前」一句、`status`、`start plan` 在五种档位与 `step=design／regression` 上按 Spec 决策 10 的文字；`combined` 项目里新模块写「需求与技术方案分开交」
  - 验证：逐种档位比对文字；老模块文字不变

### Checkpoint 3（gate）：契约 v2.10 发版

- [ ] session-protocol v2.10 已发版并含节点「技术方案」：没发就停在这里（其余已完成的照常保留），发【等待其他会话】；用户若决定不改契约，请用户定替代做法再继续

- [ ] Task 8：协议认「技术方案」（Spec 决策 2、9；验收 10）
  - 做：`protocol.REVIEW_NODES`、`WAIT_KINDS`、放行通知节点正则加「技术方案」；契约样例放 `tests/fixtures/session-protocol/v2.10/`；过渡写法提示改写
  - 验证：契约样例逐条通过；`protocol check` 认新节点与要点；过渡写法仍收并提示
- [ ] Task 9：多模块布局（Spec 决策 8；验收 8）——sg-coord 已同意方向（#22384，经 mc-coord #22385 转来），正式采纳写进 spec-guard `regression-doc-check` 的 Spec、经它的用户审批后回告字段；按回告做：
  - **等上游**：spec-guard 现在把 `spec/usage/` 下所有 `*.md` 当用法草案解析，`spec/usage/<需求>.regression.md` 会让 `milestoneStop` 报未验证；`regression-doc-check` 发版（排除 `*.regression.md`）前，本模块只在测试夹具里用这个文件，不在任何真实仓库建它；读联调回归结论的提示等它发版再接上，没发版时照兜底不提示
  - 采纳：`review batch` 把同一需求（同一 `spec/usage/<需求>.md`）的模块 Spec 与需求一级文档并成一张卡；`merge push-plan`、`start plan` 在 `milestoneStop` 出现且联调回归没有结论时提示（不拦）
  - 不采纳：不做这一项，Spec 去掉范围第 7 条与 AC8（变更记录追加一行，随最终验收复审），todo 记「按答复取消」
  - 验证（采纳时）：同需求三个模块并成一张卡；有结论时不提示；没有用法草案的单模块不受影响

### Checkpoint 4（gate）：上游发版与实测

- [ ] 本机装上含 interface 1.18 的 spec-guard（flow-doc-skeletons 随 M1 发）：没装就停在这里，发【等待其他会话】；装了就读真实 interface.json 与 `/map --json` 核对 `tier`、`step`，不同就改夹具与实现并记 Spec 变更记录。
  `design-review`／`takeover-redefine`／`regression-doc-check` 与 delegate 1.7 没发版的，照兜底交付，在最终验收写明「待上游发版后接上」，不为它们停

- [ ] Task 10：文档与全量测试（Spec 文档建议；验收 1、11）
  - 做：四份 skill、README 中英、`interface.json` 的 `contract` 改为 2.10——发【公共变更请求】，等答复后照答复改；`module-crew sync` 后后台跑全量测试；`module-crew check quick`
  - 验证：全量测试全过；`check quick` 通过；本机用真装 spec-guard 在一个夹具项目上看到新模块的节点拒收与开工判定

### Checkpoint 5（gate）：最终验收

- [ ] 回告：完成情况经模块协调转告 ecosystem-lead 与 sg-coord（module-crew 跟随 S110 的部分已实现；多模块布局按 sg-coord 的答复落地或取消）

## Risks

| 风险 | 影响 | 缓解 |
|---|---|---|
| spec-guard 1.18 字段与夹具不同 | 返工夹具与实现 | 夹具按 sg-coord #22378 与已验收源码写；Checkpoint 4 用真装版本核对，差异记变更记录 |
| `design-review` 等后续模块迟迟不发 | 技术方案只能人批 | Spec 已定兜底；不为它们停，最终验收写明待接上 |
| 改开工判定碰坏老模块 | 老模块收不到开工通知 | 老模块走原判定分支；现有开工、提前开工、外包测试逐字通过 |
| 契约 v2.10 不批或晚到 | Task 8 做不了 | 过渡写法先可用；Checkpoint 3 停下请用户定替代做法，不擅自借用别的节点名 |
| sg-coord 最终不采纳多模块布局，或 `*.regression.md` 被误当用法草案 | Task 9 白做，或真实仓库的 `milestoneStop` 报未验证 | Task 9 排在回告之后，按回告做或取消；上游排除前不在真实仓库建 `*.regression.md` |
| 与挂起的 crew-takeover-merge 改同一文件 | 恢复时冲突 | 该模块剩余任务已按 C698 Q4 撤（Task 10 的 K 另开轻任务），本模块只改 `merge.py` 的 `push-plan` 提示 |

## 中途会停下来问你的地方

- Checkpoint 3（gate）：契约 v2.10 未发版或不批时。
- Checkpoint 4（gate）：本机还没有 interface 1.18 时。
- Checkpoint 5（gate）：最终验收。
- 另照常：测试改不红、Spec 没覆盖的决策、高风险不可逆改动时停下。

## 未决问题

无（Spec 的 Q1～Q4 已按 C698 推荐定；决策 8 sg-coord 已同意方向、等它的用户审批后回告字段，已排进 Task 9）。
