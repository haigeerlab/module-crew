# Todo: crew-docs

> 依据：`tasks/crew-docs/plan.md`、`spec/crew-docs.md`（C320 批准）。

- [x] Task 1：一致性测试先红（`tests/test_docs.py`；`test_readme` 改读 `docs/guide.md`）
- [x] Task 2：命令参考 `docs/commands.md`（31 个命令组，对照 `--help` 与代码）
- [x] Task 3：使用手册前半（术语、角色、流程、项目开关）
- [x] Task 4：使用手册后半（轻任务、修订、Codex 与换宿主、审查与决策收件箱、权限预配、出状况、已知限制）
- [x] Checkpoint 1（report）：命令参考与使用手册就位（`test_docs` 命令覆盖、`test_readme` 通过）
- [x] Task 5：架构 `docs/architecture.md`
- [x] Task 6：`README.md` 重写＋`CHANGELOG.md` 收下 0.18.0 一节
- [x] Task 7：`README.en.md`
- [x] Task 8：`LICENSE`（MIT）、`CONTRIBUTING.md`、`SECURITY.md`
- [x] Task 9：过程记录（删两份、四份加说明行、`pilot-report.md` 路径改写）
- [x] Checkpoint 2（report）：全部文档就位（`tests.test_docs` 6 项通过）
- [x] Task 10：sync 后全量测试、补完核实记录、越界检查
- [x] Checkpoint 3（gate）：最终验收
- [x] 回告：无外部来源；列出用户要做的一步（GitHub 打开私下漏洞报告）——无外部来源需回告；私下漏洞报告已于 2026-10-28 打开（模块协调按用户原话勾选）

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

### README 与 CHANGELOG（Task 6）

- 版本行：`.claude-plugin/plugin.json`、`.codex-plugin/plugin.json`、`interface.json` 都是 0.18.0，契约 2.6。
- 依赖版本：agent-relay 主版本 2（`probe.RELAY_MAJOR`）、spec-guard 0.68.0／接口 1.1（`probe.PLANNING_MINOR`，0.68.0 写在 probe 的提示里）与 0.85.0／接口 1.11（`autonomy.py` 的版本检查）、delegate 接口 1.3（`offload.py`）。Python：`module_crew/` 用了 `Path.is_relative_to`（3.9 起），本机测试在 3.10.7，README 写「开发与测试用 3.10」，不写没测过的最低版本。
- 安装写法：对照 Claude Code 官方文档（code.claude.com/docs/en/plugins/install）——`claude plugin marketplace add` 接受 GitHub `owner/repo` 简写与本地路径，`claude plugin install <插件>@<市场名>`；市场名取 `.claude-plugin/marketplace.json` 的 `module-crew-local`。
- 地址按 C320-3：module-crew `github.com/haigeerlab/module-crew`（预定，仓库还没建）；agent-relay、spec-guard-plugin、delegate-plugin 在 `github.com/haigeerlab/` 下；session-protocol 未公开，只写名字和 v2.6。
- CHANGELOG：`git diff` 只删了开头说明一行、加了新说明与 0.18.0 一节（12 行新增、1 行删除），原有条目没动。
- 后续事项（不在本模块改）：从 GitHub 装时市场名仍叫 `module-crew-local`，名字里的「local」对远端安装会让人困惑，改名要动插件清单。

### README.en.md（Task 7）

- 两份 README 都是 8 个二级标题、一一对应；英文版里使用手册、命令参考、架构、CHANGELOG 的链接都指向中文文件，并在开头一句说明其余文档是中文。

### LICENSE、CONTRIBUTING、SECURITY（Task 8）

- LICENSE：MIT 标准全文，Copyright (c) 2026 haigeerlab（C320-1）。
- CONTRIBUTING：按 C320-2 A 收 issue 和 PR；提交前缀照本仓库最近 40 个提交的习惯（`docs`、`feat`、`fix`、`test`、`chore` 加范围）；全量测试时长按 README 原有的约 2000 秒写成「约半小时」。
- SECURITY：渠道是 GitHub 私下漏洞报告（C320-2）；没写回复时限、支持哪些版本这类用户没定的承诺。
- 用户要做的一步：仓库建好后在仓库设置里打开私下漏洞报告（Private vulnerability reporting），否则 Security 页没有「Report a vulnerability」入口。

### 过程记录（Task 9）

- 删除：`docs/kickoff-prompts.md`（52 行）、`docs/session-protocol-notes.md`（46 行）。
- 四份加说明行（标题下一行引用块）：`requirements-record.md`、`pilot-report.md`、`capability-map-draft.md`、`spec-guard-additions.md`；`pilot-report.md` 另把两处 `~/Documents/haigeerlab/` 改成 `~/Documents/haigeerlab/`。`git diff --stat`：4 个文件 10 行新增、2 行删除。
- 链接核对：`git grep` 取 `spec/`、`tasks/`、`tests/`、`module_crew/`、两套 skill 里所有 `docs/…md` 路径逐个看在不在。不在的三类，都不是本模块弄断的：decision-inbox 仓库自己的 `docs/host-differences.md`（3 份 Spec 引用别的仓库）；测试与契约夹具里的假路径（`docs/x.md`、`docs/acceptance/crew-store.md` 等）；本模块自己的 Spec 与 Plan 里点名要删的两份。
- `git grep '/Users/'` 在 `docs/`、两份 README、CONTRIBUTING、SECURITY 里没有结果。

### 全量测试与越界检查（Task 10）

- `module-crew sync`：已包含集成分支 main c66645e。
- 第一次全量（1a135c2）：1123 个，6 项没过——Plan 只预计到 `test_readme` 读 README，实际还有 `test_handover_docs`（2 项）、`test_declared_scope`、`test_reopen_module` 读的 README 章节已搬进使用手册，`test_readme_hosts` 要求 README 宿主一行写 `coordinator handover`，`test_glossary` 查出 README 一处旧称「审核」。
- 修法（f6eb7e5）：三个测试改读 `docs/guide.md`，断言词不变，只有 `test_reopen_module` 的标题断言去掉「（第九版）」（对外文档不带版本标记，Spec 假设 3）；`test_glossary` 的扫描范围从 README 扩到 guide、commands、architecture（原 README 的内容在那里），顺带改掉三处旧称；README 两版宿主一行补换宿主。
- 第二次全量（f6eb7e5）：`python3 -m unittest discover -s tests` 1123 个全部通过，1520 秒。
- 越界检查：相对集成分支 c66645e 改 22 个文件。比 Plan「影响面」多 4 个测试文件（`test_declared_scope.py`、`test_glossary.py`、`test_handover_docs.py`、`test_reopen_module.py`，各改 1～2 行，原因见上）；其余与 Plan 一致。没碰 `spec/`、其他模块的 `tasks/`、代码、skill、钩子、插件清单、`interface.json`、版本号。
