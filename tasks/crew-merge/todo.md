# Todo: crew-merge

测试命令：`python3 -m unittest discover -s tests -v`

- [x] Task 1：`merge approve` 与 `merge queue`
  - 验收：Spec 验收 1、2
  - 验证：`python3 -m unittest discover -s tests -p test_merge_run.py -v`
  - 文件：`module_crew/merge.py`、`tests/helpers.py`、`tests/test_merge_run.py`

- [x] Task 2：合并前清单与检查命令配置
  - 验收：Spec 验收 3、4
  - 验证：同上
  - 文件：`module_crew/merge.py`、`tests/test_merge_run.py`

- [x] Task 3：合并成功路径与通知
  - 验收：Spec 验收 5
  - 验证：同上
  - 文件：`module_crew/merge.py`、`tests/test_merge_run.py`

- [x] Task 4：检查失败撤销、超时、冲突中止与退回通知
  - 验收：Spec 验收 6、7（含退回类【协调通知】）
  - 验证：同上
  - 文件：`module_crew/merge.py`、`tests/test_merge_run.py`

- [x] Checkpoint 1（report）：全部测试全绿，记下命令与结果后继续
  - 记录：`python3 -m unittest discover -s tests -v` → Ran 171 tests in 66.379s OK（2026-10-18）；任务 2～4 测试在同一文件，一并提交；发现检查命令在清单不过时已写入配置，改为清单通过后再写

- [x] Task 5：`merge cleanup`
  - 验收：Spec 验收 8
  - 验证：`python3 -m unittest discover -s tests -p test_merge_finish.py -v`
  - 文件：`module_crew/merge.py`、`tests/test_merge_finish.py`

- [x] Task 6：`merge push-plan` 与 `merge push`
  - 验收：Spec 验收 9、10
  - 验证：同上
  - 文件：`module_crew/merge.py`、`tests/test_merge_finish.py`

- [x] Task 7：命令行与协调会话 skill
  - 验收：Spec 验收 11
  - 验证：`python3 -m unittest discover -s tests -p "test_[ms]*.py" -v`
  - 文件：`module_crew/__main__.py`、`skills/crew-coordinator/SKILL.md`、`tests/test_skills.py`、`tests/test_merge_finish.py`

- [x] Checkpoint 2（gate）：模块最终验收——全部测试全绿、11 条验收标准逐条对应测试、列出实际改动文件并贴出 skill 新增一节；停下等用户确认
  - 记录：179 个测试全绿（连跑 3 次）；8 个文件 +749/−9；用户 2026-10-18 验收通过
