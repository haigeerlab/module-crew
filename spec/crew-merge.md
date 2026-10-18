<!-- spec-guard: review approved e9d146d28022 -->
# Spec: crew-merge

> 能力图模块 `crew-merge`。需求来源：`docs/requirements-record.md` B5（两层合并）、假设 6（完整检查命令）、假设 9（远端合并由用户做）、第 5 节规则措辞（模块合入本地集成分支可在用户批准最终验收后由协调会话执行）。
> 契约：session-protocol v1.5（246e138）的【协调通知】类型「退回」（`returned`）。假设见下文，用户 2026-10-18 已确认（第 4 条选 A）。

## 目标

用户批准某个模块的最终验收后，协调会话把它按 Build order 一次一个、`--no-ff` 合入本地集成分支，合后跑完整检查；不过就撤销并退回模块。
一批合完，经用户明确授权推送到远端的一个新分支并开一个 PR，由用户在远端合并。模块做完后，经用户同意收回它的 worktree、退役会话登记。

## 范围

**范围内**

- `module_crew/merge.py` 与命令 `module-crew merge approve|queue|run|cleanup|push-plan|push`。
- `item`（`kind: "merge-approval"`）的字段与流转；运行配置新增 `checkCommand`、`checkTimeout`、`remote`、`prBase`。
- 合并、检查、撤销、退回；收尾与同步基线通知；worktree 收回与会话退役；推送与开 PR。
- `skills/crew-coordinator/SKILL.md` 增加「合并与收尾」一节。

**范围外**

- 远端 PR 的合并（用户做）；GitHub 自动合并（不开）。
- agent-relay 邮箱身份的退役：`merge cleanup` 只列出待退役的名字，经用户同意后由用户在 Claude Code 里用 `/agent-relay:collaboration`（或 Codex 的 collaboration-ops skill、或 agent-relay 插件的退役脚本）退役；module-crew 不定位也不运行 agent-relay 的脚本（2026-10-18 修订）。
- spec-guard 进度重算（`/map` 自己算）。

## 假设（用户 2026-10-18 已确认）

1. 最终验收【交审】照常 `review add`、交用户审；批准后 `merge approve <交审编号> --original-file` 记批准并排入本地合并队列（批准即授权合入本地集成分支）。
2. 合并前清单：模块分支 HEAD 等于交审时记下的提交；模块 worktree 干净；集成基线干净；任一不满足不合并并写明原因。
3. `merge run` 按 Build order 一次只合一个：`git merge --no-ff`，合后跑完整检查（`checkCommand`，参数列表、不经 shell、默认超时 30 分钟）；不过 `git revert -m 1` 并退回；冲突 `git merge --abort` 并退回。
4. 退回用新的【协调通知】类型「退回」——先改契约（已提需求）。（2026-10-18 契约 v1.5 已发版，见变更记录。）
5. 合并成功：给该模块发收尾通知、其他在用模块发同步基线通知，关最终验收交审。
6. `merge cleanup <模块> --original-file` 经用户同意：`git worktree remove`（不加 `--force`，不干净就拒绝）、会话登记改为退役；邮箱退役由协调会话用 agent-relay 工具做。
7. `merge push-plan` 只读预告；`merge push --original-file` 经用户明确授权推送并 `gh pr create` 开一个 PR；无远端报出，无 `gh` 打印 PR 正文；不开自动合并。
8. 合并后 `/map` 自己重算；下游靠同步基线通知合入集成分支。

## 关键决策与取舍（请重点审）

1. **推送到远端的新分支，不推集成分支本身。** 集成分支通常就是本地 `main`，直接推等于绕过 PR、替用户合并到远端。所以 `merge push` 执行
   `git push <remote> <集成分支>:refs/heads/crew/batch-<批次号>`，PR 从这个新分支开向 `prBase`（默认取集成分支名）。批次号是本次推送记录的编号。
2. **合并队列不另存，按记录算**：队列 = 所有 `open` 的 `merge-approval` 事项，按模块在 Build order 里的位置排序（取 `/map --json` 的模块顺序）。
   `merge run` 只处理队首一个；协调会话发完通知再跑下一次，保证每次合并后的通知和下游同步不会被下一次合并打乱。
3. **检查失败的撤销是一个新提交**（`git revert -m 1 --no-edit`），不改写历史；集成分支上留下「合并 + 撤销」两个提交，原因写进合并批准事项（`closedReason: "returned"`）。
   冲突时 `git merge --abort`，集成分支不变。两种情况都把模块的会话保持在用，等它重新交审最终验收（重新 `review add` → `merge approve`）。
4. **完整检查命令写进运行配置**：第一次 `merge run --check-command "<命令>"` 写入 `checkCommand`（用 `shlex.split` 拆成参数，不经 shell），之后不接受修改（要改用户在对话里明确说，协调会话用 `merge run --check-command` 加 `--replace-check` 才写，命令输出旧值与新值）；
   在集成 checkout 里运行，超时按 `checkTimeout`（默认 1800 秒）算失败。
5. **退回通知**：`merge run` 检查失败或冲突时，生成给该模块的退回类【协调通知】：「依据」写那次最终验收的合并批准事项编号、退回原因与相关提交或冲突文件，
   「要你做什么」写「同步集成基线、修好后重新发最终验收【交审】」。退回不撤销那次最终验收批准的记录，但合并批准事项关为 `returned`，模块须重新交审、重新批准。
6. **收回 worktree 是删除操作，只在用户原话授权、且模块已合并后执行**；`git worktree remove` 不加 `--force`，模块分支保留不删。

7. **只给还在开发的模块发同步基线**（2026-10-18 修订）：合入成功后，同步基线通知跳过已合入的模块（有关闭为 merged 的合并批准）和仍在合并队列里的模块（有未关闭的合并批准）；
   后者排到它合并时用 `--no-ff` 一起带上新基线，先同步反而会让它的合并因「交审后又有提交」被拒。
8. **最终验收由协调会话在集成分支勾选**（2026-10-18 修订）：合入并通过完整检查后，若 `tasks/<模块>/todo.md` 恰好剩一个未勾项，就在集成分支把它勾上并单独提交（「勾选 <模块> 的最终验收（合并批准事项 #N）」）；剩 0 个不动；不止 1 个只报告、不勾。模块会话获批后不再自己勾（crew-dev skill）。

## 接口约定

### 记录

```json
// item kind=merge-approval
{"state": "open", "kind": "merge-approval", "module": "b", "review": 31, "commit": "<最终验收交审时的模块提交>",
 "from": "shop-b", "relayId": 4800, "answer": {"original": "...", "answeredAt": "..."},
 "closedReason": null, "mergeCommit": null, "revertCommit": null, "reason": null}
// 合并成功：state=closed, closedReason=merged, mergeCommit=...
// 退回：state=closed, closedReason=returned, reason=..., revertCommit=...（冲突时为 null）
// item kind=push：{"state": "closed", "kind": "push", "closedReason": "pushed", "remoteBranch": "crew/batch-40", "commits": [...], "pr": "<链接或 null>", "answer": {...}}
```

### 命令

```bash
bin/module-crew merge approve <最终验收交审编号>… (--original <原话> | --original-file <文件>)
bin/module-crew merge tick <模块 id> (--original <原话> | --original-file <文件>)
bin/module-crew merge queue [--json]
bin/module-crew merge run [--check-command "<命令>" [--replace-check]]
bin/module-crew merge cleanup <模块 id> (--original <原话> | --original-file <文件>)
bin/module-crew merge push-plan [--json]
bin/module-crew merge push (--original <原话> | --original-file <文件>)
```

- `approve`：可一次给多个编号，逐个记批准并各生成【用户答复】（输出发送参数）；`0` 成功；`3` 任一交审不存在、已关闭或不是最终验收（什么都不写）。
- `tick`：补救修订前合并时漏勾的最终验收：在集成分支勾上该模块 todo 唯一的未勾项并单独提交；`0` 成功；`3` 模块没有已合并的合并批准、未勾项不是恰好一个、集成基线不干净或原话为空。
- `queue`：`0` 队列非空；`3` 空。
- `run`：`0` 合并成功（输出合并提交与要发送的收尾、同步基线通知）；`5` 检查失败已撤销或冲突已中止（输出要发送的退回通知）；`3` 合并前清单不过（什么都没动）；`2` 没有检查命令或参数错；`4` 撤销本身失败（集成 checkout 状态写明，交用户）。
- `cleanup`：`0` 成功（输出列出待退役的邮箱名与退役做法，以及该模块还开着的等待单编号，只提醒不自动关）；`3` 模块未合并、worktree 不干净或不存在。
- `push-plan`：列出远端、新分支名、`prBase`、要推送的提交、PR 标题与正文；`0` 有可推送的提交；`3` 没有或没有远端。
- `push`：`0` 推送成功（远端是 github.com 且有 `gh` 时附 PR 链接；其他远端或没有 `gh` 时打印 PR 标题与正文）；`3` 检查不过；`4` 推送或开 PR 失败。
  PR 正文先随推送记录写进状态库（落盘）再调 `gh`，开好后另记一次 PR 链接（2026-10-18 修订）。

## 项目结构

```text
module_crew/merge.py
module_crew/__main__.py            加 merge 子命令
skills/crew-coordinator/SKILL.md   加「合并与收尾」一节
tests/test_merge_run.py            批准、队列、合并、检查、撤销、冲突
tests/test_merge_finish.py         收回、推送预告、推送（本地裸仓库作远端，假 gh）
```

## 命令

```bash
python3 -m unittest discover -s tests -v
```

## 代码风格

沿用前几个模块；外部命令一律参数列表、带超时、不用 shell；git 状态读取用 `--no-optional-locks`。

## 测试策略

- 复用 crew-review-batch 的测试基类（b、c 两个模块会话），在模块 worktree 里写代码并提交，构造最终验收【交审】。
- 完整检查命令用临时目录里的小脚本（按文件是否存在决定成败），验证通过、失败撤销、超时三种。
- 冲突：在集成分支与模块分支上改同一行。
- 远端：临时目录里的裸仓库；`gh` 用放在临时 PATH 里的假脚本记录参数。

## 边界

- **始终**：一次只合一个；合前清单全过才动；推送前有用户原话。
- **先问**：修改已写定的检查命令；收回 worktree；推送与开 PR。
- **绝不**：推送集成分支本身到远端同名分支；`--force`；删除模块分支；开自动合并；改写集成分支历史。

## 验收标准

1. `merge approve`：最终验收交审关为 `answered`、生成【用户答复】；记 `merge-approval`（`open`，含模块、交审编号、交审时的提交、原话）；非最终验收或已关闭的交审被拒。
2. `merge queue` 按 Build order 排序（c 先批准、b 后批准，队列仍是 b、c）。
3. 合并前清单任一不过（模块分支在交审后又有提交、模块 worktree 不干净、集成基线不干净）：退出码 3，集成分支与状态库不变。
4. 首次 `merge run` 没给检查命令：退出码 2；给了就写进配置，之后不带也用它；不带 `--replace-check` 改命令被拒。
5. 检查通过：集成分支多一个 `--no-ff` 合并提交（两个父提交）；`merge-approval` 关为 `merged` 记合并提交；生成给该模块的收尾通知、给其他在用模块的同步基线通知（都能被 `protocol.parse` 判为合格）；只合了队首一个。
6. 检查失败或超时：集成分支多一个撤销提交、内容回到合并前；`merge-approval` 关为 `returned` 并记原因与撤销提交；退出码 5；生成给该模块的退回类【协调通知】（依据含合并批准事项编号与撤销提交，`protocol.parse` 判为合格）。
7. 合并冲突：集成分支不变（`merge --abort`），`merge-approval` 关为 `returned`，原因写明冲突文件；退出码 5；生成退回类【协调通知】（依据含编号与冲突文件，判为合格）。
8. `merge cleanup`：已合并模块的 worktree 被 `git worktree remove` 移除、分支保留、会话改为退役；未合并或 worktree 不干净时拒绝且不动。
9. `merge push-plan`：列出远端分支 `crew/batch-<号>`、`prBase`、待推送提交与 PR 正文（含本批合并的模块与批准事项编号）；不推送。
10. `merge push`：裸仓库远端出现新分支、内容等于集成分支；远端的 `prBase` 分支不变；有假 `gh` 时以 `--base <prBase> --head crew/batch-<号>` 调用且不带自动合并参数；没有 `gh` 时打印 PR 正文；记一条 `kind: "push"` 事项。
12. 同步基线收件人：b、c 都已批准最终验收，第一次 `merge run` 合入 b 后不给仍在队列里的 c 发同步基线；第二次合入 c 后不给已合入的 b 发；另一个仍在开发的模块 d 两次都收到。
13. 合入并通过检查后，模块 todo 恰好剩一个未勾项时集成分支多一个勾选提交、该项已勾；剩 0 个时没有勾选提交；不止 1 个时不勾并在输出里报告；检查失败或冲突时不勾。
14. `merge approve 15 16`：两个都记批准并各生成【用户答复】；其中一个不合格时退出码 3、什么都不写。
15. `merge tick b`：已合并、todo 剩一个未勾项时在集成分支勾上并提交；未合并、未勾项不是一个、原话为空时退出码 3 且不改动。
16. `merge push`：假 `gh` 被调用时 `--body-file` 指向的正文文件已经存在；远端不是 github.com 时不调用 `gh`、打印 PR 正文、退出码 0。
17. `merge cleanup`：输出列出待退役的邮箱名与 `/agent-relay:collaboration` 的做法，不含 agent-relay 脚本的路径；该模块有开着的等待单时列出编号、不关单。
11. 协调会话 skill 有「合并与收尾」一节：`review add`／`merge approve` → `merge run` 一次一个、发通知 → 退回时转告原因 → 用户同意后 `merge cleanup` 并用 agent-relay 退役邮箱 → `merge push-plan` 给用户看 → 用户授权后 `merge push` → 远端 PR 由用户合并。

## 未决问题

无。

## 文档建议

README「一次完整流程」补上合并、退回、收尾、推送与 PR 一节，强调远端合并由用户做。

## 变更记录

- 2026-10-18：契约 v1.5 已新增「退回」类型，删去「发版前不生成退回通知」的过渡做法与对应未决问题；关键决策 5、验收 6、7 改为生成退回类【协调通知】。原因：契约负责人发布 v1.5（246e138）；来源：用户 2026-10-18 批准（选 A）。
- 2026-10-18：同步基线只发给还在开发的模块（关键决策 7）；合入通过检查后由协调会话在集成分支勾选最终验收（关键决策 8），并加 `merge tick` 补救修订前漏勾的数据；`merge approve` 一次可收多个编号；增加验收 12–15。原因：试点发现缺陷 A、B、C 与不一致 E；来源：第 7 关试点（`docs/pilot-report.md`），用户 2026-10-18 批准。
- 2026-10-18：`merge push` 先落盘 PR 正文再调 `gh`，远端不是 github.com 时只打印正文；`merge cleanup` 列出待退役的邮箱名（由用户经 `/agent-relay:collaboration` 退役，module-crew 不定位 agent-relay 脚本）与该模块开着的等待单；增加验收 16、17。原因：试点问题 J（推送成功却退出码 4）、K（agent-relay 0.8.2 无退役工具，负责人确认只能由用户同意后走运维脚本，接口保持 2.5）、I；来源：第 7 关试点收尾（`docs/pilot-report.md`），用户 2026-10-18 批准。
