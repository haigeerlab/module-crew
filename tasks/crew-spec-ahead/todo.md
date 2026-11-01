# Todo: crew-spec-ahead

> 依据 `tasks/crew-spec-ahead/plan.md`。

- [x] Task 1：实测 spec-guard 0.85.2 对 `not_ready` 模块写批准标记与显示阶段（Spec 未决问题）——临时仓库能力图 a → b：b 无 Spec 时 `/map` 为 `not_ready`、`missingDeps=[a]`；`review_mark.py` 给 b 写 Spec、Plan approved 均退出码 0；有 Spec 后 b 显示 `in_progress`、`missingDeps` 为空，所以依赖就位按 depends-on 自算、不靠 `missingDeps`（与 Plan 一致）
- [x] Task 2：`start prepare` 认出提前开工、登记 `specAhead`、开工批准事项与输出行（Spec 验收 1、3、4）——测试先红后绿（test_spec_ahead 7 个）；store 校验 `specAhead`、`kickoff`；test_start_prepare 里原先用 not_ready 的 e 作「不在可开工列表」的例子改为能力图外的 x；test_st* 93 个照常通过
- [ ] Task 3：`declaredScope` 打开时的两处放宽（Spec 验收 5、6）
- [ ] Task 4：开工说明限定段，Claude 与 Codex 宿主（Spec 验收 2）
- [ ] Checkpoint 1（report）：开会话这半段走通，相关测试通过
- [ ] Task 5：`deps_ready` 与 `review approve` 的开工通知闸（Spec 验收 7、8）
- [ ] Task 6：`start kickoff` 命令（Spec 验收 9 拒绝部分、11、12）
- [ ] Task 7：`status` 与 `merge run` 的提示（Spec 验收 9 提示部分、10）
- [ ] Checkpoint 2（report）：命令层做完，全量测试通过
- [ ] Task 8：文档与技能（Spec 验收 13）
- [ ] Task 9：`module-crew sync` 后全量测试（Spec 验收 14）
- [ ] Checkpoint 3（gate）：最终验收
- [ ] 回告：mc-coord（转用户）live-saas-backoffice 可凭原话提前开依赖未完成的模块
