# Todo: crew-onboarding

测试命令：`python3 -m unittest discover -s tests -v`

- [ ] Task 1：`inbox add` 骨架
  - 验收：Spec 验收 5、6
  - 验证：`python3 -m unittest discover -s tests -p test_inbox.py -v`
  - 文件：`module_crew/inbox.py`、`module_crew/__main__.py`、`tests/helpers.py`、`tests/test_inbox.py`

- [ ] Task 2：【等待用户】记账与取代
  - 验收：Spec 验收 1、2
  - 验证：同上
  - 文件：`module_crew/inbox.py`、`tests/test_inbox.py`

- [ ] Task 3：等待单、关单、【已恢复】、【撤回】、重复提交
  - 验收：Spec 验收 3、4、7
  - 验证：同上
  - 文件：`module_crew/inbox.py`、`tests/test_inbox.py`

- [ ] Checkpoint 1（report）：全部测试全绿，记下命令与结果后继续

- [ ] Task 4：`answer`
  - 验收：Spec 验收 8、9、10
  - 验证：`python3 -m unittest discover -s tests -p test_answer.py -v`
  - 文件：`module_crew/inbox.py`、`module_crew/__main__.py`、`tests/test_answer.py`

- [ ] Task 5：两份 skill
  - 验收：Spec 验收 11
  - 验证：`python3 -m unittest discover -s tests -p test_skills.py -v`
  - 文件：`skills/crew-coordinator/SKILL.md`、`skills/crew-dev/SKILL.md`、`tests/test_skills.py`

- [ ] Checkpoint 2（gate）：模块最终验收——全部测试全绿、11 条验收标准逐条对应测试、列出实际改动文件并贴出两份 skill 全文；停下等用户确认
