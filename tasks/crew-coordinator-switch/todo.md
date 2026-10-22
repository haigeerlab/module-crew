# Todo: crew-coordinator-switch

> 依据 `tasks/crew-coordinator-switch/plan.md`。

- [x] Task 0：告诉总协调要改钩子与绑定（只在本地，不发版）——2026-10-22 已发会话消息
- [x] Task 1：体检新增 `spec-guard-enabled`（Spec 验收 2）——测试先红后绿；夹具仓库改为带 `.agent/config.json`
- [x] Task 2：`coordinator up`／`down`、默认上限 2、`start prepare` 衔接（Spec 验收 1、2、3、4、10）——旧称扫描要求输出用「模块协调」，不写「协调会话」，提醒文案随之改
- [x] Task 3：钩子安静与一次性提醒（Spec 验收 5、6、7、9）——与 Task 4 同一次提交；这两项的实现先于测试写成（没看到先红），测试补齐后全过
- [x] Checkpoint 1（report）：开关与提醒就位——全量 523 个测试首轮 10 处失败，都是旧测试按默认上限 3 写的，按上限 2 改或显式给 3 后相关文件重跑全过；全量在 Task 6 再跑
- [x] Task 4：`SessionEnd` 与清空交接（Spec 验收 8、9）
- [x] Task 5：`status` 两个新段（Spec 验收 11）——测试先红后绿
- [x] Task 6：skill、README、CHANGELOG、版本 0.10.0、全量测试（Spec 验收 12）——全量 526 个测试通过（含旧称扫描）；三处清单版本同步为 0.10.0；未打标签、未升级本机
- [ ] Checkpoint 2（gate）：实地验证前停下问用户
- [ ] Task 7：实地 `/clear` 验证（Spec 验收 13）
- [ ] Checkpoint 3（gate）：最终验收
- [ ] 回告：完成情况发给总协调（local_d7434023）

## 外部审查意见

<!-- spec-guard: external-review declined -->
用户 2026-10-22 批准 Plan 时说「不用外部复核」。
