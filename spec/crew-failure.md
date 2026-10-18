<!-- spec-guard: review approved 4c8a1e8c3c71 -->
# Spec: crew-failure

> 能力图模块 `crew-failure`。需求来源：`docs/requirements-record.md` B6（失败与回退：等外部条件挂起不占名额；异常停点、同一 gate 再挡、改能力图复用 spec-guard 规则；崩溃在原 worktree 换会话；
> 互不拖累；不设固定超时，醒来时看在线状态与待答复；用户随时可退回串行）。假设见下文，用户 2026-10-18 已确认。

## 目标

并行开发出状况时，协调会话有现成的命令可用：等外部条件的模块挂起、让出名额；列出各模块会话的事实，帮协调会话发现悄悄停下的会话；
会话崩溃时生成恢复说明，在原 worktree 开新会话接着做；用户想收手时一条命令退回串行，不再开新模块。

## 范围

**范围内**

- `module_crew/failure.py` 与命令 `module-crew suspend|resume|sessions|resume-kit|serial`。
- 会话登记的 `suspended` 字段；运行配置的 `mode` 字段。
- crew-start 的空位计算不数挂起的会话、`mode: "serial"` 时拒绝开新模块（crew-start 修订，追加变更记录）。
- 两份 skill 各加一节。

**范围外**

- 调用 spec-guard 的 `module-suspend`（interface 1.1 未登记；由模块会话在自己的 worktree 里用 spec-guard 命令）。
- 判断会话是否已停下、读 agent-relay 在线状态（协调会话自己看）；定时巡视（第一版不做）。
- 异常停点、同一 gate 再挡、改能力图（复用 spec-guard 现有规则）。

## 假设（用户 2026-10-18 已确认）

1. `suspend <模块> --reason --original-file` 在会话登记加 `suspended`（原因、时间），状态仍在用；`resume <模块>` 撤掉；挂起不占名额（crew-start 空位计算修订）；spec-guard 的挂起由模块会话自己做。
2. `sessions` 只读列出每个在用模块会话的最后动静、未关等待单与事项、四档状态、是否挂起；只列事实、不设超时、不下结论。
3. `resume-kit <模块>` 生成恢复说明正文存进状态库；协调会话经用户同意（配合 `takeover`）在原 worktree 开新会话，第一条消息用它。
4. `serial --original-file` 记 `mode: "serial"`，之后 `start plan`／`start prepare` 拒绝开新模块；`serial --off` 恢复；skill 提醒用 `/spec-guard:config` 关 `moduleConcurrency`。
5. 异常停点、同一 gate 再挡、改能力图复用 spec-guard 规则，只在 skill 里各加一句。
6. 一个模块挂起、退回或崩溃不影响其他模块的合并队列与通知，用测试证明。

## 关键决策与取舍（请重点审）

1. **挂起用字段、不用新状态**：会话登记 `status` 仍是 `active`（crew-store 的状态取值不变），另加 `suspended: {"reason", "at", "original"}`；
   恢复时把字段设为 `null`。凡是「数名额」的地方（`start.plan`、`start.validate`）都改为不数 `suspended` 非空的会话；钩子、收件、合并都照常认这个会话（挂起只让名额，不让它失去身份）。
2. **「最后动静」取状态库事件**：某会话最后一次作为 `actor` 写入、或被写入的会话／请求／事项／等待单事件的时间。只给时间与「距今多久」，不给阈值、不标红。
3. **恢复说明复用钩子的文字**：正文 = `hooks.session_start(worktree, "compact")` 的内容 + 「这是换会话后的恢复：先在 agent-relay 用同一个邮箱名重新注册（需要用户先在协调会话同意 `takeover`）」；
   存成 `body` 正文，命令输出正文路径与 worktree 路径。
4. **退回串行只关「开新」**：`mode: "serial"` 只影响 `start plan`／`start prepare`（退出码 3，原因写明）；已开的模块继续交审、合并、收尾。
   `serial` 需要用户原话（记进配置事件），`serial --off` 同样需要原话。
5. **互不拖累由数据结构保证**：各命令只按模块、编号操作自己的记录；本模块加一个跨模块测试：b 挂起、c 正常交审与合并、d 被退回，三者的状态与通知互不影响。

## 接口约定

### 命令

```bash
bin/module-crew suspend <模块 id> --reason <原因> (--original <原话> | --original-file <文件>)
bin/module-crew resume <模块 id> (--original <原话> | --original-file <文件>)
bin/module-crew sessions [--json]
bin/module-crew resume-kit <模块 id>
bin/module-crew serial (--original <原话> | --original-file <文件>) [--off]
```

- `suspend`／`resume`：`0` 成功；`3` 模块没有在用会话、已挂起（`suspend`）或未挂起（`resume`）、原话为空。（2026-10-18 修订：`resume` 也要用户原话）
- `suspend`／`resume` 各记一条已答事项（`kind` 为 `suspend`／`resume`，含用户原话），并生成一条契约 v1.8 的【协调通知】（类型挂起／恢复）给模块会话：
  挂起类带「原因」，「依据」写那条事项编号；恢复类「依据」写恢复事项编号与当初的挂起依据。「要你做什么」另带 module-crew 的做法（在本 worktree 用 spec-guard 挂起／取消挂起）；
  挂起之后有模块合入集成分支时，恢复类「要你做什么」写明先把集成分支合进模块分支、跑完整检查再继续（含合入的模块与合并批准事项编号）。
- `sessions`：`0`；没有在用模块会话时输出「没有在用的模块会话」，仍为 `0`。
- `resume-kit`：输出 worktree 路径、邮箱名与恢复说明正文路径；`0` 成功；`3` 模块没有在用会话。
- `serial`：`0` 成功；`3` 已是该模式或原话为空。

## 项目结构

```text
module_crew/failure.py
module_crew/start.py               空位计算与 serial 模式（修订）
module_crew/__main__.py            加五个子命令
skills/crew-coordinator/SKILL.md   加「出状况时」一节
skills/crew-dev/SKILL.md           加「挂起与异常」一节
tests/test_failure.py
```

## 命令

```bash
python3 -m unittest discover -s tests -v
```

## 代码风格

沿用前几个模块；`failure.py` 复用 `hooks._stage`、`hooks.session_start` 与 `store` 事务，不另读 spec-guard。

## 测试策略

- 复用 crew-merge 的测试基类（b、c 两个模块会话，夹具 `startable` 含 b、c、d）。
- 挂起后 `start plan` 的空位多一个；`serial` 后 `start plan`／`prepare` 退出码 3。
- 跨模块测试按关键决策 5。

## 边界

- **始终**：只增字段不改状态取值；需要用户原话的操作没有原话就拒绝。
- **先问**：替用户判断会话已停下；自动挂起或自动换会话。
- **绝不**：删除会话登记；在退回串行时中断已开模块的工作。

## 验收标准

1. `suspend b --reason "等设计稿" --original "先挂起 b"`：b 的会话登记带 `suspended`（原因、时间、原话）、状态仍为 `active`；`start plan` 空位从 1 变为 2（上限 3、在用 b、c）；再挂一次退出码 3。
2. `resume b --original "恢复 b"`：`suspended` 为 `null`，空位恢复，事件记原话；未挂起或原话为空时 `resume` 退出码 3。（2026-10-18 修订）
3. 挂起的 b 仍能被钩子识别为模块会话、仍能 `inbox add` 收件。
4. `sessions` 列出 b、c：最后动静时间、未关等待单与事项编号、四档状态、挂起原因（如有）；`--json` 可解析；不含任何「已停下」之类的判断字样。
5. `resume-kit b`：正文含模块、邮箱名、worktree、当前档位、「以状态库为准」、`takeover` 与 `bridge_register` 的做法；存为正文、可按编号读回。
6. `serial --original "先不并行了"`：配置 `mode` 为 `serial`；`start plan` 与 `start prepare` 退出码 3 并写明「已退回串行」；已开模块的 `review add`、`merge run` 照常；`serial --off --original "恢复"` 后又能开。
7. 跨模块：b 挂起、c 交审并合并、d 被退回——c 的合并与通知、d 的退回通知都正确，b 的记录不受影响。
8. 两份 skill 新增一节：协调会话「出状况时」（`sessions` 结合 agent-relay 在线状态判断、`suspend`／`resume`、`resume-kit` 配合 `takeover`、`serial` 与 `/spec-guard:config`、异常停点／同一 gate 再挡／改能力图按 spec-guard 规则）；模块会话「挂起与异常」（等外部条件时请协调会话挂起并在本 worktree 用 spec-guard 挂起、同一 gate 再挡时停下交协调会话）。
9. crew-start 修订：`start.plan`／`validate` 不数挂起会话、`mode: "serial"` 时拒绝；crew-start 原有测试全部通过；`spec/crew-start.md` 末尾追加变更记录。

10. `suspend b` 与 `resume b` 各输出一条给 b 的挂起／恢复类【协调通知】（`protocol.parse` 合格，依据里的编号指向记着用户原话的事项，恢复类同时列出挂起依据）；b 挂起期间 c 合入后，恢复类「要你做什么」写明先同步并含 c 的合并批准事项编号，没有合入时不写。
11. `resume-kit b`：正文不含「刚压缩过」；b 有未关的最终验收交审时「当前」写「最终验收已交审（交审事项 #N）」。

## 未决问题

无。

## 文档建议

README 增加「出状况时怎么办」：挂起、换会话、退回串行。能力图全部完成后另提一次整体文档建议。
- 2026-10-18：`resume` 要用户原话；`suspend`／`resume` 生成给模块的通知正文（契约 v1.8 前为非协议消息，已向契约负责人提需求），`resume` 在挂起期间有合入时补发同步基线；恢复说明不再带压缩提示；增加验收 10、11，改验收 2。原因：试点问题 M、I、L、J；来源：第二轮试点（`docs/pilot-report.md` 第二轮一节），用户 2026-10-18 批准修法。
- 2026-10-18：契约 v1.8（c982bc3）新增挂起、恢复类【协调通知】，`suspend`／`resume` 改为记一条已答事项并生成正式通知（取代上一条里的非协议正文与单独的同步基线通知），改验收 10。原因：契约负责人按本模块的需求发布 v1.8；来源：第二轮试点修法（用户 2026-10-18 批准「契约发版后改为正式通知」）。
