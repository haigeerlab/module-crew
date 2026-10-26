# Implementation Plan: crew-autonomy-tier

<!-- spec-guard: review pending -->

> 依据：`spec/crew-autonomy-tier.md`（用户 2026-10-26 批准，事项 C234「C234 A」）。任务清单：`tasks/crew-autonomy-tier/todo.md`。

## Overview

先打底（读档位、生效档位与降档上限、`tier` 与 `tier --preflight`），再接 standard 的两项效果（评审节奏、声明范围），
然后做出事降档与 `tier restore`、升档建议、relaxed 的 `tier digest`，接着 `status` 一段与底线测试，最后改 skill 与 README、同步后跑全量测试。
每个任务先写失败的测试、看到红再实现到绿，在本模块分支本地提交；不推送、不发版。每个任务都验证「档位没设时行为逐字不变」。

## Architecture Decisions

- **新文件 `module_crew/autonomy.py`** 集中本模块的逻辑：`read(project) -> Tier`、`effective(db, project) -> Effective`（进程内缓存）、`preflight(db, project) -> (ok, lines)`、
  `incident(db, project, kind, detail) -> str | None`、`restore(db, project, original)`、`evidence(db, since)`、`suggestion(db, project)`、`digest(db, project, mark_told)`。
  其他文件只加一两行调用，减少和 crew-codex-offload 的冲突面。
- **读档位**：复用 `probe.find_plugin`／`read_interface`；`autonomyTier.readFrom` 必须以固定前缀开头，命令参数列表写死在 `autonomy.py`（`python3 -B hooks/project_config.py show --project <集成 checkout> --format json`），
  脚本路径核对在 spec-guard 安装目录内，`cwd` 设为安装目录、带 `probe.MAP_TIMEOUT` 超时、不经 shell。集成 checkout 用 `probe._checkout_of(project, integrationBranch)` 找。
- **版本比较**：`preflight` 用 `found.version` 按点分整数比较 ≥ `0.85.0`，读不出版本按不满足。Codex 会话判定：状态库 `session` 里 `host == "codex-desktop"` 且 `status == "active"`。
- **状态记录**：`config/autonomy` 一条记录（`config` 种类已有，不改 `store.py`）；事件动作 `tier-seen`、`tier-lowered`、`tier-restored`、`tier-cap-cleared`、`tier-suggested`、`digest-told`。
  `effective` 在读到的生效档位与 `seen` 不同时写一次 `tier-seen`，设的档位与 `capFor` 不同时清 `cap` 并写 `tier-cap-cleared`；档位没设且没有 `cap` 时什么都不写（验收 1：没有 `config/autonomy`）。
- **standard 的接入点**：`declared.enabled(db)` 在 `declaredScope` 没设时调 `autonomy.effective`（项目路径由 `db.path` 反推到仓库）；`start.cadence_info` 在 `cap` 生效且压到 strict 时把值改成 `separate`、来源写「自治档位降到 strict」，
  `review_cadence` 跟着它走，所以开工说明与 `review batch`（`review.py:627` 已调 `start.review_cadence`）不用另改。
- **降档挂钩**：`merge._run` 退回分支 `kind == "module"` 时、`merge.revoke` 成功后、`review.note` 记 `rework-over-limit` 后、`checks.baseline` 新跑出失败调 `fix_task` 处，各调一次 `autonomy.incident` 并把返回行加进输出；
  幂等键 = `kind + 事项号（或基线树）`，记在 `config/autonomy.incident` 与事件里，同一键不降第二次。
- **digest 的来源**：只读事件日志里 `seq > toldSeq` 的行：`item.merged`（合入与同步通知的收件人取自合入时的会话登记）、`request.landed`／`partly-landed`、`check.*`、`config.integration-seen`（不经队列的提交）；
  `--mark-told` 写 `toldSeq` 并对还没汇总的提前落地调 `changes` 现有的 mark-told 逻辑（只调用，不改 `changes.py`）。

## 影响面

新增：`module_crew/autonomy.py`、`tests/test_autonomy_tier.py`。
修改：`declared.py`（`enabled`）、`start.py`（`cadence_info`）、`merge.py`（`_run` 退回分支与合入后输出、`revoke`）、`review.py`（`note`）、`checks.py`（`baseline`）、`probe.py`（`status` 的 `store.autonomy`）、
`__main__.py`（`tier` 子命令、`status` 一段）、`skills/crew-coordinator/SKILL.md`、`codex-skills/crew-coordinator/SKILL.md`、`skills/crew-dev/SKILL.md`、`codex-skills/crew-dev/SKILL.md`、`README.md`。
不新增依赖；不改契约、钩子、`interface.json`、`store.py`、`changes.py`、`present.py`、`unqueued.py`、版本号、CHANGELOG（发版时由模块协调写）。公共文件不碰。

## Task List

- [ ] Task 1：读档位与生效档位——`autonomy.read`、`effective`、`config/autonomy` 的 `seen`／`cap` 清除规则；`tier [--json]`（Spec 验收 2、验收 1 的 `tier` 部分）
  - 验证：1.11 夹具三种值三种来源读对；1.10、`readFrom` 写法不同、脚本跑不成都读作 strict 带原因；档位没设时不写 `config/autonomy`
- [ ] Task 2：`tier --preflight`（Spec 验收 3）
  - 验证：0.85.0 退出码 0；0.84.2、接口没有 `autonomyTier` 退出码 3 带原因；登记过 Codex 会话多一行提醒、退出码不变

### Checkpoint 1（report）：读档位就位，相关测试通过，记入 todo 后继续

- [ ] Task 3：standard 的两项效果——`declared.enabled` 派生、`start.cadence_info` 在 `cap` 压到 strict 时返回 separate、standard 而 `reviewCadence=separate` 的提示行（Spec 验收 4、验收 6 的评审节奏部分）
  - 验证：standard + combined 时开工说明写 combined、`review batch` 合并 Spec 与 Plan；`declaredScope` 没设时 `change add` 走名单内分类、设 `off` 时不走；档位没设时与改前逐字一致
- [ ] Task 4：出事降档与 `tier restore`——四个挂钩、幂等、`cap` 清除（Spec 验收 6、7）
  - 验证：四类事件各降一档、输出带「马上告诉用户」、记 `tier-lowered`；strict 不变无输出；环境退回、旧基线失败记录不降；同一事项不降两次；`restore` 没原话或没 `cap` 退出码 3，有原话抬一档
- [ ] Task 5：升档建议——证据统计、`tier`／`merge run` 合入输出的建议行、同一起点只记一次（Spec 验收 8）
  - 验证：造 3 个达标合入模块出建议；其中一个返工 2 次不出；档位没设不出；`tier-suggested` 只一条

### Checkpoint 2（report）：降档、恢复与建议就位，相关测试与合并、返工、基线检查回归测试通过，记入 todo 后继续

- [ ] Task 6：relaxed 的 `tier digest [--json] [--mark-told]`（Spec 验收 5）
  - 验证：列出 `toldSeq` 之后的同步、检查账、不经队列的提交、未汇总的提前落地，按模块分组带汇总正文；`--mark-told` 后退出码 3；降档、等待用户、修基线任务不在里面
- [ ] Task 7：`status` 档位一段与 `--json` 的 `store.autonomy`；底线测试（Spec 验收 9、决策 9）
  - 验证：开关没开且无 `cap` 时 `status` 逐字不变、`autonomy` 为 null；relaxed 下 `review approve` 没原话被拒、开工说明仍有「收到开工类【协调通知】之前不要开始构建」、最终验收仍要 `review answer`
- [ ] Task 8：四份 skill、README；`module-crew sync` 合入集成分支后后台跑全量测试；本机 spec-guard 0.85.0 实测读档位一次（Spec 验收 10、11、验收 1）

### Checkpoint 3（gate）：最终验收

- [ ] 回告：完成情况经模块协调转告 ecosystem-lead（S32 第二节 module-crew 第 5 条已实现）

## Risks

| 风险 | 影响 | 缓解 |
|---|---|---|
| 和 crew-codex-offload 同改 `merge.py`、`__main__.py`、`probe.py`、coordinator skill | 合并冲突 | 改动集中在 `autonomy.py`，现有文件只加调用行；Spec「并行边界」已列函数名供协调排顺序 |
| `declared.enabled`、`cadence_info` 每次都调 spec-guard 子进程 | 命令变慢 | `declaredScope` 显式设过就不读档位；`effective` 进程内缓存一次 |
| 档位没设时行为被带歪 | 现有项目受影响 | 每个任务都加「没设时逐字一致」的测试；全量测试原样通过 |
| `readFrom` 是文字不是命令数组 | spec-guard 改写法后读错 | 只认固定前缀，不符合就读作 strict 并写原因（宁严勿松） |
| 降档在合并事务里出错 | 合并记录不完整 | `incident` 放在合并事务提交之后单独一个事务，失败只少一行提示，不影响合并结果 |
