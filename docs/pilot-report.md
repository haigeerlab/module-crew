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
