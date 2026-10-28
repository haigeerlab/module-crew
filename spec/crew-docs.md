# Spec: crew-docs

> 能力图模块 `crew-docs`（排在 `crew-codex-offload` 之后，Build order 最后一个）。开会话依据：用户批准事项 C318。
> 需求来源：用户在 mc-coord 会话里确认的需求假设（只动本仓库文档；`spec/`、`tasks/` 不算对外文档；参照开源插件的通行做法；英文版命名 `README.en.md`、中英互链、英文版里其他文档链接仍指向中文；`docs/` 下现有 7 份过程记录逐份列处理方式，用户批准后才删）。
> 依赖 `crew-codex-offload`：文档按它合入后的 0.18.0 写。本 Spec 只定「写哪些文档、每份写什么、过程记录怎么处理、怎么核实」，正文在构建时写。

## 目标

module-crew 的对外文档现在都挤在一份 42KB 的 README 里：开头是「0.18.0 的变化」，各节标题带「第十版」「第六版」，命令一览和真实命令有出入的风险没人查，没有 LICENSE、英文说明、架构说明，`docs/` 里混着 7 份开发过程记录。
这个模块按 0.18.0 的完整功能把对外文档整理成开源插件的通行样子：README 只讲「这是什么、怎么装、怎么开始、去哪看更多」，中文为默认、另出英文版；使用手册、命令参考、架构说明各一份（只写中文）；按版本的内容只在 CHANGELOG；过程记录逐份决定去留。
文档里能和代码、命令输出对上的说法（命令名、参数、退出码、开关名、默认值、依赖版本），构建时逐条对照核实，并加一个文档一致性测试，以后命令变了而文档没跟上时测试会红。

## 范围

**范围内**

1. 按下面「文档清单」新增、更新或删除文件；每份的作用与大纲以本 Spec 为准。
2. README 重写（中文），新增 `README.en.md`（英文，内容与中文版对应，不逐字翻译）。
3. CHANGELOG 收下 README 里现有的「0.18.0 的变化」一节，README 不再有按版本的内容。
4. `docs/` 下 7 份过程记录按「过程记录的处理」一节逐份处理；删除只在本 Spec 批准后做（批准本 Spec 即批准该节列出的删除）。
5. 对照代码与命令输出核实文档里的事实（核实方法见决策 6）。
6. 新增文档一致性测试 `tests/test_docs.py`；`tests/test_codex_coordinator.py` 里读 README 文字的那条测试改读这些文字的新位置（决策 7）。

**范围外**

- `spec/`、`tasks/` 下的任何文件（包括其中指向 `docs/` 的链接）；能力图。
- 代码、skill（`skills/`、`codex-skills/`）、钩子、`interface.json`、插件清单（`.claude-plugin/`、`.codex-plugin/`）的描述文字——清单描述里的旧称「协调会话」记为后续事项，不在本模块改。
- 架构、使用手册、命令参考等的英文版。
- 版本号与发版（本模块不改 `plugin.json` 版本、不写新的 CHANGELOG 版本条目，见决策 4）。
- 别的仓库（session-protocol、spec-guard、agent-relay、delegate、decision-inbox）的文档。

## 假设（请逐条确认）

1. **只动本仓库的对外文档**：根目录的 README、CHANGELOG、LICENSE、CONTRIBUTING、SECURITY，和 `docs/` 下的文件；`spec/`、`tasks/` 是开发记录，不算对外文档，不改。
2. **读者是想在自己项目里用 module-crew 的人**：已经在用 Claude Code 桌面版（或 Codex 桌面版）、听说过 git worktree；不假定读者装过 spec-guard、agent-relay，也不假定读者看得到本机其他仓库（`../session-protocol`、`livesaas-integration/GLOSSARY.md`、plugin-ecosystem）。所以对外文档里不再出现只有本机才打得开的相对路径和内部仓库名；要提依赖时写它的名字与公开地址（地址见 D3）。
3. **文档写当前功能，不写演进史**：「第十版」「第六版」「0.5.2 更正」「S38」「C318」这类开发过程编号不进 README、使用手册、命令参考、架构；版本演进只在 CHANGELOG。CHANGELOG 里已有的条目原样保留，不回头改写。
4. **英文版只有 README**：`README.en.md` 里指向其他文档的链接仍指向中文文档；中英两份 README 开头互相链接（中文版写「English」，英文版写「中文」）。
5. **README 不放完整命令一览**：完整命令表移到命令参考 `docs/commands.md`，README 只列入门要用的 3～5 条并链过去。
6. **`spec/` 里指向 `docs/` 过程记录的链接不能断**：`docs/requirements-record.md` 被能力图与 20 份模块 Spec 引用、`docs/pilot-report.md` 被 6 份 Spec 与 1 个测试引用、`docs/capability-map-draft.md` 被能力图引用、`docs/spec-guard-additions.md` 被 `spec/crew-probe.md` 引用、`docs/intent/codex-offload-native.md` 被 `spec/crew-codex-offload.md` 引用。被引用的记录不挪位置（挪了就得改已批准的 Spec）。
7. **本模块不需要新依赖**：一致性测试只用 Python 标准库，和现有测试一样用 `python3 -m unittest` 跑。

## 待用户决定（D 编号）

- **D1 许可证选哪种**（仓库现在没有 LICENSE；module-crew 是 Claude Code／Codex 插件，代码全是 Python 标准库，没有第三方依赖要兼容）：
  - A：MIT——最宽松、最常见，别人可以随意用、改、闭源再发，只要保留版权声明。
  - B：Apache-2.0——同样宽松，另外写明专利授权与「改过的文件要标明」，企业用户更放心；文本较长。
  - C：先不加 LICENSE——不加就等于「保留所有权利」，别人在法律上不能用，不算真正开源。
  - 我不替你选；选 A 或 B 时版权人写 `haigeerlab`、年份 2026（不对请一并说）。
- **D2 接受外部贡献吗**（决定 CONTRIBUTING、SECURITY 写多细）：
  - A：接受 issue 和 PR——CONTRIBUTING 写开发环境、跑测试、提交信息格式（中文、`fix:`／`feat:` 前缀）、PR 流程，以及「本仓库自己用 spec-guard + module-crew 开发，大改动先开 issue 讨论」；SECURITY 写私下报告漏洞的渠道和回复预期。
  - B：只收 issue、不收 PR——CONTRIBUTING 只写怎么报问题、需要附什么；SECURITY 写报告渠道。
  - C：不接受外部贡献——不建 CONTRIBUTING；SECURITY 只留一行报告渠道（或也不建）。README 写明「暂不接受外部贡献」。
  - 选 A 或 B 时请给出报告安全问题的渠道（邮箱或 GitHub 私下报告），我不替你填邮箱。
- **D3 公开地址**：本仓库现在没有 git 远端。README 的安装步骤要写「从哪里装」，依赖要写去哪里找。请给出（或说明哪些暂不公开）：
  - module-crew 自己的公开仓库地址；
  - agent-relay、spec-guard、delegate、session-protocol 契约的公开地址（没公开的就只写名字和版本要求，不放链接）。
  - 没给地址的，安装一节先写「本地路径安装」（现在的写法），把远端安装留到地址定下来再补。

## 文档清单

| 文件 | 处理 | 作用 |
|---|---|---|
| `README.md` | 更新（重写） | 中文默认入口：是什么、为什么、前提、安装、5 分钟上手、文档导航、许可证。只写当前功能 |
| `README.en.md` | 新增 | 英文版入口，与中文版结构对应；其他文档链接指向中文版 |
| `CHANGELOG.md` | 更新 | 收下 README 现有的「0.18.0 的变化」一节作为最新条目；开头说明改成「README 只写当前功能」 |
| `docs/guide.md` | 新增 | 使用手册：术语、角色、完整流程、各项目开关、轻任务、修订模块、Codex 与换宿主、审查与决策收件箱、权限预配、出状况、已知限制 |
| `docs/commands.md` | 新增 | 命令参考：每条子命令的用途、谁在哪跑、要不要用户原话、主要参数、退出码；对照 `--help` 与代码核实 |
| `docs/architecture.md` | 新增 | 架构说明：组件、状态库、钩子、消息流、与上游插件的接口、对外出口（`sessions --json`、`interface.json`） |
| `LICENSE` | 新增（按 D1） | 许可证全文；D1 选 C 就不建 |
| `CONTRIBUTING.md` | 新增（按 D2） | 怎么报问题、怎么开发与提交；D2 选 C 就不建 |
| `SECURITY.md` | 新增（按 D2） | 安全问题怎么报告；一节概述 module-crew 的权限模型（禁止推送、删除、全局安装等）并链到使用手册的权限预配 |
| `docs/` 下 7 份过程记录 | 逐份处理 | 见下一节 |

不建的（开源插件常见但这里不值得）：`CODE_OF_CONDUCT.md`（D2 选 A 时可以加，默认不加）、issue／PR 模板（没有远端前用不上）、单独的术语表文件（术语放进使用手册第一节）、`docs/` 索引页（README 的文档导航就是索引）。

### README 大纲（中英两版相同结构）

1. 标题 + 一句话说明 + 语言切换链接 + 版本行（`0.18.0`，取自 `.claude-plugin/plugin.json`）
2. **它解决什么**：spec-guard 一次只推进一个模块；module-crew 让多个会话各在自己的 worktree 同时开发多个模块，所有批准由用户亲手给，会话中断后从状态库恢复。配一张角色与消息流的简图（文字或 mermaid）
3. **前提**：依赖表（宿主、agent-relay、spec-guard、Python 3、可选 delegate），版本要求核实后写
4. **安装**：Claude Code（插件市场清单）与 Codex 两种；信任钩子、更新后开新会话；装好后 `module-crew status` 体检
5. **上手**：升级模块协调 → `start plan`／`start prepare` 开模块 → 模块会话写 Spec 交审 → 批准 → 构建 → 最终验收 → 合并，每步一句话加一条命令，详细链到使用手册
6. **项目开关一览**：一张表（开关名、默认、作用一句话、链到手册对应节）——声明范围、检查记账、自治档位、额度外包、多模块并行
7. **文档导航**：使用手册、命令参考、架构、CHANGELOG、CONTRIBUTING、SECURITY
8. **开发**：跑测试的一条命令，链到 CONTRIBUTING
9. **许可证**：按 D1

### 使用手册 `docs/guide.md` 大纲

由现在 README 的各节搬过来、去掉版本标记、按核实结果改正，并补上 README 里没有的术语说明：

1. 术语：模块协调、模块会话、轻任务会话、集成分支、状态库、worktree、C／W／T 编号与 `#数字`、消息标签（【交审】【等待用户】等）、「用户原话」
2. 角色与边界（谁能做什么、不能做什么）
3. 一次完整流程（开工、写 Spec 与 Plan、批量批准、公共文件、合并、收尾与推送）
4. 项目开关：声明范围 `declaredScope`、检查记账 `checkLedger`、自治档位 `autonomyTier`、额度外包 `codexOffload`、并行／串行
5. 轻任务
6. 修订已完成的模块
7. Codex 模块会话；换宿主；模块协调在 Codex 上
8. 审查就近与决策收件箱
9. 权限预配与推送守门
10. 出状况时怎么办
11. 已知限制与尚未验证（现 README「尚未验证」一节，核实后保留仍然成立的条目）

### 命令参考 `docs/commands.md` 大纲

1. 用法总述：入口（插件内 `bin/module-crew` 与状态库里的固定入口）、「要用户原话」的含义（`--original`／`--original-file`）、通用退出码表
2. 按命令组逐个列（顺序同 `module-crew --help`）：`store`、`protocol`、`status`、`inbox`、`answer`、`start`、`config`、`review`、`change`、`merge`、`hook`、`source`、`wait`、`ticket`、`unqueued`、`task`、`coordinator`、`bind`、`takeover`、`suspend`、`resume`、`sessions`、`permissions`、`host-check`、`scope`、`sync`、`check`、`tier`、`offload`、`resume-kit`、`serial`。每组写：做什么、谁跑（模块协调／模块会话／轻任务会话）、在哪跑（集成 checkout／模块 worktree）、子命令与主要参数、是否要用户原话、特有退出码
3. 不写的：每个参数的完整说明以 `module-crew <命令> --help` 为准，参考里只写常用参数，并写明这一点

### 架构 `docs/architecture.md` 大纲

1. 总览图：用户、模块协调、模块会话、决策收件箱（可选）、agent-relay、spec-guard、git（集成分支与 worktree）之间的关系
2. 组件：`bin/module-crew`、`module_crew/` 各文件的职责（按文件一行）、`skills/` 与 `codex-skills/`、`hooks/hooks.json`
3. 状态库：位置（git 公共目录下 `module-crew/`）、`events.jsonl` 是事实来源、记录种类、为什么不进版本库、固定入口
4. 消息与批准：消息走 agent-relay、格式由 session-protocol 契约定（钉住版本）、「只认用户原话」的批准链、可信批准来源
5. 合并与检查：合并队列、完整检查与快检查、合并锁、退回
6. 与上游的接口：读 spec-guard 的哪些接口（`/map --json`、interface 1.1／1.10／1.11 的能力）、agent-relay、delegate 1.3；对外出口 `sessions --json`（schemaVersion 1 的字段）与 `interface.json`
7. 设计取舍（每条一两句）：只用标准库、状态库不进 git、不自动推送与远端合并、不可逆操作写禁止规则不写确认

## 过程记录的处理

| 文件 | 内容 | 被谁引用 | 处理 |
|---|---|---|---|
| `docs/requirements-record.md` | 多模块并行的需求记录（第 1～2 关结论与后续补充） | 能力图、20 份模块 Spec、1 份 todo、README | **保留原位**，开头加一行「开发过程记录，不随版本更新；现行用法见使用手册」；对外文档不再链它 |
| `docs/pilot-report.md` | 第 7 关试点报告 | 6 份 Spec、`tests/test_merge_pilot.py` 的文档字符串、README | **保留原位**，加同样的说明行；第 3、5 行的本机绝对路径改成不带用户名的写法（决策 5）；README 不再链它 |
| `docs/capability-map-draft.md` | 第 2 关能力图草案 | 能力图第 5 行 | **保留原位**，加说明行（已被 `spec/CAPABILITY-MAP.md` 取代） |
| `docs/spec-guard-additions.md` | 交给 spec-guard 负责人的新增模块清单 | `spec/crew-probe.md` 第 44 行 | **保留原位**，加说明行 |
| `docs/intent/codex-offload-native.md` | 额度外包的意图（用户 2026-10-27 确认） | `spec/crew-codex-offload.md` 与它的 plan、todo | **保留原位**，不改（现行模块的需求来源） |
| `docs/kickoff-prompts.md` | 第 3 关发给三条线的开工提示词 | 没有 | **删除**：一次性的过程文本，内容已执行完，含 4 处本机路径；git 历史里仍可查 |
| `docs/session-protocol-notes.md` | 第 2 关的契约说明草案 | 没有 | **删除**：已被 session-protocol 契约仓库取代；git 历史里仍可查 |

不新建 `docs/history/` 归档目录：被引用的记录挪进去会让已批准的 Spec 链接断掉（假设 6），没被引用的两份直接删比归档更干净。

## 关键决策与取舍（请重点审）

1. **README 瘦身、内容进使用手册**：现在 README 的绝大部分（流程、开关、轻任务、换宿主、出状况、权限预配）搬到 `docs/guide.md`，README 只保留入门所需。取舍：读者要多点一次链接；换来 README 能在一屏多一点读完、中英两版好维护。
2. **命令参考按命令组写，不复制 `--help`**：只写用途、谁跑、在哪跑、要不要原话、特有退出码与常用参数，完整参数以 `--help` 为准。取舍：不追求逐参数完整，换来不容易过时；一致性测试保证每个命令组都在参考里出现。
3. **英文版不逐字翻译**：`README.en.md` 结构与中文版一致、内容对应，用英文读者习惯的说法；术语给出中英对照一次（如 module coordinator／模块协调），命令与参数原样。
4. **不发版**：本模块只改文档与测试，不改 `plugin.json` 的版本，也不在 CHANGELOG 加新版本条目；合入后随下一个版本一起发时由发版那一步写 CHANGELOG。取舍：文档改动暂时没有版本号可指；好处是不为纯文档单独发一版。（如你希望这次就发 0.18.1，请在批准时说明，我把版本与 CHANGELOG 条目加进 Plan。）
5. **保留记录只做两种改动**：加一行说明、把 `pilot-report.md` 里带用户名的本机绝对路径改成 `~/…` 或「本机试点目录」之类的写法；其他文字一字不改。`requirements-record.md` 里的会话编号（`local_…`）不含个人信息，不改。
6. **怎么核实**：构建时逐份对照，结果写进最终验收的「验收结果」：
   - 命令：每个命令组与子命令名对照 `module-crew --help` 与 `module-crew <组> --help` 的实际输出；退出码对照代码里的返回值。
   - 开关名、默认值、配置字段：对照 `module_crew/` 里的读写代码。
   - 依赖版本要求：对照代码里的版本检查（如 spec-guard interface、delegate interface、agent-relay 主版本）。
   - 版本行：对照 `.claude-plugin/plugin.json`、`.codex-plugin/plugin.json`、`interface.json`。
   - 文档里写到的命令输出样子（如 `status` 的七项体检）：在本 worktree 实际跑一次对照。
   - 核实中发现代码与文档不一致时，**改文档、不改代码**；看起来是代码缺陷的，记进最终验收作为后续事项，不在本模块修。
7. **一致性测试**（`tests/test_docs.py`，标准库 `unittest`）：
   - `module-crew --help` 列出的每个命令组都在 `docs/commands.md` 里有一节；
   - `README.md` 与 `README.en.md` 互相链接；
   - README 两版、`docs/guide.md`、`docs/commands.md`、`docs/architecture.md`、CONTRIBUTING、SECURITY 里的相对链接都指向存在的文件；
   - 这些对外文档里没有 `../`（指到仓库外）的链接，没有 `/Users/` 开头的本机路径；
   - README 两版里没有「## 0.x 的变化」这类按版本的标题，README 的版本行与 `.claude-plugin/plugin.json` 一致。
   - `tests/test_codex_coordinator.py` 的 `test_readme` 现在断言 README 含「### 模块协调在 Codex 上」等文字，这些内容会搬进使用手册，测试改为读 `docs/guide.md`，断言的词不变（测试文件不是公共文件里的「测试资源」，是本模块直接要动的测试）。

## 项目结构（要改的文件）

- 新增：`README.en.md`、`docs/guide.md`、`docs/commands.md`、`docs/architecture.md`、`tests/test_docs.py`；按 D1、D2：`LICENSE`、`CONTRIBUTING.md`、`SECURITY.md`
- 修改：`README.md`、`CHANGELOG.md`、`docs/requirements-record.md`、`docs/pilot-report.md`、`docs/capability-map-draft.md`、`docs/spec-guard-additions.md`（后四份只加说明行，`pilot-report.md` 另改两行路径）、`tests/test_codex_coordinator.py`（`test_readme` 一处）
- 删除：`docs/kickoff-prompts.md`、`docs/session-protocol-notes.md`
- 不动：`spec/`、`tasks/`、`module_crew/`、`skills/`、`codex-skills/`、`hooks/`、插件清单、`interface.json`

## 命令

```bash
python3 -m unittest tests.test_docs -v          # 文档一致性
python3 -m unittest discover -s tests -v        # 全量（约 2000 秒，最终验收前跑）
bin/module-crew --help                          # 核实命令组
bin/module-crew <组> --help                     # 核实子命令
```

## 代码风格

- 文档正文中文为主（`README.en.md` 除外），用词按本仓库现行说法（模块协调、模块会话、轻任务会话、集成分支、状态库），句子短、先结论；命令、参数、文件路径用代码格式。
- 测试代码与注释照现有测试：英文文档字符串、标准库 `unittest`、用 `PLUGIN_ROOT` 找插件根目录。

## 测试策略

- 一致性测试（决策 7）先写、先红（新文档不存在时红），文档写好后转绿。
- 内容正确性靠决策 6 的逐项对照，不靠测试；对照结果作为验收证据。
- 全量测试在最终验收前跑一次，确认改 `test_readme` 没带坏别的。

## 边界

- **总是**：写之前先对照代码或命令输出；对外文档不放本机路径、内部仓库名、开发过程编号；删除只删本 Spec 列出的两份。
- **先问**：要改 `spec/`、`tasks/`、代码、skill、插件清单；要删或挪本 Spec 没列的文件；核实发现代码缺陷想顺手修。
- **从不**：替用户选许可证、填联系邮箱或公开地址；改 CHANGELOG 里已有条目的内容。

## 验收标准

1. 文档清单里每份「新增／更新」的文件都在，结构符合本 Spec 对应的大纲；D1、D2 的结果按用户选择落实（选 C 的不建）。
2. `README.md` 只写当前功能：没有按版本的章节、没有「第 N 版」「S<号>」「C<号>」这类过程编号；`README.en.md` 结构与之对应；两份开头互链，英文版里其他文档链接指向中文文档。
3. `CHANGELOG.md` 的最新条目是原 README 的「0.18.0 的变化」，原有条目一字未改（对照 `git diff` 只有新增行与开头说明行）。
4. `docs/commands.md` 覆盖 `module-crew --help` 列出的全部 31 个命令组，每组写明谁跑、在哪跑、要不要原话。
5. `docs/guide.md` 覆盖原 README 除「0.18.0 的变化」「命令一览」之外的每一节内容（逐节列出去向作为证据），并有术语一节。
6. `docs/architecture.md` 写出组件、状态库、消息与批准、合并与检查、上游接口与对外出口。
7. 过程记录按「过程记录的处理」一表处理：两份删除，四份加说明行，`intent/` 一份不动；`pilot-report.md` 里不再有带用户名的本机路径。`git grep` 证明 `spec/`、`tasks/` 里指向 `docs/` 的链接全部仍然指向存在的文件。
8. 决策 6 的每一类核实都有记录：对照了什么、发现几处不一致、怎么改的。
9. `python3 -m unittest tests.test_docs` 通过；全量测试通过（或与集成分支同样的已知失败，照实写）。
10. `spec/`、`tasks/`（本模块自己的除外）、代码、skill、插件清单没有改动（`git diff --stat` 对照集成分支）。

## 并行边界

本模块改 `README.md`、`CHANGELOG.md`、`docs/`、`tests/test_codex_coordinator.py`。Build order 里它是最后一个，眼下没有别的在用模块；若构建期间有别的模块或轻任务改 README、CHANGELOG（发版常改），合并时以集成分支的新内容为准把它们的新增并进新结构。

## 未决问题

- D1、D2、D3 待用户决定（见上）。
- 插件清单（`.claude-plugin/plugin.json`、`marketplace.json`）描述里仍用旧称「协调会话」：不在本模块改，最终验收时列为后续事项。

## 文档建议

本模块本身就是文档整理，README 在清单里；另无建议。

## 变更记录

（尚无）
