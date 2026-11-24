# Usage draft: auto-takeover

> **已留档（2026-11-24）**：S101 于 11-24 停下，M1、M2 不再确认，剩余归 S110。原在 `spec/usage/auto-takeover.md`，移出后不再参与里程碑停点与校验。依据：用户「推送 0.24.2，S101 停」「丙：问 sg-coord」「移去留档」（mc-coord 会话），做法按 sg-coord #22371。

> 需求：S101 自动接管（plugin-ecosystem `research/2026-11-21-自动接管合并方案.md`，bfce091）。模块 `crew-takeover-approve`、`crew-takeover-merge`（能力图 6636f7e）。
> 补写：两个模块的 Spec、Plan 已批（C607、C610、C620、C623）之后才写这份草案，按 spec-guard「用法草案」规则补审。
> 接管档位本身（`takeover`／`moduleTakeover` 的设置与存储、收窄入口）归 spec-guard 0.91.0；下面只列 module-crew 的入口。

## Entry points

| Entry | Does | Module |
|---|---|---|
| `module-crew tier [--json]` | 看接管档位（项目与在用模块）、每项人批还是 Codex 放行、Codex 放行计数、autonomyTier 退役提示 | crew-takeover-approve |
| `module-crew tier --preflight` | 写 takeover 之前核对 spec-guard ≥ 0.91.0、接口 1.15 | crew-takeover-approve |
| `module-crew tier degrade --reason <文字> --ref <标识>` | 外部信号收窄接管档位（调 spec-guard 收窄入口，先撤合并、再 Plan、最后 Spec） | crew-takeover-approve |
| `module-crew review codex C<n>` | 给出这一轮要跑的 `/delegate:review --backend codex` 命令（Spec、Plan、接口提案） | crew-takeover-approve |
| `module-crew review codex-note C<n> --report <json>` | 记 Codex 结论：有阻断自动返工（最多 2 轮）、无阻断放行、超限或不可用停下交用户 | crew-takeover-approve |
| `module-crew config --digest on` 或 `off` | 收尾汇总开关（从退役的 autonomyTier 拆出） | crew-takeover-approve |
| `status`、交审登记行、`review batch`、开工说明里的「批准方式」一行 | 写清每个模块 Spec、Plan、合并各由谁批 | crew-takeover-approve |
| 出事自动收窄（合并退回、撤销批准、返工超限、基线变红） | 自动调 spec-guard 收窄入口并马上告诉用户 | crew-takeover-approve |
| `module-crew review codex C<n>`（最终验收） | 给出按提交范围审最终补丁的 `/delegate:review` 命令 | crew-takeover-merge |
| `module-crew merge auto C<n>` | Codex 无阻断后：非作者完整检查、放行、接着跑合并队列（合进本地集成分支） | crew-takeover-merge |
| `module-crew check evidence [<提交>] --json` | 给 autopilot 读：检查记录（是否非作者）与未推送的自动合证据 | crew-takeover-merge |
| 合入后写 `codex-approved` 验收标记 | 自动合的模块合入后在集成分支记 spec-guard 验收标记 | crew-takeover-merge |

## Typical usage

### U1: 只接管 Plan：Plan 由 Codex 放行

用户在集成 checkout 用 `/spec-guard:config` 把项目档位设成「只接管 Plan」（module-crew 先 `tier --preflight`；它读状态库，项目还没有状态库时先 `module-crew store init`，否则退出码 2）。`module-crew tier` 显示「Spec 人批、Plan Codex 放行、合并人合」。
模块会话交 Spec：照旧交用户批。交 Plan：`review add` 登记行写「Codex 放行：下一步 review codex C<n>」，不进给用户的批次。
模块协调后台跑 `review codex C<n>` 给出的命令，再 `review codex-note C<n> --report <报告>`：有阻断就发返工通知，模块改完重交；无阻断就落地 Plan、记 `codex-approved` 标记、发开工通知（依据写 Codex 放行事项号）。
`status` 的接管一段写「Codex 放行：Plan 1 次」；Codex 没跑成时退出码 5，给出【等待用户】草稿（带 delegate 的 diagnostics），用户选等 Codex 或这次自己批。
Codex 审满两轮仍有阻断时同样停下交用户；之后这个节点重交改为人批，不再交 Codex。

### U2: 接管到合并：最终验收由 Codex 放行并自动合进集成分支

项目档位设成「接管到合并」（开着检查记账）。模块交最终验收：登记行写「最终验收，自动合：下一步 review codex C<n>」。
`review codex` → 后台跑 Codex 审最终补丁 → `review codex-note`：无阻断时输出下一步 `module-crew merge auto C<n>`（后台跑）。
`merge auto` 在模块 worktree 跑一次非作者完整检查、放行、跑合并队列：合进本地集成分支、完整检查、勾最终验收、写 `codex-approved` 验收标记。
`module-crew check evidence --json` 列出这次合并的三样证据，供 autopilot 推 batch 分支、合远端 PR（那一步不归 module-crew）。

### U3: 出事收窄

自动合的模块在合并队列里因模块原因被退回（或用户撤销合并批准、返工超限、基线变红，或 autopilot 调 `tier degrade --reason … --ref …`）：
module-crew 调 spec-guard 收窄入口，「接管到合并」降为「只接管 Plan」，输出「接管档位已收窄（项目 接管到合并 → 只接管 Plan）：<原因>。马上告诉用户；…」，模块协调马上告诉用户；同一事项只降一次。
放宽要用户原话，经 `/spec-guard:config` 写；`module-crew tier restore` 只给出这条指引。

## Milestones

| Milestone | Usage | Modules |
|---|---|---|
| M1 | U1, U3 | crew-takeover-approve |
| M2 | U1, U2, U3 | crew-takeover-merge |

## 评审记录

- 2026-11-21：用户在 mc-coord 会话批准本草案（原话「批草案并改边界」）。补写于两个模块 Spec、Plan 批准之后；拆分核对：无。

## 变更记录

- 2026-11-23：U1 写明 `tier --preflight` 要先有状态库、Codex 没跑成的草稿带 diagnostics、两轮阻断后改人批；U3 的收窄提示按实际措辞写。原因：0.24.1 沙箱实跑报告（M1-M2-REPORT.md）注意 5、7 与问题 B、C、E。来源：crew-takeover-approve 第 3 轮返工 Task 17（用户「按推荐继续」，C686），随返工最终验收复审。
