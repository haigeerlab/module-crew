# Implementation Plan: crew-takeover-merge

<!-- spec-guard: review approved -->

> 依据：`spec/crew-takeover-merge.md`（用户 2026-11-21 批准，事项 C620「C620 A」）。任务清单：`tasks/crew-takeover-merge/todo.md`。
> 本模块是提前开工：依赖 `crew-takeover-approve` 合入、收到开工类【协调通知】并 `module-crew sync` 之后才构建。

## Overview

先停在一个 `gate` 等三件事：`crew-takeover-approve` 已合入集成分支、spec-guard 0.91.0（interface 1.15）与 delegate 接口 1.5 已发版。
通过后按真实接口核对 Spec 假设 1，再依次做：最终验收的「自动合」判定（Task 1）、Codex 最终验收审查（Task 2）、`merge auto` 放行加合并（Task 3）、合并第一段完成记录（Task 4）、
出事收窄与 Codex 不可用的回退（Task 5）。给 autopilot 的读接口要先经模块协调与 autopr-design 对一次字段（第二个 `gate`），再实现 `merge first-stage` 与 `interface.json`（Task 6）。
最后补显示（Task 7）、skill 与文档、同步后全量测试与本机实测（Task 8）。
每个任务先写失败的测试、看到红再实现到绿，在本模块分支本地提交；不推送、不发版。每个任务都验证「`merge: human`／不接管时输出与今天相同」。

## Architecture Decisions

- **在 `crew-takeover-approve` 之上加，不另起一套**：判定只在 `takeover.approver` 的 `final` 分支加条件与原因（`takeover.final_reason`）；Codex 审查复用 `review codex`／`codex-note` 与它抽出的返工、超限函数，最终验收只换审查说明、审查范围（`--base <合并基点> --head <X>`）和「无阻断时记 `pass` 不落地」这一分支。
- **`merge auto` 复用 `merge run` 的 `_run`**：放行在一个事务里落盘（关交审事项、记 `auto-release`、建带 `auto` 的合并批准），再以同一把合并锁调 `_run`；`_run` 只在合入通过后、关合并批准的同一事务里对带 `auto` 的合并批准记 `firstStage`，不写任何文件、不加提交。
- **非作者检查就是合并队列那次完整检查**：不另跑；「非作者」判定写成一个函数（`checks.non_author(rec, module_session)`）给 `merge first-stage` 用。module-crew 不调 spec-guard 的 `--target acceptance`、不写 `~/.autopilot/`。
- **收窄沿用 `autonomy.incident`**：只在三个点传新的 `kind`（`auto-check-failed`、`auto-merge-returned`；撤销沿用 `revoked`），`merge-returned` 对自动合的事项改传 `auto-merge-returned`，不叠加。
- **读接口是提案**：`merge first-stage` 的 JSON 先按 Spec 决策 7 写测试，第二个 `gate` 对完字段后再实现；对方要改的字段照改，在 Spec「变更记录」追加一行、随最终验收复审。

## 影响面

新增：`tests/test_takeover_merge.py`、测试夹具（假 spec-guard 的 `merge: auto`、假 delegate 最终验收报告）。
修改：`module_crew/takeover.py`、`module_crew/review.py`、`module_crew/merge.py`、`module_crew/checks.py`、`module_crew/probe.py`、`module_crew/__main__.py`、`interface.json`（`firstStage` 一节、`interface` 1.1）、
`skills/crew-coordinator/SKILL.md`、`codex-skills/crew-coordinator/SKILL.md`、`skills/crew-dev/SKILL.md`、`codex-skills/crew-dev/SKILL.md`、`docs/guide.md`、`docs/commands.md`、`README.md`。
不新增依赖；不改 `store.py`、版本号、CHANGELOG（发版时由模块协调写）。`interface.json` 属公共文件：改动随最终验收审（Spec 并行边界已列）；开工说明若要求先发【公共变更请求】就照发。

## 构建开始时（不是 Task，开工通知到了就做）

- 单独执行 `module-crew sync`，拿到 `crew-takeover-approve` 的代码；读它实际落地的 `takeover.py`、`review.py`（`codex`／`codex-note`、`_land`）、`autonomy.incident`，与本 Plan 的接入点不同处就地调整，不改它已批的行为。

## Task List

### Checkpoint 0（gate）：依赖与上游

- [ ] `crew-takeover-approve` 已合入且本分支已 `module-crew sync`；本机装好 spec-guard 0.91.0（interface 1.15，有 `takeover` 与最终验收的 `codex-approved` 入口）与 delegate 接口 1.5。缺哪样就停在这里，发【等待其他会话】给 mc-coord（在等谁、等什么）；齐了读真实接口，与 Spec 假设 1 不同处改 Spec 并记变更记录，再继续

- [ ] Task 1：最终验收的「自动合」判定与 `review add`（Spec 决策 1；验收 1、2）
  - 做：`takeover.approver(..., "final")` 按 `merge: auto`、强制人批、假设 3 的三个前提返回 `codex`／`human` 并给原因；`review add` 对最终验收按判定记 `reviewer`／`sentTo`，输出指向 `review codex`；档位 `auto` 但前提不满足时多一行原因
  - 验证：不接管、`merge: human`、读不到 1.15、`checkLedger` 关、轻任务、Spec 或 Plan 没批时输出与改前相同（只多原因行）；强制人批照人合；`review list` 显示「最终验收（自动合）」
- [ ] Task 2：Codex 最终验收审查（Spec 决策 2、3；验收 3、4）
  - 做：`review codex` 对最终验收给出 `--base <合并基点> --head <X>` 的命令与审查说明（假设 5）；`codex-note` 对最终验收：有阻断照返工、超限与没有结论出【等待用户】草稿（最终验收版选项），无阻断记 `codex.verdict: pass`、事项保持开着、提示 `merge auto`
  - 验证：返工第 1、2 轮发通知，第 3 次仍阻断退出码 5；复审带 `--previous-report`；报告指纹与 X 对不上退出码 3 不记；Spec、Plan 节点的 Codex 放行回归测试不变

### Checkpoint 1（report）：判定与 Codex 审查就位，本模块测试与 `crew-takeover-approve`、审查就近回归测试通过，记入 todo 后继续

- [ ] Task 3：`merge auto` 放行加合并（Spec 决策 4、5；验收 5）
  - 做：`merge auto C<n>`：前提核对 → 指纹再核 → 事务内放行（`auto-release`、带 `auto` 的合并批准、交审事项关成 `answered`）→ 同一把锁调 `_run`；`__main__` 加子命令与退出码
  - 验证：放行后合入（`--no-ff`、完整检查照跑、检查脚本只被调用一次）、没有【用户答复】；交审后又有提交或指纹对不上退出码 3、什么都不写；检查失败退出码 5 并退回；队首是别的事项时合那一个并提示再跑；锁被占退出码 6
- [ ] Task 4：合并第一段完成记录（Spec 决策 6；验收 6）
  - 做：`_run` 对带 `auto` 的合并批准合入通过后记 `firstStage`（集成分支、合并提交、X、合并树、检查账键）与事件 `item.first-stage`；`gateTick` 照今天
  - 验证：夹具记下参数含报告、检查账键、X；提交排在勾选提交之前；入口拒绝或钩子拒绝时合并照算成功、集成 checkout 干净；人合的合并没有这个提交

### Checkpoint 2（report）：自动放行与合并链路就位，本模块测试与合并、检查账、最终验收拆分回归测试通过，记入 todo 后继续

- [ ] Task 5：出事收窄与 Codex 不可用的回退（Spec 决策 8、9；验收 8、10）
  - 做：三个出事点传 `auto-` 前缀的 `kind`；`merge approve`／`merge accept` 对没有 `fallback` 的自动合事项拒绝；用户选「这次由用户验收」后记 `reviewer: "human"`、`fallback`，走今天的最终验收
  - 验证：模块原因退回、撤销批准各调一次收窄入口（夹具看参数）；环境原因、钩子拒绝、超限、不可用不调；同一事项只降一次；回退后 `merge approve` 成功且不再 `merge auto`

### Checkpoint 3（gate）：`merge first-stage` 字段与 autopr-design 对齐

- [ ] 把 Spec 决策 8 的字段经 mc-coord 转给 autopr-design 确认（发【等待其他会话】，在等 autopr-design 答复字段）；对方要改就照改 Spec 并记变更记录，再继续

- [ ] Task 6：`merge first-stage` 与 `interface.json`（Spec 决策 7；验收 7）
  - 做：`merge.first_stage(project)` 与 `merge first-stage [--json]`；`interface.json` 加 `firstStage` 一节、`interface` 升 1.1
  - 验证：集成分支顶端的检查记录 `nonAuthor` 按假设 4，继承记录为假；只列最近一次推送之后的合并及其 Codex 验收证据；没有记录退出码 3；`interface.json` 的现有 `sessions` 一节不变
- [ ] Task 7：显示（Spec 决策 10；验收 9）
  - 做：`review list`／`show` 写自动合进度；`review batch`／`--for-hub` 不列自动合的最终验收、末尾告知行列出；`merge queue` 带「（自动合，Codex 验收放行 C<k>）」；`status` 与 `store.takeover` 加自动合计数
  - 验证：不接管时这些输出逐字不变；计数与事项一致

### Checkpoint 4（report）：读接口与显示就位，记入 todo 后继续

- [ ] Task 8：四份 skill、`docs/guide.md`、`docs/commands.md`、README；`module-crew sync` 后跑 `module-crew check quick` 与全量测试；上游发版后本机实测一次自动合并全链路，`merge first-stage --json` 的输出经 mc-coord 交 autopr-design 核对（Spec 验收 11、12、13）

### Checkpoint 5（gate）：最终验收

- [ ] 回告：完成情况经模块协调转告 ecosystem-lead 与 autopr-design（S101 合并方案 module-crew「合并第一段」已实现；`merge first-stage` 接口可读）

## Risks

| 风险 | 影响 | 缓解 |
|---|---|---|
| `crew-takeover-approve` 落地的接入点与 Spec 推定不同 | 返工接入代码 | 开工先 sync 再读它的实际代码；只在接入点调整，不改它已批的行为 |
| autopr-design 要的证据字段与提案差得多 | Task 6 返工 | 第二个 gate 先对字段再写实现；测试先按提案写、对完再改 |
| 合并队列再跑一次完整检查，自动合耗时翻倍 | 体验慢 | 守门不变，照实记入未决问题 1，由用户另定 |
| 上游迟迟不发版 | 停在 Gate 0 | 照规则发【等待其他会话】，必要时请模块协调挂起本模块 |

## 变更记录

- 2026-11-22（Checkpoint 0）：随 Spec 同日修订改 Task 3、4、6 与 Checkpoint 3：去掉合并前在模块 worktree 补跑非作者检查，Task 4 由「写 codex-approved 验收标记」改为「记合并第一段完成（firstStage）」，读接口由 `check evidence` 改为 `merge first-stage`；Task 5 收窄去掉非作者检查失败一类。原因与来源见 Spec 变更记录同日一行；停在 Checkpoint 0 交用户复审。
