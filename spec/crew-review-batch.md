<!-- spec-guard: review approved e829c4633b2b -->

# Spec: crew-review-batch

> 能力图模块 `crew-review-batch`。需求来源：`docs/requirements-record.md` B2（批量审批、提交到基线后才开工构建）、A3（扩张点前批量前置审，批准后 Spec 与 Plan 提交到集成基线、同批互相读得到）、
> 第 5 节规则措辞（评审标记由听到批准的会话写入）、B1（协调会话汇总交审、记批准，不出审查结论）。契约 session-protocol v1.4。假设见下文，用户 2026-10-18 已确认。

## 目标

模块会话写好 Spec、Plan（或接口提案）发来【交审】后，协调会话把同一批收齐、核对、一次交用户审；用户批准后，由一条命令把这些 Spec 与 Plan
原样提交到集成基线、写上评审标记、给每个模块生成【用户答复】，对 Spec 与 Plan 都已批准的模块再生成开工类【协调通知】。

## 范围

**范围内**

- `module_crew/review.py` 与命令 `module-crew review add|batch|approve|answer`。
- `item`（`kind: "review"` 交审事项、`kind: "review-approval"` 批准事项）的字段与流转。
- 调 spec-guard 的评审标记入口；在集成基线上提交。
- `skills/crew-coordinator/SKILL.md` 增加「交审与批准」一节，并把收件表里退出码 4 的去向写清。

**范围外**

- 最终验收批准之后的合并（crew-merge）；公共变更请求（crew-shared-changes）。
- 判断接口内容是否对得上、出审查结论（协调会话读 Spec 后写在交审正文里，由用户判断）。
- 推送、开 PR。

## 假设（用户 2026-10-18 已确认）

1. 模块会话发【交审】前先把文件提交到自己的分支；`review add` 记账并到发件人 worktree 读文件核对指纹，对不上或发件人未登记就拒收；Spec 交审必须列出 `spec/<id>.md`，Plan 交审必须同时列出 `tasks/<id>/plan.md` 与 `tasks/<id>/todo.md`，缺了也拒收（批准只搬列出的文件）。
2. 一批 = 所有未答的交审事项；`review batch` 列出并做结构核对（依赖的提供方已完成，或其 Spec 在本批或已批准）；接口内容由用户判断。
3. `review approve <事项…> --original-file` 在用户答应后（2026-10-19 起先核对待决问题都答到，并按答案分批准、退回、保持未答，见 crew-review-nearby 关键决策 4）：复制已提交的文件到集成分支所在 checkout、写评审标记 approved、在集成分支一次提交、生成每个交审的【用户答复】与开工类【协调通知】。
4. 要求修改用 `review answer <事项> --original-file`：只生成【用户答复】、关事项，不碰集成基线；模块改完重发【交审】。
5. 评审标记按 spec-guard interface 1.1 的 `reviewMark` 入口调用，键名定稿前用夹具，定稿后对照一次。
6. Spec、Plan、接口提案走上述流程；最终验收可 `review add` 记账，批准后的合并归 crew-merge，本模块只生成答复。
7. 集成基线上只提交 `spec/<id>.md`、`tasks/<id>/`，提交信息写批准事项编号；基线不干净就拒绝；不推送。
8. `review batch` 原样列出涉及本批模块的 `startable.conflicts`，不自动裁决。

## 关键决策与取舍（请重点审）

1. **指纹核对以模块分支上已提交的内容为准。** `review add` 记下模块分支当时的提交号；核对时文件必须已被 git 跟踪、工作区与该提交一致，
   并且 `sha256` 以交审里写的指纹开头。`approve` 复制的是**这个提交**里的文件（`git show <提交>:<路径>`），不是 worktree 里此刻的内容——批准的就是用户审过的那一版。
2. **同一模块同一节点的新交审取代旧的**（还没答的那条关为 `superseded`）。契约的默认取代只写了【等待用户】；这里沿用同样的思路，避免一批里出现同一份 Spec 的两个版本。
3. **开工通知的条件：这个模块的 Spec 与 Plan 都已批准**（本次批准或之前批准过的都算）。只批了 Spec 的模块只收到【用户答复】，等 Plan 批了再发开工通知。
   接口提案的批准不触发开工通知。
4. **`approve` 的顺序与失败处理**：先做全部检查（事项都还开着且是可批准的节点、集成基线干净、文件都能从记下的提交里取出、评审标记入口可用）；
   然后复制文件 → 逐个写评审标记 → `git add` 这些路径 → 一次 `git commit` → 一个状态库事务（批准事项、关交审事项、写所有答复与通知正文）。
   复制或写标记中途失败时停下，**不回滚也不删**集成 checkout 里已复制的文件（它们未提交），输出写明哪些文件已改，交用户决定；退出码 4。
5. **评审标记命令的安全限制与 `/map` 一样**：必须 `python3` 开头、脚本在 spec-guard 安装目录内；占位符 `<project-root>`、`<module-id>`、`<spec|plan|both>`、`<pending|approved>` 由本模块填（按 interface 1.1 定稿的写法），末尾加 `--confirm`。
6. **批准事项单独一条**（`kind: "review-approval"`，已答，记原话、批准的交审编号、集成基线提交号）；开工通知的「依据」引用它的编号——满足契约「开工类【协调通知】必须写明所依据的批准事项编号」。
- **提交信息与提交钩子**（2026-10-18 修订）：提交信息一律以 `chore(crew): ` 开头（符合 Conventional Commits，首行不超过 100 字符），后面照旧写中文说明与编号；提交失败且仓库启用了提交钩子时，原因写「提交钩子拒绝：<钩子输出首行>」，不并入其他原因。（2026-10-18 修订）


## 接口约定

### 记录

```json
// item kind=review（键 = 编号）
{"state": "open", "kind": "review", "from": "shop-b", "relayId": 4600, "text": "【交审】...",
 "module": "b", "node": "spec", "files": [{"path": "spec/b.md", "fingerprint": "sha256:3f2a9c1e7b4d"}],
 "commit": "<模块分支提交号>", "closedReason": null, "answer": null}
// item kind=review-approval
{"state": "closed", "kind": "review-approval", "closedReason": "answered", "reviews": [12, 13],
 "baselineCommit": "<集成分支提交号>", "answer": {"original": "...", "answeredAt": "..."}}
```

### 命令

```bash
bin/module-crew review add <文件> --from <邮箱名> --relay-id <M>
bin/module-crew review batch [--json]
bin/module-crew review approve <事项编号>… (--original <原话> | --original-file <文件>)
bin/module-crew review answer <事项编号> (--original <原话> | --original-file <文件>)
```

- `review add`：`0` 已记账（或已记过）；`3` 拒收（不合格、发件人未登记、模块与发件人登记的不符、必列文件没列、文件未提交、指纹不符），什么都不写；`2` 参数错。
- `review batch`：列出未答交审（编号、模块、节点、文件、要点）、依赖核对结果、冲突；依赖与冲突没有问题时也各输出一行「依赖：全部就绪」「并行边界重叠：无」（2026-10-18 修订）；`0` 有未答交审，`3` 没有。
- `review approve`：输出批准事项编号、集成基线提交号、要发送的消息清单（每条：收件人、`replyTo`（答复有，通知无）、一条答复同时答几条交审时的其余原消息号 `alsoAnswers`、正文路径）；`0` 成功；`3` 检查不过什么都没做；`4` 中途停下；`2` 参数错。
- `review answer`：输出收件人、`replyTo`、正文路径；`0` 成功；`3` 事项不存在或已关闭。

## 项目结构

```text
module_crew/review.py
module_crew/__main__.py            加 review 子命令
skills/crew-coordinator/SKILL.md   加「交审与批准」一节、更新收件表
tests/helpers.py                   假 spec-guard 增加 reviewMark 入口与脚本
tests/test_review_add.py
tests/test_review_approve.py
```

## 命令

```bash
python3 -m unittest discover -s tests -v
```

## 代码风格

沿用前几个模块；解析走 `protocol`，状态走 `store` 事务，体检走 `probe`，开工相关配置读 `config/main`。

## 测试策略

- 在临时仓库里用 crew-start 的 `prepare` 开出两个模块 worktree，在 worktree 里写并提交 `spec/<id>.md`、`tasks/<id>/plan.md`，再构造【交审】。
- 假 spec-guard 的 `reviewMark` 脚本：把文件第一行改成 `<!-- spec-guard: review approved -->`（Spec 加假指纹），用来验证调用与参数。
- 集成基线：断言只多一个提交、只改动 `spec/` 与 `tasks/` 下这几个模块的路径、提交信息含批准事项编号。

## 边界

- **始终**：批准的是交审时的那个提交里的内容；检查全过才动手；答复与通知正文由命令生成。
- **先问**：在集成基线上提交 `spec/`、`tasks/` 以外的路径；没有用户原话就批准。
- **绝不**：推送；改写模块分支；替用户判断接口是否对得上。

## 验收标准

1. 合格【交审】（文件已提交、指纹对）：记成 `kind: "review"` 事项，带模块、节点代码、文件、模块分支提交号。
2. 拒收且不写：发件人未登记；交审的模块不是发件人登记的模块；文件未被跟踪或工作区有未提交改动；指纹不是文件 `sha256` 的前缀；消息不合格；Plan 交审没列 `tasks/<id>/todo.md` 或 `plan.md`、Spec 交审没列 `spec/<id>.md`（原因写明缺哪个文件）。
3. 同一模块同一节点再交审：旧的未答事项关为 `superseded`；同一 `--relay-id` 重复提交只记一次。
4. `review batch` 列出未答交审；依赖核对：依赖已完成（`/map` 状态 `done`）、或在本批有 Spec／接口提案、或之前批准过 Spec／接口提案的为通过，否则列为「依赖未就绪」；涉及本批模块的冲突原样列出。
5. `review approve 12 13`（b 的 Spec 与 Plan）：集成分支多一个提交，只含 `spec/b.md`、`tasks/b/plan.md`、`tasks/b/todo.md`（与交审时提交的内容相同，外加评审标记），提交信息含批准事项编号；
   两个交审事项关为 `answered`；生成两条【用户答复】（`replyTo` 各为原交审的邮箱号，原话一致）与一条给 b 的开工类【协调通知】（依据含批准事项编号，可被 `protocol.parse` 判为合格）。
6. 只批了 c 的 Spec：c 收到【用户答复】，没有开工通知；之后批了 c 的 Plan：发出开工通知。
7. 检查不过（事项已关闭、节点是最终验收、集成基线不干净、评审标记入口不安全或不可用）：退出码 3，集成 checkout、分支与状态库都不变。
8. 写评审标记中途失败：退出码 4，输出列出已复制的文件；集成分支没有新提交，状态库不变。
9. `review answer`：生成【用户答复】、关事项，集成基线不变。
10. `inbox add` 收到合格【交审】仍返回 4；协调会话 skill 写明「4 → 【交审】用 `review add`，【公共变更请求】用 crew-shared-changes 的命令」，并有「交审与批准」一节：`review batch` → 交用户审（要点写在正文里）→ `review approve`／`review answer` → 按输出逐条 `bridge_send`。
- 集成 checkout 装只认 `类型(范围): ` 开头的 commit-msg 钩子时 `review approve` 照常提交；钩子拒绝时退出码 4、状态库不变、输出含「提交钩子拒绝」。（2026-10-18 修订）

- 交审按模块分组（2026-10-18 修订）：c 先交 Spec、b 再交 Plan、c 再交 Plan、b 最后交 Spec 时，`review batch` 的条目按 Build order 与节点排成 b Spec、b Plan、c Spec、c Plan，`--json` 带 `groups`，文字输出每个模块一节（`## <模块>（职责）`）。


## 未决问题

- 无（`reviewMark` 已按 interface 1.1 定稿对照，见变更记录；0.68.0 发版后在第 7 关用真实安装副本再核一次）。

## 文档建议

README「一次完整流程」接着写：交审 → `review batch` → 用户批准 → `review approve` → 发答复与开工通知。

## 变更记录

- 2026-10-18：开工类【协调通知】的「要你做什么」补一句「`spec/<id>.md`、`tasks/<id>/` 冲突时取集成分支的版本（它带评审标记）」，crew-dev skill 增加「同步集成基线」一节，并加回归测试。原因：`review approve` 在集成分支提交带评审标记的副本，模块分支上是同名不带标记的文件，模块同步集成分支时出现 add/add 冲突（crew-recovery-hooks 构建中发现，临时目录已复现）；来源：用户 2026-10-18 选 A。
- 2026-10-18：`reviewMark.command` 的占位符改为定稿写法 `<spec|plan|both>`、`<pending|approved>`（原按 `<target>`、`<state>` 填），测试夹具同步；不认识的占位符仍按原规则拒绝。原因：interface 1.1 定稿；来源：spec-guard 负责人通知 interface.json 1.1 定稿（spec-guard 分支 `claude/module-concurrency` 提交 6231abc，0.68.0 未发版），用户 2026-10-18 复审批准。
- 2026-10-18：`review batch` 在依赖与冲突都没有问题时也明确输出「依赖：全部就绪」「并行边界重叠：无」。原因：试点发现「没有冲突」与「不输出」分不清（问题 G）；来源：第 7 关试点（`docs/pilot-report.md`），用户 2026-10-18 批准。
- 2026-10-18：批准提交的信息加 `chore(crew): ` 前缀，提交钩子拒绝时单独标原因；增加对应验收。原因：module-crew 的提交过不了前端的 commitlint；来源：联合演练批 2 准备（前端 husky 跑 `@commitlint/config-conventional`，lint-staged 对全部暂存文件跑 `oxfmt --check`），用户 2026-10-18 批准先修再发 0.1.1。
- 2026-10-18：`review approve` 带负责人转交（lead）来源时只记账、不写标记不开工，带收件枢纽来源时提交说明写 #H（细则见 crew-hub-bridge 关键决策 9）。来源：用户 2026-10-18 确认 0.1.1 范围；spec-guard 0.70.0（PR haigeerlab/spec-guard-plugin#352）最终措辞：负责人转交不算写标记的来源，收件枢纽转来的批准写标记时在提交说明记 #H。
- 2026-10-18：批量交审按模块分组——条目按「模块在 Build order 的位置 → 节点（Spec、接口提案、Plan、最终验收）→ 编号」排序，`--json` 增加 `groups`，文字输出每个模块一节；协调会话 skill 写明按模块分节交用户审；增加对应验收。来源：用户 2026-10-18 经 spec-guard 负责人会话提出（交审给人看要一个模块一个模块地出现），本会话 2026-10-18 批准修法。
- 2026-10-18：`review add` 检查必列文件——Spec 交审必须列 `spec/<id>.md`，Plan 交审必须同时列 `tasks/<id>/plan.md` 与 `todo.md`，缺了拒收；改假设第 1 条、退出码说明与验收 2、5；两份 crew-dev skill 写明。原因：联合演练 T1 中 beta 的 Plan 交审漏列 todo.md 仍被收下，批准后 todo.md 没进集成分支；来源：接入方案会话转报，用户 2026-10-18 批准修法（0.2.2）。
- 2026-10-18：`review approve` 的发送清单给出 `alsoAnswers`（合成答复里除 `replyTo` 外的原消息号），协调会话 skill 写明一并带上。原因：联合演练 T1 一条答复覆盖两条交审时命令没给出 alsoAnswers；来源：监测会话转报，用户 2026-10-18 批准修法（0.2.2）。
- 2026-10-19：`review approve` 先核对本次交审的待决问题（D1…）都答到，没答全退出码 3、什么都不做；模块协调生成的问题按答案批准、退回或保持未答；`review add` 在登记审查者时输出送审发送项、认「不同意」与最终验收的「验收标准与证据」。原因：审查就近（R1、R2、R17）；来源：用户 2026-10-19 批准修订后的 crew-review-nearby Spec 与 Plan（决定 41、46、47、49；Task 7、9、11、13），随它的最终验收复审。
