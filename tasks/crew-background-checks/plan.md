# Implementation Plan: crew-background-checks

<!-- spec-guard: review approved -->

> 依据：`spec/crew-background-checks.md`（用户 2026-10-22 批准）。任务清单：`tasks/crew-background-checks/todo.md`。

## Overview

先做锁本身（拿、放、读、失效判断），再让 `merge run` 用它、让其余写命令查它，然后接 `status`，最后改 skill 与 README。
每个任务先写失败的测试、看到红再实现到绿，单独在 `main` 本地提交，不推送、不发版。

## Architecture Decisions

- **新文件 `module_crew/mergelock.py`**：`acquire(db, approval, unit) -> Lock | Held`（`os.open(..., O_CREAT|O_EXCL)` 写 JSON：`approval`、`unit`、`pid`、`host`（`socket.gethostname()`）、`startedAt`）、
  `release(db, lock)`（只删自己拿的那把：核对 pid 与开始时间）、`read(db) -> dict | None`、`stale(info) -> bool`（同主机且 `os.kill(pid, 0)` 报 `ProcessLookupError`）、
  `guard(db, project) -> str | None`（写命令开头调：锁被占且有效 → 返回挡住的原因；失效且集成 checkout 干净、没有 `MERGE_HEAD` → 清掉并返回 None，同时给出一行说明；失效但不干净或主机不同 → 返回原因交用户）。
- **merge run**：校验通过后、动集成 checkout 之前 `acquire`；拿不到就退出码 6；之后整段放进 `try/finally`，`finally` 里 `release`。
- **其余写命令**：`change land`、`review approve`、`merge tick`、`merge cleanup`、`unqueued --notify`、`coordinator down` 在动手前调 `guard`，被挡住返回退出码 6（命令行层统一转换）。
- **status**：`probe.summarize_store` 加 `mergeLock`（含已跑分钟数与 `stale`），`__main__` 显示一行；只读，不清锁。
- **测试里的「后台合并」**：用会睡几秒的检查脚本在子进程里跑 `merge run`，等锁文件出现后再从测试进程调别的命令。

## 影响面

新增：`module_crew/mergelock.py`、`tests/test_background_checks.py`。修改：`merge.py`、`changes.py`、`review.py`、`unqueued.py`、`coordinator.py`、`probe.py`、`__main__.py`、
`skills/crew-coordinator/SKILL.md`、`README.md`。不新增依赖，不改契约、钩子、`interface.json`、版本号。

## Task List

- [ ] Task 1：`mergelock` 拿锁、放锁、读锁、失效判断（Spec 验收 1 的锁部分、验收 3）
- [ ] Task 2：`merge run` 拿放锁（成功、退回、冲突、超时、异常都放锁），第二个 `merge run` 退出码 6（Spec 验收 1、2）
- [ ] Task 3：其余六个写命令查锁，退出码 6、什么都不写；只读命令照常（Spec 验收 2、3）

### Checkpoint 1（report）：锁就位，相关测试通过，记入 todo 后继续

- [ ] Task 4：`status` 一行与 `--json` 的 `mergeLock`（Spec 验收 4）
- [ ] Task 5：crew-coordinator skill 后台运行的做法、README「合并」一步、全量测试与旧称扫描（Spec 验收 5、6）

### Checkpoint 2（gate）：最终验收

- [ ] 回告：完成情况发给总协调（local_d7434023）

## Risks

| 风险 | 影响 | 缓解 |
|---|---|---|
| 锁没放掉 | 之后所有写命令被挡 | `try/finally`；失效判断按进程号自动清；`status` 显示锁，用户一眼可见 |
| 误判失效清掉了正在用的锁 | 两个写操作同时动集成 checkout | 只在同主机且进程确实不在时清；集成 checkout 不干净或有 `MERGE_HEAD` 不清 |
| 测试里的时序 | 偶发失败 | 等锁文件出现再动作，检查脚本睡足够久；超时宽松 |
