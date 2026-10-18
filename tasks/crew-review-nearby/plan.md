# Implementation Plan: crew-review-nearby

<!-- spec-guard: review approved -->

> 依据：`spec/crew-review-nearby.md`（用户 2026-10-19 批准，同日修订待复审）。任务清单：`tasks/crew-review-nearby/todo.md`。

## Overview

Task 1–5 已按修订前的 Spec 做完并提交（协议层、C 编号、送审与审查状态、`review note` 返工循环、合批）。修订后：先钉契约 v2.1、把协议字段名对齐定稿；
再重写提请批准（一个模块一项、原样展示、原文文件、「待用户决定」字段，去掉 T5 的摘要与截断）、最终验收的证据检查、批准核对待决问题；
然后做评审节奏、合并批准撤回、状态可见，最后补 skill、README 与版本号。每个任务先写失败的测试，再实现到全绿，单独提交。

## Architecture Decisions

- 沿用已做的部分：`review_state` 六种状态、`_rounds` 按事件计轮次、送审与返工都是发送项、`refs.py`。
- **提请批准一条一个模块**：`for_hub` 改为返回列表 `[(正文号, 路径, 文本)]`，每个模块一条、各记一条 `hub-batch` 记录（`module`、`reviews`、`decisions` 对照）；D 号每条从 D1 起。
- **原文文件**：写在 `<状态库>/originals/`，文件名 `C<号>-submission.txt`、`C<号>-review-<审查编号>.txt`，写入后不覆盖（已存在且内容相同则复用）；指纹用 sha256 全长。
- **产物路径**：模块会话登记的 worktree 绝对路径 + 交审文件相对路径，提交取交审记下的 `commit`；重交时上一版取被取代交审的 `commit`。
- **评审节奏**：`start._settings` 读 `.agent/config.json` 的 `reviewCadence`，非法或缺省按 `separate`，记入运行配置 `reviewCadence`；`render_kickoff` 按它写「这一步只做」。
- **批准核对**：从原话里认 `D<k>[：: ]?(选)?\s*<字母>`；按最近一条覆盖这些交审的 `hub-batch` 对照核对，没有对照（单用）时按 `numbered_decisions` 现算。

## 影响面

修改：`protocol.py`、`review.py`、`merge.py`、`start.py`、`failure.py`、`probe.py`、`__main__.py`、三份 skill、README、版本文件；
新增：`tests/fixtures/session-protocol/v2.1/`（替换 v1.9 目录）。不涉及界面。T5 写的摘要、截断、「共 N 条」与对应测试删除。

## Task List

### 已完成（修订前）

- [x] Task 1–5（见 todo）

### Phase 2：对齐契约与提请批准

- [ ] Task 6：钉契约 v2.1——换样例目录、`CONTRACT_VERSION`、Task 1 字段名照定稿（`disputes`、`bad-dispute-line`、`localItem`、`localRefs`／`reviewRefs`、顶层 `decisions`、`leanReason`）、解析【登记回执】与【等待用户】的「产物」「交审原文」「审查原文」「待用户决定」（验收 18）
- [ ] Task 7：提请批准重写——一个模块一项、要点原样不截断、原文文件、产物行（含上一版）、「待用户决定」字段、「批准会发生什么」、`separate`／`combined` 分项；去掉摘要与截断（验收 3、5、6、10、11、14）
- [ ] Task 8：最终验收证据——`review add` 缺「验收标准与证据」拒收；提请批准把它排在要点最前（验收 16）
- [ ] Task 9：批准核对待决问题、分三路、追问正文；单用时同样核对（验收 7、8）

### Checkpoint 2（report）：完整返工循环与提请批准在三种组合下跑通，记入 todo 后继续

### Phase 3：节奏、撤回、可见与收尾

- [ ] Task 10：评审节奏——`start prepare` 读 `reviewCadence`、开工说明按节奏写、`status` 写生效值（验收 15）
- [ ] Task 11：`merge revoke` 与撤销批准通知（验收 12）
- [ ] Task 12：`status` 与 `sessions --json` 返工轮次（验收 17）
- [ ] Task 13：skill 与 README——送审与返工、「有须修改项」范围、「不同意」、待决问题必须答全、合并前复述、按节奏交审、「验收标准与证据」、有决策收件箱时只在那里问；README 按文档建议；版本号 0.3.0（验收 19）

- [ ] Task 14：R20——合并检查失败的退回分「模块需要修改」「检查环境出了问题」两种、`merge renotice`、`merge run` 输出提交钩子退出码与最后 10 行；skill 写明两种退回怎么处理（验收 20、21）

### Checkpoint 3（gate）：模块最终验收

- [ ] 全部测试全绿；21 条验收逐条对应测试；列出实际改动文件；附 Spec 与 crew-protocol Spec 的修订差异；冻结前按需求文档 R1–R20 逐项勾清单给用户看
- [ ] 本 Plan 获批即授权：每个任务完成后在 `main` 本地提交；不推送；不冻结、不动 `module-crew-release/`；冻结 0.3.0 与通知各方要用户在最终验收后另行批准

## Risks and Mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| 一个模块一项改动 `for_hub` 的返回值，牵动命令行与 `--then-batch` | 中 | Task 7 一并改调用方与测试 |
| 原文文件与正文记录不一致（写了文件但事务失败） | 中 | 文件按内容寻址、可重复写；记录在事务里写，失败时文件只是多余、不被引用 |
| 契约 v2.1 样例与已有实现的键名不同 | 中 | Task 6 先改钉，逐份对照，对不上的报给契约负责人 |
| 赶不上批 2 阶段丙 | 中 | Task 6–9 优先；Task 11、12 可后移 |

## 变更记录

- 2026-10-19：加 Task 14（R20 两项小修），最终验收改为 21 条验收并在冻结前按需求文档逐项勾清单。原因：用户决定 51；来源：用户 2026-10-19 在本会话选做法 A。
