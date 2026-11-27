# Todo: crew-design-mark-sync

> 依据 `tasks/crew-design-mark-sync/plan.md`。

- [x] Task 1：先写失败的测试——三条落地路径（Spec 决策 1、2、3、8；AC1、AC2、AC3、AC6）——新文件 `tests/test_design_mark.py`，测试里把假 spec-guard 换成 interface 1.27 的 `reviewMark.command` 和一个记参数的 `review_mark.py`（不改 `tests/helpers.py`）；改动前 4 个红（用户批、第二审查者放行、没有审查者后用户批、需求在前），免审那条为绿（a175408）
- [x] Task 2：实现标记循环（同上）——`review._approve` 的标记循环按 `NODE_RANK` 排序；技术方案走 `_design_mark`：免审（`codex.skip`）不写，第二审查者放行（`codex.design`）写 `reviewer-approved --review <codex-note 存下的报告>`，用户批写 `approved`，升级前的旧放行事项（codex 里没有 design）不写；新用例全绿；`test_flow_v2`（39）、`test_review_approve`（10）、`test_review_mark_compat`（4）、`test_takeover_approve`（53）、`test_approve_restore`（2）、`test_reapprove_original`（2）、`test_review_gates_align`（13）全部通过，现有测试一个没改（50f47a3）
- [x] Task 3：失败与低版本兜底（Spec 决策 5、6；AC4、AC5）——补 4 个用例，不用改代码：用户批时 spec-guard 拒绝技术方案标记 → 退出码 4、首行「写批准标记失败，已停下：design-blocking…」、HEAD 不动、已跟踪文件还原、交审仍未答（新建的文件按现在的还原做法留给用户，和上一模块一样）；第二审查者放行时被拒 → codex-note 退出码 4、记 `landFailed`、提示 `review codex-fallback`、集成分支上没有 design.md；interface 1.15 写法的命令 → 不写技术方案标记、照常落地、结果里有 `DESIGN_MARK_UNSUPPORTED` 一行；`_design_mark_supported` 只认 `--target` 占位符里的 design。本模块 9 个用例全部通过
- [x] Checkpoint 1（report）：代码就位，本模块与相关测试通过——见 Task 2、3 的测试结果
- [ ] Task 4：变异检查（AC8）
- [ ] Task 5：本机 spec-guard 0.101.0 实跑（AC1、AC2 的真 designApproval）
- [ ] Task 6：文档与 crew-flow-v2 变更记录（公共变更请求；AC7）
- [ ] Task 7：同步与检查（AC8）
- [ ] Checkpoint 2（gate）：最终验收
- [ ] 回告：经模块协调告诉 ecosystem-lead 本模块已做（来源 #23580），并转告 Spec 未决 Q1、Q2；结果记在本项
