# Todo: crew-hub-bridge

测试命令：`python3 -m unittest discover -s tests -v`

- [ ] Task 1：来源白名单与 `sources.check`
  - 验收：Spec 验收 1；验收 3 的校验部分
  - 文件：`module_crew/sources.py`、`module_crew/__main__.py`、`tests/test_sources.py`

- [ ] Task 2：批准入口接来源、`source map`
  - 验收：Spec 验收 2、3、4
  - 文件：`module_crew/__main__.py`、`review.py`、`merge.py`、`start.py`、`changes.py`、`failure.py`、`inbox.py`、`hooks.py`、`sources.py`、`tests/test_sources.py`

- [ ] Task 3：`review note` 与 batch 审查行
  - 验收：Spec 验收 6
  - 文件：`module_crew/review.py`、`module_crew/__main__.py`、`tests/test_hub_output.py`

- [ ] Task 4：`review batch --for-hub`
  - 验收：Spec 验收 7
  - 文件：`module_crew/review.py`、`module_crew/__main__.py`、`tests/test_hub_output.py`

- [ ] Checkpoint 1（report）：全部测试全绿，记下命令与结果后继续

- [ ] Task 5：`sessions --json` 契约与 `interface.json`
  - 验收：Spec 验收 8、9
  - 文件：`module_crew/failure.py`、`module_crew/__main__.py`、`interface.json`、`tests/test_hub_output.py`、`tests/test_failure.py`

- [ ] Task 6：两份 skill 与 README
  - 验收：Spec 验收 11
  - 文件：`skills/crew-coordinator/SKILL.md`、`skills/crew-dev/SKILL.md`、`tests/test_skills.py`、`README.md`

- [ ] Checkpoint 2（gate）：v1.6 前的阶段验收——全部测试全绿、验收 1–4、6–9、11 逐条对应测试、列出实际改动文件；停下等用户确认

- [ ] Task 7：改钉 v1.6、hub 来源对照、lead 来源（v1.6 发版后）
  - 验收：Spec 验收 3、5

- [ ] Task 8：转交枢纽答复与【已恢复】、crew-dev 核对（v1.6 发版后）
  - 验收：Spec 验收 10

- [ ] Checkpoint 3（gate）：模块最终验收；停下等用户确认
