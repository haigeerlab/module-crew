# Implementation Plan: crew-spec-ahead

> 依据：`spec/crew-spec-ahead.md`（用户 2026-11-01 批准，事项 C459，原话「批准 C459」）。任务清单：`tasks/crew-spec-ahead/todo.md`。
> 本次随 Plan 一并复审 Spec 的一处修订（见 Spec「变更记录」）：CHANGELOG 与版本号改为随 0.23.0 发版由模块协调写，文档补 `docs/commands.md`。

## Overview

先实测 spec-guard 0.85.2 对依赖未完成的模块能否照常写批准标记（Spec 未决问题），再按链路逐段做：`start prepare` 认出提前开工并放宽 `declaredScope` 的两处挡住 →
开工说明限定段 → `review approve` 的开工通知闸 → 新命令 `start kickoff` → `status`／`merge run` 提示 → 文档与技能 → 同步后全量测试。
每个任务先写失败的测试、看到红再实现到绿，单独在模块分支本地提交，不推送、不发版；合入集成分支用 `module-crew sync`。

## Architecture Decisions

- **认出提前开工（`start.validate`）**：模块不在 `startable.modules`、也不能按重开处理时，若 `/map` 状态为 `not_ready`（`missingDeps` 非空），记入 `proposal.specAhead[m] = {"missing": [...], "info": {...}}`，不报拒绝原因；
  `blocked`、`suspended`、`in_progress` 照旧（Spec 假设 13）。判断顺序：已有在用会话 → 重开 → 提前开工 → 拒绝。
- **`declaredScope` 放宽**：`_held(db, mapped, modules)` 的调用处跳过 `proposal.specAhead` 里的模块；同批依赖检查在 a、b 之一属于 `specAhead` 时跳过。`plan()` 不变（不提议、原因照旧「等 …」）。
- **落地（`start.prepare`）**：`info` 合入 `specAhead` 的模块信息；开工批准事项加 `specAhead: [模块…]`（有才写）；会话登记加 `specAhead: {"missing": [...], "since": <批准事项号>}`；
  输出每个提前开工模块一行「<m>：提前开工（依赖 <列表> 未完成），只写 Spec 与 Plan」。store 的会话校验若对未知字段严格，同步加 `specAhead`、`kickoff` 校验。
- **开工说明（`render_kickoff`）**：新增参数 `spec_ahead: list[str] | None`，非空时在「这一步只做」行之后、「收到开工类【协调通知】之前不要开始构建」之前插入 Spec 关键决策 3 的两行；Codex 宿主照旧附 `codex_lines`。
- **依赖就位判断（新函数 `start.deps_ready(db, mapped, module) -> list[str]`）**：返回还没就位的依赖（`/map` 状态非 `done` 且不在 `_merged_modules(db)`）。`review`、`merge`、`status`、`kickoff` 共用。
- **开工通知闸（`review._approve`）**：在 `_start_todo` 之前判断：该模块在用 dev 会话带 `specAhead`、`kickoff` 为空、`deps_ready` 非空 → 不生成开工通知，输出 Spec 关键决策 4 的一行，`continue`。
  依赖已就位时照今天发，并把会话登记的 `kickoff` 记为本批准事项号（之后不再提示）。`/map` 由 `probe.run(project).map` 取，一次 approve 只取一次。
- **`start kickoff`（`start.kickoff(project, module, original) -> Outcome`）**：照 `offload.decline` 的结构。校验（Spec 关键决策 5）→ 一个事务：分配事项号写 `kind: "start-kickoff"` → 调 `review._start_todo`（外包开关打开且条件不满足返回 None 时整个事务不提交、退出码 3、照它的提示输出）→
  `protocol.render_coordination_notice(kind="start", basis=review.start_basis(...) + "，依赖 <列表> 已合入，用户 C<号> 同意开工", todo=...)` 写正文 → 会话登记写 `kickoff`。
  取 Spec 与 Plan 都已批准的那次批准事项：沿用 `offload._approval(db, module)` 的口径（必要时提到 `review` 里共用）。
- **提示（新函数 `start.spec_ahead_rows(db, report) -> list[dict]`）**：遍历在用 dev 会话里带 `specAhead` 且 `kickoff` 为空的，给出 `{module, missing, planApproved, kickoffReady, kickoff}`。
  `status` 文字在「会话与待办」打印 Spec 关键决策 6 的行，`status --json` 经 `probe.summarize_store` 加 `store.specAhead`；
  `merge run` 合入成功后，比较合入前后的 `missing`，对这次变成就位、Plan 已批的模块输出「依赖已就位」行。
- **CLI**：`__main__` 加 `start kickoff <模块> (--original | --original-file) [--json]`，属模块协调的写命令（照 `start prepare` 受会话守门）。

## 影响面

新增：`tests/test_spec_ahead.py`。
修改：`module_crew/start.py`、`review.py`、`merge.py`、`probe.py`（`summarize_store` 加字段）、`__main__.py`、按需 `store.py`（会话字段校验），
`skills/crew-coordinator/SKILL.md`、`codex-skills/crew-coordinator/…`、`skills/crew-dev/SKILL.md`、`codex-skills/crew-dev/…`、`docs/guide.md`、`docs/commands.md`、`README.md`、`README.en.md`，以及按需调整断言的已有测试。
不新增依赖，不改契约、`interface.json`、版本号、CHANGELOG（随发版由模块协调写）；不改公共文件。

## Task List

- [ ] Task 1：实测 spec-guard 0.85.2 对 `not_ready` 模块写批准标记与显示阶段（Spec 未决问题）——验证：临时仓库能力图 a → b、a 未完成，对 b 的 Spec、Plan 跑 `reviewMark` 入口写 approved 成功、`/map --json` 照常给出 b 的 `review`；拒绝就停在这里发【等待其他会话】
- [ ] Task 2：`start prepare` 认出提前开工、登记 `specAhead`、开工批准事项与输出行（Spec 验收 1、3、4）——验证：新测试先红后绿；`blocked`、名额满、已有会话、目录／分支已存在、串行照旧拒绝且不写；`start plan` 不提议 b；`test_start_plan`、`test_start_prepare` 照常通过
- [ ] Task 3：`declaredScope` 打开时的两处放宽（Spec 验收 5、6）——验证：开关关／开时 `prepare a b` 都成功；a 在用时 `prepare b` 成功；两个普通可开工模块有依赖、普通模块与在用模块有依赖照旧挡（回归）；`test_declared_scope` 照常通过
- [ ] Task 4：开工说明限定段，Claude 与 Codex 宿主（Spec 验收 2）——验证：b 的开工说明含两行限定、其余与普通开工说明逐行一致；Codex 宿主含限定段并附 Codex 段

### Checkpoint 1（report）：开会话这半段走通，相关测试通过，记入 todo 后继续

- [ ] Task 5：`deps_ready` 与 `review approve` 的开工通知闸（Spec 验收 7、8）——验证：a 未合入时只发【用户答复】、无开工通知、输出含「依赖 a 还没合入」；a 已合入时照今天发；`test_review_approve`、`test_review_start_notice` 照常通过
- [ ] Task 6：`start kickoff` 命令（Spec 验收 9 的拒绝部分、11、12）——验证：依赖未就位、Plan 未批、已发过、原话为空各退出码 3 且状态库不变；成功时记 `start-kickoff` 事项、开工通知可被 `protocol.parse` 判为合格、登记 `kickoff`；外包条件不满足时不发、不记、退出码 3 并提示 `offload decline`
- [ ] Task 7：`status`（文字与 `--json`）与 `merge run` 的提示（Spec 验收 9 的提示部分、10）——验证：a 未合入显示「b 提前开工，等 a 合入」；`merge run` 合入 a 后输出与 `status` 都含「b 的依赖已就位，可以发开工通知」；`--json` 的 `specAhead` 可解析；kickoff 后不再提示；`test_probe_status`、`test_merge_run` 照常通过

### Checkpoint 2（report）：命令层做完，全量测试通过，记入 todo 后继续

- [ ] Task 8：文档与技能：crew-coordinator（两份）「开工」补「提前开工」、crew-dev（两份）补 Plan 批准后停住、`docs/guide.md`、`docs/commands.md`、README／README.en（Spec 验收 13）——验证：文档断言测试先红后绿；`test_docs`、`test_skills`、`test_readme_hosts` 照常通过
- [ ] Task 9：`module-crew sync` 后全量测试（Spec 验收 14）——验证：`python3 -m unittest discover -s tests` 全部通过

### Checkpoint 3（gate）：最终验收

- [ ] 回告：发版后告诉 mc-coord（转用户）live-saas-backoffice 可以凭原话提前开依赖未完成的模块（来源 S60，随最终验收列出）

## 风险与对策

- **spec-guard 不认依赖未完成模块的批准**：整个功能就跑不通。对策：Task 1 先实测，拒绝就停下交模块协调（改 spec-guard 属 S61），不绕过。
- **放宽 `declaredScope` 波及普通模块**：对策：放宽只看 `proposal.specAhead`；Task 3 用两组回归测试锁住普通模块的挡住行为。
- **开工通知闸误伤普通模块**：对策：闸只对会话登记带 `specAhead` 且 `kickoff` 为空的生效；Task 5 跑已有开工通知测试回归。
- **`merge run` 输出改动影响解析方**：对策：只追加新行、不改已有行；`test_merge_run` 回归。
