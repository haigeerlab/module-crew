# Todo: crew-docs

> 依据：`tasks/crew-docs/plan.md`、`spec/crew-docs.md`（C320 批准）。

- [x] Task 1：一致性测试先红（`tests/test_docs.py`；`test_readme` 改读 `docs/guide.md`）
- [x] Task 2：命令参考 `docs/commands.md`（31 个命令组，对照 `--help` 与代码）
- [x] Task 3：使用手册前半（术语、角色、流程、项目开关）
- [x] Task 4：使用手册后半（轻任务、修订、Codex 与换宿主、审查与决策收件箱、权限预配、出状况、已知限制）
- [x] Checkpoint 1（report）：命令参考与使用手册就位（`test_docs` 命令覆盖、`test_readme` 通过）
- [x] Task 5：架构 `docs/architecture.md`
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

### 原 README 各节去向（Task 3、4）

| 原 README 一节 | 去向 |
|---|---|
| 开头说明 | README「它解决什么」（Task 6） |
| 0.18.0 的变化 | CHANGELOG 最新条目（Task 6） |
| 前提、安装 | README「前提」「安装」（Task 6） |
| 角色 | 手册「角色与边界」；状态库一句进「术语」 |
| 一次完整流程 | 手册「一次完整流程」（补第 0 步升级模块协调、检查时限、提交前缀；声明范围细节挪到「项目开关」） |
| 检查记账、自治档位、额度外包 | 手册「项目开关」三小节 |
| 轻任务、修订已完成的模块、Codex 模块会话、换宿主、模块协调在 Codex 上 | 手册同名各节 |
| 出状况时怎么办 | 手册同名一节（补 `merge renotice`、`merge record`、写类 git 超时三行；「想收手」挪到「并行与串行」；升级后要做的挪到表后一段） |
| 审查就近与决策收件箱 | 手册同名一节（术语表来源一行删去：外部读者看不到；「验收标准与证据」改为契约 v2.6 的「验收结果」） |
| 命令一览 | 命令参考 `docs/commands.md` |
| 开发 | README「开发」与 CONTRIBUTING（Task 6、8） |
| 权限预配 | 手册「权限预配」（重排为放行／禁止／不写规则三类加步骤；版本更正的历史说明删去） |
| 尚未验证 | 手册「已知限制与尚未验证」 |

### 「尚未验证」逐条（Task 4）

- `gh` 开 PR：仍成立（本仓库没有远端，没跑过），保留。
- 放行规则是否减少弹窗：没有新证据，保留。
- 钩子按会话认身份、没看过注入文字：**删去，挪进已验证**。依据：本会话（Claude 桌面版，`module-crew bind mc-crew-docs` 之后）收到钩子注入的「module-crew：你是模块 crew-docs 的模块会话……」与命令入口一行。
- 桌面版退出重开后会话 id：只补「`/clear` 不变」（记忆里 2026-10 的实测），整个退出重开仍没测，保留。
- Codex 固定入口：仍成立，去掉版本号保留。
- 第十版四个开关、外包只测两种情形：仍成立，去掉「第十版」「第 2 轮」「LIVE-SAAS 下一轮」字样保留。
- 模块协调在 Codex 上：仍成立，保留。

### 架构的核对（Task 5）

- 组件表：逐个读 `module_crew/` 32 个文件的模块说明与 `hooks/hooks.json`、`bin/module-crew`。
- 状态库：记录种类对照 `store.KINDS`（11 种）、编号种类对照 `store.NUMBERED`；子目录对照实际状态库目录与代码里的路径（`originals/`、`merge-output/`、`handover-guide/`、`tmp/`、`bodies/`、`meta.json`）。
- `sessions --json`：在本 worktree 实跑，顶层两项、每个会话 20 个字段，与文档一致。
- 上游接口：agent-relay 主版本 2（`probe.RELAY_MAJOR`）、spec-guard 1.1 起（`probe.PLANNING_MINOR`）、delegate 1.3（`offload.py` 的版本判断）、契约 2.6（`protocol.CONTRACT_VERSION`、`interface.json`）。
- 后续事项（不在本模块改）：`module_crew/protocol.py` 的模块说明仍写「session-protocol v2.4」，实际钉住 2.6。
