# 参与贡献

欢迎提 issue 和 PR。下面是这个仓库的做法，照着做能少来回几次。

## 报问题

在 [GitHub issue](https://github.com/haigeerlab/module-crew/issues) 里写：

- module-crew 的版本（`.claude-plugin/plugin.json` 的 `version`）与宿主（Claude Code 桌面版或 Codex 桌面版）；
- `module-crew status` 的输出（涉及 Codex 时另附 `module-crew host-check`）；
- 做了什么、期望什么、实际看到什么；命令的完整输出与退出码。

贴输出前去掉个人信息（如路径里的本机用户名）。安全问题不要开公开 issue，见[安全](SECURITY.md)。

## 开发环境

- Python 3（开发与测试用 3.10），只用标准库，不需要装依赖。
- 跑全部测试：

  ```bash
  python3 -m unittest discover -s tests -v
  ```

  全量测试较慢（本机约半小时）。改动小的时候可以先只跑相关文件，例如 `python3 -m unittest discover -s tests -p 'test_docs.py'`，提 PR 前再跑全量。
- 命令入口是 `bin/module-crew`；代码在 `module_crew/`，各文件的职责见[架构](docs/architecture.md)。

## 改动的做法

- **大改动先开 issue 讨论**：加命令、改状态库记录、改消息格式、改给模块协调或模块会话的规矩（`skills/`、`codex-skills/`）之前，先在 issue 里说清要解决什么。
- 本仓库自己用 spec-guard 与 module-crew 开发：需求与设计在 `spec/<模块>.md`，任务在 `tasks/<模块>/`。较大的功能会写成一个模块的 Spec 与 Plan，PR 里可以引用相关的 Spec。
- **先写测试**：改行为先写一个会失败的测试，再改到它通过；修 bug 先写复现测试。
- **只用标准库**，不加第三方依赖。
- **两个宿主一起改**：`skills/` 与 `codex-skills/` 是同一套规矩的 Claude 版和 Codex 版，改一边时看另一边要不要跟着改。
- **文档跟着改**：改了命令、参数、开关或默认值，同步改[命令参考](docs/commands.md)与[使用手册](docs/guide.md)；`tests/test_docs.py` 会检查每个命令组都在命令参考里。按版本的变化写在 [CHANGELOG](CHANGELOG.md)，README 只写当前功能。

## 提交与 PR

- 提交信息用中文，带类型前缀：`feat:`、`fix:`、`docs:`、`test:`、`chore:` 等，可以加范围，如 `fix(merge): …`。
- 一个 PR 做一件事；PR 描述写改了什么、为什么、怎么验证的（跑了哪些测试）。
- 合并前全量测试要通过。
