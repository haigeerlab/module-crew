# module-crew

让多个 Claude 桌面版会话在同一个项目里**并行开发多个模块**：一个协调会话统筹，每个模块会话在自己的 git worktree 里开发；
所有批准都由用户在协调会话里亲手给出；会话中断、压缩或换新会话后，从状态库恢复，不靠对话记忆。

> 版本 0.0.1。已在试点项目上跑过两轮实地验证（见 `docs/pilot-report.md`），还没验证的见文末「尚未验证」。

## 前提

| 依赖 | 要求 |
|---|---|
| 宿主 | Claude 桌面版（Code 标签）；协调会话与模块会话都在同一台 Mac 上。第一版不支持 Codex 模块会话 |
| agent-relay | **必需**，接口主版本 2。会话之间用它收发消息（`bridge_send` 的 `bodyFile`、`replyTo`、`expectsReply`） |
| spec-guard | 项目已启用本地多 Spec 约定（`spec/CAPABILITY-MAP.md`）。开工、批量审批、合并依赖 spec-guard 0.68.0（`interface.json` 1.1、`/map --json` 的 `moduleConcurrency`、`startable`） |
| 项目 | git 仓库，能建 worktree；有一条能在本地跑完的完整检查命令，合并后用它判断集成是否通过 |
| 运行环境 | Python 3（只用标准库） |

消息格式以 [session-protocol](../session-protocol) 契约为准（现钉住 v1.8）。

## 安装

1. 本仓库自带本地插件市场清单（`.claude-plugin/marketplace.json`，市场名 `module-crew-local`），用本机路径装上，同时装好 agent-relay 与 spec-guard：

   ```bash
   claude plugin marketplace add /path/to/module-crew
   claude plugin install module-crew@module-crew-local
   ```

2. **信任 module-crew 的钩子**：首次使用时 Claude Code 会询问是否信任插件钩子，要同意；否则压缩、换会话后不会注入角色提示。
3. **插件更新后要开新会话**才生效：已开着的会话还在用旧版本的钩子与 skill。

装好后在项目里跑一次体检：

```bash
bin/module-crew status
```

它检查 git、agent-relay、spec-guard、spec-guard 规划层、集成基线与状态库六项，任何一项阻塞都会写明原因。

## 角色

- **协调会话**（加载 `crew-coordinator` skill）：统筹、收件记账、转达用户的决定、管集成分支与公共文件、合并。不开发任何模块，不出审查结论。
- **模块会话**（加载 `crew-dev` skill）：只在自己的 worktree 里开发一个模块，只和协调会话说话；被挡住必须发【等待其他会话】。

状态库放在仓库公共 git 目录下的 `module-crew/`（`events.jsonl` 是事实来源），所有 worktree 共用一份；不进版本库。

## 一次完整流程

1. **开工**（协调会话）
   - `module-crew start plan`：按能力图的 Build order 提议可开的模块（不超过空位，默认上限 3）。
   - 只问用户一次「开这 N 个吗？」，用户答应后
     `module-crew start prepare <模块>… --original-file <原话文件> --project-short <简称>`：为每个模块建 worktree（`<仓库名>-crew/<模块>`）、登记会话、生成开工说明。
   - 用桌面版在每个 worktree 里开新会话，第一条消息用开工说明全文。
2. **写 Spec 与 Plan**（模块会话）：写好后发【交审】；收到开工类【协调通知】之前不构建。
3. **批量审批**（协调会话）
   - `module-crew review add` 记下每条【交审】，`module-crew review batch` 汇总，把要点写在正文里交用户审。
   - 用户批准后 `module-crew review approve <编号>… --original-file <原话文件>`：在集成分支记评审标记，生成【用户答复】与开工通知。
   - 模块会话把集成分支合进自己的分支（Spec／Plan 冲突取集成分支版本）后开始构建。
4. **公共文件**：模块会话不改公共文件，发【公共变更请求】；协调会话 `change add` → 在集成 checkout 改 → `change land`，其他模块收到同步基线通知。
5. **合并**
   - 模块做完发最终验收【交审】，用户批准后 `module-crew merge approve <交审编号> --original-file <原话文件>`。
   - `module-crew merge run`（第一次带 `--check-command "<完整检查命令>"`）：按 Build order 一次只合一个，`--no-ff` 合入本地集成分支后跑完整检查；
     不过就把集成分支重置回合并前（模块分支原样保留）并退回该模块，冲突就中止并退回。
   - 合并成功：该模块收到收尾通知，其他在用模块收到同步基线通知。
6. **收尾与推送**
   - 用户同意后 `module-crew merge cleanup <模块> --original-file <原话文件>` 收回 worktree（分支保留）。
   - `module-crew merge push-plan` 预告；用户明确授权后 `module-crew merge push --original-file <原话文件>`，推到远端新分支 `crew/batch-<号>` 并开一个 PR。
   - **远端合并始终由用户做**；不开自动合并，不推集成分支本身。

每条要发的消息，命令都会生成正文文件；协调会话用 `bridge_send` 的 `bodyFile` 原样发出，不改一字。

## 出状况时怎么办

| 情况 | 做法 |
|---|---|
| 不知道哪个会话停下了 | `module-crew sessions` 列出每个模块会话的最后动静、未关的等待单与事项、当前档位、挂起原因；只列事实，结合 agent-relay 在线状态自己判断 |
| 某个模块会话在「等待审批」 | 权限弹窗只能用户去那个会话亲手点；协调会话醒来时会提醒，并核对各模块会话的权限模式有没有变宽 |
| 消息发出去对方没反应 | 桌面版会停掉空闲会话，agent-relay 叫不醒（`pendingReason: offline`）；用桌面版跨会话消息发一句「去读 agent-relay 收件箱」 |
| 模块在等外部条件（设计稿、别人交付） | 用户同意后 `module-crew suspend <模块> --reason "<原因>" --original-file <原话文件>`，不再占名额；按输出把挂起正文发给模块会话，它在自己的 worktree 里用 spec-guard 挂起。条件满足、用户同意后 `module-crew resume <模块> --original-file <原话文件>` |
| 会话崩溃或要换新会话 | `module-crew resume-kit <模块>` 生成恢复说明；用户同意后 `module-crew takeover <邮箱名> --original-file <原话文件>`，在原 worktree 开新会话，第一条消息用恢复说明，新会话用同一个邮箱名重新注册 |
| 会话被压缩 | 钩子会提醒先跑 `module-crew status`、以状态库为准，不按压缩前的记忆重做 |
| 想收手、不再并行 | `module-crew serial --original-file <原话文件>`：不再开新模块，已开的模块照常交审、合并、收尾；再用 `/spec-guard:config` 关掉 `moduleConcurrency`。恢复用 `serial --off` |
| 合并被退回 | 集成分支已回到合并前、模块分支不动；模块修好后重新发最终验收【交审】（不用撤销任何提交） |
| 同一个 gate 再次挡住、异常停点、要改能力图 | 按 spec-guard 的规则办，把选项与代价交用户决定 |

一个模块挂起、退回或崩溃，不影响其他模块的交审、合并与通知。

## 接入收件枢纽

有收件枢纽（如 decision-inbox）时，用户可以在枢纽里给决定：

1. 在协调会话里由用户亲口登记来源：`module-crew source add <枢纽邮箱名> --kind hub --original-file <原话>`；审查会话登记为 `--kind lead`。
2. `module-crew review batch --for-hub` 把一批交审合成一条【等待用户】交给枢纽；审查会话的结论用 `review note` 记下，正文里带审查行。
3. 枢纽转来【用户答复】后，批准命令带 `--source <枢纽> --source-item <H> --source-relay-id <消息号> --original-file <那条消息>`，用户原话从消息里读出。
4. `module-crew source map <H>` 查一个枢纽事项批准了哪些 crew 编号。
5. 外部插件读 `module-crew sessions --json`（`schemaVersion` 1：module、relayName、worktree、stage、stageText、suspended、lastActivity），出口与契约版本登记在根目录 `interface.json`。

指定负责人用【负责人转交】转来的决定登记为 `--kind lead`；带来源批准时，给模块的【用户答复】按契约 v1.6 带「转自」，命令同时给出发回枢纽的【已恢复】「结束：#H」。

## 命令一览

```text
module-crew status [--json]                      体检与全貌（只读）
module-crew store init|check                     状态库
module-crew protocol check <文件>                消息自检
module-crew inbox add <文件> --from --relay-id   收件记账
module-crew answer <编号> --original(-file)      转达用户答复
module-crew start plan|prepare                   开工
module-crew review add|batch|approve|answer      交审与批量批准
module-crew change add|list|land|answer          公共变更请求
module-crew merge approve|queue|run|cleanup|push-plan|push
module-crew suspend|resume|sessions|resume-kit|serial
module-crew takeover <邮箱名> --original(-file)  换会话接管
module-crew source add|remove|list|map           批准来源（收件枢纽、负责人）与对照
module-crew review note|batch --for-hub          审查行、交枢纽正文
module-crew ticket close <编号> --reason …        协调会话关等待单
module-crew hook session-start|prompt            插件钩子入口（只读，永远退出码 0）
```

需要用户批准的命令都要 `--original` 或 `--original-file`：只记用户在协调会话里亲手输入的话，别的会话转来的话不算批准。

## 开发

```bash
python3 -m unittest discover -s tests -v
```

需求与设计在 `docs/requirements-record.md`、`spec/CAPABILITY-MAP.md` 与 `spec/<模块>.md`。

## 尚未验证

两轮试点（第一轮 auto 权限、第二轮默认权限）已经实地验证：真实 spec-guard 0.68.0、会话间真实收发、开工、批量审批、合并与退回、
挂起与恢复、换协调会话与换模块会话、退回串行、收尾与推送到本机远端。还没验证的：

- 用 `gh` 真正开 PR（试点远端是本机裸仓库，只打印 PR 正文）。
- 预配项目工具许可能否减少模块会话的权限弹窗。
- 挂起、恢复类【协调通知】（契约 v1.8）在真实会话之间收发。
