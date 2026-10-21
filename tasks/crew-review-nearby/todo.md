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

- [x] Task 9：批准核对待决问题、分三路
  - 验收：Spec 验收 7、8
  - 文件：`module_crew/review.py`、`module_crew/merge.py`、`tests/test_review_nearby.py`

- [x] Checkpoint 2（report）：完整返工循环与提请批准在三种组合下跑通（2026-10-19：单用——ReviewCase 不登记来源与审查者的批准、合并测试；不配审查者——test_sources 带收件枢纽来源批准；两者都配——test_review_nearby 返工循环、提请批准、待决问题与 test_hub_output；全量通过）

- [x] Task 10：评审节奏
  - 验收：Spec 验收 15
  - 文件：`module_crew/start.py`、`module_crew/probe.py`、`tests/test_review_nearby.py`、`tests/test_start_prepare.py`

- [x] Task 11：`merge revoke`
  - 验收：Spec 验收 12
  - 文件：`module_crew/merge.py`、`module_crew/__main__.py`、`tests/test_review_nearby.py`

- [x] Task 12：`status` 与 `sessions --json` 返工轮次
  - 验收：Spec 验收 17
  - 文件：`module_crew/failure.py`、`module_crew/probe.py`、`tests/test_review_nearby.py`

- [x] Task 13：skill、README、版本号 0.3.0
  - 验收：Spec 验收 19
  - 文件：`skills/crew-coordinator/SKILL.md`、`skills/crew-dev/SKILL.md`、`codex-skills/crew-dev/SKILL.md`、`README.md`、`tests/test_skills.py`、版本文件

- [x] Task 14：R20 退回分原因、`merge renotice`、提交钩子输出
  - 验收：Spec 验收 20、21
  - 文件：`module_crew/merge.py`、`module_crew/commits.py`、`module_crew/__main__.py`、`skills/crew-coordinator/SKILL.md`、`skills/crew-dev/SKILL.md`、`codex-skills/crew-dev/SKILL.md`、`tests/test_review_nearby.py`

- [x] Checkpoint 3（gate）：模块最终验收——全部测试全绿、21 条验收逐条对应测试、列出实际改动文件、冻结前按需求文档 R1–R20 逐项勾清单（用户 2026-10-19 批准，含 7 份 Spec 修订）

## 外部审查意见

<!-- spec-guard: external-review declined -->
用户 2026-10-19 批准 Plan 时决定不做外部复核。

- [x] Task 15（0.4.1）：评审节奏优先读 `/map --json` 的顶层 `reviewCadence`，没有时退回读文件；`status` 写明来源
  - 验收：Spec 验收 15（修订后）
  - 文件：`module_crew/start.py`、`module_crew/__main__.py`、`module_crew/review.py`（不改读法，只核对）、`tests/test_review_nearby.py`

- [x] Task 15 验收（2026-10-19 用户批准；全量 407 个测试通过；提交 9b5523a；随 0.4.1 冻结）
- [x] 修订（2026-10-21 追加，演练执行 local_7b860c90 报的缺陷）：交决策收件箱的卡片漏了审查建议——`_advice()` 只取审查结论「要点」的第一行（0.2.2 起），审查者先写总评、再写「建议1：」「建议2：」时，建议没进「注意」与「架构审查」（演练 C261 / R-kappa-2）。改为要点里有「建议N：」行时收齐全部建议原文（「；」连接、「注意」不截断），没有时照旧取第一行。复现测试 `AdviceLinesTest`（改前红）。用户 2026-10-21 选 A：本地提交，不打标签、不升级本机，和 W257 一起等 0.9.1
- [x] 修订（2026-10-22 追加，职责边界审查第 6 条）：模块协调生成的三种待决问题倾向 B 写进 Spec，三种情况各一句理由，卡片「推荐理由」带上；版本 0.9.5——超时、不同意两种用例加理由与推荐理由断言；全量 491 个测试通过
