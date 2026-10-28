# Todo: crew-docs

> 依据：`tasks/crew-docs/plan.md`、`spec/crew-docs.md`（C320 批准）。

- [x] Task 1：一致性测试先红（`tests/test_docs.py`；`test_readme` 改读 `docs/guide.md`）
- [x] Task 2：命令参考 `docs/commands.md`（31 个命令组，对照 `--help` 与代码）
- [ ] Task 3：使用手册前半（术语、角色、流程、项目开关）
- [ ] Task 4：使用手册后半（轻任务、修订、Codex 与换宿主、审查与决策收件箱、权限预配、出状况、已知限制）
- [ ] Checkpoint 1（report）：命令参考与使用手册就位
- [ ] Task 5：架构 `docs/architecture.md`
- [ ] Task 6：`README.md` 重写＋`CHANGELOG.md` 收下 0.18.0 一节
- [ ] Task 7：`README.en.md`
- [ ] Task 8：`LICENSE`（MIT）、`CONTRIBUTING.md`、`SECURITY.md`
- [ ] Task 9：过程记录（删两份、四份加说明行、`pilot-report.md` 路径改写）
- [ ] Checkpoint 2（report）：全部文档就位
- [ ] Task 10：sync 后全量测试、补完核实记录、越界检查
- [ ] Checkpoint 3（gate）：最终验收
- [ ] 回告：无外部来源；列出用户要做的一步（GitHub 打开私下漏洞报告）

## 核实记录

（按 Spec 决策 6 的五类填写：命令、开关与默认值、依赖版本、版本行、命令输出；另记原 README 各节去向与后续事项）

### 命令（Task 2）

- 对照：`bin/module-crew --help` 与每个命令组、子命令的 `--help`；谁能跑对照 `module_crew/__main__.py` 的 `_ANY_SESSION` 与 `_session_guard`；退出码对照 `__main__.py` 的返回值与 `crew-coordinator` skill 的说明。
- 结果：31 个命令组（其中 18 组带子命令，共 65 个子命令），`docs/commands.md` 每组一节（`test_docs` 的命令覆盖一项通过）。
- 原 README「命令一览」与实际命令的出入 11 处，都按实际命令写进参考：缺 `merge renotice`、`merge tick`、`source scope`、`review answer`、`task show`、`task cancel`；缺参数 `review show --spec-diff`、`review batch --parallel-with`、`coordinator up --short`、`permissions verify --record/--allowed/--denied`；`change land` 跳过检查的参数实际叫 `--skip-check`（README 一处仍写旧名 `--skip-quick-check`）。
- 通用退出码表（0～7）按代码整理；1 只出现在 Codex 沙箱拒绝写状态库时。
