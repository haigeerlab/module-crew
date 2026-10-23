# Implementation Plan: crew-host-handover

> 依据：`spec/crew-host-handover.md`（接口提案，用户 2026-10-23 批准，事项 C15，「C15 A」）。任务清单：`tasks/crew-host-handover/todo.md`。

## Overview

先放开状态库里模块协调的宿主并加 `hostHandover` 记录，再做只读的收尾条件清单（`handover --check`），然后做 `handover --to` 本身（登记、权限、交接说明），
接着让 `bind --takeover` 核对宿主、完成交接；之后做宿主跟随（`start prepare`、`task dispatch`）和收尾提示，最后改文档、跑全量测试。
每个任务先写失败的测试、看到红再实现到绿，单独在模块分支本地提交，不推送、不发版；合入集成分支用 `module-crew sync`。

## Architecture Decisions

- **新文件 `module_crew/handover.py`**：
  - `readiness(db, project, to=None) -> list[Check]`：Spec 关键决策 1 的五项（`sessions`、`tasks`、`merge`、`pending`、`clear-handover`），`--to codex` 时多一项 `codex-coordinator-skill`（插件根下 `codex-skills/crew-coordinator/SKILL.md` 是否存在，关键决策 6）。
    每项 `Check(id, ok, reason)`；`pending` 读 `item`／`request` 记录与等待记录的未结状态（构建时按 store 现有字段取，不新增字段）；`merge` 用 `mergelock` 的持有判断与已批准未合并的事项。
  - `handover(project, to, original, session_id) -> (code, lines)`：前置核对全过才在一个事务里改登记（`host`、`hostHandover`），事件 `coordinator.handover`；随后调权限写入，再生成交接说明。
  - `guide(to, name, entry, integration, original_file) -> str`：交接说明正文，按方向出步骤，每步三项「去哪个会话／做什么／做完的样子」；保存到 `<状态库目录>/handover-guide/<时间>.md`。
- **store**：`role: coordinator` 允许 `codex-desktop`；`hostHandover` 可选，校验 `from`／`to` 在 HOSTS 内、`at` 字符串、`original` 非空、`pending` 布尔。`coordinator.up` 不改（仍写 `claude-desktop`）。
- **权限**：`permissions.checkouts` 的集成 checkout 宿主改为取模块协调登记的 `host`（没有模块协调时仍是 Claude）；新增 `permissions.follow_integration(project)` 给 `handover` 用，沿用合并写入、git 忽略核对与状态库记录；没 apply 过时什么都不写。
- **`bind --takeover` 宿主核对**：`_take_over` 里按环境变量判调用者宿主（`CODEX_THREAD_ID` → `codex-desktop`，否则 `claude-desktop`），与登记 `host` 不一致抛 `BindRefused`（退出码 3）；成功时把 `hostHandover.pending` 置为 false。
- **宿主跟随**：`__main__` 里 `start prepare`、`task dispatch` 的 `--host` 默认改为 `None`，由 `handover.default_host(db)` 取模块协调宿主；模块协调在 Codex 且显式 `--host claude` 时退出码 2、不写。
  `tasks.dispatch` 加 `host` 参数，登记 `host`，开工说明在 Codex 时追加 `start.codex_lines`（并去掉 Claude 钩子那行，与 `start` 的做法一致）。
- **收尾提示**：`handover.ready_line(db, project)` 在五项基本条件全满足且状态库里有过合并时返回那一行；`merge cleanup` 收回后与 `status` 打印；`probe.summarize_store` 加 `coordinatorHost`、`handoverReady`。
- **写命令守门**：`coordinator handover --check` 加入只读豁免表；`coordinator handover --to` 是写命令，照常受守门。

## 影响面

新增：`module_crew/handover.py`、`tests/test_host_handover.py`。
修改：`module_crew/store.py`、`coordinator.py`、`hooks.py`、`permissions.py`、`start.py`、`tasks.py`、`merge.py`、`probe.py`、`__main__.py`、
`skills/crew-coordinator/SKILL.md`、`codex-skills/crew-dev/SKILL.md`、`README.md`、`spec/crew-codex-host.md`（只在「变更记录」追加一行，Spec 接口约定里写明的），以及按需调整断言的已有测试（如 `test_codex_host` 里「模块协调登记 codex-desktop 被拒」改为「只能经 handover」）。
不新增依赖，不改契约、`interface.json`、版本号。

## Task List

- [ ] Task 1：store 放开模块协调的 Codex 宿主、`hostHandover` 校验，`coordinator up` 仍只登记 Claude（Spec 验收 8）
- [ ] Task 2：`handover.readiness` 与 `coordinator handover --check`（含 `--json`、B 未发版那一项、只读豁免）（Spec 验收 1 的检查部分）
- [ ] Task 3：`coordinator handover --to`：前置核对、改登记与事件、交接说明生成与保存；条件不满足／原话空／目标相同／B 未发版时什么都不写（Spec 验收 1、2、3 的登记与说明部分、4）
- [ ] Task 4：权限跟随：集成 checkout 按模块协调宿主写规则，`handover` 调用；没 apply 过不写，写失败在说明里标出（Spec 验收 2、3 的权限部分）
- [ ] Task 5：`bind --takeover` 宿主核对与清 `pending`（Spec 验收 5）

### Checkpoint 1（report）：交接链路就位，相关测试通过，记入 todo 后继续

- [ ] Task 6：宿主跟随：`start prepare`、`task dispatch` 默认跟随模块协调，Codex 下拒 `--host claude`；`task dispatch --host codex` 的开工说明；Codex 版 crew-dev「轻任务」一节（Spec 验收 6、7）
- [ ] Task 7：收尾提示：`merge cleanup` 与 `status` 的那一行，`status --json` 的 `coordinatorHost`、`handoverReady`（Spec 验收 9）
- [ ] Task 8：README「换宿主（空档）」与命令一览、crew-coordinator skill「空档换宿主」、crew-codex-host Spec 变更记录、全量测试（Spec 验收 10、11 的测试部分）

### Checkpoint 2（gate）：最终验收

- 实地来回换一次不在本 Plan 里做：放进演练、经用户同意才开始（Claude→Codex 要等模块 B），最终验收里如实写「宿主未实测」与原因。

- [ ] 回告：发版后告诉 ecosystem-lead S13 的模块 A 已就位、`--to codex` 等模块 B（随最终验收列出，经 mc-coord 转）
