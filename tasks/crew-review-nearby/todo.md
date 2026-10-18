# Todo: crew-review-nearby

测试命令：`python3 -m unittest discover -s tests -v`

- [x] Task 1：协议层（须修改、待用户决定、不同意、返工、撤销批准、多段切分、C 编号开工依据）
  - 验收：Spec 验收 2、4、6、9（协议部分）
  - 文件：`module_crew/protocol.py`、`tests/test_review_nearby.py`

- [x] Task 2：编号对外写 `C<数字>`
  - 验收：Spec 验收 13
  - 文件：`module_crew/refs.py`、`module_crew/*.py`（对外文字）、`module_crew/__main__.py`、`tests/test_refs.py`、受影响的现有测试

- [x] Checkpoint 1（report）：Phase 1 全绿；不登记审查者与收件枢纽时现有流程通过（2026-10-19，320 个测试；现有测试只改了编号写法与通知 refs 的断言——refs 只放枢纽事项号，crew 批准写在依据里的 C<N>；协调会话 skill 第 167 行示例「批准 #32 #33」留到 Task 13 改成 C）

- [x] Task 3：送审与审查状态
  - 验收：Spec 验收 1、4、5
  - 文件：`module_crew/review.py`、`tests/test_review_nearby.py`

- [x] Task 4：`review note` 多段、返工、上限、`--then-batch`
  - 验收：Spec 验收 2、3、4、9、10
  - 文件：`module_crew/review.py`、`module_crew/__main__.py`、`tests/test_review_nearby.py`

- [x] Task 5：合批（进合批条件、D 编号、经 N 轮、摘要、要点列表、选项后果）
  - 验收：Spec 验收 3、5、6、11、14、15
  - 文件：`module_crew/review.py`、`tests/test_review_nearby.py`、`tests/test_hub_output.py`

- [x] Task 5 注：2026-10-19 Spec 修订后，摘要（R8）与要点截断（R7）作废，合批正文由 Task 7 重写

- [x] Task 6：钉契约 v2.1、协议字段名对齐定稿、解析登记回执与【等待用户】新字段
  - 验收：Spec 验收 18
  - 文件：`tests/fixtures/session-protocol/v2.1/`、`module_crew/protocol.py`、`module_crew/review.py`、`tests/test_protocol_conformance.py`、`tests/test_review_nearby.py`

- [x] Task 7：提请批准重写（一个模块一项、原样、原文文件、产物、待用户决定字段、批准会发生什么）
  - 验收：Spec 验收 3、5、6、10、11、14
  - 文件：`module_crew/review.py`、`module_crew/__main__.py`、`tests/test_review_nearby.py`、`tests/test_hub_output.py`、`tests/test_review_grouping.py`

- [x] Task 8：最终验收「验收标准与证据」
  - 验收：Spec 验收 16
  - 文件：`module_crew/review.py`、`tests/helpers.py`、`tests/test_review_nearby.py`

- [ ] Task 9：批准核对待决问题、分三路
  - 验收：Spec 验收 7、8
  - 文件：`module_crew/review.py`、`module_crew/merge.py`、`tests/test_review_nearby.py`

- [ ] Checkpoint 2（report）：完整返工循环与提请批准在三种组合下跑通

- [ ] Task 10：评审节奏
  - 验收：Spec 验收 15
  - 文件：`module_crew/start.py`、`module_crew/probe.py`、`tests/test_review_nearby.py`、`tests/test_start_prepare.py`

- [ ] Task 11：`merge revoke`
  - 验收：Spec 验收 12
  - 文件：`module_crew/merge.py`、`module_crew/__main__.py`、`tests/test_review_nearby.py`

- [ ] Task 12：`status` 与 `sessions --json` 返工轮次
  - 验收：Spec 验收 17
  - 文件：`module_crew/failure.py`、`module_crew/probe.py`、`tests/test_review_nearby.py`

- [ ] Task 13：skill、README、版本号 0.3.0
  - 验收：Spec 验收 19
  - 文件：`skills/crew-coordinator/SKILL.md`、`skills/crew-dev/SKILL.md`、`codex-skills/crew-dev/SKILL.md`、`README.md`、`tests/test_skills.py`、版本文件

- [ ] Checkpoint 3（gate）：模块最终验收——全部测试全绿、19 条验收逐条对应测试、列出实际改动文件

## 外部审查意见

<!-- spec-guard: external-review declined -->
用户 2026-10-19 批准 Plan 时决定不做外部复核。
