# Todo: crew-spec-ahead

> 依据 `tasks/crew-spec-ahead/plan.md`。

- [x] Task 1：实测 spec-guard 0.85.2 对 `not_ready` 模块写批准标记与显示阶段（Spec 未决问题）——临时仓库能力图 a → b：b 无 Spec 时 `/map` 为 `not_ready`、`missingDeps=[a]`；`review_mark.py` 给 b 写 Spec、Plan approved 均退出码 0；有 Spec 后 b 显示 `in_progress`、`missingDeps` 为空，所以依赖就位按 depends-on 自算、不靠 `missingDeps`（与 Plan 一致）
- [x] Task 2：`start prepare` 认出提前开工、登记 `specAhead`、开工批准事项与输出行（Spec 验收 1、3、4）——测试先红后绿（test_spec_ahead 7 个）；store 校验 `specAhead`、`kickoff`；test_start_prepare 里原先用 not_ready 的 e 作「不在可开工列表」的例子改为能力图外的 x；test_st* 93 个照常通过
- [x] Task 3：`declaredScope` 打开时的两处放宽（Spec 验收 5、6）——测试先红后绿（3 个：开关关／开同批开 b、e，b 在用时开 e，两个普通模块有依赖照旧挡）；test_declared_scope 照常通过（38cdf80）
- [x] Task 4：开工说明限定段，Claude 与 Codex 宿主（Spec 验收 2）——测试先红后绿（2 个：两行限定的位置、去掉后与普通开工说明逐行一致、Codex 宿主同样带）（38cdf80）
- [x] Checkpoint 1（report）：开会话这半段走通，相关测试通过——test_spec_ahead、test_st*（93 个）、test_codex*、test_reopen*、test_declared_scope 全部通过
- [x] Task 5：`deps_ready` 与 `review approve` 的开工通知闸（Spec 验收 7、8）——测试先红后绿（3 个）；函数名实际为 `start.deps_missing`（返回未就位的依赖，Plan 写的 `deps_ready` 同义）；依赖已就位直接发开工通知时会话登记记 `kickoff`（38cdf80）
- [x] Task 6：`start kickoff` 命令（Spec 验收 9 拒绝部分、11、12）——测试先红后绿（5 个：依赖未就位、Plan 未批、原话为空、普通模块、已发过各退出码 3 且状态库不变；成功时事项、通知、kickoff；外包条件不满足不发；CLI）（38cdf80）
- [x] Task 7：`status` 与 `merge run` 的提示（Spec 验收 9 提示部分、10）——测试先红后绿（3 个）；`status --json` 的 `store.specAhead` 另带 `session`、`planApproved`、`dependsOn` 三个辅助字段（38cdf80）
- [x] Checkpoint 2（report）：命令层做完，全量测试通过——见 Task 9
- [x] Task 8：文档与技能（Spec 验收 13）——断言先红后绿（DocsTest 3 个）；test_skills、test_docs、test_readme_hosts 通过；test_glossary 拦下手册里「交审批准」含旧称「审批」，改为「交审、由用户批准」后通过（6606d50）
- [x] Task 9：`module-crew sync` 后全量测试（Spec 验收 14）——sync 显示已包含 main 1d1c8a6；3cefd91 上全量 1260 个测试全部通过（1604 秒）
- [x] Checkpoint 3（gate）：最终验收
- [ ] 回告：mc-coord（转用户）live-saas-backoffice 可凭原话提前开依赖未完成的模块
