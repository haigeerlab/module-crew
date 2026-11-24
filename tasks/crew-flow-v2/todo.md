# Todo: crew-flow-v2

> 依据 `tasks/crew-flow-v2/plan.md`。

- [x] Task 1：认新模块（Spec 决策 1；验收 1）——实现先于测试（同一次提交）；新增 `module_crew/flow.py`（`tier_of`、`tier`、`is_v2`、`full_docs`、`step_word`、`summarize`），`/map` 经 `takeover._map` 读、低于 1.15 或没有 `tier` 一律按老模块；`probe.summarize_map` 只在有新流程模块时加 `flowV2`；本模块 5 个通过，变异（`is_v2` 恒假）转红；probe 回归 30 个通过（4bf4d15）
- [x] Task 2：交审节点合法性与过渡（Spec 决策 2、3、9；验收 2、3、4）——实现先于测试；`flow.refuse`／`transition_node`，`review.add` 先按档位拒收（新模块 Plan、bug／small 技术方案、老模块技术方案），过渡写法「节点：Spec」只列 design.md、regression.md 记作 `design`；`REQUIRED_FILES`、`NODE_NAME`、`NODE_RANK`、`CARD_KIND`、`sources.NODES` 加 `design`；拒收表 5×5 逐格测；变异（去掉 Plan 拒收）3 个转红（850dfdc）
- [x] Task 3：开工判定、开工与放行通知文字（Spec 决策 4、5；验收 2、3、4）——实现先于测试；`flow.ready_to_start`（需求＋技术方案或只需求，重批已批的那份不再开工并说明）、`flow.start_todo`、`flow.after_release`；`APPROVABLE` 加 `design`，技术方案不写 spec-guard 标记；`start_basis` 记技术方案；`start.flow_v2` 让 combined 项目里新模块分开交（开工说明与批量交审两处）；给决策收件箱的卡片在契约 v2.10 前把技术方案写成类型 Spec；变异（开工仍要 Plan）转红（850dfdc）
- [x] Checkpoint 1（report）：节点与开工就位——本模块与交审、批准、分组、开工通知、显示、审查就近、路由、来源、开工计划与准备、提前开工、外包、轻任务、重开、接管、卡片、收件枢纽输出、停滞信号、出事等 20 个文件 477 个通过（跑到一半时 Task 4、5 的改动已在工作区，后半段测的是新代码）
- [x] Task 4：谁批（Spec 决策 6；验收 5）——实现先于测试；`takeover.module` 在新模块上 Spec 强制人批（「新流程：需求永远由用户确认」）、Plan 一项不再起作用，技术方案读 `takeover.design`／`designApproval`（`not-required` 为免审；字段名按草案 v1，Checkpoint 4 核对），重要需求人批、读不到写「因上游未发版而人批」；`review add` 对免审直接落地并发开工通知（「免审放行」）；变异（reviewer 不认）转红（b100141）
- [x] Task 5：交第二审查者（Spec 决策 7；验收 6）——实现先于测试；`review codex` 对技术方案给 `--profile design --backend auto --author-host <宿主>`、两份文件与 Spec，第 2 轮带 `--previous-report`；报告后端不限 codex；`selection=none` 记「未审放行」；放行记录与提示写「第二审查者放行」、同厂商加「（同厂商审查）」；返工通知不让模块跑 review-mark；两轮仍阻断交用户；变异（去掉 --previous-report）转红（0bbf516）
- [x] Checkpoint 2（report）：批准链路就位——本模块 36 个与接管、旧档位、声明范围、钩子、只读与钩子、最终验收、合并、检查账、probe、开工通知等 13 个文件 280 个通过（2dfbb49）
- [x] Task 6：最终验收按回归（Spec 决策 11；验收 7）——实现先于测试；新模块「验收结果」至少一行 `R<n>：`，装的 spec-guard 有 `regressionView`（名称按草案，Checkpoint 4 核对）时列出缺的用例、manual 不算缺；老模块照旧；变异转红（817dd20）
- [x] Task 7：显示（Spec 决策 4、10；验收 9）——实现先于测试；交审事项记 `tier`，钩子「当前」一句按它给新模块四种阶段（不在钩子里读 /map）、新模块的放行也算批准；`start plan` 把 design／regression 写成「写技术方案」「写回归」；spec-guard 接口 ≥ 1.18 时开工说明第一步补一句新流程写法；变异转红（2dfbb49）
- [x] Checkpoint 3（gate）：契约 v2.10 发版——session-protocol v2.10 于 03cabf3 合入（W705 已结）；用户答复 C709「C709 A」继续后半段
- [x] Task 8：协议认「技术方案」（Spec 决策 2、9；验收 10）——实现先于测试；`CONTRACT_VERSION` 2.10，【交审】节点表加「技术方案」（【审查结论】另用 `CONCLUSION_NODES` 不加），技术方案节点缺文件报 `missing-design-file:*`（排在 bad-file-line 之后），放行节点正则加「技术方案」并按匹配文字取代码，`WAIT_KINDS`／`REVIEW_POINTS` 加七个小项；样例复制到 `tests/fixtures/session-protocol/v2.10/`（SHA256SUMS 全过），v2.2～v2.10 全部通过（v2.10 解析 130 份）；过渡写法仍收并提示改写；卡片类型改为「技术方案」；变异（节点表去掉技术方案）3 个转红；`interface.json` 的 contract 已发【公共变更请求】#22421，回复前 test_hub_output 的 test_interface_json 红（bf0b973）
- [x] Task 9：多模块布局——按用户答复 C715「C715 B」取消：不等 sg-coord，Spec 去掉范围第 7 条与 AC8（决策 8 提案原文留作参考，变更记录已加），没有写代码；等待记录 W714 以【已恢复】关闭
- [x] Checkpoint 4（gate）：上游发版与实测（spec-guard interface 1.18）——实测：本机 spec-guard 0.94.0，interface 1.18；本仓库 /map 43 个模块 tier 全为 null（老模块不变）；临时项目里带 flow v2 行的两个模块 tier 读成 important（规则判 multi-module，写 bug 的也按 important）、step 为 regression／design，flow.summarize、step_word、refuse 照预期；本机没有 takeover.design、designApproval、regressionView（spec-guard 后续模块未发），delegate 最高 0.11.0／接口 1.6（1.7 未发）：技术方案一律人批、最终验收只查有 R<n>，照兜底交付；用户 C715「C715 B」通过本停点
- [ ] Task 10：文档（公共变更请求）、同步后全量测试、本机实测（验收 1、11）
- [ ] Checkpoint 5（gate）：最终验收
- [ ] 回告：经模块协调转告 ecosystem-lead 与 sg-coord
