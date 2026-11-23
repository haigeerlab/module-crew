# Todo: crew-takeover-merge

> 依据 `tasks/crew-takeover-merge/plan.md`。

- [x] Checkpoint 0（gate）：依赖合入与上游发版（crew-takeover-approve、spec-guard 0.91.0／interface 1.15、delegate 接口 1.5）
- [x] Task 1：最终验收的「自动合」判定与 `review add`（Spec 决策 1；验收 1、2）
- [x] Task 2：Codex 最终验收审查（Spec 决策 2、3；验收 3、4）
- [x] Checkpoint 1（report）：判定与 Codex 审查就位（test_takeover_merge 9 项、test_takeover_approve／review_approve／review_nearby／final_accept 115 项通过）
- [x] Task 3：`merge auto` 放行加合并（Spec 决策 4、5；验收 5）
- [x] Task 4：合并第一段完成记录（Spec 决策 6；验收 6）
- [x] Checkpoint 2（report）：自动放行与合并链路就位（test_takeover_merge 15 项、test_merge_run／check_ledger 55 项通过）
- [x] Task 5：出事收窄与 Codex 不可用的回退（Spec 决策 8、9；验收 8、10）
- [x] Checkpoint 3（gate）：`merge first-stage` 字段与 autopr-design 对齐（autopr-design #22079 经 mc-coord #22080：加 repo、baseBranch、reportSha256）
- [x] Task 6：`merge first-stage` 与 `interface.json`（Spec 决策 7；验收 7）
- [x] Task 7：显示（Spec 决策 10；验收 9）
- [x] Checkpoint 4（report）：读接口与显示就位（test_takeover_merge 22 项、test_takeover_approve 通过）
- [x] Task 8：skill、文档、`module-crew sync` 后全量测试、本机实测（Spec 验收 11、12、13）
- [x] Checkpoint 5（gate）：最终验收
- [x] 回告：经模块协调转告 ecosystem-lead 与 autopr-design（2026-11-22，#22146、#22147）

## 返工：M2 停点不通过（2026-11-23，第 2 轮）

- [ ] Task 9：最终验收审查不把流程文件判为越界——给 Codex 的最终验收审查说明写明 `tasks/<模块>/` 是流程文件、勾选是规定动作；验证：只多勾了 todo 的交审不被判越界（报告问题 H）
- [ ] Task 10：第一个模块也能自动合、同步通知不重复——允许不经合并单独设完整检查命令（例如 `config set --check-command`，凭用户原话），或在草案与提示里写明第一个模块必然人合并给出设法；同一次 `merge run` 对同一模块只发一条同步基线通知（报告问题 J、K）
- [ ] Task 11：用法草案 U2 按实现改写——入口表与 U2 改为 `merge auto C<n>` 与只读 `merge first-stage --json`、合入后记 firstStage（不写 codex-approved 验收标记），写明 J 的前提；按已批准文件追加变更记录，随返工最终验收复审
- [ ] Task 12：同步 skill 与文档、`module-crew sync` 后全量测试；安装版重跑 M2 由模块协调安排
- [ ] Checkpoint 6（gate）：返工最终验收
