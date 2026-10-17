<!-- spec-guard: review approved -->
# Implementation Plan: crew-review-batch

> 依据：`spec/crew-review-batch.md`（已批准）。任务清单：`tasks/crew-review-batch/todo.md`。

## Overview

先做 `review add`（指纹核对、取代、查重），再做只读的 `review batch`，然后是 `review answer`（最简单的答复路径），
最后是 `review approve`（复制、标记、提交、答复与通知）及其失败处理；收尾接命令行与 skill。每个任务先写失败的测试，再实现到全绿，单独提交。

## Architecture Decisions

- `module_crew/review.py` 入口：`add(db, text, sender, relay_id)`、`batch(project)`、`answer(db, number, original)`、`approve(project, numbers, original)`；
  复用 `inbox` 的 `Outcome`／`AnswerRefused`／`Reply` 与查重写法（事件 `data.relayId`）。
- 指纹核对：`git -C <worktree> ls-files --error-unmatch <path>`、`git -C <worktree> diff --quiet HEAD -- <path>`，再算 `sha256`；记录 `git rev-parse HEAD`。
- `approve` 的评审标记命令从 spec-guard `interface.json` 的 `reviewMark.command` 取，校验与填占位符复用 `probe` 中 `_map_command` 的规则（抽出一个通用的 `_safe_command(root, command, fill)`，`run_map` 改为调用它，行为不变）。
- 集成 checkout 用 `probe._checkout_of(project, integrationBranch)`；复制用 `git -C <模块 worktree> show <提交>:<路径>` 的输出写入集成 checkout。
- 开工通知判断：本次批准后，该模块是否已有 `answered` 且属于某个 `review-approval` 的 Spec 与 Plan 交审。
- 测试夹具：`tests/helpers.py` 的假 spec-guard 在 1.1 时多一个 `reviewMark` 入口与 `hooks/review_mark.py` 假脚本（可用环境变量让它失败），`StartCase` 增加「开出两个模块、在 worktree 提交 Spec 与 Plan、生成交审正文」的辅助方法。

## 影响面

新增：`module_crew/review.py`、`tests/test_review_add.py`、`tests/test_review_approve.py`。
修改：`module_crew/probe.py`（抽出命令安全校验，行为不变）、`module_crew/__main__.py`（`review` 子命令）、`skills/crew-coordinator/SKILL.md`、`tests/helpers.py`、`tests/test_skills.py`。
测试会在临时仓库的集成分支上真实提交；不涉及界面。

## Task List

### Phase 1：收件与列表

- [ ] Task 1：`review add`——指纹核对、拒收、取代、查重（验收 1、2、3）
- [ ] Task 2：`review batch`——列出、依赖核对、冲突（验收 4）

### Checkpoint 1（report）

- [ ] 全部测试全绿

### Phase 2：答复与批准

- [ ] Task 3：`review answer`（验收 9）
- [ ] Task 4：抽出命令安全校验 + `review approve` 成功路径与开工通知条件（验收 5、6）
- [ ] Task 5：`review approve` 的检查与中途失败（验收 7、8）

### Phase 3：命令与 skill

- [ ] Task 6：命令行与协调会话 skill（验收 10）

### Checkpoint 2（gate）：模块最终验收

- [ ] 全部测试全绿；逐条对照 Spec 的 10 条验收标准，写明各由哪个测试覆盖
- [ ] 在对话里列出本模块实际改动的文件（新增、修改、删除与行数），并贴出 skill 新增与改动部分
- [ ] 本 Plan 获批即授权：每个任务完成后在 `main` 做一次本地提交；测试只在临时仓库的集成分支上提交；不推送

## Risks and Mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| 抽出命令校验时改坏 crew-probe | 中 | 先跑 crew-probe 全部测试作基线，抽出后原样通过 |
| `reviewMark` 键名定稿后与夹具不同 | 中 | 键名集中在一处常量；未决问题已登记 |
| 批准中途失败留下未提交文件，用户不知道 | 中 | 退出码 4 并逐个列出已改文件；skill 写明此时交用户决定 |
