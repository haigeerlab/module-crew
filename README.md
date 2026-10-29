# module-crew

让多个 Claude Code 或 Codex 桌面版会话在同一个项目里**并行开发多个模块**的插件。

中文 | [English](README.en.md)

> 版本 0.20.0 · 许可证 [MIT](LICENSE)

## 它解决什么

[spec-guard](https://github.com/haigeerlab/spec-guard-plugin) 按能力图一个模块接一个模块推进（Spec → Plan → 实现），模块多、彼此又独立时，整体进度被串行和逐个审查拖慢。
module-crew 在它之上加一层运行层：

- **一个模块协调统筹**：开模块、收件记账、转达用户的决定、管集成分支与公共文件、合并。
- **每个模块一个会话**：各在自己的 git worktree 里写 Spec、Plan、代码，只和模块协调说话。
- **所有批准都由用户亲手给出**：Spec、Plan、最终验收、合并、推送都要用户在模块协调里的原话；别的会话转来的话不算批准。
- **中断了能接上**：会话崩溃、被压缩或换新会话后，从状态库恢复，不靠对话记忆。

```text
用户 ──原话批准──> 模块协调（集成 checkout）
                     │  ▲   agent-relay 消息
                     ▼  │
        模块会话 A（worktree A）  模块会话 B（worktree B） …
                     │
           状态库（git 公共目录下 module-crew/，所有 worktree 共用）
```

另外还有轻任务（单个需求或 bug，不写 Spec 也走合并队列）、可选的审查者与决策收件箱、空档时整体换到 Codex、把实现交给 Codex 的额度外包。详见[使用手册](docs/guide.md)。

## 前提

| 依赖 | 要求 |
|---|---|
| 宿主 | Claude Code 桌面版（Code 标签）；模块会话也可以开在 Codex 桌面版，一批收尾后模块协调可用 `coordinator handover` 整体换到 Codex 桌面版。所有会话在同一台 Mac 上 |
| [agent-relay](https://github.com/haigeerlab/agent-relay) | 必需，接口主版本 2。会话之间用它收发消息 |
| [spec-guard](https://github.com/haigeerlab/spec-guard-plugin) | 必需，0.68.0 起（接口 1.1 的规划层）；项目已启用 spec-guard 的本地多 Spec 约定（`spec/CAPABILITY-MAP.md`）。声明范围、自治档位、额度外包要 0.85.0 起（接口 1.11） |
| [delegate](https://github.com/haigeerlab/delegate-plugin) | 可选，只有打开额度外包时才要：0.8.0 起（接口 1.3） |
| session-protocol | 会话间消息的格式契约，module-crew 钉住 v2.6（契约本身随 module-crew 内置的解析器生效，不用另装） |
| 项目 | git 仓库，能建 worktree；有一条能在本地跑完的完整检查命令，合并后用它判断集成是否通过 |
| 运行环境 | Python 3（只用标准库；开发与测试用 3.10） |

## 安装

**Claude Code**：本仓库自带插件市场清单（`.claude-plugin/marketplace.json`，市场名 `module-crew-local`）。先装好 agent-relay 与 spec-guard，再：

```bash
claude plugin marketplace add haigeerlab/module-crew
```

```bash
claude plugin install module-crew@module-crew-local
```

也可以从本地 clone 装：`claude plugin marketplace add /path/to/module-crew`。

- 首次使用时 Claude Code 会询问是否信任插件钩子，**要同意**；否则压缩、换会话后不会注入角色提示。
- 插件更新后，在用的会话在原会话里 `/clear` 一次（或开新会话）才用上新版本的钩子与 skill。

**Codex**（只在要开 Codex 模块会话、或把模块协调换到 Codex 时需要）：在 Codex 里装同一版本的本插件（`.codex-plugin/plugin.json`，提供 Codex 版 `crew-dev` 与 `crew-coordinator` 两个 skill），装完完全退出 ChatGPT 应用再打开。动 Codex 侧插件前先备份 `~/.codex/config.toml`。

装好后在项目里体检：

```bash
bin/module-crew status
```

它检查 git、agent-relay、spec-guard、项目是否启用 spec-guard、spec-guard 规划层、集成分支与状态库七项，任何一项阻塞都会写明原因。

## 上手

1. **升级模块协调**：在你想让它统筹的会话里明说「把本会话升级为模块协调」，它运行 `module-crew coordinator up`。
2. **开模块**：模块协调 `module-crew start plan` 按能力图提议可开的模块；你答应后 `module-crew start prepare <模块>…` 建 worktree、生成开工说明，在每个 worktree 开新会话、贴上开工说明。
3. **写 Spec 与 Plan**：模块会话写好后发【交审】，模块协调汇总给你审；你批准后它 `module-crew review approve`，模块会话收到开工通知再构建。
4. **合并**：模块做完发最终验收，你批准后模块协调 `module-crew merge run` 合入本地集成分支并跑完整检查，不过就自动退回。
5. **推送**：你授权后 `module-crew merge push` 推到远端新分支并开 PR；远端合并由你自己做。

完整流程、每一步的细节与出状况时怎么办见[使用手册](docs/guide.md)。

## 项目开关

都默认关，凭用户原话由模块协调打开；不打开时一切照旧。

| 开关 | 作用 | 说明 |
|---|---|---|
| `declaredScope` 声明范围 | Plan 里预先声明的公共文件，模块直接在自己分支改，最终验收一并审 | [使用手册](docs/guide.md#声明范围declaredscope) |
| `checkLedger` 检查记账 | 平时只跑快检查、按树哈希记账；完整检查只在合并队列里跑 | [使用手册](docs/guide.md#检查记账checkledger) |
| `autonomyTier` 自治档位 | `strict`（默认）／`standard`／`relaxed`：交审节奏与消息汇总的松紧，出事自动降档 | [使用手册](docs/guide.md#自治档位autonomytier) |
| `codexOffload` 额度外包 | Claude 额度紧张时，开工后的模块把 Task 交给同一个 Codex 会话实现，模块会话核对后提交 | [使用手册](docs/guide.md#额度外包codexoffload) |

## 文档

| 文档 | 内容 |
|---|---|
| [使用手册](docs/guide.md) | 术语、角色、完整流程、项目开关、轻任务、修订模块、Codex 与换宿主、审查与决策收件箱、权限预配、出状况、已知限制 |
| [命令参考](docs/commands.md) | 每条命令做什么、谁跑、在哪跑、要不要用户原话、退出码 |
| [架构](docs/architecture.md) | 组件、状态库、消息与批准、合并与检查、上游接口与对外出口 |
| [更新记录](CHANGELOG.md) | 各版本的变化 |
| [参与贡献](CONTRIBUTING.md) | 报问题、开发与提交 |
| [安全](SECURITY.md) | 怎么报告安全问题 |

`docs/` 下另有几份开发过程记录（需求记录、试点报告等），不随版本更新，现行用法以上面几份为准。

## 开发

```bash
python3 -m unittest discover -s tests -v
```

本仓库自己也用 spec-guard 与 module-crew 开发：需求与设计在 `spec/`，任务在 `tasks/`。详见[参与贡献](CONTRIBUTING.md)。

## 许可证

[MIT](LICENSE) © 2026 haigeerlab
