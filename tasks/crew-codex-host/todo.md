# Todo: crew-codex-host

测试命令：`python3 -m unittest discover -s tests -v`

- [x] Task 1：状态库认 `codex-desktop`，协调会话仍只许 Claude
  - 验收：Spec 验收 4
  - 文件：`module_crew/store.py`、`tests/test_codex_host.py`

- [x] Task 2：`start prepare --host codex` 与开工说明 Codex 段
  - 验收：Spec 验收 1、2、3
  - 文件：`module_crew/start.py`、`module_crew/__main__.py`、`tests/test_codex_host.py`

- [x] Checkpoint 1（report）：Phase 1 全绿、Claude 开工说明逐字比较通过（test_claude_path_unchanged；test_start* 全绿，2026-10-18）

- [ ] Task 3：`module-crew host-check`
  - 验收：Spec 验收 5
  - 文件：`module_crew/hostcheck.py`、`module_crew/__main__.py`、`module_crew/start.py`（记 `pluginVersion`）、`tests/test_codex_host.py`

- [ ] Task 4：`resume-kit` 按宿主出说明、`sessions` 加 `host`
  - 验收：Spec 验收 6、7
  - 文件：`module_crew/failure.py`、`tests/test_codex_host.py`

- [ ] Task 5：`.codex-plugin/plugin.json` 与 Codex 版 crew-dev
  - 验收：Spec 验收 8
  - 文件：`.codex-plugin/plugin.json`、`codex-skills/crew-dev/SKILL.md`、`tests/test_skills.py`

- [ ] Task 6：协调会话 skill「Codex 模块会话」一节、`status` 提示、README
  - 验收：Spec 验收 9、10
  - 文件：`skills/crew-coordinator/SKILL.md`、`module_crew/probe.py`、`module_crew/__main__.py`、`README.md`、`tests/test_skills.py`

- [ ] Checkpoint 2（gate）：模块最终验收——全部测试全绿、10 条验收逐条对应测试、列出实际改动文件
