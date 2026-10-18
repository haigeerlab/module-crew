# 第 7 关试点报告

> 2026-10-18。试点项目 `/Users/vilin/Documents/haigeerlab/crew-pilot`（本机裸仓库远端 `crew-pilot-remote.git`），
> module-crew 以本地插件 `module-crew@module-crew-local`（a93dd6e）安装，spec-guard 0.68.0，agent-relay 0.8.2。
> 原始时间线：`/Users/vilin/Documents/haigeerlab/crew-pilot-notes.md`（协调会话记录）。
> 两轮：第一轮跑到合入本地 main 后停下修缺陷 A–G；修好后用新版收尾（补勾、推送、收回、退役），又发现 I–K 并修复。

## 跑了什么

一个协调会话 + 两个模块会话（slugify、palindrome），都是 Claude 桌面版会话，权限模式 auto。

| 时间 | 节点 | 结果 |
|---|---|---|
| 11:10 | `status`、`start plan` | 体检全绿；提议 slugify、palindrome（wordcount 为「进行中」不在可开工列表，符合预期） |
| 11:11 | 用户批准开工 → `start prepare` | 两个 worktree、角色标记、会话登记、开工说明；退出码 0 |
| 11:12 | 开两个模块会话 | 开工说明作第一条消息 |
| 11:13 | 4 条【交审】（Spec、Plan 各两条） | 开工后约 2 分钟交回；`review add` 全部 0 |
| 11:15 | 用户批准 → `review approve 4 5 6 7` | 集成分支提交带评审标记的 6 个文件；4 条【用户答复】+ 2 条开工通知经 agent-relay 发出 |
| 11:16 | 两条最终验收【交审】 | 开工通知后约 1 分钟交回 |
| 11:18 | 用户批准 → `merge approve` ×2、`merge run` ×2 | 两个模块 `--no-ff` 合入本地 main（71cf0b6），完整检查 14 个测试通过 |
| 11:19 | `merge push-plan` | 预告推到 `crew/batch-25`，10 个提交；用户决定先修缺陷，未推送 |
| 11:3x | 修复后 `merge tick` ×2 | 集成分支补勾两个模块的最终验收（1c34665、3e96819） |
| 11:40 | 用户授权 → `merge push` | 推到本机远端 `crew/batch-26`，远端 main 未动；开 PR 一步报错（问题 J） |
| 11:41 | 用户同意 → `merge cleanup` ×2、退役两个邮箱名 | worktree 收回、分支保留；邮箱名用 agent-relay 运维脚本退役（问题 K） |

从开工到两个模块合入本地集成分支约 8 分钟。

## 验证到的

- 真实 spec-guard 0.68.0：`/map --json` 的 `startable`、`checkoutRole` 写角色、`reviewMark` 写评审标记都按 interface 1.1 工作。
- 会话之间真实收发：【交审】【用户答复】【协调通知】【等待其他会话】都经 agent-relay 送达，`bodyFile` 原样发出，`replyTo` 对得上。
- 批准只来自用户在协调会话亲手输入的话（三次：开工、批量审批、最终验收）。
- 两个模块真正同时开发，互不冲突；冲突时取集成分支版本的规则模块会话照做了。
- **权限弹窗**：协调会话侧 0 次（auto 模式）；模块会话侧未见「等待审批」状态。默认权限模式下的弹窗次数未测。

## 发现的问题

| # | 问题 | 影响 | 性质 |
|---|---|---|---|
| A | 第二次 `merge run` 给**已合入、已收尾**的 slugify 发「同步基线…继续」，与收尾通知矛盾 | 照做会在已收尾的 worktree 上继续动 | 缺陷（crew-merge） |
| B | 模块收到最终验收批准后才勾 todo 末项并提交，而 `merge run` 已合入勾选前的提交；main 里两个模块的末项都没勾 | spec-guard 把两个模块显示为「暂停：1 个未勾选项」，`status` 仍算「进行中」；slugify 开了等待单 #25；module-crew 没有补救命令 | 缺陷（crew-merge 与 crew-dev 的先后没对齐） |
| C | `merge run` 给**仍在合并队列里**的 palindrome 发「同步基线」；照做会多一个提交，它自己的合并就会被「交审后又有提交」拒掉 | palindrome 自判没执行，这次没出事 | 缺陷（crew-merge） |
| D | 协调会话自己的邮箱名（`pilot-coord`）没人注册：skill 与 `start prepare` 都没提 | 协调会话手动 `bridge_register` 才收得到消息 | 缺口（crew-start、crew-coordinator skill） |
| E | `merge approve` 只收一个编号，`review approve` 收多个；skill 没写 | 退出码 2，逐个重跑 | 不一致（crew-merge） |
| F | 开会话工具 fresh 模式强制附 ≥80 字背景，第一条消息做不到「只有开工说明」 | 无实际影响，协调会话把背景标成「不是开工说明」 | 宿主限制（写进 skill） |
| G | `review batch` 没有冲突段落，「没有冲突」与「不输出」分不清 | 审批时少一条明确信息 | 小改进（crew-review-batch） |
| H | 加载 skill 时显示的目录是开发源目录，不是插件安装副本 | 本次两份内容相同，无影响 | 宿主行为：本地目录市场的插件直接从源目录读（`claude plugin update` 明说「read from its folder」），缓存副本只在安装时复制一次，只记录 |

| I | 等待单 #25 关不掉：发单的模块已收回、不能再发【已恢复】，module-crew 也没有关单命令 | 等待单永远开着 | 缺口（crew-onboarding） |
| J | `merge push` 推送成功却退出码 4：事务提交前就调 `gh`，正文文件还没落盘；远端不是 GitHub 时也去开 PR | 误报失败 | 缺陷（crew-merge） |
| K | skill 写「用 agent-relay 退役邮箱名」，但 agent-relay 0.8.2 没有退役工具，只有运维脚本，且未登记在 interface.json | 协调会话自己找脚本 | 过时（crew-merge、skill）；agent-relay 负责人确认接口保持 2.5、由用户经 `/agent-relay:collaboration` 退役 |

已核对、不算问题：palindrome 用 12 位指纹被接受——session-protocol 规定指纹取 12～64 位。

## 修复（2026-10-18，用户批准）

Spec 修订 ce26d8b（crew-merge、crew-start、crew-review-batch），实现 79daaf5，全量 233 个测试通过，插件已重装（缓存副本也是 79daaf5）。

| # | 修法 |
|---|---|
| A、C | 同步基线只发给还在开发的模块：跳过已合入的、仍在合并队列里的 |
| B | `merge run` 合入通过检查后，在集成分支勾上模块 todo 唯一的未勾项（单独提交）；crew-dev 改为获批后不自己勾；`merge tick` 补救修订前漏勾的数据 |
| D | `start prepare` 输出与协调会话 skill 提醒先注册 `<简称>-coord` |
| E | `merge approve` 一次可收多个编号，任一不合格什么都不写 |
| F | 协调会话 skill 写明强制背景要标明「不是开工说明的一部分」 |
| G | `review batch` 明确输出「依赖：全部就绪」「并行边界重叠：无」 |
| I | 新增 `ticket close --reason happened|user`（契约第 11 节理由 3、4）；`merge cleanup` 列出模块开着的等待单；skill 加「等待单」一节（Spec 6633a88，实现 3a14189） |
| J | `merge push` 先提交推送记录与正文再调 `gh`，开好后另记 PR 链接；只对 github.com 远端开 PR，其他远端打印正文、退出码 0 |
| K | `merge cleanup` 列出「待退役的邮箱名」，由用户同意后经 `/agent-relay:collaboration` 退役；module-crew 不定位、不运行 agent-relay 脚本 |

第二轮修复后全量 239 个测试通过，插件重装为 3a14189。

## 还没做

- 等待单 #25 仍开着（用户决定挂着；现在可以用 `ticket close 25 --reason happened` 关）。
- `gh` 真正开 PR（远端是本机裸仓库，按修复后的规则只打印正文）。
- 换会话恢复（`resume-kit`、`takeover`）、挂起、退回串行、合并失败退回：这次都没遇到，未实地验证。
- 默认权限模式下的弹窗次数；预配工具许可的效果。

## 验收

- 2026-10-18 用户批准：I、J、K 修复验收通过，第 7 关最终验收通过。

---

# 第二轮试点（默认权限）

> 2026-10-18。同一试点项目，搭场提交 637775b（新增 caesar、vowels、acronym 三个模块与检查开关 `tests/test_gate.py`）。
> 插件 a6226c5，spec-guard 0.68.0。协调会话与三个模块会话**都用默认权限模式**（第一轮是 auto），专门看弹窗对并行流程的影响。
> 原始时间线：`crew-pilot-notes.md` 的「## 第二轮」一节。

## 场景与结果

| 场景 | 做了什么 | 结果 |
|---|---|---|
| 0 换协调会话 | 新会话加载 skill → `status` → 用户同意 → `takeover pilot-coord` | ✅ 状态与接管前一致；agent-relay 重新注册要传接管参数 |
| 1 开工 | `start plan` 提议三个 → 用户答「3」→ `start prepare` → 三个模块会话各一轮交回 Spec／Plan | ✅ 6 条交审、`review batch` 带「依赖」「并行边界」两段 |
| 2 挂起与恢复 | 批准 caesar、acronym；`suspend vowels`；后来 `resume vowels` 并批准它的 Spec／Plan | ✅ 挂起不占名额、恢复重新占名额；问题 H、I、L、M |
| 3 崩溃换会话 | caesar 已交最终验收时归档它的会话 → `resume-kit` → `takeover pilot-caesar` → 原 worktree 开新会话 | ✅ 新会话没有重做、没有重发；问题 J（靠 `status` 自己纠正） |
| 4 合并失败退回 | 打开检查开关后 `merge run` | ✅ 退出码 5、撤销合并、发退回通知；**问题 K**：模块要自己撤销那次撤销才能重新合入 |
| 5 退回串行 | vowels 构建中 `serial` → `start plan` 退出码 3；vowels 照常交审、合并；`serial --off` | ✅ 已开模块不受影响；问题 O、P |
| 收尾 | 三个 `merge cleanup`，列出待退役邮箱名 | ✅ worktree 收回、分支保留 |

最终：本地 main 65e3f1c，33 个测试通过，未推送；状态库未关事项 0，等待单只剩第一轮的 #25。
第一轮修过的 B（自动勾选）、C（不给排队中的模块发同步）、D（提醒注册协调邮箱名）、E（多编号批准）、G（批次两段）都在实地生效。

## 权限弹窗（默认权限）

| 会话 | 弹窗 | 备注 |
|---|---|---|
| 协调会话 | 至少 1 次 | 约 12:57 有一次；往共享笔记目录追加内容的命令疑似也在等确认 |
| caesar（原会话） | 有，次数未记 | 模式中途变成 acceptEdits |
| caesar（恢复会话） | 未见 | 模式保持 default |
| vowels | 至少 2 次 | 构建时、读收尾通知时；模式变成 acceptEdits |
| acronym | 至少 2 次 | 13:15 一条只读命令被中断（用户说没点拒绝，原因不明），那一轮中止；模式变成 acceptEdits |

结论：默认权限下每个模块会话每轮都可能停在弹窗上，协调会话只能从「需要用户」状态看出来、不能替用户点；
三个模块会话的权限模式都从 default 抬到了 acceptEdits，skill 只在开会话那一刻核对，之后没人发现。

## 发现的问题

| # | 问题 | 影响 | 性质 |
|---|---|---|---|
| G | 空闲的桌面版会话收不到 agent-relay 的叫醒：`bridge_send` 全是 queued，警告「Claude session is not running」 | 全程靠协调会话用桌面版跨会话消息手动叫醒 | 宿主／agent-relay 行为；module-crew skill 没写怎么办 |
| H | `start plan` 把已开工、已挂起的 vowels 当成新模块提议 | 用户若答应会重复开工 | 缺陷（crew-start） |
| I | 协调会话挂起或恢复模块时没有协议消息：【协调通知】没有这两种类型，`suspend` 也不生成通知 | 只能发普通消息，`protocol check` 报 unknown-kind | 契约缺口（session-protocol） |
| J | 恢复说明的「当前」一行写「可以构建」，没提未关的最终验收交审 #45；还带一句「刚压缩过」 | 新会话可能重做或重发 | 缺陷（crew-recovery-hooks） |
| K | 合并检查失败时用 `git revert` 撤销：模块分支的提交已进入集成分支历史，再合并带不进任何改动，同步基线还会删掉模块自己的文件 | acronym 自己撤销那次撤销才绕过去；通知没提示 | **严重缺陷**（crew-merge） |
| L | `merge run` 给挂起中的 vowels 发「同步基线…后继续」 | 「继续」与挂起矛盾，它的 Spec／Plan 当时还没批准 | 缺陷（crew-merge） |
| M | `resume` 不收用户原话，`suspend` 要 | 恢复的同意不进状态库 | 不一致（crew-failure） |
| N | 请用户给原话时没给可复制的句子 | 用户不知道怎么回 | 已修（a6226c5） |
| O | 已合入的模块要等 `merge cleanup` 才让出名额 | 串行前 `start plan` 显示「空位：0」 | 不一致（crew-start） |
| P | `start plan` 退出码 3 却不说原因（能力图上剩下的 wordcount 是 spec-guard 的当前模块、report 等它） | 协调会话没有可以告诉用户的阻塞项 | 缺陷（crew-start） |
| 漂移 | 模块会话的权限模式中途变宽，skill 没有后续核对 | 违反「模块会话不比协调会话更宽」 | 缺口（crew-coordinator skill） |

小项（不单独修，写进对应修法或文档）：合并队列「队首」按交审事项号排，skill 没写；退回原因只给 unittest 的点阵，不说哪个测试失败；
`status` 的「进行中：wordcount」其实是 spec-guard 的当前模块，没开工；指纹 16 位与 64 位都被接受（符合契约）。

## 修复

用户 2026-10-18 批准修法（含向契约负责人提 v1.8、向 agent-relay 负责人报告 G）。全量 279 个测试通过。

| # | 修法 |
|---|---|
| K | 检查失败时先核对集成分支顶端正是本次合并提交，再 `git reset --hard` 回合并前；模块分支不动，修好后再合能带入全部改动；对不上就不动、退出码 4。退回通知附 FAIL／ERROR 行 |
| L | 同步基线不发给挂起中的模块；恢复类通知写明挂起期间合入了谁、先同步再继续 |
| M | `resume` 必须带用户原话 |
| I | 契约 v1.8（c982bc3）新增挂起、恢复类【协调通知】；`suspend`／`resume` 记一条已答事项并生成正式通知，样例改钉 v1.8（解析 64 份） |
| H、O、P | `start plan` 不提议已有会话（含挂起）的模块；已合入的模块不占名额；没有可开的模块时逐个写原因 |
| J | 新档位「最终验收已交审（交审事项 #N），等用户批准；不要重做或重发」；恢复说明不再带压缩提示；只读出口 stage 枚举不变 |
| G | agent-relay 负责人确认是宿主限制（桌面版停掉空闲会话）；两份 skill 写明 `pendingReason: offline` 时用桌面版跨会话消息发一句「去读 agent-relay 收件箱」，不带正文 |
| 漂移 | 协调会话每次醒来核对模块会话权限模式，比自己宽就告诉用户，由用户决定 |
| 小项 | skill 写明合并队列按 Build order 排；README「尚未验证」按两轮结果重写 |

## 第二轮验收

- 2026-10-18 用户批准：第二轮修复（5715986）最终验收通过，6 份 Spec（crew-merge、crew-start、crew-failure、crew-recovery-hooks、crew-onboarding、crew-protocol）与能力图的修订复审通过；同意回告 LIVE-SAAS 方案会话。

- 2026-10-18 用户批准：0.1.1（b70ac3b）验收通过——提交过 commitlint、钩子拒绝单独标原因、负责人转交只记账、收件枢纽批准记 #H；crew-hub-bridge、crew-merge、crew-review-batch、crew-shared-changes 的修订复审通过。

- 2026-10-18 用户批准：0.2.0（4145e8b）验收通过——Codex 模块会话（crew-codex-host）、批量交审按模块分组、【撤回】规则、status 措辞、改钉契约 v1.9；crew-review-batch、crew-hub-bridge、crew-probe、crew-protocol 的修订复审通过；联合演练第一波用 0.2.0。

- 2026-10-18 用户批准：0.2.1（bc5cd26）验收通过——修复联合演练批 2 第 3 步报来的缺陷：先 `source add` 再第一次 `start prepare` 崩溃（KeyError: crewDir）；运行配置是否写定改按 `crewDir` 判断，首次写入保留已登记的来源，退回串行同样改按 `crewDir` 判断；Spec 未改；演练现有状态库可直接继续。
