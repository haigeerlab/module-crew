# 第 3 关开工提示词（三条线）

> 第 2 关草案，待用户审。第 3 关按顺序发出：先 ① 与 ② 并行（spec-guard 规划层与契约迁移互不依赖），
> ③ 在 ② 的 v1.1 批准后开始写能力图正文。发出前先确认对方会话在线，按「动别的仓库前先通知负责人」的规矩来。

## ① 给 spec-guard 插件负责人

```text
请在 spec-guard 仓库为「多模块并行开发」加入规划层能力。需求已由用户批准，完整依据在
~/Documents/haigeerlab/module-crew/docs/requirements-record.md（第 5、9 节），模块清单在同目录 spec-guard-additions.md。

要点：
- 全部由新配置项 moduleConcurrency（默认 off）控制，off 时所有输出逐字不变，每个模块都要有证明这点的回归测试。
- 只增不改：/map --json 的 schemaVersion 保持 1 只加字段；interface.json 升 1.1 只加入口。
- spec-guard 里不放任何运行时（不开会话、不建 worktree、不发消息、不合并），运行时由新插件 module-crew 负责。
- 保留 scripts/check-no-parallel-surface.py，新内容不用 parallel- 命名；0.12.0 退役并行工作流的教训见需求记录第 9 节。
- 不改选当前模块的逻辑与阶段计算；需要改时停下来问用户。

请用 add-module（或 Proposal）把清单里的模块插进能力图，按 spec-guard 自己的流程推进；模块 id 你可以定稿，
觉得哪项不合理就提出来交用户决定。来源登记为「用户本人，经多模块并行需求讨论（2026-10-17～18）」。
发版后回告 module-crew 的负责人会话。
```

## ② 给 decision-inbox 负责人（契约迁移）

```text
用户批准建立共用契约仓库 session-protocol（~/Documents/haigeerlab/session-protocol，本地，建远端前另问用户），
说明见 ~/Documents/haigeerlab/module-crew/docs/session-protocol-notes.md。

请你做 v1.0 迁移：
- 把 decision-inbox 的 spec/message-protocol.md 与 tests/fixtures/protocol/ 的五份样例迁成契约 v1.0
  （PROTOCOL.md、fixtures/ 下的样例与期望结果、conformance 说明）；
- decision-inbox 改为钉住 v1.0、在自己测试里跑契约样例；行为不变。

另：module-crew 会提出 v1.1（新增【交审】【公共变更请求】【协调通知】），由用户批准后再加，请你也看一眼是否与 decision-inbox 冲突。
契约改动一律经用户批准。有不同意见直接提出，交用户决定。
```

## ③ 给 module-crew 开发会话（新会话，工作目录 ~/Documents/haigeerlab/module-crew）

```text
你负责新插件 module-crew：让多个 Claude 会话在同一项目里同时开发多个模块（协调会话统筹，模块会话各在自己的 worktree）。
需求已由用户批准：docs/requirements-record.md；能力图草案：docs/capability-map-draft.md；契约：docs/session-protocol-notes.md。

第一步：在本仓库运行 /spec-guard:setup-convention（先预览，用户确认后执行），/spec-guard:config 设产物语言 zh-CN；
然后用 /spec 的 Phase 0 把能力图草案写成 spec/CAPABILITY-MAP.md 交用户评审，再按 Build order 逐个模块走 Spec → Plan → 实现。
本仓库自己串行开发，不用未完成的并行能力开发自己。

约束：第一版只支持 Claude 桌面版；agent-relay 是必需依赖；只读 spec-guard 的 interface.json 与 /map --json，不读它的内部文件；
消息格式以 session-protocol 为准（先改契约再改实现）；状态库放仓库公共 git 目录；防线 L1–L5 见需求记录第 9 节。
crew-start 及之后的模块依赖 spec-guard 规划层发版，之前用夹具推进；第 7 关实地验证必须用真实版本。
```
