<!-- spec-guard: review approved -->

# Implementation Plan: crew-shared-changes

> 依据：`spec/crew-shared-changes.md`（已批准）。任务清单：`tasks/crew-shared-changes/todo.md`。

## Overview

先做 `change add`（记账、等待单、分流提示、查重）与只读的 `change list`，再做 `change answer`，然后是 `change land`（核对、提交、通知），
最后接命令行与 skill。每个任务先写失败的测试，再实现到全绿，单独提交。

## Architecture Decisions

- `module_crew/changes.py` 入口：`add(db, text, sender, relay_id)`、`pending(db)`、`answer(db, number, original)`、`land(project, number, original=None)`；
  复用 `inbox` 的 `Outcome`／`AnswerRefused`／`Reply`，查重沿用事件 `data.relayId` 的写法。
- 分流提示 `hints_for(files, others)` 是纯函数，规则按 Spec 关键决策 4 写成模块级常量。
- 等待单与请求在同一事务里写：先分配等待单编号写 `ticket`，再写 `request` 并记下等待单编号；`waitingFor` 填协调会话的邮箱名（取状态库在用 `coordinator`）。
- `land` 的核对：`git -C <集成 checkout> status --porcelain --untracked-files=all`，逐行取路径（含改名的新旧两侧），全部须在清单内且至少一条。
- 通知正文：`protocol.render_coordination_notice("sync-baseline", ...)`；给请求方的在前面加 `回复：#<relayId>\n` 后用 `protocol.parse` 自检。

## 影响面

新增：`module_crew/changes.py`、`tests/test_changes.py`。
修改：`module_crew/__main__.py`（`change` 子命令）、`skills/crew-coordinator/SKILL.md`、`tests/test_skills.py`。
测试会在临时仓库的集成分支上真实提交；不涉及界面。

## Task List

### Phase 1：记账

- [ ] Task 1：`change add` 与 `change list`（验收 1、2、3、4）
- [ ] Task 2：`change answer`（验收 8）

### Checkpoint 1（report）

- [ ] 全部测试全绿

### Phase 2：落地与命令

- [ ] Task 3：`change land`（验收 5、6、7）
- [ ] Task 4：命令行与协调会话 skill（验收 9）

### Checkpoint 2（gate）：模块最终验收

- [ ] 全部测试全绿；逐条对照 Spec 的 9 条验收标准，写明各由哪个测试覆盖
- [ ] 在对话里列出本模块实际改动的文件（新增、修改、删除与行数），并贴出 skill 改动
- [ ] 本 Plan 获批即授权：每个任务完成后在 `main` 做一次本地提交；测试只在临时仓库的集成分支上提交；不推送

## Risks and Mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| `git status --porcelain` 的改名、带空格路径解析错 | 中 | 用 `-z` 输出解析；测试含改名与带空格路径 |
| 分流规则漏掉某种锁文件 | 低 | 只是提示，最终由协调会话判断；规则只增不改，漏了补 |

## 0.17.0 返工说明（2026-10-27）

为什么返工：LIVE-SAAS 现场问题与 0.16.1 期间暴露的流程卡点，用户在 mc-coord 确认 0.17.0 做这几件（见 todo「0.17.0 修订」一节）。超出原范围，Plan 改回 pending，由模块会话按修订后的 Spec 补写本节的任务分解后交审。

### 依据与架构决定

依据：`spec/crew-shared-changes.md` 关键决策 7、8，验收 10～16（2026-10-27 批准，C280）。用户在 C281 答「README 与 crew-coordinator skill 两边照常各改各的段落」：本模块只改这两个文件里「公共文件」「公共变更请求」相关的段落。

- `changes.land_batch(project, numbers, original=None, skip_check=False) -> LandResult`：单个编号仍走原来的 `land`，一行不改它的行为（验收 14）。
  顺序：全部核对（编号、状态、每份清单都改了、改动不出并集）→ `git add` 并集 → 检查 → 提交 → 一个状态库事务（关请求、关等待单、生成通知）。核对不过直接返回 3，此时还没暂存。
- 检查：`checks.enabled(cfg)` 为真时用 `checks.check_tree(..., "quick", <write-tree>, ...)`（记账）；否则有 `checkCommand` 就用 `checks.run_command(cfg["checkCommand"], checkout, checks._timeout(cfg))`（不记账）；都没有且没给 `--skip-check` 加原话就返回 3。
- 提交、超时、钩子拒绝沿用 `land` 里的写法（`commits.message`、`merge.commit_timeout`、`commits.failure`／`hook_lines`、`unqueued.mark`），抽一个两边共用的小函数，只搬代码、不改单条的输出。
- 通知：`LandResult.sends` 每项多一个 `alsoAnswers` 键（单条时为空列表），`__main__` 有值时才打印。
- 保护文件：`changes.LOCK_FILES`、`changes.protected_lines(files, cfg) -> list[str]`（纯函数）；`add` 记账成功后把它的结果追加到 `Outcome.lines`；配置写入放在 `__main__._config_set`，和 `commitPrefix` 同一个事务写法，路径校验放在 `changes.protected_problem(path)`。

### 任务分解

- [ ] Task 5：批量落地 `land_batch`（验收 10、11、12、13、14）
  - 先写失败的测试：两条请求一起落地、同一请求方两条、整批拒绝 5 种、检查三种情况（开着快检查／没开跑 `checkCommand`／都没有与 `--skip-check`）、单条不变
  - 文件：`module_crew/changes.py`、`tests/test_changes.py`
  - 验证：`python3 -m unittest tests.test_changes -v`
- [ ] Task 6：命令行 `change land <编号>...`、`--skip-check`、`alsoAnswers` 输出；协调会话 skill 与 README 补批量落地（验收 16 前半）
  - 文件：`module_crew/__main__.py`（`_change` 与 `change` 解析器）、`skills/crew-coordinator/SKILL.md`、`README.md`、`tests/test_changes.py`（`CliTest`）、`tests/test_skills.py`
  - 验证：`python3 -m unittest tests.test_changes tests.test_skills -v`
- [ ] Task 7：保护文件名单与 `change add` 提示（验收 15、16 后半）
  - 文件：`module_crew/changes.py`、`module_crew/__main__.py`（`_config_set` 与 `config set` 解析器）、`skills/crew-coordinator/SKILL.md`、`README.md`、`tests/test_changes.py`、`tests/test_skills.py`
  - 验证：同上
- [ ] Checkpoint（report）：完整检查 `python3 -m unittest discover -s tests` 在后台跑（约 1800～3000 秒），全绿后记下用时与测试数继续；红了停下排查
- [ ] Checkpoint（gate）：最终验收——验收 10～16 逐条对应测试、列出实际改动文件与行数、贴出 skill 与 README 改动；停下等用户确认

每个 Task 完成后在模块分支本地提交一次；不推送。本 Plan 获批即授权以上改动与提交。不加新依赖。

### 风险

| 风险 | 影响 | 缓解 |
|---|---|---|
| 抽共用提交函数时改坏单条 `land` 的输出 | 中 | 先跑一遍已有 `LandTest`、`CliTest` 记基线，抽完逐字对比；验收 14 |
| `__main__.py` 与 crew-light-task 同时改 | 低 | 只动 `_change`、`_config_set` 两个函数和对应解析器；合并冲突由后合并的一方 `module-crew sync` 解决 |
| 完整检查测试里真跑 `checkCommand` 太慢 | 低 | 测试里的 `checkCommand` 用临时仓库里的小脚本（`python3 -c` 退出 0／1） |
| README、skill 两个模块都改 | 低 | 按 C281 只改自己的段落 |

## 变更记录

- 2026-10-27：追加「0.17.0 返工说明」，评审标记 approved 改回 pending；原因：0.17.0 修订超出原范围；来源：用户在 mc-coord 原话「0.17.0 需求就是这四件，前提假设 A1～A5 全按推荐」
- 2026-10-27：在「0.17.0 返工说明」补依据、架构决定、Task 5～7 与两个检查点、风险；原因：Spec 0.17.0 修订已批（C280）；来源：用户在 mc-coord 原话「C280 A；C281 A，README 与 crew-coordinator skill 两边照常各改各的段落」
