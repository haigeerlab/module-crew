# Todo: crew-contract-v26

> 依据 `tasks/crew-contract-v26/plan.md`。

- [x] Task 1：钉住 v2.6 夹具与解析（Spec 验收 1、2、3）——v2.6 的 115 个样例先红后绿，v2.2～v2.5 照旧；`interface.json` 的 contract 也改为 2.6（Plan 原写不改 interface.json，但 decision-inbox doctor 读的就是它）（3e45796）
- [x] Task 2：按登记版本编 C 或 D、答复两种都认、登记 2.6（Spec 验收 4、7）——测试先红后绿；没有收件箱时改编 C，test_review_nearby 四条、test_card_fields 一条旧断言跟着改（d3c5504）
- [x] Checkpoint 1（report）：解析与编号就位——相关测试通过；中途插入热修 0.11.2（用户选 A），合回 main 后全量 657 个通过
- [x] Task 3：答复块与只用交审号（Spec 验收 5）——测试先红后绿；卡片本来就只用交审号，补测试守住（b03695f）
- [x] Task 4：「验收结果」改名（Spec 验收 6）——测试先红后绿（c90a038）
- [x] Task 5：skill、README、全量测试（Spec 验收 6、7）——全量 675 个测试通过（ffc9dc9）
- [ ] Checkpoint 2（gate）：最终验收
- [ ] 回告：总协调（local_d7434023）与契约负责人（local_e1431df1）

## 外部审查意见

<!-- spec-guard: external-review declined -->
用户 2026-10-22 批准 Plan 时说「不用外部复核」。
