# Todo: crew-autonomy-tier

> 依据 `tasks/crew-autonomy-tier/plan.md`。

- [x] Task 1：读档位与生效档位、`tier [--json]`（Spec 验收 2、1）——测试先红（没有 tier 子命令）后绿；config 种类只允许键 main，降档记录改放 `config/main.autonomy`（不改 store.py，Spec 待补变更记录）
- [x] Task 2：`tier --preflight`（Spec 验收 3）——测试先红后绿；版本按点分整数比较，读不出版本按不满足
- [x] Checkpoint 1（report）：读档位就位——本模块 8 个测试通过
- [x] Task 3：standard 的评审节奏与声明范围（Spec 验收 4、6）——测试先红后绿；`declared.enabled` 在开关没设时看生效档位，`start.cadence_info` 在降档压到 strict 时返回 separate；声明范围、开工、评审节奏相关 4 个回归测试文件通过
- [ ] Task 4：出事降档与 `tier restore`（Spec 验收 6、7）
- [ ] Task 5：升档建议（Spec 验收 8）
- [ ] Checkpoint 2（report）：降档、恢复与建议就位
- [ ] Task 6：relaxed 的 `tier digest`（Spec 验收 5）
- [ ] Task 7：`status` 档位一段与底线测试（Spec 验收 9）
- [ ] Task 8：skill、README、`module-crew sync` 后全量测试、本机实测读档位（Spec 验收 10、11、1）
- [ ] Checkpoint 3（gate）：最终验收
- [ ] 回告：完成情况经模块协调转告 ecosystem-lead
