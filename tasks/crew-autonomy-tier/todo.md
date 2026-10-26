# Todo: crew-autonomy-tier

> 依据 `tasks/crew-autonomy-tier/plan.md`。

- [x] Task 1：读档位与生效档位、`tier [--json]`（Spec 验收 2、1）——测试先红（没有 tier 子命令）后绿；config 种类只允许键 main，降档记录改放 `config/main.autonomy`（不改 store.py，Spec 已补变更记录）
- [x] Task 2：`tier --preflight`（Spec 验收 3）——测试先红后绿；版本按点分整数比较，读不出版本按不满足
- [x] Checkpoint 1（report）：读档位就位——本模块 8 个测试通过
- [x] Task 3：standard 的评审节奏与声明范围（Spec 验收 4、6）——测试先红后绿；`declared.enabled` 在开关没设时看生效档位，`start.cadence_info` 在降档压到 strict 时返回 separate；声明范围、开工、评审节奏相关 4 个回归测试文件通过
- [x] Task 4：出事降档与 `tier restore`（Spec 验收 6、7）——挂钩先于测试写成，测试一次通过；临时去掉 merge.py、review.py 的挂钩后相关测试转红，确认测到了挂钩；基线新失败另用检查账测试夹具验证
- [x] Task 5：升档建议（Spec 验收 8）——实现先于测试；去掉 merge.py 的建议行后合入测试转红；`merge run` 只主动推一次，`tier`／`status` 照样显示（Spec 已补变更记录）
- [x] Checkpoint 2（report）：降档、恢复与建议就位——本模块测试与合并、返工、检查账、后台检查、轻任务等 6 个回归测试文件通过
- [x] Task 6：relaxed 的 `tier digest`（Spec 验收 5）——测试先红后绿；`module-crew sync` 不记账，汇总里没有它的结果，不经队列的提交按记下的顶端去重（Spec 已补变更记录）
- [x] Task 7：`status` 档位一段与底线测试（Spec 验收 9）——实现先于测试，测试一次通过；档位没设时 `store.autonomy` 为 null、文本不出现档位
- [x] Task 8：skill、README、`module-crew sync` 后全量测试、本机实测读档位（Spec 验收 10、11、1）——四份 skill 各加「自治档位」一节、README 加一节与 tier 命令；sync 后集成分支仍是 6878f41，全量测试 1012 个全过（2361 秒）；本机 spec-guard 0.85.0 实测读档位三种情况、preflight 退出码 0；中途一次批量修改误把测试内容写进 Spec，已从集成分支恢复并重做修订（f3f4cd9）
- [ ] Checkpoint 3（gate）：最终验收
- [ ] 回告：完成情况经模块协调转告 ecosystem-lead
