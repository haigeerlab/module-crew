# Todo: crew-review-rules-follow

> 依据 `tasks/crew-review-rules-follow/plan.md`。

- [x] Task 1：里程碑停点按 `blocking`（Spec 决策 1、2；AC1、AC2）——测试先红（8 个）后绿；`milestone_stop` 返回（阻塞项、警告、提示）三项，只有 `blocking is False` 给提示；`Proposal.notes` 进 `start plan` 文字（ℹ️）、`--json` 与 `prepare` 结果行，不进 `warnings`；true、缺字段、`"false"`、0、null 照旧阻塞；开工计划与准备 42 个通过；变异（改成真值判断）6 个转红
- [x] Task 2：重要需求的技术方案按档位（Spec 决策 3、4；AC3、AC4）——测试先红（4 个）后绿；`_design` 删掉 `tier == "important"` 一支，改判 `takeover.designForcedBy == "important"`（spec-guard 1.22～1.26）仍人批并显示「重要需求：技术方案由用户批」；`tests/test_flow_v2.py` 原 `test_important_design_always_user`（钉被推翻的决定）改为 `test_important_design_follows_takeover`：reviewer／human／免审／读不到四种与 normal 相同；新流程 38 个通过；变异（恢复 important 强制）4 个转红
- [x] Task 3：重要需求没有可用审查者时送用户（Spec 决策 5；AC5）——测试先红后绿；`codex_note` 在技术方案报告 `reviewer.selection = none` 且模块档位为 `important` 时不放行：记 `codex-unavailable`、退出码 5、给【等待用户】草稿（`no_reviewer_draft`：A 你来批这一版／B 装好第二审查者后重跑，`protocol.parse` 无问题）；normal 照旧未审放行（原测试不改、通过）；新流程 39 个通过；变异（去掉档位判断）转红
- [x] Checkpoint 1（report）：代码就位，相关测试通过——`scripts/validate.sh --quick` 退回全量（树 7fa8268）：1477 个用例全部通过，墙钟约 1795 秒（期间同机另有测试在跑）
- [ ] Task 4：文档与 crew-flow-v2 变更记录（公共变更请求；AC6）
- [ ] Task 5：同步、检查与本机实测（AC7）
- [ ] Checkpoint 2（gate）：最终验收
- [ ] 回告：Q1～Q3 经模块协调转告 ecosystem-lead 与 sg-coord
