# spec-guard 新增模块清单（交 spec-guard 插件负责人）

> 第 2 关草案，待用户审。批准后在第 3 关交给 spec-guard 插件负责人，由他在 spec-guard 仓库用 `/spec-guard:add-module`
> （或 Proposal）插进能力图，按 spec-guard 自己的流程逐个推进。需求依据见 `requirements-record.md` 第 5、9 节。

## 总约束（每个模块都适用）

- 全部由新开关 `moduleConcurrency`（`.agent/config.json`，默认 off）控制；**off 时所有输出逐字不变**，每个模块都要有证明这一点的回归测试。
- 只增不改：`/map --json` 的 `schemaVersion` 保持 1，只加字段；`interface.json` 从 1.0 升到 1.1，只加入口。
- 不放任何运行时：不开会话、不建 worktree、不发消息、不合并；hook 仍只报告。
- 保留 `scripts/check-no-parallel-surface.py`；新文件与新文字不用 `parallel-`／`parallel_`。
- 不改选当前模块的逻辑、阶段计算、挂起与暂停；出现需要改这些的情况就停下复盘（防线 L5）。
- 共享判据同时改 `phase-guard` 与 `verify-artifacts`，两边各有正反回归（spec-guard 不变量）。

## 模块（建议的 id、职责、依赖，id 由负责人定稿）

| 建议 id | 职责 | 依赖 |
|---|---|---|
| module-concurrency-switch | 配置项 `moduleConcurrency: off|on`，`/spec-guard:config` 预览确认后设置并汇总显示；无效值按现有项目配置规则报错 | — |
| concurrency-assessment | 能力图评审停点上的并行评估与提醒：两条硬门槛、三项参考、Build order 逗号组与前移建议（只在开关 on 时出现；挂在现有「文档建议」同一停点） | module-concurrency-switch |
| module-scope-boundary | 模块 Spec 的「并行边界」一节（目录独占路径 + 公共文件四类）；只读越界检查脚本（对比集成基线、对照并行边界）；最终验收的改动文件清单加「超出并行边界」标记 | module-concurrency-switch |
| map-startable | `/map --json` 新增 `buildOrderGroups`、每模块 `scope`、顶层 `startable`（按 Build order、含 `conflicts`）；表格在可开始的模块后加简短说明 | module-scope-boundary |
| checkout-role | 角色标记命令（`$(git rev-parse --git-path spec-guard)/`，模块：<id>／协调，预览确认后写）；按角色的注入文字（模块会话做完「交回协调会话」、协调会话统筹总览、不建议 `/build`）；`/map` 新增每模块 `worktree`（读本机其他 worktree 的 todo，标未合入） | map-startable |
| crew-interface-and-wording | `interface.json` 1.1 登记角色标记、越界检查、`review-mark` 三个入口；检查点规则措辞：评审标记由「听到批准的会话」写入；「合并到远端分支由用户进行；并行模式下模块合入本地集成分支可在用户批准最终验收后由协调会话执行」；设计文档与 CHANGELOG | checkout-role |

Build order 建议：module-concurrency-switch → concurrency-assessment, module-scope-boundary → map-startable → checkout-role → crew-interface-and-wording

## 交给负责人时要附的话

- 这些改动由用户批准的需求记录驱动，来源写「用户本人，经多模块并行需求讨论（2026-10-17～18）」；按 spec-guard「需求来源与回告」登记。
- 发版后回告 module-crew 的负责人会话（会话名届时补）。
- 负责人觉得某项不合理可以提出，交用户决定（不硬塞）。
