# Todo: crew-takeover-approve

> 依据 `tasks/crew-takeover-approve/plan.md`。

- [x] Task 1：autonomyTier 退役与三个开关（Spec 决策 10、11；验收 11）——测试先红（4 个失败 1 个报错）后绿；`declared.enabled` 只认显式开关，`cadence_info` 去掉降档上限分支，升档建议整段删除，`tier restore` 退出码 3 给指引，新开关 `config set --digest`（Spec 写的是 `config --digest`，实际挂在现有 `config set` 下）；`test_autonomy_tier` 改写：删 StandardTest（3 个）、StandardKickoffTest、AdviceTest（4 个）、IncidentTest 的两个 restore 用例，改 ReadTest 两个、ExternalDegradeTest 的 restore 用例、StatusTest 一个，由新文件 RetireTest 等 8 个覆盖；`incident`／`degrade` 留到 Task 6 再改
- [x] Checkpoint 1（report）：退役就位——本模块与旧档位测试 36 个通过；声明范围、开工、合并、提前开工、批量交审与批准等回归测试 182 个通过
- [ ] Checkpoint 0（gate）：上游发版（spec-guard 0.91.0／interface 1.15、delegate 接口 1.5）
- [ ] Task 2：`takeover.py` 读档位、`tier`／`--preflight`、`status` 接管一段（Spec 决策 1、2；验收 1、2）
- [ ] Task 3：显示批准方式、批量交审排除 Codex 项、批准人不同自动分开批（Spec 决策 2、8；验收 3、8）
- [ ] Checkpoint 2（report）：读档位与显示就位
- [ ] Task 4：`review codex`／`codex-note`：返工、超限、对得上（Spec 决策 3、4；验收 4、6）
- [ ] Task 5：放行落地与记账、Codex 不可用、`review approve` 的回退（Spec 决策 5、6、7；验收 5、7、10）
- [ ] Checkpoint 3（report）：Codex 放行链路就位
- [ ] Task 6：出事收窄与 `tier degrade`（Spec 决策 9、10；验收 9）
- [ ] Checkpoint 4（gate）：契约「放行」类型已发版
- [ ] Task 7：认「放行」通知、只放行 Spec 时发它（Spec 决策 12）
- [ ] Task 8：skill、README、`module-crew sync` 后全量测试、本机实测（Spec 验收 12、13、1）
- [ ] Checkpoint 5（gate）：最终验收
- [ ] 回告：经模块协调转告 ecosystem-lead 与 autopr-design
