# Implementation Plan: crew-codex-offload

<!-- spec-guard: review approved -->

> 依据：`spec/crew-codex-offload.md`（用户 2026-10-26 批准，事项 C233「C233 A」，集成分支提交 f8fbc4e）。任务清单：`tasks/crew-codex-offload/todo.md`。

## Overview

先打底（开关、外包记录、条件核对 `ready`），再做派出（`offload start` 与任务说明）、收结果（`settle` 的四个分支），
然后续跑与重派、交还与扣下开工通知、`show`，最后改 skill、README，sync 后跑全量测试，并用本机 delegate 0.6.0 实测一次。
每个任务先写失败的测试、看到红再实现到绿，在本模块分支本地提交；不推送、不发版。每个任务都验证「开关关着时行为不变」。

## Architecture Decisions

- **新文件 `module_crew/offload.py`** 集中本模块的逻辑：`enabled(db)`、`set_switch(...)`（供 `config set` 调用）、`ready(db, project, module) -> str | None`（决策 2，返回第一条不满足的原因）、
  `delegate_interface(project)`（只读 interface.json，判 `>=1.1,<2.0` 与 `run.resume`；另报是否 ≥1.2 且 `statuses` 含 `timeout`）、
  `parse_result(text, exit_code) -> Result`（结果行、`NEED_USER:`、分成 done／needs-input／timeout／unknown）、`next_item(todo_text)`（第一个未勾项及是不是 Task）、
  `render_brief(...)`、`start`、`settle`、`resume`、`handback`、`decline`、`show`。其他文件只加一两处调用，减少和 crew-autonomy-tier 的冲突面。
- **状态库**：`store.KINDS` 加 `offload`；键是模块 id，不进 `NUMBERED`。外包的答复原话照 `start prepare --source` 的做法记来源。
- **范围核对**：经 `probe.safe_command(..., "scopeCheck", ...)` 在模块 worktree 跑 spec-guard，`--base` 用派出时记下的 `base`；`outside` 的文件再用 `declared.read(...).inside` 放行（`declared.enabled` 时）；状态 `D` 一律越界。
- **快检查与代提交**：`git add -A -- <改动文件>` 后 `git write-tree` 取树，调 `checks.check_tree(db, cfg, "quick", tree, worktree, "offload", None, False)`；通过才 `git commit`，前缀取 `commits.prefix_of(db)`。git 调用带超时、参数列表、`--no-optional-locks` 读状态。
- **review.py 只动 `approve` 里渲染开工通知的那一段**：抽成 `_start_todo(db, project, m) -> str | None`；返回 None 表示扣下开工通知（外包条件不满足），开关关着返回原文，所以关着时逐字不变。crew-autonomy-tier 改的是 `note`，不同段落。
- **不改 merge.py、probe.py**：`status` 不加外包一段（Spec 决策 12），查看走 `offload show`。
- **delegate 夹具只放 interface.json**：测试不跑 Codex；delegate 的输出由测试写成文本文件喂给 `settle`。实测放在最后一个任务，测不成照实写原因。

## 影响面

新增：`module_crew/offload.py`、`tests/test_codex_offload.py`。
修改：`store.py`（`KINDS`）、`review.py`（`approve` 的开工通知段）、`__main__.py`（`_config_set` 加 `--codex-offload`、`offload` 子命令组）、
`skills/crew-coordinator/SKILL.md`、`codex-skills/crew-coordinator/SKILL.md`、`skills/crew-dev/SKILL.md`、`codex-skills/crew-dev/SKILL.md`、`README.md`。
不新增依赖；不改契约、钩子、`interface.json`、版本号、CHANGELOG（发版时由模块协调写）。公共文件不碰。

## Task List

- [ ] Task 1：打底——`store.KINDS` 加 `offload`；`offload.enabled`；`config set --codex-offload on|off`（checkLedger 没开拒绝、没原话拒绝、条件不满足逐条警告）；`ready` 六项条件（Spec 验收 1、3）
  - 验证：六个缺项各给对应原因；全满足通过；开关写入后读回、事件记原话；全量里与 config、store 相关的回归测试仍过
- [ ] Task 2：`offload start` 与任务说明；`parse_result`（Spec 验收 5、验收 2 的 start 部分）
  - 验证：第一个未勾项是 Task 时记 `running`、任务说明含 Task 原文、三种必停、`NEED_USER:`、不提交不推送不删除，输出 `/delegate:run --write --resumable` 写法；Checkpoint 时不派；不干净、没包含批准提交、已有待处理外包时退出码 3 且不写；开关关时退出码 3
- [ ] Task 3：`settle` 的 done 分支——勾选核对、scopeCheck 范围核对（含名单内放行与删除越界）、暂存区快检查、代提交（Spec 验收 6）
  - 验证：全过时模块分支多一个提交（信息含 Task 编号与 runId）、检查账有 `by: offload`、记录回 `idle`；越界、没勾、勾了别项、快检查失败各自不提交、文件原样、退出码 5、记录 `stopped` 带原因

### Checkpoint 1（report）：派出与 done 代提交就位，本模块测试与 review、checks、declared 相关回归测试通过，记入 todo 后继续

- [ ] Task 4：`settle` 的 needs-input、timeout（1.1 与 1.2）、认不出四个分支；【等待用户】草稿（Spec 验收 7 的前半、8、9）
  - 验证：问题原文逐字相同、草稿被 `protocol.parse` 判合格；超时不调快检查脚本、不提交、输出 status 与 diff --stat 和 ABC 选项；1.2 夹具给 resume 写法、进度说明原样附上；64、其他非 0、无结果行、未知状态、输出读不出都 `stopped`、退出码 5、附最后 20 行
- [ ] Task 5：`offload resume`、`offload start --again`（Spec 验收 7 的后半、8 的后半）
  - 验证：没原话退出码 3；有原话时输出 `--resume <runId> --write` 写法、记下答复与来源；状态不对时退出码 3
- [ ] Task 6：开工通知分叉——`review._start_todo`；`offload decline`；`offload handback`（Spec 验收 4、10、验收 2 的 approve 部分）
  - 验证：开关开且条件满足时开工通知是外包写法、`protocol.parse` 合格；条件不满足时不发开工通知并输出原因；`decline` 带原话发今天的开工通知；`handback` 生成类型「恢复」的通知、记 `handed-back`、之后 `start` 不带 `--again` 被拒；开关关时 `approve` 输出与开工通知逐字不变（用改前输出对照）
- [ ] Task 7：`offload show` 与 `--json`（Spec 验收 11）

### Checkpoint 2（report）：命令全部就位，本模块测试与相关回归测试通过，记入 todo 后继续

- [ ] Task 8：四份 skill 各加一节、README 命令一览与流程一段；`module-crew sync` 合入集成分支后后台跑全量测试；本机 delegate 0.6.0 实测一次（Spec 验收 12、13）
  - 验证：全量测试通过；实测的结果行与 `settle` 输出写进最终验收，测不成照实写原因

### Checkpoint 3（gate）：最终验收

- [ ] 回告：完成情况经模块协调转告 ecosystem-lead（S32 第二节 module-crew 第 6 条已实现）
