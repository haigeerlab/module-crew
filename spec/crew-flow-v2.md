# Spec: crew-flow-v2

<!-- spec-guard: review approved 630d5a607cd6 -->

> 能力图模块 `crew-flow-v2`。需求来源：接缝 S110，plugin-ecosystem `research/2026-11-24-开发流程改版/需求.md`（用户 2026-11-24 确认）第七节 module-crew 一行，
> 以及第三节总表 ②③④⑦、第五节第 3、4 条。开会话依据：用户批准事项 C696。
> 上游：spec-guard 用法草案 `spec/usage/dev-flow-v2.md` 对外接口 v1（sg-coord #22365，分支 `claude/dev-flow-v2`，提交 cb75ad03）；
> spec-guard 模块 `flow-doc-skeletons`（interface 1.18，构建中）；delegate 接口 1.7（`--profile design`，delegate-owner #22369、#22372，计划 0.12.0）。
> sg-coord 请 module-crew 按第七节提出「多模块时需求、技术方案、回归放在哪」的方案，写进本 Spec（决策 8，**这一节是给 spec-guard 的接口提案**）。
> 依赖 `crew-start`（开工说明、`start plan`）、`crew-review-batch`（交审、`review approve` 落地与开工通知）、`crew-merge`（最终验收、合并）、
> `crew-takeover-approve`（按档位交第二审查者、`review codex`、放行通知）。
> 现状取自 0.24.2 源码（`review.py`、`protocol.py`、`takeover.py`、`sources.py`、`start.py`、`hooks.py`、`probe.py`）。标「新」的是写 Spec 时补的实现取舍，请重点审。

## 目标

spec-guard 新流程（需求文档 → 技术方案 → 回归测试文档 → 拆任务 → 实现 → 按回归验收）上线后，module-crew 的交审、开工、合并跟着走，老模块一切照旧：

- **认得新模块**：`/map --json` 里 `tier` 不为 null 的模块按新流程处理；`tier` 为 null（老模块，或 spec-guard 低于 interface 1.18）逐字照今天。
- **交审节点跟着换**：新模块的节点是「Spec」（即需求文档）→「技术方案」（新，技术方案与回归一起交）→「最终验收」；**Plan 不再交审**，模块会话写完 Plan、todo 就开工。
  bug、小改动只有「Spec」和「最终验收」。
- **谁批跟着换**：需求永远用户批；技术方案按 spec-guard 给的生效档位，人批或交第二审查者审一轮、改一轮；重要需求的技术方案永远人批。
- **开工跟着换**：新模块在需求（bug、小改动）或技术方案（普通、重要）批准后发开工通知，通知里写「写 Plan、todo，不交审，提交后按它构建」。
- **验收按回归**：新模块的最终验收「验收结果」按回归文档的用例编号逐条写。
- ~~**多模块写法**~~：已取消（用户 C715「B」，见变更记录）；多模块布局的提案留给 spec-guard `regression-doc-check`，本模块不实现。

## 范围

**范围内**

1. **识别**：`probe` 读 spec-guard interface ≥ 1.18 时从 `/map --json` 取每个模块的 `tier` 与 `step`（`design`、`regression`），记在 module-crew 读到的模块信息里（决策 1）。
2. **新节点「技术方案」**：`protocol` 认【交审】节点「技术方案」、它的要点、必须列出的文件；`review add` 按模块是否新流程判哪些节点合法（决策 2、3）。需要 session-protocol 新版（决策 9）。
3. **Plan 不交审**：新模块的 Plan 交审被拒并说明原因；`review approve` 的开工判定改为按新流程（决策 4、5）。
4. **谁批**：新模块的「Spec」永远人批；「技术方案」按 spec-guard 的生效档位人批或交第二审查者（决策 6、7）。
5. **开工与放行通知的文字**：开工通知、放行通知、`start plan`、`status`、钩子注入的「当前」一句按新流程写下一步（决策 5、10）。
6. **最终验收**：新模块「验收结果」按回归用例编号核对（决策 11）。
7. ~~**多模块布局**~~：已取消（用户 C715「B」）。
8. **skill 与文档**：`crew-coordinator`、`crew-dev`（Claude 与 Codex 各一份）、README、`interface.json`（契约版本）。

**范围外**

- 三份文档的骨架、分档、需求拷问触发、`designReview` 开关、Plan 自动批准的标记、回归文档格式检查、⑦ 的通过标准与校验器：归 spec-guard。
- 技术方案的审查判据、第二审查者的检测与选择：归 delegate。module-crew 只调 delegate 给的命令、读报告的约定字段。
- ⑦ 合并前验证的执行、证据绑定补丁、自动合并、附带意见开 issue、合规监测、接管档位的预设与旧值兼容：归 autopilot 与 spec-guard。
- 老模块（没有流程标记）：Spec → Plan → todo 照旧，不改不补。
- 挂起的 `crew-takeover-merge` 剩余 Task 9～12：不并进本模块（见未决问题 Q4）。
- 改模块会话的停点：三种必停情况与 Plan 里标 `gate` 的检查点照旧。

## 上游依赖（构建要等）

| 上游 | 版本 | 本模块用到 | 未发版时 |
|---|---|---|---|
| spec-guard `flow-doc-skeletons` | interface 1.18 | `/map --json` 的 `tier`、`step` 取值 `design`／`regression`；文档位置 `spec/<id>.md`、`tasks/<id>/design.md`、`tasks/<id>/regression.md` | 所有模块按老流程；构建停在 Plan 第一个 `gate`，发【等待其他会话】 |
| session-protocol | v2.10（新，决策 9） | 【交审】节点「技术方案」及其要点；放行通知的节点可写「技术方案」；【等待用户】类型「技术方案」 | 按记忆规则先向契约提需求、经用户批准、契约发版后再构建这一项 |
| spec-guard `design-review`、`takeover-redefine` | 接口版本待定（排在 1.18 之后） | `/map --json` 的 `designApproval` 与生效档位 `takeover.design`（`human`／`reviewer`）；技术方案批准的记录入口 | 新模块的技术方案一律人批（决策 6 的兜底），其余照做 |
| spec-guard `plan-auto-approve` | 同上 | Plan 写完即批准，`/build` 认它 | module-crew 不代写 Plan 的批准标记；新模块的试点等它发版，见未决问题 Q3 |
| spec-guard `regression-doc-check` | 同上 | `regression_view --json` 的用例编号 | 最终验收只查「验收结果」里写了 `R<n>`，不逐条对照（决策 11 的兜底） |
| delegate | 接口 1.7（0.12.0） | `/delegate:review --profile design --backend auto --author-host …`、`--previous-report`、报告 `reviewer.{vendor,same_vendor,selection}`、`recheck.items` | 技术方案不交第二审查者，人批 |

读不到某项时一律退回更保守的做法（人批、老流程），不报错；`status` 与 `start plan` 写明「因上游未发版而人批」。

## 关键决策与取舍（请重点审）

1. **怎么认新模块（新）**：只看 `/map --json` 的 `tier`（interface 1.18 每个模块都有，老模块为 null）。module-crew 不自己读 `spec/<id>.md` 的流程标记行，不解析文档。
   重开修订的老模块仍是老模块；spec-guard 判为 `important` 而档位写的不是 `important` 时，以 `/map` 给的 `tier` 为准。
2. **新节点叫「技术方案」，技术方案和回归一起交（新）**：总表 ③ 要求回归「跟随技术方案、与技术方案一起审」，所以不另设「回归」节点。
   - 必须列出的文件：`tasks/<id>/design.md`、`tasks/<id>/regression.md`（同今天 Spec 必须列 `spec/<id>.md` 的做法，批准时只把列出的文件搬进集成分支）。
   - 要点固定项（契约 v2.10 提案）：「现状调研」「影响面」「实现方案」「风险与回滚」「回归用例」「受影响的老功能」「未决问题」，后两项可写「无」。
   - 节点代码 `design`；`sources` 的审查者负责范围 `--nodes` 也认 `design`。
3. **哪些节点合法**：

   | 模块 | 档位 | 合法节点 | 被拒的节点 |
   |---|---|---|---|
   | 老模块 | null | Spec、接口提案、Plan、最终验收（照今天） | 技术方案 |
   | 新模块 | `normal`、`important` | Spec、接口提案、技术方案、最终验收 | Plan（「新流程模块的 Plan 不交审：写完 Plan、todo 提交后直接构建」） |
   | 新模块 | `bug`、`small` | Spec、最终验收 | 技术方案、Plan（「bug／小改动只写一份文档」） |

   接口提案在新模块上等同「Spec」（今天的 `MARK_TARGET` 就把它当 Spec），不变。
4. **评审节奏**：新模块的需求与技术方案**总是分开交**：技术方案要在确认过的需求上写（需求「每次都等我确认」）。项目设了 `combined` 时，新模块不按它合并，`start plan` 写明「新流程模块：需求与技术方案分开交」。老模块照项目节奏。
5. **开工判定（新）**：今天 `review approve` 要 Spec 与 Plan 都批准才发开工通知。新模块改为：

   | 档位 | 发开工通知的时机 |
   |---|---|
   | `bug`、`small` | Spec 批准（或放行）后 |
   | `normal`、`important` | Spec 与技术方案都批准（或放行）后 |

   开工通知「要你做什么」：先 `module-crew sync`，再写 `tasks/<id>/plan.md`（只留任务与检查点）、`tasks/<id>/todo.md`，**不交审**，提交后按它构建；公共文件只能经【公共变更请求】改。
   「依据」照 S53 的写法列出这次批准的节点和以前批准的节点（「Spec 以前批准于 C<n>」「技术方案由第二审查者放行于 C<n>」）。
   Plan、todo 跟着模块分支在最终验收时合入，不在开工前搬进集成分支。
6. **谁批（新）**：
   - **Spec（需求文档）永远人批**：新模块上即使旧档位写了 Spec 交 Codex，也按人批，`status` 写「新流程：需求永远由用户确认」。
   - **技术方案**：读 spec-guard 给的生效档位 `takeover.design`（已算进「重要需求永远人批」）。`human` → 送用户；`reviewer` → 不送用户，模块协调照决策 7 交第二审查者；
     spec-guard 判定这一份不用审（`designApproval` 表明免审）→ 不送任何人，`review add` 直接记为「免审放行」并照决策 5 发开工通知。
   - **兜底**：spec-guard 还没有 `takeover.design`／`designApproval`（上游未发版）时，技术方案一律人批。
   - 旧档位里的 Plan 一项在新模块上不起作用，`status` 标「已不生效」。
7. **交第二审查者（新）**：沿用 crew-takeover-approve 的 `review codex C<n>`／`review codex-note`，只换命令和判据：
   - 命令取 delegate 1.7：`/delegate:review --profile design --backend auto --author-host <模块会话的宿主> --paths tasks/<id>/design.md --paths tasks/<id>/regression.md --spec spec/<id>.md`
     （再加影响面里列的已有文件，由 spec-guard 给出时照它）；第二轮加 `--previous-report <上一轮报告>`。不带 `--model`、`--effort`。
   - 阻断 = `recheck.items` 里 `unresolved` 的 + `findings` 里非 `suggestion` 的；没有阻断就放行，有就返工。**最多两轮**，第二轮只核对上一轮；第二轮仍有阻断 → 送用户批，不开第三轮。
   - 报告 `reviewer.same_vendor` 为 true 时，放行记录与给用户的显示写「同厂商审查」。
   - `reviewer.selection` 为 `none`（没有可用审查者）：**取代**今天「Codex 不可用一律停下等用户」那一条（需求第五节第 4 条）。普通需求记为「未审」放行、写明由回归兜底；
     重要需求本来就人批，不走到这里。（这一条请确认，见假设 A3。）
   - 写代码的会话不审自己：审查由模块协调发起，`--author-host` 填模块会话的宿主，delegate 据此选别的厂商或同厂商独立会话。
8. **多模块布局（给 spec-guard 的接口提案，新）——本模块已取消实现（用户 C715「B」）**，下面的提案原样留作给 spec-guard `regression-doc-check` 的参考：一个需求拆成多个模块时（即今天有用法草案 `spec/usage/<需求>.md` 的情形）：

   | 文档 | 位置 | 谁写、何时 | 谁批 |
   |---|---|---|---|
   | 需求一级文档 | `spec/usage/<需求>.md`：在现有用法草案里加需求文档的各节（目标、给谁用、使用场景、业务规则和异常情形、不做什么、成功标准 `S<n>`、待定问题），入口表、里程碑照旧 | 插入模块时由写能力图的会话写 | 用户确认一次，与能力图插入同批 |
   | 模块需求 | `spec/<id>.md`（带流程标记，档位按模块定）：只写「需求来源：`spec/usage/<需求>.md`」、本模块承担的成功标准编号、本模块特有的业务规则与不做什么 | 模块会话 | 与需求一级文档同一批交用户，用户只确认一次（`review batch` 把同一需求的模块 Spec 并成一张卡） |
   | 技术方案、回归 | 每个模块 `tasks/<id>/design.md`、`tasks/<id>/regression.md`（与单模块相同） | 模块会话 | 按决策 6 |
   | 整体联调回归 | `spec/usage/<需求>.regression.md`：用例格式与模块回归相同（`### R<n>`），另有「成功标准 → 联调用例」与「涉及的模块」两节；只放跨模块的成功标准 | 写需求一级文档时起草（只需黑盒用例），各模块技术方案批准后按需补，补了记变更 | 与需求一级文档同批确认；补的部分随最后一个模块的技术方案一起交 |

   - **何时跑联调回归**：同一里程碑的模块都合入集成分支（spec-guard `milestoneStop` 出现）后、`milestone-mark` 之前，由非作者照它执行；结论格式复用 spec-guard.verification/v1，「模块」写需求名。
     module-crew 只在 `merge push-plan` 与 `start plan` 里提示「<需求> 的联调回归还没有结论」，不执行、不拦推送（执行与把关归 autopilot）。
   - **为什么放在 `spec/usage/`**：spec-guard 已经用它把一个需求的多个模块连起来（里程碑、`milestoneStop`），不另立目录；单模块需求没有这一级，照单模块写。
   - 这是提案：位置与字段以 spec-guard 的 Spec 为准；sg-coord 采纳后 module-crew 按它实现，不采纳就只做第 2～7、9～11 条。
9. **契约（新）**：节点「技术方案」、它的要点、放行通知可写「技术方案」、【等待用户】类型「技术方案」都要 session-protocol 新版（提案 v2.10）。按记忆规则先向契约提需求、经用户批准再改本仓库；
   契约未发版前，交审节点只认今天的四种，新模块的技术方案按「Spec」节点交、`review add` 不拒（过渡），开工判定仍按决策 5。
10. **阶段显示**：钩子注入的「当前」一句、`status`、`start plan` 在新模块上写：等需求确认／写技术方案与回归／技术方案待批（人或第二审查者）／写 Plan、todo 后构建／待最终验收；
    `step` 为 `design`、`regression` 时显示「写技术方案」「写回归」。
11. **最终验收按回归（新）**：新模块的最终验收「验收结果」每行以回归用例编号开头（`R<n>：<结果与证据>`）；spec-guard 有 `regression_view` 时 `review add` 对照用例清单，缺哪条就拒收并列出；没有时只查至少有一行 `R<n>`。
    执行方式为 `manual` 的用例写「待用户测」，不算缺。老模块照今天按 Spec 验收标准写。

## 接口约定

- **读**：`/map --json` 每个模块的 `tier`、`step`；之后版本的 `designApproval`、`takeover.design`、`regression_view --json`（字段名以 spec-guard 发版为准，读不到按兜底）。
- **写**：module-crew 不写 spec-guard 的任何文件与配置；技术方案的批准记录写法等 spec-guard `design-review` 定（预计同 `reviewMark` 新 target），本模块按它调用。
- **协议**：【交审】「节点：技术方案」，「文件」必须列 `tasks/<id>/design.md`、`tasks/<id>/regression.md`；【协调通知】放行类「依据」可写「技术方案」；开工通知「要你做什么」按决策 5。
- **`interface.json`**：`contract` 升到 2.10（契约发版后）。

## 项目结构

- 改：`module_crew/probe.py`（读 `tier`、`step`）、`protocol.py`（节点、要点、放行节点）、`review.py`（合法节点、开工判定、最终验收按回归、免审放行）、`takeover.py`（新模块的批准方、生效档位）、
  `sources.py`（`design` 节点）、`start.py`、`hooks.py`、`present.py`（显示）、`__main__.py`（如有参数变化）。
- 改：`skills/crew-coordinator/`、`skills/crew-dev/`、`codex-skills/` 两份、`README.md`、`README.en.md`、`interface.json`、`CHANGELOG.md`。
- 新增测试：`tests/test_flow_v2.py`；夹具按 interface 1.18 的 `/map --json` 形状造。

## 命令

```bash
python3 -m unittest discover -s tests
module-crew check quick
```

## 代码风格

照仓库现有写法：标准库、函数注释写决策编号（`crew-flow-v2 decision N`）、给用户的文字用中文。

## 测试策略

- 每条决策一组单元测试，夹具模拟 `/map --json` 的老模块、`bug`、`small`、`normal`、`important` 五种；上游字段缺失的兜底各一条。
- 变异：去掉 `tier` 判断、开工判定仍要 Plan、Plan 交审不拒，各让对应测试变红。
- 老模块回归：现有测试全部不改、全绿。

## 边界

- **会做**：范围内 1～8。
- **先问再做**：改老模块的任何行为；改契约现有节点或字段；改 spec-guard 的文件。
- **不做**：范围外列出的事；自己解析 spec-guard 的文档格式。

## 验收标准

- **AC1** 老模块（`tier` 为 null）与 spec-guard 低于 1.18 时：交审、开工、显示、最终验收与 0.24.2 一致，现有测试全绿。
- **AC2** `normal`／`important` 模块：Plan 交审被拒并给原因；Spec 与技术方案都批准后才发开工通知，通知写「写 Plan、todo，不交审」。
- **AC3** `bug`／`small` 模块：技术方案、Plan 交审被拒；Spec 批准后即发开工通知。
- **AC4** 技术方案交审必须列 `design.md`、`regression.md`，少列被拒；批准后两份文件进集成分支。
- **AC5** 新模块 Spec 在旧档位为 Codex 时仍送用户；技术方案在 `takeover.design=reviewer` 时交第二审查者、`human` 或读不到时送用户、免审时直接放行并发开工通知。
- **AC6** 第二审查者：命令带 `--profile design --backend auto --author-host`，第二轮带 `--previous-report`；两轮后仍有阻断送用户；`same_vendor` 写进显示；`selection=none` 普通需求记「未审」放行。
- **AC7** 新模块最终验收：缺 `R<n>` 行被拒；有 `regression_view` 时缺哪条用例被列出。
- ~~**AC8**~~ 已取消（用户 C715「B」）。
- **AC9** 钩子、`status`、`start plan` 在五种档位与 `step=design／regression` 上的文字按决策 10。
- **AC10** 契约 v2.10 发版后协议自检认「技术方案」节点；发版前按决策 9 过渡。
- **AC11** 变异测试见测试策略，全部变红；`module-crew check quick` 通过。

## 并行边界

- 独占：`spec/crew-flow-v2.md`、`tasks/crew-flow-v2/`、`module_crew/probe.py`、`module_crew/protocol.py`、`module_crew/review.py`、`module_crew/takeover.py`、`module_crew/sources.py`、`module_crew/start.py`、`module_crew/hooks.py`、`module_crew/present.py`、`module_crew/flow.py`、`tests/test_flow_v2.py`
- 公共：`skills/`、`codex-skills/`、`README.md`、`README.en.md`、`interface.json`、`CHANGELOG.md`（发【公共变更请求】）

## 并行说明

能力图上本模块排在最后、串行；`crew-takeover-merge` 已挂起，不与它同时改 `review.py`、`merge.py`。

## 要你确认的假设

- **A1** 新流程只看 `/map --json` 的 `tier`，module-crew 不读文档里的标记行。
- **A2** 技术方案与回归合成一个交审节点「技术方案」，不另设「回归」节点。
- **A3** 第二审查者都不可用时，普通需求记「未审」放行、由回归兜底（取代 11-21「Codex 不可用就停下」）；重要需求照旧人批。
- **A4** 新模块的需求与技术方案总是分开交，不受项目 `combined` 影响。
- **A5** 多模块时需求一级文档写进现有用法草案 `spec/usage/<需求>.md`，联调回归放 `spec/usage/<需求>.regression.md`，用户只确认一次（决策 8，交 sg-coord 定）。
- **A6** 联调回归 module-crew 只提示不拦，执行与把关归 autopilot。

## 未决问题

- **Q1** 契约 v2.10：节点「技术方案」的要点固定项按决策 2 提，是否同意先向 session-protocol 提这份需求？（推荐：同意，提完经用户批准再改。）
- **Q2** 多模块布局（决策 8）：用户 C715「B」不等 sg-coord，本模块去掉范围第 7 条与 AC8，其余照做。
- **Q3** spec-guard `plan-auto-approve` 晚于本模块构建完时，新模块写完 Plan 后 `/build` 会不会因 Plan 未批准停下：推荐等它发版再开工构建新模块（本模块构建不受影响，只是试点要等）；不由模块协调代写批准标记。
- **Q4** 挂起的 `crew-takeover-merge` 剩余 Task 9～12：Task 9（Codex 最终验收不判流程文件越界）在新流程不再用 Codex 最终验收、可撤；Task 10 里「同一次 `merge run` 同步通知不重复」（问题 K）是通用缺陷，推荐另开轻任务；其余撤。由用户定。

## 文档建议

README「流程」一节加「新流程模块」：节点、谁批、何时开工；`crew-dev`、`crew-coordinator` 两份 skill 同步。项目没有文档基线。

## 变更记录

- 2026-11-24：「并行边界」独占文件由花括号写法改为逐个列出；原因：module-crew 读并行边界时把花括号路径报为 bad-path，内容不变；来源：mc-coord #22376（随 C698 批准附带的修改要求）。
- 2026-11-24：取消范围第 7 条（多模块布局）与 AC8，决策 8 的提案原文保留作参考；并行边界独占改为去掉 `module_crew/merge.py`（不再改）、加上 `module_crew/flow.py`（Plan 已批的新文件）。原因：sg-coord 对决策 8 还没有定论，用户选不等；来源：用户在 mc-coord 答复 C715「C715 B」（#22427），即 Spec Q2 的退路。
- 2026-11-27：推翻目标第 3 条「重要需求的技术方案永远人批」、决策 6 括注「已算进『重要需求永远人批』」、决策 7「重要需求本来就人批，不走到这里」与假设 A3 后半句：重要需求的技术方案改按 spec-guard 生效档位 `takeover.design`，没有可用审查者时送用户批；原因：spec-guard 0.99.0（interface 1.27，模块 sg-review-rules）不再强制重要需求人批；来源：模块 crew-review-rules-follow 的 Spec（用户批准事项 C854「C854 A」），ecosystem-lead #23377、#23442。
- 2026-11-27：推翻假设 A3 前半句「普通需求记『未审』放行、由回归兜底」与决策 7 的对应一句「普通需求记为『未审』放行、写明由回归兜底」：第二审查者都不可用时普通需求的技术方案也交用户批；原因：spec-guard 1.27（模块 sg-review-rules 第 12 条）对这种情形记 `designApproval.status = unreviewed`、由用户批；来源：模块 crew-review-gates-align 的 Spec（用户批准事项 C881「C881 A」），ecosystem-lead #23522。
