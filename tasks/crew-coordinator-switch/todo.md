# Todo: crew-coordinator-switch

> 依据 `tasks/crew-coordinator-switch/plan.md`。

- [ ] Task 0：告诉总协调要改钩子与绑定（只在本地，不发版）
- [ ] Task 1：体检新增 `spec-guard-enabled`（Spec 验收 2）
- [ ] Task 2：`coordinator up`／`down`、默认上限 2、`start prepare` 衔接（Spec 验收 1、2、3、4、10）
- [ ] Task 3：钩子安静与一次性提醒（Spec 验收 5、6、7、9）
- [ ] Checkpoint 1（report）：开关与提醒就位，全量测试通过
- [ ] Task 4：`SessionEnd` 与清空交接（Spec 验收 8、9）
- [ ] Task 5：`status` 两个新段（Spec 验收 11）
- [ ] Task 6：skill、README、CHANGELOG、版本 0.10.0、全量测试（Spec 验收 12）
- [ ] Checkpoint 2（gate）：实地验证前停下问用户
- [ ] Task 7：实地 `/clear` 验证（Spec 验收 13）
- [ ] Checkpoint 3（gate）：最终验收
- [ ] 回告：完成情况发给总协调（local_d7434023）

## 外部审查意见

<!-- spec-guard: external-review declined -->
用户 2026-10-22 批准 Plan 时说「不用外部复核」。
