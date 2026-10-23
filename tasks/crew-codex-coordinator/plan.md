# Implementation Plan: crew-codex-coordinator

<!-- spec-guard: review pending -->

> 依据：`spec/crew-codex-coordinator.md`（用户 2026-10-23 批准，事项 C32，「C32 A；Q1 不放开；Q2 不加；并行边界补成独占／公共两行」）。任务清单：`tasks/crew-codex-coordinator/todo.md`。

## Overview

先做「Codex 里的模块协调认得出自己、查得出障碍」：`status` 首行与 `codexSelf`、`host-check` 的模块协调检查项、沙箱拒绝与找不到插件时的补句，
再用夹具确认模块协调登记为 Codex 时各协调命令不因宿主被拒。然后做合并长检查的 `merge run --detach` 与 `merge result`，
接着补开工输出与交接说明里的 Codex 指引，最后写 Codex 版模块协调 skill、做 `handover --to codex` 端到端、改文档并跑全量测试。
每个任务先写失败的测试、看到红再实现到绿，单独在模块分支本地提交，不推送、不发版；合入集成分支用 `module-crew sync`。
构建在 T26 合入、收到开工类【协调通知】之后才开始，开工第一步 `module-crew sync`。

## Architecture Decisions

- **认出 Codex 里的模块协调（Spec 关键决策 4）**：`probe` 加 `codex_self(db) -> dict | None`：没有 `CODEX_THREAD_ID` 返回 `None`；有时返回 `{"name", "registered"}`，
  `registered` 看它是否等于在用模块协调的 `hostSession.sessionId`。`status` 文本输出在有值时多打一行首行；`--json` 的 `store` 加 `codexSelf`。没有 `CODEX_THREAD_ID` 时输出逐字不变（测试比对）。
- **`host-check` 的模块协调检查（关键决策 3）**：`hostcheck.run` 先判调用目录：集成 checkout 时走 `_coordinator_checks`（集成 checkout、模块协调在用、版本一致、能写 git 公共目录、能读状态库、
  找得到 spec-guard、固定入口存在），否则沿用现有模块会话检查。`Report` 加 `role`，`--json` 多 `role` 字段。能写 git 目录那项不通过时 `fix` 写「申请在沙箱外运行」。
- **沙箱拒绝的识别（关键决策 2）**：新增一个小函数 `probe.sandbox_hint(text) -> str | None`，在错误文字里认 `Operation not permitted` 与 `index.lock` 的 `Permission denied`／`File exists` 被拒两种，
  返回补句「Codex 沙箱不让写 git 目录：请申请在沙箱外运行这条命令」；接在 `__main__` 统一打印错误的出口（`store` 写失败的 `OSError` 与 `_git` 失败的标准错误），不在各命令里散写。别的错误原样。
- **找不到插件的补句（关键决策 5，用户定 Q2 不加）**：`probe.find_plugin` 不改；调用处拿到原因字符串后，有 `CODEX_THREAD_ID` 时追加「Codex 侧的插件安装 module-crew 不读：请在 Claude Code 里装同一插件」。
  集中在一个 `probe.plugin_missing(reason)` 里，`status`、`host-check` 用它；`review.py` 里的那处调用**不改**（并行边界）。
- **Codex 协调下各命令照常可用（验收 3）**：夹具把模块协调登记成经 `handover` 的 `codex-desktop`，设 `CODEX_THREAD_ID` 为登记的会话，逐个跑列出的命令。
  现有代码按会话编号守门（`own_session_id` 已认 `CODEX_THREAD_ID`），预计不用改；测出被宿主拒的地方再按最小改动修，修不了（要改 `review.py`）就停下发【等待其他会话】。
- **`merge run --detach`（关键决策 6）**：
  - 把 `merge.run` 拆成「前置」（队列、锁检查、合并前清单、拿锁）与「主体」（合并、检查、退回、放锁），前台 `run` 依次调两段，行为与输出不变（回归测试比对）。
  - `--detach`：父进程跑完前置并拿到锁后，用 `subprocess.Popen` 起本插件 `bin/module-crew merge run --detached-child …`（`start_new_session=True`、`pass_fds` 交出锁的文件描述符、
    标准输出与错误写到 `<状态库目录>/merge-output/C<号>.log`、标准输入接 `/dev/null`），父进程关闭自己那份描述符后立即打印 C 号与日志路径、退出码 0。
    子进程从环境变量拿到描述符接管锁，跑主体，打印内容与前台完全相同；结束后把 `exitCode`、`finishedAt`、`log`、`resultRead: false` 写进 `merge-running.json`（只在记录的 C 号与自己相同时写，原子替换）。
  - `--detached-child` 是内部参数，不写进帮助；没有拿到描述符时拒绝运行（退出码 2），避免被当成普通命令误用。
  - 子进程被杀：锁随进程由系统放掉，记录仍是「在跑」→ 沿用 crew-background-checks 的失效处理，不另写。
- **`merge result [C<号>] [--wait <分钟>]`（只读）**：读 `merge-running.json`；不给 C 号取最近一次后台合并。还在跑（锁被持有）退出码 6、写已跑分钟；
  有结果时原样打印日志、按 `exitCode` 退出，并把 `resultRead` 置真（这是唯一的写，只改这一个字段，事件 `merge.result-read`）；没有可取的结果退出码 3。
  `--wait` 每 5 秒看一次、最多 8 分钟（超过 8 按 8），等不到退出码 6。`merge result` 加入写命令守门的只读豁免表（只改 `resultRead` 不算写集成 checkout）。
- **`status` 的结果提示**：`mergelock` 加 `finished_unread(db)`；`status` 在有未读结果时打印「合并 C<号> 已结束，运行 merge result 取通知」，`--json` 的 `mergeLock` 旁加 `mergeResult`（只增不改）。
- **开工输出的 Codex 指引（关键决策 7）**：模块协调在 Codex 时，`start prepare`、`task dispatch` 输出末尾加「请用户去 Codex 新建任务」段，每个模块（或 T 号）一行：工作目录、开工说明文件。
  模块协调在 Claude 时逐字不变（已有测试比对）。
- **交接说明补两句（关键决策 8）**：`handover.guide` 的 Codex 方向在 `bind --takeover` 之后加「运行 host-check」，末尾加「之后每轮按 Codex 版 crew-coordinator 的开头三步」；判断 `--to codex` 能否执行的逻辑不改。
- **Codex 版模块协调 skill（关键决策 1）**：`codex-skills/crew-coordinator/SKILL.md`，先「Codex 特有的几件事（先读）」，其余各节与 Claude 版同名同序；
  `tests/test_skills.py` 加断言两份共同关键句与 Codex 特有关键句（`test_skills.py` 是已有测试文件，不是测试资源；若要改 `tests/helpers.py` 先发【公共变更请求】）。

## 影响面

新增：`codex-skills/crew-coordinator/SKILL.md`、`tests/test_codex_coordinator.py`。
修改：`module_crew/probe.py`、`hostcheck.py`、`merge.py`、`mergelock.py`、`start.py`、`tasks.py`、`handover.py`、`__main__.py`、
`skills/crew-coordinator/SKILL.md`、`.codex-plugin/plugin.json`、`README.md`，以及 `tests/test_skills.py`（加断言）和按需调整断言的已有测试。
不改 `module_crew/review.py`；不新增依赖；不改契约、`interface.json`、版本号。公共文件：预计不碰；夹具真需要改 `tests/helpers.py` 时先发【公共变更请求】。

## Task List

- [ ] Task 1：`status` 在 Codex 里认出／否认模块协调，`--json` 加 `codexSelf`；无 `CODEX_THREAD_ID` 时逐字不变（Spec 验收 7）
- [ ] Task 2：`host-check` 在集成 checkout 按模块协调查，`--json` 加 `role`（Spec 验收 6）
- [ ] Task 3：沙箱拒绝写 git 目录时报错带「申请在沙箱外运行」；Codex 下找不到 spec-guard／agent-relay 的原因带补句（Spec 验收 8）
- [ ] Task 4：夹具确认模块协调登记为 Codex 时各协调命令不因宿主被拒，测出的问题最小改动修掉（Spec 验收 3）

### Checkpoint 1（report）：Codex 协调认得出自己、查得出障碍，相关测试通过，记入 todo 后继续

- [ ] Task 5：拆 `merge.run` 为前置与主体（前台行为逐字不变），加 `merge run --detach` 与内部 `--detached-child`（Spec 验收 4 的启动、锁、被杀部分）
- [ ] Task 6：`merge result [C<号>] [--wait]`、结果写回与 `resultRead`、`status` 的「已结束」一行与 `mergeResult`（Spec 验收 4 的结果部分、5）
- [ ] Task 7：模块协调在 Codex 时 `start prepare`、`task dispatch` 输出「去 Codex 新建任务」段；交接说明 Codex 方向补 `host-check` 与每轮三步（Spec 验收 9、2 的说明部分）

### Checkpoint 2（report）：命令层做完，全量测试通过，记入 todo 后继续

- [ ] Task 8：Codex 版 crew-coordinator skill，`test_skills` 断言共同与特有关键句（Spec 验收 1）
- [ ] Task 9：`handover --to codex` 端到端：夹具用插件里真实的 Codex 版 skill，收尾条件满足即完成；`--to claude` 不变（Spec 验收 2）
- [ ] Task 10：README「换宿主」补「模块协调在 Codex 上」与命令一览、`.codex-plugin/plugin.json` 描述、Claude 版 skill「空档换宿主」改为两个方向可用；全量测试（Spec 验收 10、11 的测试部分）

### Checkpoint 3（gate）：最终验收

- 无中途 gate；最终验收不含推送与开 PR（合并与推送由模块协调按用户原话做）。
- 实地在 Codex 上换宿主、合并一个模块、再换回，不在本 Plan 里做：放进演练、经用户同意才开始；最终验收里如实写「宿主未实测」与原因，未决问题 3、4 一并留待演练。

- [ ] 回告：发版后告诉 ecosystem-lead S13 的模块 B 已就位、`handover --to codex` 已放开、实地验证结果（随最终验收列出，经 mc-coord 转）

## 风险

- **拆 `merge.run` 改坏前台合并**：Task 5 先跑全部合并相关已有测试作基线，拆完逐字比对输出与退出码；不改合并逻辑本身。
- **把锁的描述符交给子进程**：`flock` 锁属于打开的文件描述，`pass_fds` 继承后父进程关掉自己那份，锁仍由子进程持有；测试里核对父进程退出后锁仍被持有、子进程结束后放掉。
  macOS 上 `start_new_session` 与 `pass_fds` 同用的行为在测试里实跑确认。
- **结果写回与下一次合并抢 `merge-running.json`**：只在记录的 C 号与自己相同时写；下一次合并已开始时放弃写回，日志仍在，`merge result C<号>` 从日志读（退出码取日志末行的固定格式行）。
- **Codex 宿主行为未实测**（子进程能否活过本轮、提权能否继承、单次调用时限）：只能演练确认，本 Plan 不声称已验证。
- **T26 同时在改 `review.py`**：本模块不改它；`sync` 后若与 T26 的改动冲突在别的文件，按 crew-dev 的同步规则处理。
