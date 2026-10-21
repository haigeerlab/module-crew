# Todo: crew-hub-card-fields

> 依据 `tasks/crew-hub-card-fields/plan.md`。

- [x] Task 1：解析器升到 v2.3 与契约样例（Spec 验收 1）——提交 9f2ad23；v2.2 样例 97 份、v2.3 样例 101 份全过
- [x] Task 2：`source add --protocol` 与版本开关（Spec 验收 6）——提交 9b25f65
- [x] Checkpoint 1（report）：解析器与开关就位，全量测试通过（2026-10-19，445 个测试全过）
- [x] Task 3：`review batch --for-hub` 的 2.3 写法（Spec 验收 2～5）——提交 03b92f4；v2.2 写法与改前生成的 3 份夹具逐字一致；2.3 下选项 A 的「选了会怎样」与「批了会怎样」同一函数生成
- [x] Task 4：三份 skill（Spec 验收 7）——提交 0a56146
- [x] Task 5：README、版本 0.7.0、全量测试（Spec 验收 8）——提交 826b6de；全量 450 个测试通过（含旧称扫描）
- [x] Checkpoint 2（gate）：最终验收——用户 2026-10-19 批准；除契约样例外 21 个文件 +607 −40，另钉 v2.3 契约样例 206 个文件（d10ae2c..44a5919）
- [x] 回告：结果告诉 di-p0-tester（local_bbdaaaab）与契约负责人（local_a9d06942）——2026-10-19 已发会话消息；向契约负责人更正「拿能力图核对接口提案影响的模块」未做
- [x] 修订（2026-10-22 追加，职责边界审查第 12 条）：删提请批准卡片的 v2.2 写法与 card-fields 回归夹具，未写版本的 hub 按 2.4，拒绝登记 2.2；解析器与契约样例保留——删 tests/fixtures/card-fields 三份夹具与 V22UnchangedTest，改为 NoVersionTest；skill、README 同步；全量 491 个测试通过
