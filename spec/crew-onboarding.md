<!-- spec-guard: review approved e0241ca063f1 -->

# Spec: crew-onboarding

> 能力图模块 `crew-onboarding`。需求来源：`docs/requirements-record.md` B1（角色与职责、权限弹窗）、B4（消息、答复有效性、被挡住必须报、规则不写进 worktree）、
> 第 7 节（对话里不留唯一副本）；契约 session-protocol v1.3 第 4、5、8、9、11 节。假设见下文，用户 2026-10-18 已确认。

## 目标

让协调会话和模块会话「知道怎么说话、怎么记账」：两份 skill 写清各自的规则；协调会话收到的等待类消息与它转达的用户答复，
由命令判断并记进状态库，会话只照做。这样换会话、压缩之后，谁在等什么、哪件事用户答了什么，都能从状态库查到，不靠对话记忆。

## 范围

**范围内**

- `skills/crew-coordinator/SKILL.md`、`skills/crew-dev/SKILL.md`。
- `module_crew/inbox.py` 与两个命令：`module-crew inbox add`、`module-crew answer`。
- `item`（待用户决定事项）与 `ticket`（等待单）两种记录的字段与状态流转。

**范围外**

- 【交审】【公共变更请求】的记账（crew-review-batch、crew-shared-changes）；本模块只解析它们，不合格的给出退回原因。
- 开会话、注册邮箱、写开工说明（crew-start）；每轮注入与 `takeover`（crew-recovery-hooks）；巡视与超时（第一版不做）。
- 发消息本身：命令只生成正文文件和发送参数，由会话调用 agent-relay `bridge_send`。

## 假设（用户 2026-10-18 已确认）

1. 两个 skill 放插件 `skills/`，不写进任何 worktree 的 CLAUDE.md；由开工说明点名加载；本模块不做钩子。
2. 协调会话用记账命令：`inbox add` 解析【等待用户】【等待其他会话】【已恢复】【撤回】并记账或给出退回原因，【等待用户】按契约默认取代；`answer` 生成【用户答复】正文、写进状态库、打印正文路径、记事项已答；【交审】【公共变更请求】只解析不记账。
3. 用户原话真实性靠 skill 规则（只转达用户在本会话亲手输入的话）；命令原样保存传入的原话。
4. 模块会话核对答复靠 skill 规则：`protocol check`、发件人是登记的在用协调会话、原消息号是自己发过的（用 `bridge_outbox` 核对）、执行前回显。
5. 权限弹窗：协调会话醒来时看 agent-relay 在线状态里的「等待审批」，提醒用户去那个会话点。（2026-10-18 补充）醒来时还核对各模块会话的权限模式，比本会话宽（plan < default < acceptEdits < auto < bypassPermissions）就告诉用户、由用户决定，协调会话不自己改。
6. 被挡住必须发【等待其他会话】；模块做完发节点为最终验收的【交审】。
7. 邮箱身份 `<项目简称>-coord`／`<项目简称>-<模块 id>`、`wake: "auto"`，注册归 crew-start，skill 只写换会话后按状态库登记重新注册；`takeover` 归 crew-recovery-hooks。

## 关键决策与取舍（请重点审）

1. **记录状态只有 `open`／`closed` 两种，关闭原因单独记。** 这与 crew-probe 的「未关 = `state` 不是 `closed`」一致。
   事项的关闭原因：`answered`／`superseded`／`withdrawn`；等待单用契约第 11 节的 1～4。
2. **只收登记过的在用模块会话的消息。** `--from` 不是状态库里 `active` 的 `dev` 会话时拒收（退出码 3），不记账。
   这样别的会话误发或冒名的消息进不了账；代价是 crew-start 之前没法用 `inbox add`（本模块的测试直接往状态库写会话登记）。
3. **编号对应：结束行与【撤回】里的 `#N` 先按状态库编号找，找不到再按该发件人自己的邮箱号找；只认同一发件人的记录。**
   对不上的编号不报错，在输出里列为「没对上」，由协调会话决定是否追问（契约：结束写法不能代替有效性核验）。
4. **默认取代按契约第 4 节**：同一发件人新的【等待用户】没写标记时，关掉它所有 `open` 的【等待用户】事项（原因 `superseded`），
   并在输出里给出要转告发件人的原句「#旧 已被新事项自动取代；确实要两项都答，请写【与 #旧 并行】重发」；写了【与 #N 并行】的不取代 #N；
   写了【取代 #N】的只取代 #N。多线事项（带「适用会话」）与单线互不取代。
5. **`answer` 只接受 `open` 的事项，选项字母必须是该事项里有的；原话可从 `--original` 或 `--original-file` 传入**（多行原话用文件，避免 shell 引号改写原话）。
   一次 `answer` 在同一事务里：分配编号、写正文、把事项关为 `answered` 并记下原话、答复时间与正文编号。命令输出发送参数：收件人、`replyTo`、正文绝对路径。
6. **原始消息全文进状态库**：`inbox add` 把收到的原文存进记录的 `text` 字段，换会话后能原样核对，也不用回到邮箱翻。

## 接口约定

### 记录字段

```json
// item（键 = 编号）
{"state": "open", "kind": "wait-user", "from": "shop-crew-store", "relayId": 4540, "text": "【等待用户】\n...",
 "decide": "要你决定原文", "options": [{"letter": "A", "text": "..."}], "recommended": "A", "fullyStopped": true,
 "multiline": false, "closedReason": null, "answer": null}
// 答复后：state=closed, closedReason=answered, answer={"original": "...", "option": "A", "answeredAt": "...", "body": 13}

// ticket（键 = 编号）
{"state": "open", "from": "shop-crew-store", "relayId": 4551, "text": "...", "waitingFor": "API", "what": "...",
 "closedReason": null, "closedBy": null}
// 关闭后：state=closed, closedReason=1..4, closedBy=关闭它的那条消息的邮箱号
```

事件动作：`item.created`、`item.superseded`、`item.withdrawn`、`item.answered`；`ticket.opened`、`ticket.closed`。

### 命令

```bash
bin/module-crew inbox add <文件> --from <邮箱名> --relay-id <M>
bin/module-crew answer <编号> (--original <原话> | --original-file <文件>) [--option <字母>]
```

- `inbox add` 输出：类型、分到的编号（或关掉的编号）、没对上的编号、要转告发件人的原句；退出码 `0` 记账成功，`3` 消息不合格或发件人未登记（打印问题代码与退回原因，不写任何东西），
  `4` 合格但这种消息不由本命令记账（【交审】【公共变更请求】），`2` 参数错或未建库。同一发件人同一 `--relay-id` 重复提交时不重复记账，退出码 0 并说明「已记过」。
- `answer` 输出：`收件人`、`replyTo`、`正文文件`（绝对路径）三行，供 `bridge_send` 使用；退出码 `0` 成功，`3` 事项不存在、已关闭或选项不存在，`2` 参数错。

### skill 要点

- **crew-coordinator**：只统筹不开发、不出审查结论、不替用户决定；收到消息先存文件再 `inbox add`，按退出码处理（3 退回原因原样发回、4 交给对应模块的命令）；
  把【等待用户】转述给用户时附上事项编号与选项；只把用户在本会话亲手输入的话交给 `answer`；用 `bodyFile` 发出 `answer` 生成的正文，不手改；
  每次醒来先跑 `module-crew status`，再看 agent-relay 在线状态里「等待审批」的会话并提醒用户去点；【协调通知】不是批准。
- **crew-dev**：只做分配的模块、不改公共文件（要改就发【公共变更请求】）、不创建会话、只和协调会话说话；发出前用 `module-crew protocol check` 自检；
  被挡住必须发【等待其他会话】，恢复发【已恢复】；做完发节点为最终验收的【交审】；只认协调会话转来的【用户答复】，执行前回显「收到用户对 #N 的答复：『原话』」；
  换会话后按状态库的会话登记重新注册同一个邮箱名。
- 两份 skill 都写明：规则来自本插件，不要抄进 worktree 的 CLAUDE.md。

## 项目结构

```text
skills/crew-coordinator/SKILL.md
skills/crew-dev/SKILL.md
module_crew/inbox.py               记账逻辑
module_crew/__main__.py            加 inbox add、answer
tests/test_inbox.py                记账与流转
tests/test_answer.py               答复生成与记账
tests/test_skills.py               skill 结构与关键规则
```

## 命令

```bash
python3 -m unittest discover -s tests -v
```

## 代码风格

沿用前几个模块；解析一律走 `module_crew.protocol`，状态一律走 `module_crew.store` 的事务，不另写文件。

## 测试策略

- 每个测试建临时仓库与状态库，直接写入 `coordinator` 与 `dev` 会话登记，用契约样例风格的消息文本喂 `inbox add`。
- 流转覆盖：新建、默认取代、显式取代、并行、撤回、结束行关单（状态库编号与邮箱号两种）、没对上、重复提交、未登记发件人、不合格消息。
- `answer` 的正文与 `protocol.render_user_reply` 逐字一致，并能被 `protocol.parse` 读回原话。
- skill 用结构检查（frontmatter 的 `name`、`description`）和关键规则短语检查；语义靠评审。

## 边界

- **始终**：先解析再记账；拒收时什么都不写；正文由命令生成。
- **先问**：新增记录字段之外的顶层种类；改变「只收登记会话」的规则。
- **绝不**：替会话发消息；改写用户原话；把规则写进项目文件。

## 验收标准

1. 登记过的 `dev` 发来合格【等待用户】：记成 `item`，`open`，带原文、选项、推荐、是否完全停住；输出编号。
2. 同一发件人再发无标记的【等待用户】：旧的 `open` 单线事项关为 `superseded`，输出含要转告的原句；写【与 #旧 并行】时旧事项保持 `open`；写【取代 #N】时只关 #N。
3. 【等待其他会话】记成 `ticket`；它的「结束：#旧」关掉同一发件人的旧等待单（原因 2）；【已恢复】的「结束：#a、#b」关单（原因 1），#a 用状态库编号、#b 用邮箱号都能对上；对不上的列为「没对上」。
4. 【撤回】「事项：#N」关掉同一发件人的事项（`withdrawn`）；别人的事项不受影响。
5. 不合格消息、未登记或已退役的发件人：退出码 3，打印问题代码与原因，状态库逐字节不变。
6. 合格的【交审】【公共变更请求】：退出码 4，状态库不变；不合格的退出码 3。
7. 同一发件人同一 `--relay-id` 再提交一次：退出码 0、「已记过」，状态库不变。
8. `answer`：生成的正文与 `render_user_reply(item, original, answeredAt, option_text, source_relay_id)` 逐字相同；事项变为 `closed`/`answered` 并记下原话与正文编号；输出收件人、`replyTo`、正文绝对路径。
9. `answer` 对不存在、已关闭的事项或不存在的选项字母：退出码 3，状态库不变；`--original-file` 传入的多行原话逐字保留。
10. `status` 的未关计数随这些流转正确变化（与 crew-probe 的约定一致）。
11. 两份 skill 有合法 frontmatter（`name`、`description`），并包含：`inbox add`、`answer`、`bodyFile`、「等待审批」、「不是批准」（协调会话）；`protocol check`、【等待其他会话】、【交审】、「最终验收」、回显句式（模块会话）；以及「不要抄进 worktree 的 CLAUDE.md」。

12. `ticket close <编号> --reason happened --original-file <说明>`：开着的等待单关为原因 3（所等的事已发生）并记下说明；`--reason user` 关为原因 4（用户关闭）并记下用户原话；
    不存在、已关闭或说明为空：退出码 3，状态库不变。协调会话 skill 有「等待单」一节：模块还在时办好它等的事、请它发【已恢复】自己关；模块已收回或用户说关时用 `ticket close`。（2026-10-18 修订）

13. 两份 skill 写明叫醒：`bridge_send` 结果的 `wake.pendingReason` 为 `offline`（或 queued 且带 not running 警告、`presence.state` 为 `stopped`）时，Claude 会话用桌面版跨会话消息发一句不带正文的「去读 agent-relay 收件箱」；Codex 会话做不到，交用户打开对方会话。协调会话 skill 写明权限模式核对与合并队列按 Build order 排。

## 未决问题

无。

## 文档建议

README 的「一次完整流程」里引用两份 skill 的要点；本模块不另写文档。

## 变更记录

- 2026-10-18：增加 `ticket close`，按契约第 11 节原因 3（所等的事已发生）或 4（用户关闭）由协调会话关等待单；协调会话 skill 加「等待单」一节；增加验收 12。原因：试点中发单的模块已收回、无法再发【已恢复】，等待单 #25 关不掉（问题 I）；来源：第 7 关试点收尾（`docs/pilot-report.md`），用户 2026-10-18 批准。
- 2026-10-18：skill 增加空闲会话的叫醒做法（agent-relay 负责人确认为宿主限制 H1／H4，判断条件 `pendingReason == "offline"`）、协调会话醒来核对模块会话权限模式、合并队列按 Build order；补充假设 5，增加验收 13。原因：试点问题 G 与权限模式漂移；来源：第二轮试点（`docs/pilot-report.md` 第二轮一节），用户 2026-10-18 批准修法。
- 2026-10-19：两份 crew-dev 与模块协调 skill 增加：按评审节奏交审、返工与「不同意」、最终验收「验收标准与证据」、撤销批准通知、待决问题必须答全、合并前复述与 `merge revoke`、有决策收件箱时只在那里问（下一步框不放决定按钮）。原因：R1、R5、R13、R15、R17；来源：用户 2026-10-19 批准修订后的 crew-review-nearby Spec 与 Plan（决定 41、46、47、49；Task 7、9、11、13），随它的最终验收复审。
