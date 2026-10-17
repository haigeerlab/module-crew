<!-- spec-guard: review approved -->
# Implementation Plan: crew-merge

> 依据：`spec/crew-merge.md`（已批准）。任务清单：`tasks/crew-merge/todo.md`。

## Overview

先做批准与队列，再做 `merge run` 的合并前清单与检查命令配置，然后是合并成功路径、检查失败撤销与冲突中止，
再做收回 worktree、推送预告与推送，最后接命令行与 skill。每个任务先写失败的测试，再实现到全绿，单独提交。

## Architecture Decisions

- `module_crew/merge.py` 入口：`approve(db, review_no, original)`、`queue(project)`、`run(project, check_command=None, replace=False)`、
  `cleanup(project, module, original)`、`push_plan(project)`、`push(project, original)`；复用 `review._reply_text`、`inbox.AnswerRefused／Reply`。
- 队列排序取 `probe.run(project).map["modules"]` 的顺序；`/map` 不可用时按批准编号排序并在输出里说明。
- 完整检查：`subprocess.run(shlex.split(cmd), cwd=集成 checkout, timeout=checkTimeout)`；超时与非零退出都算失败，输出尾部 40 行进原因。
- 撤销：`git revert -m 1 --no-edit <合并提交>`；冲突判断用 `git merge --no-ff` 的退出码加 `git diff --name-only --diff-filter=U`。
- 推送：远端取配置 `remote`（默认 `origin`，`git remote get-url` 不通就报没有远端）；批次号用本次 `push` 事项的编号（先由 `review._next_number` 同样的办法算出，事务里核对）；
  `gh` 用 `shutil.which("gh")` 判断，命令 `gh pr create --base <prBase> --head crew/batch-<号> --title ... --body-file <正文文件>`。
- 测试夹具：`tests/helpers.py` 加「在模块 worktree 写代码并提交、生成最终验收交审」的辅助；检查命令用临时目录里的小脚本；远端用 `git init --bare`；假 `gh` 放在测试自建 PATH 目录。

## 影响面

新增：`module_crew/merge.py`、`tests/test_merge_run.py`、`tests/test_merge_finish.py`。
修改：`module_crew/__main__.py`（`merge` 子命令）、`skills/crew-coordinator/SKILL.md`、`tests/helpers.py`、`tests/test_skills.py`。
测试在临时仓库里真实合并、撤销、推送到临时裸仓库；不涉及界面，不访问网络。

## Task List

### Phase 1：批准与合并

- [ ] Task 1：`merge approve` 与 `merge queue`（验收 1、2）
- [ ] Task 2：`merge run` 的合并前清单与检查命令配置（验收 3、4）
- [ ] Task 3：合并成功路径与通知（验收 5）
- [ ] Task 4：检查失败撤销、超时、冲突中止与退回通知（验收 6、7）

### Checkpoint 1（report）

- [ ] 全部测试全绿

### Phase 2：收尾与远端

- [ ] Task 5：`merge cleanup`（验收 8）
- [ ] Task 6：`merge push-plan` 与 `merge push`（验收 9、10）
- [ ] Task 7：命令行与协调会话 skill（验收 11）

### Checkpoint 2（gate）：模块最终验收

- [ ] 全部测试全绿；逐条对照 Spec 的 11 条验收标准，写明各由哪个测试覆盖
- [ ] 在对话里列出本模块实际改动的文件（新增、修改、删除与行数），并贴出 skill 新增一节
- [ ] 本 Plan 获批即授权：每个任务完成后在 `main` 做一次本地提交；测试只在临时目录合并、推送到临时裸仓库；不推送本仓库

## Risks and Mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| 测试误推到真实远端或调用真实 `gh` | 高 | 远端一律是临时裸仓库；测试把 PATH 指向只含假 `gh` 的目录，断言没有网络访问的参数 |
| 撤销后集成分支内容与合并前不一致 | 高 | 测试比对撤销后与合并前的树对象 |
| 检查命令长时间挂住 | 中 | 超时可配；测试用 1 秒超时验证 |
