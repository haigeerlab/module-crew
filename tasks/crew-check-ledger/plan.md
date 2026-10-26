# Implementation Plan: crew-check-ledger

<!-- spec-guard: review approved -->

> 依据：`spec/crew-check-ledger.md`（用户 2026-10-26 批准，事项 C204「C204 A」）。任务清单：`tasks/crew-check-ledger/todo.md`。

## Overview

先打底（检查账记录种类、配置与开关、读写检查账），再做模块会话用的 `check quick`，然后让 `merge run` 记账；
接着改通知措辞、做基线检查与修基线任务、`change land` 的快检查、最终验收附检查账、`status`，最后改 skill 与 README。
每个任务先写失败的测试、看到红再实现到绿，在本模块分支本地提交；不推送、不发版。每个任务都验证「开关关着时行为不变」。

## Architecture Decisions

- **新文件 `module_crew/checks.py`** 集中本模块的逻辑：`enabled(cfg)`、`tree_of(path)`（干净时返回 `HEAD^{tree}`，否则 None）、
  `lookup(db, tree, kind, command)`、`record(db, entry)`、`run_check(argv_text, cwd, timeout) -> Outcome`（复用 `merge._SHELL_OPS` 的写入校验、
  `merge.CANNOT_RUN` 的判定方式，不经 shell）、`quick(cwd)`、`baseline(project)`、`baseline_task(...)`、`step_text(db)`（决策 8 的措辞）。
  其他文件只加一两行调用，减少和 crew-declared-scope 的冲突面。
- **状态库**：`store.KINDS` 加 `check`；键 `<树>.<quick|full>` 不是编号，不进 `NUMBERED`。不改 `_validate_task`（修基线任务的预计文件按决策 7 总是非空，没有就不建）。
- **配置**：`__main__._config_set` 加 `--quick-check-command`、`--check-ledger on|off`；打开时校验两条命令都在。
- **merge.py 只动三处**：`_run_check` 末尾记账（拿到 checkout 的树）、`_run` 在勾选与标记提交之后调 `checks.inherit(...)`、`_close_merged` 的 todo 改用 `checks.step_text`。
- **基线检查拿合并锁**：`mergelock.acquire(db, approval=None, unit="基线检查")`；`describe` 对 `approval` 为 None 时写「基线检查正在跑」。`merge run` 与写命令查锁的逻辑不改。
- **通知措辞**：`sync.STEP` 不变，后半句「跑完整检查后继续」换成 `checks.step_text(db)`，开关关着返回原文，所以关着时逐字不变。

## 影响面

新增：`module_crew/checks.py`、`tests/test_check_ledger.py`。
修改：`store.py`、`merge.py`（`_run_check`、`_run`、`_close_merged`）、`mergelock.py`、`sync.py`、`changes.py`（`land`）、`failure.py`、`unqueued.py`、`tasks.py`（`render_kickoff`）、
`review.py`（`add`、`_add_task`、`show`、`batch`）、`probe.py`、`__main__.py`、`skills/crew-dev/SKILL.md`、`skills/crew-coordinator/SKILL.md`、`README.md`。
不新增依赖；不改契约、钩子、`interface.json`、版本号、CHANGELOG（发版时由模块协调写）。公共文件不碰。

## Task List

- [ ] Task 1：检查账打底——`store.KINDS` 加 `check`；`checks.py` 的读写与开关判断；`config set --quick-check-command／--check-ledger`（Spec 验收 2、验收 1 的配置部分）
  - 验证：开关缺命令被拒、shell 运算符被拒、没原话被拒；写入后能读回；全量测试仍过
- [ ] Task 2：`check quick`、`check show`、`check list`（Spec 验收 3、4，验收 12 的 show／list 部分）
  - 验证：小脚本记调用次数，同一棵树第二次不调用；`--rerun`、改命令、完整检查通过覆盖；不干净拒绝；失败记 fail；超时、找不到程序不记
- [ ] Task 3：`merge run` 记账与继承记录（Spec 验收 5）
  - 验证：开关开时检查脚本照样被调用、记 `by: merge-run`；勾选提交后的顶端树有继承记录；多出别的改动时不记；开关关时没有 `check` 记录

### Checkpoint 1（report）：检查账与快检查就位，相关测试通过，记入 todo 后继续

- [ ] Task 4：通知措辞跟着开关走——合并后同步基线、`change land` 同步通知、`unqueued --notify`、恢复补同步、`sync` 最后一行、轻任务开工说明（Spec 验收 6、验收 1 的措辞部分）
  - 验证：开关开时六处都写 `module-crew check quick` 且 `protocol.parse` 判合格；关时与现在逐字一致
- [ ] Task 5：`check baseline`、合并锁互挡、修基线任务只建一次、快检查失败时提示基线红（Spec 验收 7、8、9）
  - 验证：已有记录不重跑；不是模块协调退出码 3；锁被占退出码 6、它跑着时 `merge run` 退出码 6；有绿基线时建任务（字段齐全）、重复跑不再建；无绿基线不建
- [ ] Task 6：`change land` 提交前快检查与 `--skip-quick-check`（Spec 验收 10）
  - 验证：通过才提交并记账；失败不提交、文件仍暂存、退出码 5、请求仍开；跳过要原话并记进请求
- [ ] Task 7：最终验收附检查账（模块与轻任务）（Spec 验收 11）
  - 验证：`checks` 字段、`review show`／`review batch` 的「检查账」一行；查不到只提醒、照常收下
- [ ] Task 8：`status` 的基线检查账一行与 `--json` 的 `checks`（Spec 验收 12）

### Checkpoint 2（report）：命令与记账全部就位，全量测试通过，记入 todo 后继续

- [ ] Task 9：`crew-dev`、`crew-coordinator` skill，README 命令一览与流程一段；`module-crew sync` 合入集成分支后跑全量测试（Spec 验收 13、14、验收 1）

### Checkpoint 3（gate）：最终验收

- [ ] 回告：完成情况经模块协调转告 ecosystem-lead（S32 第二节 module-crew 第 3、4 条已实现）

## Risks

| 风险 | 影响 | 缓解 |
|---|---|---|
| 和 crew-declared-scope 同改 `changes.land`、`review.py` | 合并冲突 | 改动集中在 `checks.py`，现有文件只加调用行；Spec 已列出函数名供协调排顺序 |
| 开关关着时措辞或行为被带歪 | 现有项目受影响 | 每个任务都加「关着时逐字一致」的测试；全量测试原样通过 |
| 继承记录掩盖了真实失败 | 基线显示通过但其实红 | 只在勾选、标记提交只改那两个文件时记；`check baseline --rerun` 可补跑 |
| 基线检查和合并抢集成 checkout | 检查结果不可信 | 基线检查拿合并锁，互相挡 |
| 测试里的时序（锁互挡） | 偶发失败 | 沿用 crew-background-checks 测试的做法：等锁记录出现再动作，检查脚本睡足够久 |
