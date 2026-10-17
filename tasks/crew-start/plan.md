<!-- spec-guard: review approved -->
# Implementation Plan: crew-start

> 依据：`spec/crew-start.md`（已批准）。任务清单：`tasks/crew-start/todo.md`。

## Overview

先做只读的 `start plan`（空位与提议），再做 `start prepare` 的校验（不写任何东西），然后是逐模块落地（worktree、登记、批准事项、开工说明），
再补中途失败与重跑，最后接命令行与 skill。每个任务先写失败的测试，再实现到全绿，单独提交。

## Architecture Decisions

- `module_crew/start.py`：`plan(project) -> Proposal`、`validate(project, modules, short, max) -> list[str]`（返回拒绝原因，空表示通过）、
  `prepare(project, modules, original, short, max) -> PrepareResult`；体检一律 `probe.run()`，`/map` 结果取 `report.map`。
- 空位 = `maxModules`（配置，未建库时取参数或默认 3）减状态库里 `active` 的 `dev` 会话数。
- 落地顺序：未建库就 `store.init_store`；第一个事务写配置、协调会话登记、开工批准事项；之后每个模块：`git worktree add -b <id> <路径> <集成分支>` 成功后，一个事务登记会话并写开工说明正文。
  批准事项的编号先分配，开工说明引用它。
- 开工说明正文由 `render_kickoff(...)` 按 Spec 模板生成，依赖模块取 `/map --json` 中该模块的 `dependsOn`，接口写成 `spec/<依赖 id>.md`。
- 测试夹具：`tests/helpers.py` 的假 `map_view.py` 增加 `FAKE_MAP_FILE` 环境变量——指向一个 JSON 文件时原样输出它，供本模块构造 `startable.modules = [b, c, d]`、依赖与职责。

## 影响面

新增：`module_crew/start.py`、`tests/test_start_plan.py`、`tests/test_start_prepare.py`。
修改：`module_crew/__main__.py`（`start` 子命令）、`skills/crew-coordinator/SKILL.md`（「开工」一节）、`tests/helpers.py`（夹具开关）、`tests/test_skills.py`（新关键句）。
测试会在临时目录里真实执行 `git worktree add`；不涉及界面。

## Task List

### Phase 1：提议与校验

- [ ] Task 1：`start plan`（验收 1，及验收 2 的 plan 部分）
- [ ] Task 2：`prepare` 校验——任何一项不过都不写（验收 2 的 prepare 部分、4、7）

### Phase 2：落地

- [ ] Task 3：逐模块落地——配置、协调会话登记、批准事项、worktree、会话登记、开工说明（验收 3、6）
- [ ] Task 4：中途失败与重跑（验收 5）

### Checkpoint 1（report）

- [ ] 全部测试全绿

### Phase 3：命令与 skill

- [ ] Task 5：`start plan`／`start prepare` 命令行与 `--json`、退出码
- [ ] Task 6：协调会话 skill「开工」一节（验收 8）

### Checkpoint 2（gate）：模块最终验收

- [ ] 全部测试全绿；逐条对照 Spec 的 8 条验收标准，写明各由哪个测试覆盖
- [ ] 在对话里列出本模块实际改动的文件（新增、修改、删除与行数），并贴出 skill 新增一节全文
- [ ] 本 Plan 获批即授权：每个任务完成后在 `main` 做一次本地提交；测试只在临时目录建 worktree；不推送

## Risks and Mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| `git worktree add` 与状态库事务之间失败，留下没登记的 worktree | 中 | Spec 已定：不删、停下、输出写明；任务 4 专测 |
| 0.68.0 实际输出与夹具不同 | 中 | 字段已定稿；依赖字段名记为未决，发版后对照一次 |
| 测试误在真实仓库旁建目录 | 高 | worktree 目录按临时仓库的父目录计算；测试断言所有新目录都在临时目录内 |
