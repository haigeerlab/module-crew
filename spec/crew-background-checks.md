# Spec: crew-background-checks

<!-- spec-guard: review approved 82adf32e316a -->

> 能力图模块 `crew-background-checks`（第六版第 5 个，最后一个）。需求来源：`docs/requirements-record.md` 第 14 节第 10 条（长命令改后台运行、模块协调照常回话，用户 2026-10-22 确认）。
> 依赖 `crew-merge`（合并队列）、`crew-onboarding`（模块协调的规矩）。标「新」的是写 Spec 时补的实现取舍，请重点审。

## 目标

合并时的完整检查可能跑几分钟到半小时。模块协调要能把 `merge run` 放到后台跑、这段时间照常回用户和别的会话的话；
同时保证后台合并没跑完时，不会有第二个合并或别的集成分支写操作插进来把集成 checkout 弄乱。

## 范围

**范围内**

- 合并锁：`merge run` 开始时在状态库里拿锁（记批准事项号、进程号、开始时间），结束时放；锁被占时第二个 `merge run` 拒绝。
- 会写集成 checkout 的命令在锁被占时拒绝：`change land`、`review approve`、`merge tick`、`merge cleanup`、`unqueued --notify`、`coordinator down`。
- 进程已经不在、锁还在（崩溃、被杀）：认定锁失效，下一个命令照实说明并清掉，集成 checkout 不干净时交用户。
- `status` 显示「合并 C<号>（<模块或任务>）正在后台跑，已跑 N 分钟」。
- `crew-coordinator` skill：`merge run` 一律用后台方式运行，跑的时候照常回话、不碰集成 checkout，跑完读输出再按原样发通知。

**范围外**

- 把完整检查交给关联会话跑（需求记录第 14 节第 10 条：先后台，以后不够用再说）。
- 并行跑多个合并。
- 改检查命令本身或超时（默认 30 分钟不变）。

## 假设

1. 宿主（Claude Code 的 Bash 后台运行）负责把命令放到后台、跑完叫醒模块协调；module-crew 只管命令本身在后台运行时安全。
2. 后台运行时，模块协调仍可能被别的消息叫醒并想做别的写操作：靠锁挡住，不靠模块协调记得。
3. 只读命令（`status`、`sessions`、`review batch`、`task list`、`unqueued` 不带 `--notify`）照常可用。

## 关键决策与取舍（请重点审）

1. **（新）锁放在状态库目录里的单独文件 `merge.lock`**（JSON：`approval`、`unit`、`pid`、`host`、`startedAt`），用 `O_CREAT|O_EXCL` 创建，不进事件日志；
   锁文件跟状态库同在 git 公共目录下，所有 worktree 看到的是同一把；合并本身照旧在合并批准事项里留记录，锁不另记事件。
2. **失效判断只看进程号**：同一台机器（`host` 与本机相同）上该进程不在了，就认定失效；`host` 不同或读不出时不自动清，照实交用户（第一版只支持同一台 Mac）。
   清失效锁时检查集成 checkout：干净就清掉并说明；有合并进行中（`MERGE_HEAD`）或不干净就不清，列出状态交用户决定。
3. **被挡住的命令退出码 6**，输出「合并 C<号> 正在后台跑（已跑 N 分钟），等它结束再做」；不排队、不等待。
4. **`merge run` 照旧一次只合一个**，结束时（成功、退回、冲突、出错）都放锁，用 `try/finally`。
5. **skill 的做法**：`merge run` 用 Bash 的后台运行；输出很长时按输出文件读结果；跑的时候能做的事写清楚（回话、记账、只读命令），不能做的事（上面那几条写命令）也写清楚，被挡住就告诉对方「等合并结束」。

## 接口约定

- 状态库目录新增文件 `merge.lock`（不进事件日志）。
- 退出码：被锁挡住的写命令 `6`。
- `status --json` 的 `store` 多 `mergeLock`：`null` 或 `{"approval", "unit", "startedAt", "minutes", "stale"}`。

## 项目结构

```text
module_crew/mergelock.py      新：拿锁、放锁、读锁、失效判断
module_crew/merge.py          run 拿放锁；tick、cleanup 查锁
module_crew/changes.py, review.py, unqueued.py, coordinator.py   写操作前查锁
module_crew/probe.py, __main__.py   status 一行、退出码 6
skills/crew-coordinator/SKILL.md
tests/test_background_checks.py
```

## 命令

```bash
python3 -m unittest discover -s tests
PYTHONPATH=tests python3 -m unittest test_background_checks
```

## 代码风格

沿用现有模块：代码与注释英文，输出中文；只用标准库。

## 测试策略

- 锁：`merge run` 跑检查时（检查脚本睡几秒）另起进程跑第二个 `merge run`、`change land`、`review approve`、`merge tick`、`merge cleanup`、`unqueued --notify`，都退出码 6、什么都不写；只读命令照常。
- 放锁：成功、检查失败退回、冲突、检查超时、异常各一次，结束后锁都不在。
- 失效：写一个进程号不存在的锁 → 下一个写命令清锁并说明；集成 checkout 有 `MERGE_HEAD` 时不清、交用户；`host` 不同不清。
- `status`：显示正在跑与分钟数；失效锁显示「失效」。
- 回归：全量测试通过。

## 边界

- **始终**：锁只挡写集成 checkout 的命令；结束一定放锁。
- **先问**：让检查交给关联会话跑；改默认超时。
- **绝不**：后台合并跑着时改集成 checkout；自动清掉 `host` 不同或集成 checkout 不干净时的锁。

## 验收标准

1. `merge run` 运行期间锁文件存在且内容正确；结束（成功、退回、冲突、超时、异常）后锁不在。
2. 锁被占时第二个 `merge run`、`change land`、`review approve`、`merge tick`、`merge cleanup`、`unqueued --notify`、`coordinator down` 退出码 6、状态库与集成分支不变；只读命令照常。
3. 进程已不在的锁：集成 checkout 干净时下一个写命令清掉并说明；有 `MERGE_HEAD` 或不干净时不清、交用户；`host` 不同不清。
4. `status` 显示正在后台跑的合并与已跑分钟数、失效锁；`--json` 有 `mergeLock`。
5. skill 写明后台运行 `merge run`、跑时能做与不能做的事。
6. 全量测试通过。

## 未决问题

- 检查真的很慢（超过半小时）时要不要交给关联会话：这一版不做，看实际用下来再说。

## 文档建议

README「合并」一步补「`merge run` 放后台跑，跑的时候别的写命令会被挡住（退出码 6）」；命令一览不变。
