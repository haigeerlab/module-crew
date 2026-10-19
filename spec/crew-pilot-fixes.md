# Spec: crew-pilot-fixes

<!-- spec-guard: review approved 58bd71357c8b -->

> 能力图模块 `crew-pilot-fixes`（第五版，0.6.0 两个模块之一）。需求来源：`livesaas-integration/REQ-DECISION-CARDS.md` 第二节「3. module-crew」的 MC-3～MC-8，
> 问题证据 `DECISION-INBOX-ISSUES-2026-10-19.md` 的 X-1～X-4、I-11、I-14 与 `REHEARSAL-LOG.md`（阶段丙）。由 di-p0-tester 经 Decision-inbox 第 3 阶段能力图会话、module-crew 插件开发会话转来。
> 用户 2026-10-19 在本会话确认 7 条假设（全部照推荐）。MC-1、MC-2（决策卡片字段）拆到 `crew-hub-card-fields`，等 session-protocol v2.3 定稿后写 Spec。
> 阶段丙冻结期间（决定 68）只开发、不升级 di-p0 用的版本。契约 session-protocol v2.2 不变。

## 目标

把演练阶段丙里反复打断用户的几处 module-crew 缺口补上：模块开工、同步时合入集成分支不再弹窗；模块写 Plan、返工前能读到审查原文而不去 worktree 外找；
撤回合并批准不再把早已被取代的交审重新打开，重交审后旧的合并批准自动作废；模块协调自己开的等待记录有账可查、该关时会被提示；
派活后主动发现模块会话卡在权限弹窗上。

## 范围

- 新命令 `module-crew sync`（模块 worktree 里跑）：合入集成分支、本模块 Spec 与 tasks 冲突取集成分支版本、报结果（MC-3、MC-5）。
- 开工、同步基线、恢复类【协调通知】与两份 crew-dev skill 改为「跑 `module-crew sync`」，不再叫模块自己敲 `git merge`。
- 新命令 `module-crew review show C<N>`（只读）：输出这份交审的审查原文全文与 sha256（MC-4）；返工通知与开工通知写明这条命令。
- `merge revoke`：只在被撤回批准对应的交审仍是该模块、该节点最新一份时才重开（MC-6）。
- 重交审（同一模块最终验收又来一份【交审】）时，该模块还开着的合并批准自动作废（O-stale-approval，随 MC-6 一起修）。
- 新命令 `module-crew wait add`：模块协调把自己发出的【等待其他会话】记账；所等的事项答复转达时，命令输出提示并给出要发的【已恢复】（MC-7）。
- 发出给模块的通知或转达答复的命令，输出末尾提示核对该模块会话是否卡在权限弹窗；crew-coordinator skill 写明派活后怎么查、卡住报什么（MC-8）。
- README、两份 crew-dev skill、crew-coordinator skill 相应更新；版本 0.6.0。

不做：决策卡片的「类型」与小项（`crew-hub-card-fields`）；决策收件箱的弹窗兜底与巡视（decision-inbox）；module-crew 代码读宿主或 agent-relay 的会话状态
（Python 进程读不到，只在 skill 里规定由协调会话用 agent-relay 工具查）；放行任何 `git merge` 写法（关键决策 1）；改契约。

## 现场事实（写 Spec 时核对，2026-10-19）

1. **X-1**：`permissions.py` 的放行清单 `ROUTINE` 只有 `git add/commit/status/diff/log/show`，没有 `git merge`；开工通知第一步却要求合入集成分支，所以每个模块开工都弹一次（REHEARSAL-LOG 21:00，#45、#46）。
2. **X-3 根因**：#51 给 epsilon 写入的是 `Bash(git merge main)`、`Bash(git merge --no-edit main)`（`crew-rehearsal-crew/epsilon/.claude/settings.local.json`，21:37）；
   epsilon 会话记录（13:32、13:51 UTC）实际敲的是 `git merge main --no-edit`，选项在分支名之后，两条都匹配不上。它还把合入和
   `S=… && printf … > $S/…`、`git checkout --theirs -- …`、`git merge-base --is-ancestor …`、`… | tail` 连成一条，其中几段本来也不在放行范围。
   Claude 对复合命令逐段判断，任一段没放行就弹窗（宿主事实见 `spec/crew-host-permissions.md`）。
3. **X-2**：审查原文只在 `review batch --for-hub` 生成收件箱正文时写进 `<状态库>/originals/`（集成 checkout 的 `.git/module-crew/` 下），审查有结论后从不发给模块；
   模块按习惯去那里读，worktree 外读文件要弹窗，而且审查中、返工中的交审根本没有原文文件（#41、#42、#46）。模块 worktree 已放行 `Bash(<module-crew> *)`。
4. **X-4**：`merge.revoke` 无条件把批准对应的交审改回 open。阶段丙里 summary 的最终验收 C77 获批（合并批准 C86）后，因同步基线 HEAD 变了重交审并再获批 C93；
   撤 C86 时 C77 被重开，`sessions` 里一直显示「未关事项：C77」。同一处还有 O-stale-approval：重交审后旧批准 C86 没作废，排在合并队列队首挡住 C93，多问了用户一次（#34）。
5. **I-11**：8738 是模块协调 rh2-coord 自己发给决策收件箱的【等待其他会话】（等 #47 的答复转达），#47 结项后没发【已恢复】。
   crew-coordinator skill 只规定「模块发的等待记录由模块自己关」，没有模块协调自己开的等待记录的规则；状态库也不记它。
6. **I-14**：#40、#44 结项后 delta、epsilon 都卡在权限弹窗上，收件箱 0 项待决，模块协调被提醒后才补报「去会话操作」。skill 只写了「看到等待审批就转达」，没写派活后回头查。

## 假设（用户 2026-10-19 已确认）

1. 拆两个模块：本模块（MC-3～MC-8）现在写；`crew-hub-card-fields`（MC-1、MC-2）等契约 v2.3 定稿，字段名照定稿。
2. 版本：本模块 0.6.0，`crew-hub-card-fields` 0.7.0；冻结期间只开发不升级 di-p0。
3. MC-3、MC-5：新增 `module-crew sync` 一次做完合入，走已放行的 `Bash(<module-crew> *)`，不新增 `git merge` 规则；通知改写「跑 `module-crew sync`」，crew-dev skill 规定单独执行、不连写；
   集成 checkout 不放行 `git merge`，免得绕过合并队列。
4. MC-4：新增只读 `module-crew review show C<N>`，返工通知与开工通知写明这条命令，模块不去 worktree 外读文件。
5. MC-7：模块协调自己开的等待记录也走 CLI 记账；所等的事发生（答复转达）时，命令输出直接给出要发的【已恢复】。
6. MC-6 一并修 O-stale-approval：同一模块、同一节点重交审后旧合并批准自动作废并告诉用户。
7. 回告 di-p0-tester：都不越界；MC-8 代码兜不住只能靠 skill 与收件箱兜底；MC-1、MC-2 要等契约定稿。

## 关键决策与取舍（请重点审）

1. **`module-crew sync`**（只在登记为在用的模块 worktree 里跑，别处拒绝并说明）：
   - 前提：工作区干净（`git status --porcelain` 为空），否则拒绝，说「先提交或收起改动再同步」；不替模块提交。
   - 执行 `git merge --no-edit <集成分支>`（集成分支取运行配置 `integrationBranch`）。已包含就输出「已是最新：<集成分支短提交>」。
   - 有冲突时：本模块的 `spec/<id>.md` 与 `tasks/<id>/` 下的冲突取集成分支版本（它带批准标记），`git add` 这些文件；
     其余冲突文件**不动、不中止合并**，列出清单，说明「用编辑工具解决后 `git add` 这些文件、`git commit --no-edit`，再跑一次 `module-crew sync` 确认」——编辑、`git add`、`git commit` 都已放行；
     只有本模块文件冲突时直接 `git commit --no-edit` 完成合并。
   - 结束时核对「集成分支已在 HEAD 祖先里」，输出 HEAD 短提交、合入了几个提交；不跑完整检查（检查命令已放行，由模块照通知自己跑）。
   - 退出码：0 完成或已是最新；2 有冲突待模块解决；3 拒绝（不在模块 worktree、工作区不干净、合并命令本身失败）。
   - Codex 模块 worktree 同样适用（`codex_rules` 已放行 module-crew 路径）。
   - 不放行 `git merge`：规则写法和模块实际敲法对不上就会再弹（现场事实 2），而走 module-crew 命令只需要一条已有的放行；
     模块会话若仍自己敲 `git merge`，照旧弹窗——这是 skill 违规，不再靠加规则掩盖。
2. **通知措辞**：开工（`review.py` 生成）、同步基线（`merge.py`、`changes.py`）、恢复（`failure.py`）类【协调通知】的「要你做什么」改为
   「跑 `module-crew sync` 把集成分支合进你的模块分支（单独执行，不和别的命令连写），再跑完整检查后继续」，开工通知保留「Spec、tasks 冲突取集成分支版本」由 sync 自动处理的说明。
   字段与类型不变，契约不受影响。两份 crew-dev skill 同步改写，并加一条：开工 Plan 里的「合入集成分支」步骤写 `module-crew sync`。
3. **`module-crew review show C<N>`**（只读，任何 checkout 都能跑）：
   - 对象是交审事项 C<N>；输出每一轮审查结论的原文（按收到顺序，标审查编号、审查者、结论、sha256），最后一轮在最后；没有结论时输出「C<N> 还没有审查结论」，退出码 0。
   - `--submission` 另外输出交审原文。不是交审事项、编号不存在：退出码 3。
   - 原文取自状态库里记账时存下的正文（`reviews[].text`、交审 `text`），不依赖 `originals/` 文件是否生成过。
   - 返工通知「要你做什么」末尾加一行「审查原文：module-crew review show C<N>」；开工通知对每个带审查结论的已批交审各加一行同样的说明（写 Plan、构建时吸收遗留建议用）。
4. **撤回批准不重开已被取代的交审**：`merge revoke` 关批准照旧；对应交审只有在「同一模块、同一节点没有编号更大的交审」时才改回 open（现行为）；
   否则保持关闭，输出「交审 C<旧> 已被 C<新> 取代，不重开」，通知模块的正文不变。
5. **重交审作废旧的合并批准**：记账一份最终验收【交审】时，若该模块有开着的合并批准，就把它关掉（`closedReason: superseded`，记下新交审编号），
   输出「合并批准 C<旧> 因重交审 C<新> 作废，合并队列不再取它；告诉用户：之前批的那次验收作废，新的一份会另外提请」。
   只对最终验收；Spec、Plan、接口提案没有合并批准，不涉及。已合并（`merged`）的批准不会是开着的，不受影响。
6. **模块协调自己开的等待记录**：
   - 新命令 `module-crew wait add --file <正文文件> --to <收件会话名> --relay-id <邮箱消息号> --about <#N|C<N>>`：校验正文是合格的【等待其他会话】，
     记一条等待记录（W 编号，`from` 为模块协调、`about` 为所等的事项），输出 W 编号。重复的邮箱消息号不重复记。
   - 转达答复的命令（`answer`，以及带 `--source-item` 的批准类命令）处理事项 #N 或 C<N> 时，若有 `about` 指向它的未关等待记录，
     输出「你开的等待记录 W<n>（邮箱 #<relayId>）等的事已发生：给 <收件会话> 发【已恢复】」并生成正文文件（「结束：#<relayId>」），同时把记录标为已关。
   - `sessions`／`status` 显示模块协调自己未关的等待记录；`ticket close` 照旧可以手动关。
   - crew-coordinator skill：给任何会话发【等待其他会话】后立刻 `wait add`；收到命令给出的【已恢复】就发。
7. **派活后查权限弹窗**：
   - 生成给模块的通知或转达答复的命令（开工、同步、返工、退回、恢复、撤销批准、用户答复），输出末尾加一行
     「发完核对 <会话名> 是否停在权限弹窗：agent-relay 会话状态或应用侧栏『需要用户』；卡住就报『去会话操作』」。代码只提醒，不读宿主状态。
   - crew-coordinator skill 写明：每轮发完上述消息后、结束本轮前，用 agent-relay 的会话列表看这些模块会话的状态；处于等待审批（权限弹窗）就按「去会话操作」报决策收件箱，
     不等别人提醒；没有收件箱就在本会话告诉用户去哪个会话点。
8. **文档**：README 的命令表加 `sync`、`review show`、`wait add`，开工流程改写；两份 crew-dev skill、crew-coordinator skill 按上面改；版本号 0.6.0（plugin.json、marketplace、Codex 插件包）。

## 验收标准

1. 模块 worktree 里 `module-crew sync`：集成分支有新提交且无冲突 → 合入、退出码 0、输出合入提交数；再跑一次 → 「已是最新」。
2. 只有 `spec/<id>.md`、`tasks/<id>/` 冲突 → 取集成分支版本并完成合并，退出码 0，文件内容等于集成分支版本。
3. 有别的文件冲突 → 本模块文件已取集成分支版本，其他冲突文件列出、合并未中止，退出码 2；模块解决后再 sync 输出已包含。
4. 工作区不干净、在集成 checkout 或未登记目录里跑 → 退出码 3，什么都不改。
5. 开工、同步基线、恢复类通知正文写「module-crew sync」，不再出现「git merge」；仍通过 `protocol check`。
6. `review show C<N>` 输出各轮审查原文与 sha256，sha256 与原文一致；无结论、`--submission`、编号不对三种情况按关键决策 3。
7. 返工通知、开工通知里有「审查原文：module-crew review show C<N>」行，仍通过 `protocol check`。
8. 复现 X-4：交审 A 获批 → 合并批准 P → 同模块最终验收重交审 B → `merge revoke P` 时 A 保持关闭、输出「已被取代」；没有重交审时撤回照旧重开 A。
9. 重交审 B 记账时，开着的合并批准 P 自动关闭（superseded），`merge run` 不再取 P。
10. `wait add` 记下模块协调的等待记录；`answer` 处理所等事项时输出【已恢复】正文（「结束：#<relayId>」）并关记录；正文通过 `protocol check`；重复邮箱号不重复记。
11. 上述发通知的命令输出末尾都有「核对是否停在权限弹窗」一行。
12. 全量测试通过；旧称扫描测试通过（新文字用术语表 v1.1 的名称）。
13. 实地验证：在 crew-rehearsal 本机仓库，用默认权限模式新开一个模块会话，按 0.6.0 写的权限规则跑 `module-crew sync`（含一次本模块文件冲突），确认不弹窗；结果写进 todo。
    做不了就记「宿主未验证」并说明原因。

## 风险

- `sync` 把冲突留给模块手工解决：模块会话若改用 `git checkout --theirs` 这类没放行的命令仍会弹窗；skill 写明用编辑工具解决。
- 「派活后查弹窗」仍靠协调会话执行 skill，代码只提醒；决策收件箱那边的兜底（巡视看各会话的等待审批状态）不在本模块。
- `wait add` 要协调会话记得调用；漏记时行为与现在相同（不会更差）。

## 文档建议

- README：命令表与开工流程更新（本模块内做）。
- 其他跨模块文档：无。

## 变更记录

- 2026-10-19：初稿，待用户审。
