# Todo: crew-start

测试命令：`python3 -m unittest discover -s tests -v`

- [ ] Task 1：`start plan`
  - 验收：Spec 验收 1；验收 2 的 plan 部分
  - 验证：`python3 -m unittest discover -s tests -p test_start_plan.py -v`
  - 文件：`module_crew/start.py`、`tests/helpers.py`、`tests/test_start_plan.py`

- [ ] Task 2：`prepare` 校验
  - 验收：Spec 验收 2 的 prepare 部分、4、7
  - 验证：`python3 -m unittest discover -s tests -p test_start_prepare.py -v`
  - 文件：`module_crew/start.py`、`tests/test_start_prepare.py`

- [ ] Task 3：逐模块落地
  - 验收：Spec 验收 3、6
  - 验证：同上
  - 文件：`module_crew/start.py`、`tests/test_start_prepare.py`

- [ ] Task 4：中途失败与重跑
  - 验收：Spec 验收 5
  - 验证：同上
  - 文件：`module_crew/start.py`、`tests/test_start_prepare.py`

- [ ] Checkpoint 1（report）：全部测试全绿，记下命令与结果后继续

- [ ] Task 5：命令行与 `--json`、退出码
  - 验收：Spec「接口约定·命令」的输出与退出码
  - 验证：`python3 -m unittest discover -s tests -p "test_start_*.py" -v`
  - 文件：`module_crew/__main__.py`、`tests/test_start_plan.py`、`tests/test_start_prepare.py`

- [ ] Task 6：协调会话 skill「开工」一节
  - 验收：Spec 验收 8
  - 验证：`python3 -m unittest discover -s tests -p test_skills.py -v`
  - 文件：`skills/crew-coordinator/SKILL.md`、`tests/test_skills.py`

- [ ] Checkpoint 2（gate）：模块最终验收——全部测试全绿、8 条验收标准逐条对应测试、列出实际改动文件并贴出 skill 新增一节；停下等用户确认
