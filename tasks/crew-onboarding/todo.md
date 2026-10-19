# Todo: crew-onboarding

测试命令：`python3 -m unittest discover -s tests -v`

- [x] Task 1：`inbox add` 骨架
  - 验收：Spec 验收 5、6
  - 验证：`python3 -m unittest discover -s tests -p test_inbox.py -v`
  - 文件：`module_crew/inbox.py`、`module_crew/__main__.py`、`tests/helpers.py`、`tests/test_inbox.py`

- [x] Task 2：【等待用户】记账与取代
  - 验收：Spec 验收 1、2
  - 验证：同上
  - 文件：`module_crew/inbox.py`、`tests/test_inbox.py`

- [x] Task 3：等待单、关单、【已恢复】、【撤回】、重复提交
  - 验收：Spec 验收 3、4、7
  - 验证：同上
  - 文件：`module_crew/inbox.py`、`tests/test_inbox.py`

- [x] Checkpoint 1（report）：全部测试全绿，记下命令与结果后继续
  - 记录：`python3 -m unittest discover -s tests -v` → Ran 104 tests, OK（2026-10-18）；注：【已恢复】结束行全部没对上时什么都不写，重复提交也就无从判为「已记过」，会再报一次「没对上」

- [x] Task 4：`answer`
  - 验收：Spec 验收 8、9、10
  - 验证：`python3 -m unittest discover -s tests -p test_answer.py -v`
  - 文件：`module_crew/inbox.py`、`module_crew/__main__.py`、`tests/test_answer.py`

- [x] Task 5：两份 skill
  - 验收：Spec 验收 11
  - 验证：`python3 -m unittest discover -s tests -p test_skills.py -v`
  - 文件：`skills/crew-coordinator/SKILL.md`、`skills/crew-dev/SKILL.md`、`tests/test_skills.py`

- [x] Checkpoint 2（gate）：模块最终验收——全部测试全绿、11 条验收标准逐条对应测试、列出实际改动文件并贴出两份 skill 全文；停下等用户确认
  - 记录：111 个测试全绿（连跑 3 次）；9 个文件 +677/−7；两份 skill 全文已交审；用户 2026-10-18 验收通过。「等待审批」在线状态未实地核对，留第 7 关

- [x] Task（0.5.0，R21 MC-2 措辞）：三份 skill 写明已批范围内不问、不讨小许可、小步骤不送审、Plan 没列的依赖只问一次、宿主确认经模块协调抛出
  - 验收：Spec 验收 14（措辞部分）
  - 文件：三份 SKILL.md、`tests/test_skills.py`

- [x] Task（R21 MC-2 契约部分，钉 v2.2）：契约发布「类型：去会话操作」后钉新契约版本，`inbox add` 认这个类型并原样转决策收件箱
  - 验收：Spec 验收 14（契约部分）
  - 文件：`module_crew/protocol.py`、`tests/fixtures/session-protocol/`、`module_crew/inbox.py`

- [x] R21 MC-2（措辞与契约部分）验收（2026-10-19 用户批准；钉 v2.2，97 份契约样例一致，全量 417 个测试通过）
