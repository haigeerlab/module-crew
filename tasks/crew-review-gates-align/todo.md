# Todo: crew-review-gates-align

> 依据 `tasks/crew-review-gates-align/plan.md`。

- [x] Task 1：`review add` 拒收缺审查记录的新流程需求（Spec 决策 3、4；AC1、AC2、AC3）——测试先红（5 个）后绿；`flow.requirement_review` 在模块 worktree 上直接跑 `/map`（不走缓存），spec-guard 低于 1.27 或没装时返回 None；`flow.requirement_gate` 只判 `missing`，读不出时照收并给提示行；`review.add` 对 Spec／接口提案节点调用；新测试 `tests/test_review_gates_align.py`（Plan 写的是扩展现有测试文件，改为一个新文件，不碰别的测试）6 个通过，新流程与交审收件 48 个通过；变异（去掉 missing 判定、改读别的目录）转红
- [ ] Task 2：交用户时附审查记录与审查后的改动差异（Spec 决策 5；AC4）
- [ ] Task 3：`review approve` 认出 `requirement-unreviewed`（Spec 决策 6；AC5）
- [ ] Task 4：普通需求没有第二审查者交用户批（Spec 决策 7；AC6）
- [ ] Checkpoint 1（report）：代码就位，相关测试通过
- [ ] Task 5：文档与 crew-flow-v2 变更记录（公共变更请求；AC7）
- [ ] Task 6：同步、检查与本机实测（AC8；Spec 未决 Q2）
- [ ] Checkpoint 2（gate）：最终验收
- [ ] 回告：Spec 未决 Q1 经模块协调转告 ecosystem-lead；结果记在本项
