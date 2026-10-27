# Todo: crew-shared-changes

测试命令：`python3 -m unittest discover -s tests -v`

- [x] Task 1：`change add` 与 `change list`
  - 验收：Spec 验收 1、2、3、4
  - 验证：`python3 -m unittest discover -s tests -p test_changes.py -v`
  - 文件：`module_crew/changes.py`、`tests/test_changes.py`

- [x] Task 2：`change answer`
  - 验收：Spec 验收 8
  - 验证：同上
  - 文件：`module_crew/changes.py`、`tests/test_changes.py`

- [x] Checkpoint 1（report）：全部测试全绿，记下命令与结果后继续
  - 记录：`python3 -m unittest discover -s tests -v` → Ran 154 tests in 51.698s OK（2026-10-18）；任务 1、2 测试在同一文件，一并提交

- [x] Task 3：`change land`
  - 验收：Spec 验收 5、6、7
  - 验证：同上
  - 文件：`module_crew/changes.py`、`tests/test_changes.py`

- [x] Task 4：命令行与协调会话 skill
  - 验收：Spec 验收 9
  - 验证：`python3 -m unittest discover -s tests -p "test_[cs]*.py" -v`
  - 文件：`module_crew/__main__.py`、`skills/crew-coordinator/SKILL.md`、`tests/test_skills.py`、`tests/test_changes.py`

- [x] Checkpoint 2（gate）：模块最终验收——全部测试全绿、9 条验收标准逐条对应测试、列出实际改动文件并贴出 skill 改动；停下等用户确认
  - 记录：160 个测试全绿（连跑 3 次）；6 个文件 +471/−7；用户 2026-10-18 验收通过

## 记录

- 2026-10-18 spec-guard 负责人通知 map-startable 已实现并验收（0.68.0 发版），输出与夹具一致；细节：Build order 第一个未完成模块算 in_progress，不进 startable.modules；`paths` 取较具体路径，`apps/bill/` 与 `apps/billing/` 不算重叠。
- [x] 修订（2026-10-22 追加，职责边界审查第 1 条）：提交前缀改为项目配置 `commitPrefix`，默认 `chore(crew): `，`start prepare --commit-prefix` 设定（三类提交共用 `commits.message`）——`CommitPrefixTest` 3 个（默认、空串、命令行设自定义）

## 0.17.0 修订（2026-10-27 追加，S43；用户原话「0.17.0 需求就是这四件，前提假设 A1～A5 全按推荐」）

- [x] REV-SPEC：修订 spec/crew-shared-changes.md，加入一次落地多个请求与锁文件连带保护文件提示，Spec 评审标记改为 pending 交审
  - 记录：Spec 修订 141e8fb，用户 2026-10-27 批准（C280）
- [ ] Task 5：一次落地多个公共变更请求 `land_batch`：`change land C96 C99` 把几个已批请求的文件合成一个提交；落地前先跑检查（`checkLedger` 开着跑快检查，没开跑完整检查 `checkCommand`）；任一请求不满足或检查不过就整批不提交（S43，LIVE-SAAS C96/C99）
  - 验收：Spec 验收 10、11、12、13、14
  - 验证：`python3 -m unittest tests.test_changes -v`
  - 文件：`module_crew/changes.py`、`tests/test_changes.py`
- [ ] Task 6：命令行 `change land <编号>...`、`--skip-check`、`alsoAnswers` 输出；协调会话 skill 与 README 补批量落地
  - 验收：Spec 验收 16 前半
  - 验证：`python3 -m unittest tests.test_changes tests.test_skills -v`
  - 文件：`module_crew/__main__.py`、`skills/crew-coordinator/SKILL.md`、`README.md`、`tests/test_changes.py`、`tests/test_skills.py`
- [ ] Task 7：`change add` 认出请求里有锁文件改动时，提示项目登记的保护文件可能要连带改（名单凭用户原话 `config set --protected-file` 写进运行配置；没登记只给通用提示，不猜）
  - 验收：Spec 验收 15、16 后半
  - 验证：同上
  - 文件：`module_crew/changes.py`、`module_crew/__main__.py`、`skills/crew-coordinator/SKILL.md`、`README.md`、`tests/test_changes.py`、`tests/test_skills.py`
- [ ] Checkpoint（report）：完整检查 `python3 -m unittest discover -s tests` 后台跑全绿，记下用时与测试数后继续
- [ ] Checkpoint（gate）：最终验收
