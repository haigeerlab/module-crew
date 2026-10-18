# Todo: crew-host-permissions

测试命令：`python3 -m unittest discover -s tests -v`

- [ ] Task 1：`permissions plan`（只读）
  - 验收：Spec 验收 1
  - 文件：`module_crew/permissions.py`、`module_crew/__main__.py`、`tests/test_permissions.py`

- [ ] Task 2：`permissions apply`／`remove`（Claude 规则）
  - 验收：Spec 验收 2、3、9（Claude 部分）
  - 文件：`module_crew/permissions.py`、`module_crew/__main__.py`、`tests/test_permissions.py`

- [ ] Task 3：Codex 规则文件与信任提示
  - 验收：Spec 验收 4、9（Codex 部分）
  - 文件：`module_crew/permissions.py`、`tests/test_permissions.py`

- [ ] Checkpoint 1（report）：三种 checkout 下 plan／apply／remove 跑通，全量测试通过

- [ ] Task 4：pre-push 钩子与放行凭证
  - 验收：Spec 验收 5、6、9（钩子部分）
  - 文件：`module_crew/prepush.py`、`module_crew/permissions.py`、`module_crew/merge.py`、`tests/test_prepush.py`

- [ ] Task 5：prepare 跟随、实测清单与记录、status 显示
  - 验收：Spec 验收 7、8
  - 文件：`module_crew/start.py`、`module_crew/permissions.py`、`module_crew/__main__.py`、`tests/test_permissions.py`

- [ ] Task 6：skill 与 README
  - 验收：Spec 验收 10
  - 文件：`skills/crew-coordinator/SKILL.md`、`skills/crew-dev/SKILL.md`、`codex-skills/crew-dev/SKILL.md`、`README.md`、`tests/test_skills.py`

- [ ] Checkpoint 2（gate）：模块最终验收——全量测试全绿（验收 12）、验收逐条对应证据、验收 11 实地结果或「宿主未实测」、改动文件清单与提交号
