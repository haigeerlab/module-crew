# Implementation Plan: crew-command-entry

<!-- spec-guard: review pending -->

> 依据：`spec/crew-command-entry.md`（用户 2026-10-22 批准）。任务清单：`tasks/crew-command-entry/todo.md`。

## Overview

先修 `bin/module-crew` 的启动方式（独立、最小），再写固定启动脚本本身（定位与转发），然后让 `start prepare`、`coordinator up` 写入它，
最后把 Codex 那边的开工说明、权限规则、skill 改指它，补 README 并实测。每个任务先写失败的测试、看到红再实现到绿，单独在 `main` 本地提交，不推送、不发版。

## Architecture Decisions

- **`bin/module-crew`**：`ROOT` 照旧由脚本位置算出；改为 `exec python3 -c '<引导>' "$ROOT" "$@"`，引导把 `sys.argv.pop(1)`（即 ROOT）插到 `sys.path[0]`、
  `sys.argv[0] = "module-crew"`，再 `runpy.run_module("module_crew", run_name="__main__", alter_sys=True)`。不再设 `PYTHONPATH`（避免传给子进程）。
- **`module_crew/launcher.py` 本身就是启动脚本**：只用标准库、不 import `module_crew`，`if __name__ == "__main__": sys.exit(main())`。
  `main()`：读 `MODULE_CREW_PLUGINS_FILE` 或 `~/.claude/plugins/installed_plugins.json` → 按 `git rev-parse --show-toplevel`（当前目录）选项目级、否则用户级条目 →
  目录型市场取 `known_marketplaces.json` 登记的源目录（与 `probe._directory_source` 同规则）→ 找到 `<root>/bin/module-crew` 就 `os.execv`，否则中文原因写标准错误、返回 2。
- **写入函数也在 `launcher.py`、同样只用标准库**：`install(store_dir) -> (path, changed)`，读自身源码（`Path(__file__).read_bytes()`）与目标比对，不同才用同目录临时文件 + `os.replace` 写入并 `chmod 0o755`；不删除任何文件。
- **调用处**：`start.prepare` 与 `coordinator.up` 成功路径里调 `launcher.install(db.path)`，输出加一行。`start.codex_lines` 与 `permissions.codex_rules` 用 `launcher.entry(db.path)`（固定路径）替代 `BIN`／`CREW_BIN`；
  `codex_lines` 需要状态库目录，改为接收它作参数。
- **一致性测试**：同几组假安装记录，分别跑 `launcher` 的定位函数与 `probe.find_plugin`，比较选中的目录。

## 影响面

新增：`module_crew/launcher.py`、`tests/test_command_entry_codex.py`。修改：`bin/module-crew`、`start.py`、`coordinator.py`、`permissions.py`、`codex-skills/crew-dev/SKILL.md`、`README.md`。
不新增依赖，不改契约、钩子、`interface.json`、版本号。

## Task List

- [ ] Task 1：`bin/module-crew` 改为插件目录排最前、程序名 `module-crew`（Spec 验收 6）
- [ ] Task 2：`launcher.py` 定位与转发、找不到退出码 2、与 `probe.find_plugin` 一致（Spec 验收 2、3、4）
- [ ] Task 3：`start prepare`、`coordinator up` 写入启动脚本，内容相同不重写、输出一行（Spec 验收 1）

### Checkpoint 1（report）：启动脚本就位，相关测试通过，记入 todo 后继续

- [ ] Task 4：Codex 开工说明、Codex 权限规则、Codex 版 crew-dev skill 改用固定入口，Claude 侧不变（Spec 验收 5）
- [ ] Task 5：README「Codex 模块会话」、全量测试与旧称扫描、本机实测启动脚本 `status`（Spec 验收 7）

### Checkpoint 2（gate）：最终验收

- [ ] 回告：完成情况发给总协调（local_d7434023）
