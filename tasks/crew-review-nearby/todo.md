# Todo: crew-review-nearby

测试命令：`python3 -m unittest discover -s tests -v`

- [x] Task 1：协议层（须修改、待用户决定、不同意、返工、撤销批准、多段切分、C 编号开工依据）
  - 验收：Spec 验收 2、4、6、9（协议部分）
  - 文件：`module_crew/protocol.py`、`tests/test_review_nearby.py`

- [ ] Task 2：编号对外写 `C<数字>`
  - 验收：Spec 验收 13
  - 文件：`module_crew/refs.py`、`module_crew/*.py`（对外文字）、`module_crew/__main__.py`、`tests/test_refs.py`、受影响的现有测试

- [ ] Checkpoint 1（report）：Phase 1 全绿；不登记审查者与收件枢纽时现有流程通过

- [ ] Task 3：送审与审查状态
  - 验收：Spec 验收 1、4、5
  - 文件：`module_crew/review.py`、`tests/test_review_nearby.py`

- [ ] Task 4：`review note` 多段、返工、上限、`--then-batch`
  - 验收：Spec 验收 2、3、4、9、10
  - 文件：`module_crew/review.py`、`module_crew/__main__.py`、`tests/test_review_nearby.py`

- [ ] Task 5：合批（进合批条件、D 编号、经 N 轮、摘要、要点列表、选项后果）
  - 验收：Spec 验收 3、5、6、11、14、15
  - 文件：`module_crew/review.py`、`tests/test_review_nearby.py`、`tests/test_hub_output.py`

- [ ] Task 6：批准核对待决问题、分三路
  - 验收：Spec 验收 7、8
  - 文件：`module_crew/review.py`、`module_crew/merge.py`、`tests/test_review_nearby.py`

- [ ] Checkpoint 2（report）：完整返工循环在三种组合下跑通

- [ ] Task 7：`merge revoke`
  - 验收：Spec 验收 12
  - 文件：`module_crew/merge.py`、`module_crew/__main__.py`、`tests/test_review_nearby.py`

- [ ] Task 8：`status` 与 `sessions --json` 返工轮次
  - 验收：Spec 验收 16
  - 文件：`module_crew/failure.py`、`module_crew/probe.py`、`tests/test_review_nearby.py`

- [ ] Task 9：skill 与 README
  - 验收：Spec 验收 18
  - 文件：`skills/crew-coordinator/SKILL.md`、`skills/crew-dev/SKILL.md`、`codex-skills/crew-dev/SKILL.md`、`README.md`、`tests/test_skills.py`

- [ ] Task 10：改钉契约 v2.0、版本号 0.3.0（契约定稿后）
  - 验收：Spec 验收 17、18
  - 文件：`tests/fixtures/session-protocol/v2.0/`、`module_crew/protocol.py`、`tests/test_protocol_conformance.py`、版本文件

- [ ] Checkpoint 3（gate）：模块最终验收——全部测试全绿、18 条验收逐条对应测试、列出实际改动文件

## 外部审查意见

<!-- spec-guard: external-review declined -->
用户 2026-10-19 批准 Plan 时决定不做外部复核。
