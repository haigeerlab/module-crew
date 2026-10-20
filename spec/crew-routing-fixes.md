# Spec: crew-routing-fixes

<!-- spec-guard: review approved 23dd0bcfbb36 -->

> 能力图模块 `crew-routing-fixes`（第五版，0.9.0）。需求来源：总协调（local_d7434023）2026-10-20 转来的收发规则（点对点、沿上下级），
> 以及本会话按规则做的自查。用户原话（经总协调转达）：「module-crew 修第 1、2 条和钩子按目录认身份（我那份清单的第 9、10 条），
> 第 3 条保留……两边都先出 Spec 交我审，不直接改。」

## 目标

module-crew 生成的消息和注入的角色，只给真正要处理它的那个会话：
【交审】只送负责这个模块或节点的审查者；公共变更落地后的同步基线通知不打扰挂起中的模块；
启动钩子只给会话登记里的那个会话注入「你是模块协调／你是模块 X 的模块会话」。

## 范围

1. **【交审】按负责范围送审**（`review.py:97-105`、`sources.py`）：登记审查者（`source add --kind lead`）时必须写负责范围：
   负责哪些模块、哪些节点（spec／plan／interface／final，interface 是接口提案），全部也要明写「全部」。`review add` 只把【交审】发给范围覆盖这个模块和节点的审查者。
2. **同步基线跳过挂起模块**（`changes.py:186-199`、`failure.py` 的 `resume`）：`change land` 发同步基线通知时跳过挂起中的模块，
   和 `merge run` 的做法（`merge.py:301-302`）一致；恢复时 `resume` 的通知里补上挂起期间落地的公共变更。
3. **钩子按会话认身份**（`hooks.py:53-80` 的 `detect()`）：会话登记记下宿主会话 id；钩子拿当前会话 id 和登记核对，
   只有对上的那个会话才注入角色。同一目录里的其他会话只在启动时收到一句「本目录属于 X，你不是它的登记会话」，每轮不再注入。
4. 两份 skill 与开工说明、恢复说明的相应步骤；README；版本 0.9.0。

不做：
- 模块合入后的同步基线广播（自查第 3 条），用户定为保留；
- `review note` 校验「这个审查者是否收到过这条交审」（留作后续，见风险）；
- Codex 模块会话的钩子：Codex 侧没有 module-crew 钩子，本模块不新增；
- 改 session-protocol 契约：消息格式不变。

## 现场事实（2026-10-20 核对，基线 main baa634c，0.8.1）

1. `review.add` 取 `_reviewers(db)`（所有 `kind == "lead"` 的来源），把同一份【交审】正文发给每一个，并记 `sentTo`。登记审查者时没有范围字段。
2. `changes.land` 给所有 `role == dev`、`status == active` 的会话发同步基线，只跳过「等最终验收」的模块（`merge.awaiting_final`），不看 `suspended`；
   `merge.run` 合入后的同类通知跳过 `suspended`，`failure.resume` 只补「挂起期间合入的模块」，不补公共变更。
3. `hooks.detect(cwd)` 只看目录：checkout 有 spec-guard 角色标记就按标记找在用会话；否则看 cwd 在不在某个模块 worktree 里、在不在集成分支的 checkout 里。
   钩子收到的 payload 里有 `session_id`，但没被使用；会话登记（`start.py:246`、`:273`）只记 role、host、status、module、worktree，没有宿主会话 id。
4. 误注入实例（总协调只读排查）：10-20 02:26 前后并行协调3 38932d81 与并行协调4 cb182a33 同时收到「本会话是模块协调」
   （会话记录 3878bada….jsonl、0f36d94f….jsonl 第 4 行）；10-18、10-19 在 alpha worktree 做权限实测的 cd5cd580、697ccda9、996bf975
   都收到「你是模块 alpha 的模块会话」（5dd08a92、d6d38f60、196c085c 第 4 行）。
5. 本机 Claude Code 桌面版的命令环境里有 `CLAUDE_CODE_SESSION_ID`（与会话记录文件名、钩子 payload 的 `session_id` 同一个值）和
   `CLAUDE_CODE_HOST_SESSION_ID`（桌面版会话 id，`local_…`）。2026-10-20 在本会话的 Bash 实测。
6. Task 1 实测（2026-10-20，scratchpad 临时仓库，记录钩子写日志）：同一会话启动、桌面版里续聊、命令行 `claude --resume` 接上、`/compact` 压缩、压缩后再接上，
   钩子 payload 的 `session_id` 与环境变量 `CLAUDE_CODE_SESSION_ID` 始终是同一个值；但 `CLAUDE_CODE_HOST_SESSION_ID` 是**从父进程继承的**——从本会话的 Bash 里起的进程，
   钩子读到的是本会话的桌面版 id，不是被接上的那个会话的。所以它不能用来认会话。

## 假设（请逐条确认）

1. 发 0.9.0，做成一个修复模块，不拆成三个：三处改动都是「收窄收件对象」，相互独立但都小。
2. 审查者负责范围用「模块 × 节点」两维；旧登记没有范围的审查者，升级后**不再送审**（不默认全部），`review add` 输出一行提醒用户补登记。
3. 一个交审有多个审查者的范围都覆盖时，全部送到（多段审查本来就允许），登记时如果范围和已有审查者重叠，输出一行提示，但不拒绝。
4. 会话身份只用钩子 payload 的 `session_id` 核对（现场事实 6：压缩、接上会话后不变）；不用 `CLAUDE_CODE_HOST_SESSION_ID`（会从父进程继承，认错会话）。
   桌面版退出重开整个应用后的情况没有实测（见风险）。
5. 由会话自己登记身份：模块会话按开工说明第一步跑 `module-crew bind`，模块协调在跑 `start` 时自动登记（升级前开的协调会话手动跑一次 `bind`）。
   命令从自己的环境变量读会话 id，所以只能登记「正在跑命令的这个会话」，不能替别的会话登记。
6. 升级到 0.9.0 时，已在跑的会话都还没登记身份，钩子对它们只注入那一句「你不是登记会话」，直到它们跑一次 `bind`。
   本机按记忆在阶段丙-2 结束前不升级，所以不影响正在进行的演练。
7. 本模块不改契约，不需要契约负责人参与。

## 关键决策与取舍（请重点审）

1. **审查者范围的写法**：`source add <名> --kind lead --modules <a,b|全部> --nodes <spec,plan,interface,final|全部>`，两个参数对 lead 都必填，hub 不能带。
   已登记的审查者用新命令 `source scope <名> --modules … --nodes … --original-file <原话>` 补登记或修改。`source list` 显示范围。
   范围只决定送审给谁，不影响【负责人转交】批准来源的校验。
2. **没有匹配的审查者**：不送审，照「不配审查者时照常可用」的路径走（交审直接等用户批），输出写明「没有审查者负责 <模块> 的 <节点>，未送审」。
3. **挂起模块与请求方**：`change land` 跳过挂起中的模块，**例外是提出这条请求的模块**：它要收到带「回复：#N」的那条，才能关掉自己的等待。
   这和现有「等最终验收的模块跳过、请求方例外」是同一个规则。
4. **恢复时补发**：`resume` 的待办把「挂起期间合入的模块」和「挂起期间落地的公共变更 C<N>」合在一句里，先同步、跑完整检查再继续。
5. **身份登记存什么**：会话登记加 `hostSession: {"sessionId", "boundAt"}`，`sessionId` 取命令环境里的 `CLAUDE_CODE_SESSION_ID`（Codex 取 `CODEX_THREAD_ID`，只记录、不用于钩子）。`bind` 的规则：
   - 登记里没有身份：写入；
   - 已是同一个会话：不改，输出「已登记」；
   - 已是另一个会话：拒绝，提示走 `takeover`。`takeover` 记下用户同意时清掉旧身份，新会话按恢复说明 `bind`。
6. **钩子怎么判**：先照旧按角色标记或目录找出「这个目录属于哪条登记」，再核对会话 id：
   - 对上：照旧注入角色（启动注入和每轮一行都不变）；
   - 对不上，或登记还没有身份：只在 SessionStart 注入一句「本目录属于模块 X（登记会话 <邮箱名>）／本目录是 module-crew 的集成 checkout（模块协调 <邮箱名>）；你不是它的登记会话，
     不要按那个角色行事。如果你刚收到这个模块的开工说明或恢复说明，先按说明跑 module-crew bind」；UserPromptSubmit 不注入。
   - 不认会话 id 的场合（payload 里没有 `session_id`）按「对不上」处理。
7. **`status`** 在会话一栏标出「未登记身份」，方便模块协调发现没跑 `bind` 的会话。

## 验收标准

1. 登记两个审查者，范围分别是 {alpha: spec,plan} 和 {全部: final}：alpha 的 Spec 交审只送第一个，beta 的最终验收只送第二个，beta 的 Spec 交审两个都不送、输出写明未送审。
2. `source add --kind lead` 不带 `--modules` 或 `--nodes` 被拒、什么都不写；旧登记（没有范围）的审查者不收交审，输出提醒补登记；`source scope` 能补登记，`source list` 显示范围。
3. 模块 beta 挂起时 `change land`：beta 收不到同步基线；提出请求的模块即使挂起也收到回复；`resume beta` 的通知里写明挂起期间落地的 C<N>。合入后的同步基线（`merge run`）行为不变。
4. 钩子：同一个 worktree 里，登记会话的 SessionStart 与每轮注入角色不变；另一个 `session_id` 的会话只在 SessionStart 收到那一句，每轮不注入；集成 checkout 同理（重放 38932d81／cb182a33 的场景）。
5. `bind`：没有身份时写入；同一会话重跑不改；另一会话被拒并提示 `takeover`；`takeover` 之后新会话能 `bind`。开工说明、恢复说明、`start` 跑完后的提示都带 `bind` 这一步。
6. 实测（Task 1）：压缩、接上同一会话后 `session_id` 不变（已做，见现场事实 6）。
7. 两份 crew-dev skill、crew-coordinator skill 写明 `bind` 与审查者范围；skill 测试断言；全量测试与旧称扫描通过。

## 风险

- 桌面版退出重开整个应用后没有实测（命令行 `--resume` 走同一套会话恢复，已实测不变）；万一 `session_id` 变了：登记会话会被当成「不是登记会话」，只剩那一句注入；补救是重跑 `bind`（会被拒，要走 `takeover`）。
- 升级后忘了 `bind`：钩子不再给它注入角色，它只能靠开工说明和 skill 行事；`status` 的「未登记身份」用来提醒。
- 审查者 `review note` 仍不核对是否收到过这条交审，范围外的审查者如果主动发结论还是会被记下（不做，留作后续）。

## 文档建议

- README：0.9.0 的变化、`source add` 的新参数与 `source scope`、`bind`（本模块内做）。
- 其他跨模块文档：无。

## 变更记录

- 2026-10-20：初稿，待用户审。
- 2026-10-20：Task 1 实测后修订——身份只认 payload 的 `session_id`，去掉 `CLAUDE_CODE_HOST_SESSION_ID` 备用核对与 `hostSessionId` 字段（它从父进程继承，会认错会话）；补现场事实 6，改假设 4、关键决策 5、验收 6 与风险。来源：本模块 Task 1 实测。
- 2026-10-20：构建中补改——审查者可负责的节点补上 interface（接口提案）：【交审】的节点本来就有「接口提案」，只写三种会让接口提案永远送不到审查者；改范围第 1 条与关键决策 1。来源：Task 2 实现时核对 `protocol.REVIEW_NODES`。
