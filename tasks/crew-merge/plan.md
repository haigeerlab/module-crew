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

## 修订（2026-11-24）：规范 v1.5 F3 合并方式统一

- 来源：ecosystem-lead #22516（S109，规范 v1.5 新增 F3）；用户在 mc-coord 答复「重开 crew-merge」。
- 要改：用户在对话里说「合并」后，由 module-crew 凭原话执行 `gh pr merge --auto`（合并方式按本仓现有习惯），等必需检查 `CI required` 通过后由 GitHub 合并，再核实 PR 已合并、记下合并提交；用户不用去 GitHub 点。「合并：自动」（不问就合）不开。
- 前提：仓库开了 Allow auto-merge（ecosystem-lead 逐仓取用户同意后统一开，本模块不开），主干已有必需检查；不满足时命令拒绝并说明，不退化成直接合并。
- 影响面：`spec/crew-merge.md`（第 11 条、范围、「绝不」一节与对应验收条）、`docs/requirements-record.md`、两份 `crew-coordinator` skill、`module_crew/merge.py` 的 PR 提示文字、README 中英、`docs/guide.md`、`docs/architecture.md`，以及 CLAUDE.md／AGENTS.md 共享段中相应写法。
- 先改 Spec 交复审，Spec 批准后再细化本节任务并交审本 Plan；批准前不改代码。（2026-11-24 改为 Spec 修订与本 Plan 一起交审，依开工背景。）
- Spec 改动：新增关键决策 12（`merge pr-merge`）、13（`merge pr-check`），验收 26–30；改目标、范围、假设 7、9、「先问」「绝不」、验收 11。

### 修订任务（2026-11-24）

- [ ] Task R1：`merge pr-merge` 的只读核对与下令（验收 26、27、28）
  - 核对：推送记录有 PR；`gh pr view <PR> --json state,baseRefName,headRefOid,mergeCommit,mergedAt,autoMergeRequest`；`gh api repos/<owner>/<repo> --jq .allow_auto_merge`；
    必需检查读 `gh api repos/<o>/<r>/branches/<base>/protection/required_status_checks`（404 视为没有）与 `gh api repos/<o>/<r>/rules/branches/<base>` 里 `type == "required_status_checks"` 的项，两处合并去重。
  - 下令：先在事务里记 `mergeRequest`，再 `gh pr merge <PR> --auto --merge --match-head-commit <头提交>`，然后读一次状态（同 R2 的判定）。
  - owner/repo 用已有 `_repo_name(url)`；`gh` 用已有 `_gh()`（测试用 `MODULE_CREW_GH` 指向假脚本）；外部命令一律参数列表、带超时。
  - 验证：`tests/test_merge_pr.py` 的假 gh 按场景回 JSON 并把参数写进文件；断言参数、退出码与推送记录。
- [ ] Task R2：`merge pr-check` 与 `--wait`（验收 29）
  - 判定：`MERGED` → 记 `merged` 退出码 0；`OPEN` 且 `autoMergeRequest` 非空 → 6；`OPEN` 且为空、或 `CLOSED` → 4；读不到 → 4。
  - `--wait <秒>`：每 30 秒读一次（间隔经环境变量 `MODULE_CREW_PR_POLL` 可调，只给测试用），等到 0 或 4 就返回，到时仍排着返回 6。
- [ ] Task R3：命令行、提示文字与文档（验收 11、30）
  - `module_crew/__main__.py` 加 `pr-merge`、`pr-check` 子命令（原话参数与 `push` 同样两种写法）；`merge push` 开 PR 后的提示改为「用户在对话里说『合并』后用 merge pr-merge C<号>」，PR 正文首句同步。
  - `skills/crew-coordinator/SKILL.md`、`codex-skills/crew-coordinator/SKILL.md` 的推送一步改成 F3 流程；`README.md`、`README.en.md`、`docs/guide.md`、`docs/architecture.md`、`docs/requirements-record.md` 里「远端合并由用户做／不开自动合并」改为 F3 写法。
  - CLAUDE.md／AGENTS.md 共享段经核没有「由用户合并」的写法，不改；若构建中发现要改，按公共文件发【公共变更请求】。
  - 验证：`tests/test_skills.py` 加断言两份 skill 都有 `merge pr-merge`、`merge pr-check`，且不再有「PR 由用户在远端合并」。

### 修订检查点（gate）：最终验收

- [ ] `module-crew check quick` 通过；逐条对照验收 11、26–30 写明由哪个测试覆盖；列出实际改动的文件与行数；附 Spec 修订差异（一次批准同时批准修订后的 Spec）
- 本 Plan 获批即授权：在本模块分支做 R1–R3 的本地提交；测试只用假 `gh`，不访问网络，不对真实仓库下令合并；不推送。
