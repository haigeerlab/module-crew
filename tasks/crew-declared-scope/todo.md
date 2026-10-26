# Todo: crew-declared-scope

> 依据 `tasks/crew-declared-scope/plan.md`。

- [x] Task 1：`declared.py`（`enabled`、`read`、`inside`）与 `config set --declared-scope`（Spec 验收 1；验收 3 的四种不可用在 `read` 层）——测试先红后绿（移走 declared.py 时导入失败）；test_declared_scope 11 个通过，test_commit_prefix_config、test_commit_timeout 照常通过；另加 `interface_reason` 给 config set 打开时的警告用
- [x] Task 2：`module-crew scope` 子命令与开工说明「全局约束」一行（Spec 验收 3、4）——测试先红后绿（3 失败 1 错误）；`declared.scope` 用 `hooks.detect` 认模块、在 worktree 顶层读；开关关时不调 spec-guard；不带文件时多列一行名单；开工说明那一行抽成 `start._constraint_line`，开关关时逐字不变（test_start_prepare 等照常通过）
- [x] Task 3：`change add` 分类——名单内、混合、冲突、不可用、开关关（Spec 验收 5）——测试先红后绿（4 错误）；声明在事务外读（`changes._declared_scope`，集成 checkout 由 `probe._checkout_of(db.path.parent, …)` 找）；全在名单内但有冲突时多一行「名单内，但和别的请求改同一个文件：照今天处理」；test_changes、test_change_partial、test_change_supersede、test_review_display 照常通过
- [x] Task 4：`change land --from-module`——成功路径与四种拒绝（Spec 验收 6、7）——测试先红后绿（6 失败）；校验全在 `changes._from_module` 里、过了才 `git checkout <模块提交> -- <文件>`；另拒两种：模块分支上的文件和集成分支一样（否则取完会留下没提交的改动）、与 `--partial` 同用；`scope` 加进 `_ANY_SESSION`（模块会话要能跑）；test_changes 等照常通过
- [x] Task 5：`change landed` 与 `--mark-told`（Spec 验收 8）——测试先红后绿；`changes.landed`／`landed_rows`／`landed_summary`／`mark_told`，`--mark-told` 先全部校验再写；另：`change add` 对名单内的提前落地请求不再打印「给用户看的正文」卡片（不问用户），加了测试
- [x] Checkpoint 1（report）：公共变更这一路做完，test_declared_scope 与 test_changes、test_change_partial、test_change_supersede 通过——test_declared_scope 29 个，test_changes、test_change_partial、test_change_supersede、test_review_display、test_session_handover 通过
- [x] Task 6：最终验收「声明内公共文件」一节、提前落地标注、未声明依赖、`display.declared`（Spec 验收 9）——测试先红后绿（4 错误）；`present._declared_section` 在 `final_tables` 末尾按开关挪行、`_declared_lines` 在「代码」与「提交」之间输出；挪进这一节的行不带「超出 Plan」标记；`review.py` 没改；test_review_display、test_hub_output、test_card_fields、test_contract_v26 照常通过
- [x] Task 7：有依赖关系的模块不同时开——`plan`、`prepare`、`_why_not`，含重开的上游、已合入不挡、同批互依赖（Spec 验收 10）——测试先红后绿（3 失败）；`start._related`（上下游闭包）、`_held`（开关开时与在用未合入模块相关的）；`plan` 不提议被挡的，有别的可提议时把它们放进 `reasons`、`start plan` 多一段「暂不提议：」，没有可提议时原因优先用这一条（没有另改 `_why_not`）；`validate` 加在用与同批两种拒绝；test_start_plan、test_start_prepare、test_reopen_module、test_light_task、test_failure 照常通过
- [x] Task 8：开关没设与 `off` 时各命令输出与改前逐字相同的集中对照（Spec 验收 2）——用 `git archive` 导出 main（改前）与 7ac496f（改后）两份代码，各跑同一场景脚本（开关没设、`off` 两种；`start plan`、`start prepare` 与开工说明全文、`change add` 两条、`change land`、`review batch` 与 `display` 去掉 `declared` 键的 JSON），临时路径、提交号、时间归一后两边 266 行逐字相同；脚本在会话草稿目录，不进仓库（各任务的单元测试里已分别断言开关关时的行为）
- [x] Checkpoint 2（report）：命令层做完，全量测试通过——52e8813（工作区带着 Task 9 的文档改动）上全量 939 个测试通过（1897 秒）
- [x] Task 9：skill 四份与 README（Spec 验收 11）——断言先红后绿（`DocsTest` 3 失败）；两份 crew-dev 在「不改公共文件」后加一条，两份 crew-coordinator「公共变更请求」加第 7 条，README「一次完整流程」第 4、5 步与命令一览各补一处；test_skills、test_readme_hosts、test_glossary 照常通过
- [ ] Task 10：本机 spec-guard 0.85.0 实测 `declaredScope`；`module-crew sync` 后全量测试（Spec 验收 12）
- [ ] Checkpoint 3（gate）：最终验收
- [ ] 回告：ecosystem-lead（S32 第二节 module-crew 第 1、2 条已就位），经 mc-coord 转
