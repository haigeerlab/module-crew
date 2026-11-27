# Todo: crew-review-gates-align

> 依据 `tasks/crew-review-gates-align/plan.md`。

- [x] Task 1：`review add` 拒收缺审查记录的新流程需求（Spec 决策 3、4；AC1、AC2、AC3）——测试先红（5 个）后绿；`flow.requirement_review` 在模块 worktree 上直接跑 `/map`（不走缓存），spec-guard 低于 1.27 或没装时返回 None；`flow.requirement_gate` 只判 `missing`，读不出时照收并给提示行；`review.add` 对 Spec／接口提案节点调用；新测试 `tests/test_review_gates_align.py`（Plan 写的是扩展现有测试文件，改为一个新文件，不碰别的测试）6 个通过，新流程与交审收件 48 个通过；变异（去掉 missing 判定、改读别的目录）转红
- [x] Task 2：交用户时附审查记录与审查后的改动差异（Spec 决策 5；AC4）——测试先红（5 个）后绿；`review.requirement_diff` 在模块 worktree 上跑 reviewMark 预览（不带 --confirm），截取「Changes since the review」那一段（到标记预览、Spec digest 之前），或「nothing changed」「cannot be shown」那一行，照原话；`requirement_lines` 给「需求审查：Codex（delegate）／宿主子会话，阻断 N 条」或「没有审查者（原因：…）」加差异；批次（`review batch` 文字与 JSON 的 `requirement`）、决策收件箱交审卡、`review show C<n> --review-diff` 三处共用；老流程模块不出这一行；假 spec-guard 的预览输出在本测试文件里加前置段模拟，不改 `tests/helpers.py`；本模块 11 个通过，展示、收件箱卡片、分组与新流程 68 个通过；变异（去掉差异块）转红
- [x] Task 3：`review approve` 认出 `requirement-unreviewed`（Spec 决策 6；AC5）——测试先红后绿；`_approve` 写标记失败、spec-guard 输出以 `requirement-unreviewed` 开头时，在今天的失败行与还原说明之后加「spec-guard 拒绝：这份需求还没审过一轮…用 review answer C<n> 退回模块先审一轮，不要绕过」；还原逻辑不动（新建的文件照今天留给用户决定，测试按今天的行为断言）；其他失败输出不变；批准测试全部通过
- [x] Task 4：普通需求没有第二审查者交用户批（Spec 决策 7；AC6）——测试先红后绿；`codex_note` 删掉未审放行分支，技术方案报告 `reviewer.selection = none` 时不分档位都记 `codex-unavailable`、退出码 5、给【等待用户】草稿；普通需求写 `NORMAL_NO_REVIEWER`「本机没有可用的第二审查者，spec-guard 记为未审（unreviewed），由你批」，重要需求照旧「这是重要需求」；`test_no_reviewer_releases_unreviewed`（钉被推翻的决定）改为 `test_no_reviewer_normal_goes_to_user`；`UNREVIEWED` 只留给升级前的旧事项展示；新流程、接管与本模块测试全部通过；变异即改动前的代码（普通需求放行），新用例在改动前为红
- [x] Checkpoint 1（report）：代码就位，相关测试通过——`scripts/validate.sh --quick` 因 `module_crew/__main__.py` 对不上号退回全量，树 4c37906（提交 87d7061）上 1490 个用例全部通过，墙钟约 2488 秒
- [ ] Task 5：文档与 crew-flow-v2 变更记录（公共变更请求；AC7）
- [ ] Task 6：同步、检查与本机实测（AC8；Spec 未决 Q2）
- [ ] Checkpoint 2（gate）：最终验收
- [ ] 回告：Spec 未决 Q1 经模块协调转告 ecosystem-lead；结果记在本项
