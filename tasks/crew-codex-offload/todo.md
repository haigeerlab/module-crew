# Todo: crew-codex-offload

> 依据 `tasks/crew-codex-offload/plan.md`。

- [x] Task 1：打底——`store.KINDS` 加 `offload`、开关 `codexOffload` 与 `config set --codex-offload`、`ready` 六项条件（Spec 验收 1、3）——测试先红（没有 offload 模块）后绿；本模块 17 个、状态库与配置回归 39 个通过；`problems` 逐条列出不满足的条件供打开开关时警告
- [ ] Task 2：`offload start` 与任务说明、`parse_result`（Spec 验收 5、2）——测试先红后绿
- [ ] Task 3：`settle` 的 done 分支：勾选核对、范围核对、暂存区快检查、代提交（Spec 验收 6）——测试先红后绿
- [ ] Checkpoint 1（report）：派出与 done 代提交就位——本模块测试与相关回归测试通过
- [ ] Task 4：`settle` 的 needs-input、timeout（1.1／1.2）、认不出与【等待用户】草稿（Spec 验收 7、8、9）——测试先红后绿
- [ ] Task 5：`offload resume`、`offload start --again`（Spec 验收 7、8）——测试先红后绿
- [ ] Task 6：开工通知分叉 `review._start_todo`、`offload decline`、`offload handback`（Spec 验收 4、10、2）——测试先红后绿，关着时逐字不变
- [ ] Task 7：`offload show` 与 `--json`（Spec 验收 11）——测试先红后绿
- [ ] Checkpoint 2（report）：命令全部就位——本模块测试与相关回归测试通过
- [ ] Task 8：四份 skill、README；`module-crew sync` 后后台跑全量测试；本机 delegate 0.6.0 实测一次（Spec 验收 12、13）
- [ ] Checkpoint 3（gate）：最终验收
- [ ] 回告：完成情况经模块协调转告 ecosystem-lead
