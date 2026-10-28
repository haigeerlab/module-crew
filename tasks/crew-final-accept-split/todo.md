# Todo: crew-final-accept-split

> 依据 `tasks/crew-final-accept-split/plan.md`。

- [x] Task 1：`merge accept` 命令与 `accepted` 状态——成功、拒绝、多编号整批不写、待决问题核对、【用户答复】与【已恢复】（Spec AC1、AC3）——测试先红后绿（5 个）；待决问题核对复用 split_decisions，与 merge approve 同一段 CLI
- [x] Task 2：`merge approve` 收 `accepted`——`acceptedBy`、两段原话、不再问待决问题、`merge run` 照常合入（Spec AC2）——测试先红后绿（3 个）；交审事项关闭时 answer 里同时留 acceptance 与授权原话
- [x] Checkpoint 1（report）：两步批准能走通，相关测试与已有 merge、review 测试通过——test_final_accept 8 个与 merge_run、merge_finish、merge_pilot、review_approve、review_add、review_nearby、light_task、stage_c、pilot_fixes 全部通过（b68daf9）
- [x] Task 3：各处读取——批量与 for-hub 不列、不收同步、重交审取代、`review answer` 收 `accepted`（Spec AC4、AC5）——测试先红后绿（4 个，批量本来只取 open、加测试锁住）；改 merge.awaiting_final、review.add 取代（模块与轻任务两处）、review.answer
- [x] Task 4：阶段、状态、停滞——钩子新阶段、`sessions --json` 同值、`status` 一行、停滞不报等用户（Spec AC6）——测试先红后绿（3 个）；failure.stage_code 不用改（新阶段文字照旧落在 build，与已交审同值）；status 一行经新的 review.accepted 读出
- [x] Task 5：`merge cleanup` 拒收已接受验收的模块（Spec AC9，D2 A）——测试先红后绿；原本就因「还没有合入」退出码 3，这次改成专门的说法
- [x] Task 6：提示与卡片——`review approve`／`review answer` 新提示、最终验收卡片选项 C、Spec／Plan 卡片不变（Spec AC7、AC8，D1 A）——测试先红后绿（4 个）；卡片仍过 protocol.parse，「你该回」不变；card_fields、hub_output、review_display、contract_v26 等照常通过
- [x] Checkpoint 2（report）：命令层做完，全量测试通过——e83afe8 上全量 1148 个只有 test_autonomy_tier 一条断言旧拒绝原文而红，照实改断言后该文件通过；sync 后改码前（e4be06c）那次全量与它并行跑过一段，报 3 失败 1 错误，第二次未复现，判为两次并行运行互相干扰，Task 8 单独再跑一次全量核实
- [ ] Task 7：四份技能与两份文档改写（Spec AC10、AC11）
- [ ] Task 8：`module-crew sync` 后全量测试（Spec AC12）
- [ ] Checkpoint 3（gate）：最终验收
- [ ] 回告：ecosystem-lead（S48 的 module-crew 一侧已就位），经 mc-coord 转
