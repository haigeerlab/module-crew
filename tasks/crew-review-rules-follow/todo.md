# Todo: crew-review-rules-follow

> 依据 `tasks/crew-review-rules-follow/plan.md`。

- [x] Task 1：里程碑停点按 `blocking`（Spec 决策 1、2；AC1、AC2）——测试先红（8 个）后绿；`milestone_stop` 返回（阻塞项、警告、提示）三项，只有 `blocking is False` 给提示；`Proposal.notes` 进 `start plan` 文字（ℹ️）、`--json` 与 `prepare` 结果行，不进 `warnings`；true、缺字段、`"false"`、0、null 照旧阻塞；开工计划与准备 42 个通过；变异（改成真值判断）6 个转红
- [x] Task 2：重要需求的技术方案按档位（Spec 决策 3、4；AC3、AC4）——测试先红（4 个）后绿；`_design` 删掉 `tier == "important"` 一支，改判 `takeover.designForcedBy == "important"`（spec-guard 1.22～1.26）仍人批并显示「重要需求：技术方案由用户批」；`tests/test_flow_v2.py` 原 `test_important_design_always_user`（钉被推翻的决定）改为 `test_important_design_follows_takeover`：reviewer／human／免审／读不到四种与 normal 相同；新流程 38 个通过；变异（恢复 important 强制）4 个转红
- [x] Task 3：重要需求没有可用审查者时送用户（Spec 决策 5；AC5）——测试先红后绿；`codex_note` 在技术方案报告 `reviewer.selection = none` 且模块档位为 `important` 时不放行：记 `codex-unavailable`、退出码 5、给【等待用户】草稿（`no_reviewer_draft`：A 你来批这一版／B 装好第二审查者后重跑，`protocol.parse` 无问题）；normal 照旧未审放行（原测试不改、通过）；新流程 39 个通过；变异（去掉档位判断）转红
- [x] Checkpoint 1（report）：代码就位，相关测试通过——`scripts/validate.sh --quick` 退回全量（树 7fa8268）：1477 个用例全部通过，墙钟约 1795 秒（期间同机另有测试在跑）
- [x] Task 4：文档与 crew-flow-v2 变更记录（公共变更请求；AC6）——发【公共变更请求】#23494，模块协调记为 C871、在集成分支 636b842 落地（两份 crew-coordinator skill 的「技术方案谁批」与「里程碑停点」带 `blocking`、Codex 版补上停点一条，`spec/crew-flow-v2.md` 变更记录一行，`CHANGELOG.md`「未发版的变化」两行）；`module-crew sync` 合入（HEAD fcadc02），核对四个文件内容与请求一致
- [x] Task 5：同步、检查与本机实测（AC7）——同步后（HEAD fcadc02）`scripts/validate.sh --quick` 因 `module_crew/__main__.py` 对不上号退回全量，树 fc5dbab 上 1477 个用例全部通过（墙钟约 1741 秒）；本机实测（spec-guard 0.99.0 真装的 `hooks/map_view.py --json`，临时项目：用法草案 M1 含已完成的 a、b，另有新流程 important 模块 d）：`takeover: autopilot` 时 `milestoneStop.blocking` 为 false，`start.milestone_stop` 返回提示「按 autopilot 预设不挡开工…」、不阻塞；d 的 `takeover.design` 为 reviewer、`designForcedBy` 为 null、`designApproval` 为 not-required，`_design` 给 skip（不再强制人批）；默认档位时 `blocking` 为 true、照旧阻塞，d 的 design 为 human、`_design` 给 human；本仓库真 `/map` 的 `designForcedBy` 为 null
- [x] Checkpoint 2（gate）：最终验收
- [x] 回告：Q1～Q3 经模块协调转告 ecosystem-lead（#23517）与 sg-coord（Q3，#23518）；sg-coord #23521 回复随 spec-guard 模块 7 改 takeover.notes，ecosystem-lead #23522 转用户决定 Q1、Q2 合成一项，用户在 mc-coord 原话「合成一项，发版后排」
