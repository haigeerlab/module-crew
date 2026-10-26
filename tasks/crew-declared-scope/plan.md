# Implementation Plan: crew-declared-scope

<!-- spec-guard: review pending -->

> 依据：`spec/crew-declared-scope.md`（用户 2026-10-26 批准，「C207 A」；集成分支 e27d3fe）。任务清单：`tasks/crew-declared-scope/todo.md`。

## Overview

先做读声明的地基（`declared.py` 与开关），再按模块会话 → 模块协调的顺序接入：`scope` 自查与开工说明 → `change add` 分类 → `change land --from-module` → `change landed` 汇总；
然后是最终验收的「声明内公共文件」一节和开工的依赖核对，最后写 skill、README，用本机 spec-guard 0.85.0 实测一次，同步后跑全量测试。
每个任务先写失败的测试、看到红再实现到绿，单独在模块分支本地提交，不推送、不发版；合入集成分支用 `module-crew sync`。
开关关闭时的「逐字不变」（Spec 验收 2）在每个任务里各自断言，Task 9 再集中对照一次。

## Architecture Decisions

- **`module_crew/declared.py`（Spec 决策 2）**：
  - `enabled(db) -> bool`：`config/main.declaredScope == "on"`。
  - `read(project, module) -> Declared`：`probe.find_plugin("spec-guard")` → `read_interface` → 没有 `declaredScope` 时 `usable=False, reason="装的 spec-guard 接口 <x> 低于 1.11（没有 declaredScope）"`；
    有就 `probe.safe_command(root, doc, "declaredScope", {"<project-root>": …, "<module-id>": …})`，`subprocess.run` 参数列表、`timeout=probe.MAP_TIMEOUT`、不经 shell。
    退出码 0 且 `planApproved` 为真、`declared` 为真 → `usable=True`；`planApproved` 假 → 「Plan 批准后改过或未批准」；`declared` 假 → 「Plan 没有预先声明一节」；
    退出码 4 → 「预先声明一节格式错（<error>）」；其他退出码、超时、JSON 读不出 → 「declaredScope 没跑成（…）」。
  - `Declared.inside(path)`：等于 `publicPaths`／`configs`／`patches` 的一项，或以 `publicPaths` 里以 `/` 结尾的一项开头；`usable` 为假时恒为假。
  - `Declared` 另带 `dependencies`（`[{name, range}]`）与 `approved_commit`。
- **开关（决策 1）**：`__main__._config_set` 加 `--declared-scope on|off`，和现有两项同一事务写 `config/main`；打开时调一次 `probe.read_interface` 看有没有 `declaredScope`，没有就多打一行警告，照样写入。
- **`scope` 子命令（范围 3，假设 3）**：在当前 worktree 找 `bind` 登记的模块（与 `sync`、`host-check` 同一认法），`--project` 用当前 worktree 顶层；开关关时首行「开关没开：公共文件一律发【公共变更请求】」，
  每个文件答名单外；不在登记过的模块 worktree 里退出码 2。
- **开工说明（决策 6）**：`start.render_kickoff` 读 `cfg.get("declaredScope")`，`on` 时换「全局约束」一行，其余逐字不变。
- **`change add`（决策 3，假设 5、6）**：在算完 `hints` 之后、写记录之前：开关开 → 在集成 checkout（`probe._checkout_of`）对请求方模块 `declared.read`；
  可用、每个文件 `inside`、没有 `conflict:` 提示 → `declared=True`、`declaredCommit=approved_commit`；输出把「要问用户」那一行换成「名单内：提前落地，不用问用户；用 change land C<号> --from-module」。
  混合请求多一行「名单内：<文件…>；有名单外的文件，整条照今天处理」。不可用多一行「声明不可用：<原因>，照今天处理」。开关关时不读、不写这两个键。
  读声明放在事务外（子进程不进事务），结果带进事务。
- **`change land --from-module`（决策 4）**：`changes.land(..., from_module=True)`：先校验（请求 `declared` 为真；集成 checkout `_changed_paths` 为空；请求方模块分支 `refs/heads/<模块>` 顶端提交里每个清单文件都存在：`git cat-file -e <提交>:<文件>`；
  再读一次声明仍可用且全部 `inside`），任一不过退出码 3、什么都不改；过了在集成 checkout 跑 `git checkout <提交> -- <文件…>`，之后进入 `land` 现有路径（核对、提交、关请求、通知），
  提交信息换成「公共变更请求 C<号>（<发件人>）提前落地：<改什么>」，关请求时多记 `fromModule.commit` 与 `toldUser: False`。`git checkout` 之后若提交失败，照现有 `land` 的退出码 4 处理（文件留在暂存区，输出写明）。
- **`change landed`（决策 5）**：`changes.landed(db)` 列 `closedReason == "landed"`、带 `fromModule`、`toldUser` 为假的请求；`changes.mark_told(db, numbers)` 先全部校验再一个事务写 `toldUser: True`。
  汇总正文一行一条：「C<号> <模块>：<文件…> 已提前进集成分支（<提交短号>，<时间>），名单内、没问用户」。
- **最终验收（决策 7）**：`present.final_tables` 末尾按开关与声明（集成 checkout 上读 `rec["module"]`）把名单内的行从 `docs`／`code` 挪进 `declared.files`，
  每行查有没有该模块 `fromModule` 落地过的请求含这个文件，有就带 `landed: {"request", "commit"}`；依赖表在可用时给不在声明里的包加「（未声明）」（按包名比，`_new_dependencies` 的条目以包名开头）。
  `table_lines` 在「代码」表之后、「提交」表之前输出「声明内公共文件：」一节；`display["declared"]["state"]` 为 `off` 时这一节不输出，与改前逐字相同。
  `review.py` 不改（它已原样调用这两个函数并把 `display` 放进 `--json`）。
- **依赖核对（决策 8）**：`start` 加 `_related(mapped, a) -> set[str]`：`dependsOn` 的上游闭包 ∪ 下游闭包；在用模块 = `_active_devs` 里本轮未合入（`_merged_modules` 之外）的模块。
  开关开时：`plan` 过滤 `picked`（被滤掉的进 `reasons`，原因「和在用的 <模块> 有依赖关系，等它合入再开」）；`validate` 对每个要开的模块和在用模块、以及同批其他模块核对，冲突加拒绝原因；
  `_why_not` 在「已有模块会话」之后加这一条。开关关时三处都不调 `_related`。

## 影响面

新增：`module_crew/declared.py`、`tests/test_declared_scope.py`。
修改：`module_crew/changes.py`（`add`、`land`，新增 `landed`、`mark_told`）、`module_crew/present.py`（`final_tables`、`table_lines`）、`module_crew/start.py`（`plan`、`validate`、`_why_not`、`render_kickoff`）、
`module_crew/__main__.py`（`config set`、新 `scope` 子命令、`change land --from-module`、`change landed`）、`skills/crew-dev/SKILL.md`、`codex-skills/crew-dev/SKILL.md`、`skills/crew-coordinator/SKILL.md`、`codex-skills/crew-coordinator/SKILL.md`、`README.md`。
不改：`module_crew/merge.py`、`module_crew/review.py`、`module_crew/protocol.py`、`interface.json`、版本号。
假 spec-guard 在 `tests/test_declared_scope.py` 里按 `test_review_display` 的做法改临时插件目录的 `interface.json` 生成（不改 `tests/helpers.py`、`tests/fixtures/`），预计不改公共文件；真要改先发【公共变更请求】。
不新增依赖；不改契约。

## Task List

- [ ] Task 1：`declared.py`（`enabled`、`read`、`inside`）与 `config set --declared-scope`（Spec 验收 1；验收 3 的四种不可用在 `read` 层）
- [ ] Task 2：`module-crew scope` 子命令与开工说明「全局约束」一行（Spec 验收 3、4）
- [ ] Task 3：`change add` 分类——名单内、混合、冲突、不可用、开关关（Spec 验收 5）
- [ ] Task 4：`change land --from-module`——成功路径与四种拒绝（Spec 验收 6、7）
- [ ] Task 5：`change landed` 与 `--mark-told`（Spec 验收 8）

### Checkpoint 1（report）：公共变更这一路做完，test_declared_scope 与 test_changes、test_change_partial、test_change_supersede 通过，记入 todo 后继续

- [ ] Task 6：最终验收「声明内公共文件」一节、提前落地标注、未声明依赖、`display.declared`（Spec 验收 9）
- [ ] Task 7：有依赖关系的模块不同时开——`plan`、`prepare`、`_why_not`，含重开的上游、已合入不挡、同批互依赖（Spec 验收 10）
- [ ] Task 8：开关没设与 `off` 时各命令输出与改前逐字相同的集中对照（Spec 验收 2）

### Checkpoint 2（report）：命令层做完，全量测试通过，记入 todo 后继续

- [ ] Task 9：skill 四份与 README（Spec 验收 11）；断言写在 `tests/test_declared_scope.py`
- [ ] Task 10：本机 spec-guard 0.85.0 实测 `declaredScope`（临时仓库里一份带「预先声明」、已批准的 Plan，跑 `declared.read` 与 `scope`），结果记入 todo；`module-crew sync` 后全量测试（Spec 验收 12）

### Checkpoint 3（gate）：最终验收

- [ ] 回告：ecosystem-lead（S32 第二节 module-crew 第 1、2 条已就位：`declaredScope` 开关、名单内直接改、提前落地与事后汇总、依赖不同开），经 mc-coord 转

## 风险与对策

| 风险 | 影响 | 对策 |
|---|---|---|
| crew-check-ledger 同时改 `__main__.py`、协调 skill、README | 合并冲突 | 只加新段落、不动别人的；sync 冲突时按 crew-dev 规则解决，解决不了发【等待其他会话】 |
| 真实 `declaredScope` 输出和接口声明不符 | 夹具测得过、实机读不出 | Task 10 用本机 0.85.0 实测；不符就停下发【等待其他会话】，不自己迁就 |
| `git checkout <提交> -- <文件>` 被权限规则拦 | 提前落地这一步在协调会话里弹确认 | 这是模块协调会话执行的命令；最终验收里列出要放行的命令前缀，由模块协调按用户原话处理 |
| 依赖核对误挡正常开工 | 新模块开不了 | 只在开关打开时核对；已合入的模块不算在用；测试覆盖 startable 正常的新模块不受影响 |
| 全量测试超过 2 分钟 | 检查在前台超时 | 全量测试放后台跑，等它结束再判结果 |

## 变更记录
