# Todo: crew-review-batch

测试命令：`python3 -m unittest discover -s tests -v`

- [x] Task 1：`review add`
  - 验收：Spec 验收 1、2、3
  - 验证：`python3 -m unittest discover -s tests -p test_review_add.py -v`
  - 文件：`module_crew/review.py`、`tests/helpers.py`、`tests/test_review_add.py`

- [ ] Task 2：`review batch`
  - 验收：Spec 验收 4
  - 验证：同上
  - 文件：`module_crew/review.py`、`tests/test_review_add.py`

- [ ] Checkpoint 1（report）：全部测试全绿，记下命令与结果后继续

- [ ] Task 3：`review answer`
  - 验收：Spec 验收 9
  - 验证：`python3 -m unittest discover -s tests -p test_review_approve.py -v`
  - 文件：`module_crew/review.py`、`tests/test_review_approve.py`

- [ ] Task 4：命令安全校验抽出 + `review approve` 成功路径
  - 验收：Spec 验收 5、6；crew-probe 测试原样通过
  - 验证：`python3 -m unittest discover -s tests -p "test_[pr]*.py" -v`
  - 文件：`module_crew/probe.py`、`module_crew/review.py`、`tests/helpers.py`、`tests/test_review_approve.py`

- [ ] Task 5：`review approve` 的检查与中途失败
  - 验收：Spec 验收 7、8
  - 验证：`python3 -m unittest discover -s tests -p test_review_approve.py -v`
  - 文件：`module_crew/review.py`、`tests/test_review_approve.py`

- [ ] Task 6：命令行与协调会话 skill
  - 验收：Spec 验收 10
  - 验证：`python3 -m unittest discover -s tests -p "test_[rs]*.py" -v`
  - 文件：`module_crew/__main__.py`、`skills/crew-coordinator/SKILL.md`、`tests/test_skills.py`、`tests/test_review_approve.py`

- [ ] Checkpoint 2（gate）：模块最终验收——全部测试全绿、10 条验收标准逐条对应测试、列出实际改动文件并贴出 skill 改动；停下等用户确认
