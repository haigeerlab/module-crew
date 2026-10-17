# session-protocol 契约说明

> 第 2 关草案，待用户审。批准后第 3 关建仓库 `~/Documents/haigeerlab/session-protocol`（本地，建远端前另问用户），
> v1 的迁移请 decision-inbox 负责人做。需求依据见 `requirements-record.md` 第 8 节。

## 契约管什么

- 消息类型与字段：标签、必填／选填、出错时的问题代码（只增不改）。
- 答复有效性：什么样的【用户答复】才算用户决定、执行前回显。
- agent-relay 用法：请求标 `expectsReply`；回复填 `replyTo` 并首行写「回复：#N」；正文走 `bodyFile`；只在自己会话里写结论不发回复，算没有交付。
- 角色名与宿主名：`hub`、`coordinator`、`owner`、`dev`；`claude-desktop`、`codex-desktop`。
- 等待单关单理由（四种）。

不管：各插件的状态库格式、命令、显示、解析代码。

## 仓库内容

```
session-protocol/
├── PROTOCOL.md          协议文档，开头写版本号（主版本变 = 不兼容）
├── CHANGELOG.md
├── fixtures/<类型>/*.txt        每种消息的标准样例（含故意写错的反例）
├── fixtures/<类型>/*.json       每个样例期望的解析结果（类型、字段、问题代码）
└── conformance/README.md        各插件怎么跑这套样例
```

各插件把某个版本的 `fixtures/` 复制进自己仓库（带版本号与指纹），在自己的测试里逐个解析、对照期望结果。升级契约版本 = 换一份样例再跑通。

## 版本

- **v1.0**：从 decision-inbox 迁入。来源：`spec/message-protocol.md`（已批准）与 `tests/fixtures/protocol/` 五份样例；六种类型：
  【等待用户】【用户答复】【等待其他会话】【已恢复】【撤回】【审查结论】，以及【取代 #N】【与 #N 并行】标记。迁入后 decision-inbox 改为钉住 v1.0、跑契约样例。
- **v1.1**（module-crew 提出，先批后实现）：
  - 【交审】模块→协调：模块、节点（Spec／Plan／最终验收）、文件与指纹、要点；最终验收另附改动文件统计与越界检查结果。
  - 【公共变更请求】模块→协调：来自、文件、改什么、为什么、是否完全停住。
  - 【通知】协调→模块：类型（开工／同步基线／接口变更／收尾）、依据、要你做什么。

## 规则

- 先改契约，再改实现。
- 改动一律经用户批准；decision-inbox 与 module-crew 的负责人都可以提。
- 契约不放代码；两插件的解析代码各自实现（避免发版绑在一起）。
