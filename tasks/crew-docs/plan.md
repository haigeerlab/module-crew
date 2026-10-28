# Implementation Plan: crew-docs

<!-- spec-guard: review approved -->

> 依据：`spec/crew-docs.md`（用户 2026-10-28 批准，事项 C320「C320 A」，集成分支提交 a21ca10）。任务清单：`tasks/crew-docs/todo.md`。
> 待决问题的答复（同一条答复）：D1 → MIT，版权人 haigeerlab，2026（C320-1 A）；D2 → 收 issue 和 PR，安全问题走 GitHub 私下报告（C320-2 A）；
> D3 → module-crew 预定 `github.com/haigeerlab/module-crew`，agent-relay、spec-guard-plugin、delegate-plugin 都在 `github.com/haigeerlab/` 下，session-protocol 未公开、只写名字和版本（C320-3）。

## Overview

先写文档一致性测试并看到它红，再按「先事实、后入口」的顺序写：命令参考 → 使用手册 → 架构，最后写 README（中文、英文）、CHANGELOG、LICENSE／CONTRIBUTING／SECURITY，处理过程记录，sync 后跑全量测试。
每份文档写之前先对照代码与命令输出取事实（Spec 决策 6），对照结果按类记进 todo 末尾的「核实记录」，最终验收照它写「验收结果」。只改文档与两个测试文件，在本模块分支本地提交；不推送、不发版。

## Architecture Decisions

- **事实先于文字**：每个文档任务的第一步是取事实——`bin/module-crew --help` 与每个命令组的 `--help`、`module_crew/` 里的退出码与开关读写、版本检查常量、三份版本文件、`status` 的实际输出；不从现在的 README 抄说法再假定它对。发现文档与代码不一致时改文档，像代码缺陷的记进核实记录的「后续事项」，不改代码（Spec 决策 6）。
- **一致性测试 `tests/test_docs.py`**：标准库 `unittest`，插件根目录取法同现有测试（`handover.PLUGIN_ROOT`）；命令组列表用 `subprocess` 跑 `bin/module-crew --help`，从 `{a,b,…}` 一行解析，不在测试里写死 31 个名字。检查项照 Spec 决策 7 五条。
- **`test_readme` 只换读取的文件**：`tests/test_codex_coordinator.py` 的 `test_readme` 改读 `docs/guide.md`，断言的词一个不改；其中「`module-crew merge run --detach / merge result`」原是命令一览里的一行，命令一览移到 `docs/commands.md`，所以把使用手册「模块协调在 Codex 上」一节写成包含这串原文（引用命令参考的那一行），不改断言。
- **README 原有内容的去向表**：写使用手册时逐节记「原 README 第几节 → 新文件哪一节」，作为验收 5 的证据，放在 todo 的核实记录里，不进对外文档。
- **英文版**：`README.en.md` 在中文 README 定稿后写，结构逐节对应；术语首次出现给中英对照；其他文档链接指向中文文件。
- **安装写法按 D3**：Claude Code 从 `github.com/haigeerlab/module-crew` 加插件市场（写之前用 Claude Code 官方文档核实 `claude plugin marketplace add` 对 GitHub 仓库的写法），另保留本地路径安装；依赖表里 agent-relay、spec-guard、delegate 链到 `github.com/haigeerlab/agent-relay`、`…/spec-guard-plugin`、`…/delegate-plugin`，session-protocol 只写名字与钉住的版本 v2.6，不放链接。仓库还没建（「预定」），README 不写 star、CI 之类的徽章。
- **SECURITY 按 D2**：报告渠道写 GitHub 的私下漏洞报告（仓库 Security 页「Report a vulnerability」）；这个功能要仓库管理员在设置里打开，最终验收时作为用户要做的一步列出，本模块做不了。
- **过程记录**：说明行统一写成引用块一行，放在标题下方；`pilot-report.md` 第 3、5 行把 `/Users/vilin/Documents/haigeerlab/` 改成 `~/…`，其余一字不改（Spec 决策 5）。

## 影响面

新增：`README.en.md`、`docs/guide.md`、`docs/commands.md`、`docs/architecture.md`、`LICENSE`、`CONTRIBUTING.md`、`SECURITY.md`、`tests/test_docs.py`。
修改：`README.md`、`CHANGELOG.md`、`docs/requirements-record.md`、`docs/pilot-report.md`、`docs/capability-map-draft.md`、`docs/spec-guard-additions.md`、`tests/test_codex_coordinator.py`（`test_readme` 一行）。
删除：`docs/kickoff-prompts.md`、`docs/session-protocol-notes.md`（Spec 批准即批准这两份删除）。
不新增依赖；不改代码、skill、钩子、插件清单、`interface.json`、版本号；不改 `spec/`、`tasks/`（本模块自己的除外）。

## 预先声明

无（本模块不改公共文件）。

## Task List

- [ ] Task 1：一致性测试先红——写 `tests/test_docs.py`（Spec 决策 7 五条）；`test_readme` 改读 `docs/guide.md`
  - 验证：`python3 -m unittest tests.test_docs tests.test_codex_coordinator` 红，红的原因是新文档还不存在（不是测试写错）；其余断言在临时放好文件时能转绿（在测试里用一份最小样例自查一次后删掉样例）
- [ ] Task 2：命令参考 `docs/commands.md`——跑 `--help` 取 31 个命令组与子命令，对照 `module_crew/` 的退出码、谁能跑（模块协调专用命令的判断）、要不要原话（Spec 验收 4）
  - 验证：`test_docs` 的命令覆盖一项转绿；核实记录写下命令组数、子命令数、与原 README 命令一览的出入条数与改法
- [ ] Task 3：使用手册 `docs/guide.md` 前半——术语、角色与边界、完整流程、项目开关（声明范围、检查记账、自治档位、额度外包、并行／串行）
  - 验证：开关名、默认值、配置命令对照 `module_crew/` 的读写代码；去向表记下原 README 对应各节
- [ ] Task 4：使用手册后半——轻任务、修订模块、Codex 模块会话与换宿主（含「模块协调在 Codex 上」）、审查就近与决策收件箱、权限预配、出状况、已知限制与尚未验证（Spec 验收 5）
  - 验证：`test_readme` 转绿；去向表覆盖原 README 除「0.18.0 的变化」「命令一览」外的每一节；「尚未验证」每条注明仍成立的依据或删去的理由

### Checkpoint 1（report）：命令参考与使用手册就位，`tests.test_docs`、`tests.test_codex_coordinator` 中对应项通过，核实记录写到这里为止，记入 todo 后继续

- [ ] Task 5：架构 `docs/architecture.md`——组件（`module_crew/` 每个文件一行职责，对照文件实际内容）、状态库、消息与批准、合并与检查、上游接口（版本检查对照代码常量）、对外出口（`sessions --json` 字段对照实际输出、`interface.json`）、设计取舍（Spec 验收 6）
  - 验证：在本 worktree 实跑 `module-crew sessions --json` 与 `status`，字段与描述一致；相对链接检查通过
- [ ] Task 6：`README.md` 重写（Spec 大纲 9 节）＋ `CHANGELOG.md` 收下「0.18.0 的变化」并改开头说明（Spec 验收 2、3）
  - 验证：`test_docs` 的「无按版本标题」「版本行与 plugin.json 一致」「无 ../ 与本机路径」转绿；`git diff CHANGELOG.md` 只有新增行与开头说明行；安装写法已对照 Claude Code 官方文档
- [ ] Task 7：`README.en.md`（结构逐节对应中文版，其他文档链接指向中文）
  - 验证：`test_docs` 的互链一项转绿；两份 README 的二级标题数相同
- [ ] Task 8：`LICENSE`（MIT，Copyright (c) 2026 haigeerlab）、`CONTRIBUTING.md`（D2 A：报问题、开发环境、跑测试、提交信息格式、PR 流程、大改动先开 issue）、`SECURITY.md`（GitHub 私下报告、权限模型概述并链到使用手册）
  - 验证：LICENSE 是 MIT 标准全文；三份的相对链接检查通过；README 两版的「许可证」「文档导航」指向这几份
- [ ] Task 9：过程记录——删 `docs/kickoff-prompts.md`、`docs/session-protocol-notes.md`；四份加说明行；`pilot-report.md` 两行路径改写（Spec 验收 7）
  - 验证：`git grep -n 'docs/' -- spec tasks` 列出的每个 `docs/` 路径都存在；`git grep '/Users/' -- docs README.md README.en.md CONTRIBUTING.md SECURITY.md` 无结果；四份记录的 `git diff` 只有说明行（`pilot-report.md` 另有两行路径）

### Checkpoint 2（report）：全部文档就位，`tests.test_docs` 全绿，记入 todo 后继续

- [ ] Task 10：`module-crew sync` 合入集成分支后后台跑全量测试；补完核实记录（五类各写对照了什么、几处不一致、怎么改的）；`git diff --stat` 对照集成分支确认没碰 Spec 验收 10 列出的范围外文件（Spec 验收 8、9、10）
  - 验证：全量测试通过，或与集成分支同样的已知失败（照实写）；越界检查一致

### Checkpoint 3（gate）：最终验收

- [ ] 回告：无外部来源（需求由用户在 mc-coord 会话提出），随最终验收写「无」；用户要做的一步（在 GitHub 仓库设置里打开私下漏洞报告）列进最终验收
