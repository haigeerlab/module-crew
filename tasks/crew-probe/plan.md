<!-- spec-guard: review approved -->
# Implementation Plan: crew-probe

> 依据：`spec/crew-probe.md`（已批准）。任务清单：`tasks/crew-probe/todo.md`。

## Overview

先做依赖定位与接口读取（纯文件），再做唯一的外部命令 `/map --json`（含安全限制与超时），然后是 git 与集成基线，
最后汇总状态库并接上 `status` 命令；收尾在本机真实环境冒烟一次。每个任务先写失败的测试，再实现到全绿，单独提交。

## Architecture Decisions

- 全部在 `module_crew/probe.py`：`find_plugin()`（安装记录 → 安装目录）、`read_interface()`、`run_map()`、`check_git()`、`check_baseline()`、
  `summarize_store()`、`run()`；`Check` 与 `Report` 用冻结 dataclass。CLI 只在 `__main__.py` 做中文排版。
- 安装记录取法：`MODULE_CREW_PLUGINS_FILE` 或 `~/.claude/plugins/installed_plugins.json`；同目录 `known_marketplaces.json` 若声明该 marketplace 为 `directory` 来源，用源码目录（读它的 `marketplace.json` 与 `plugin.json`）。
- `mapView.command` 校验：第一个元素必须是 `python3`；脚本参数（第一个以 `.py` 结尾的元素）按安装目录解析后 `resolve()`，必须仍在安装目录内；`<project-root>` 原样替换。`subprocess.run(..., cwd=安装目录, timeout=10)`。
- 集成分支：状态库 `config/main` 记录的 `integrationBranch`，没有（或未建库）时取项目 checkout 的当前分支；`git worktree list --porcelain` 找检出它的 checkout。
- 夹具：`tests/fixtures/plugins/` 下放假的 `installed_plugins.json` 模板（测试里写入临时目录并替换路径）、`spec-guard-1.0/`、`spec-guard-1.1/`、`agent-relay-2.0/` 等安装目录；假 `map_view.py` 只打印固定 JSON 或按环境变量模拟超时、坏输出、退出码 3。

## 影响面

新增：`module_crew/probe.py`、`tests/fixtures/plugins/**`、`tests/test_probe_deps.py`、`tests/test_probe_map.py`、`tests/test_probe_repo.py`、`tests/test_probe_status.py`。
修改：`module_crew/__main__.py`（加 `status`）、`tests/helpers.py`（加夹具安装与只读快照工具）。不涉及界面。

## Task List

### Phase 1：依赖

- [ ] Task 1：依赖定位与接口版本（验收 1、2）
- [ ] Task 2：`/map --json` 运行、命令安全与规划层判据（验收 3、4）

### Phase 2：仓库

- [ ] Task 3：git 与集成基线（验收 5、6）

### Checkpoint 1（report）

- [ ] 全部测试全绿

### Phase 3：汇总与命令

- [ ] Task 4：状态库汇总与 `run()` 报告（验收 7、9）
- [ ] Task 5：`status` 命令与 `--json`（验收 8、9）
- [ ] Task 6：本机真实环境冒烟（验收 10，结果写进 todo）

### Checkpoint 2（gate）：模块最终验收

- [ ] 全部测试全绿；逐条对照 Spec 的 10 条验收标准，写明各由哪个测试覆盖
- [ ] 在对话里列出本模块实际改动的文件（新增、修改、删除与行数）
- [ ] 本 Plan 获批即授权：每个任务完成后在 `main` 做一次本地提交；冒烟只读运行本机已装的 spec-guard 与 agent-relay 接口；不推送

## Risks and Mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| spec-guard 1.1 字段名与夹具不一致 | 中 | 已向 spec-guard 负责人确认（2026-10-18 发出）；回复前按建议名写，回复后改夹具；判据集中在一个函数里 |
| 运行 `/map` 慢或挂住 | 中 | 10 秒超时，超时判 blocker 并写原因 |
| 测试读到本机真实安装记录 | 高 | 所有测试都设 `MODULE_CREW_PLUGINS_FILE` 到临时目录；基类断言已设置 |
