# Implementation Plan: crew-codex-host

<!-- spec-guard: review pending -->

> 依据：`spec/crew-codex-host.md`（已批准）。任务清单：`tasks/crew-codex-host/todo.md`。

## Overview

先打底：状态库认 `codex-desktop`、`start prepare --host codex` 与开工说明的 Codex 段；再做只读预检 `host-check`；然后让恢复说明与 `sessions` 认宿主；
最后补 Codex 插件包、Codex 版 crew-dev、协调会话 skill 与 README。每个任务先写失败的测试，再实现到全绿，单独提交。Claude 路径逐字不变由测试守住。

## Architecture Decisions

- `store.HOSTS = ("claude-desktop", "codex-desktop")`；会话校验加一条：`role == "coordinator"` 时 host 只许 `claude-desktop`。
- `start.prepare(..., host="claude")`：`host` 只取 `claude`／`codex`，映射到登记值；开工说明在原文末尾追加 Codex 段（`render_kickoff` 多一个 `host` 参数，Claude 时返回值与现在逐字相同）。
  命令绝对路径取 `Path(__file__).resolve().parents[1] / "bin" / "module-crew"`。
- `module_crew/hostcheck.py`：`run(cwd) -> Report(code, checks, module, host)`；检查项见 Spec 关键决策 3；写 git 目录用 `tempfile.NamedTemporaryFile(dir=git_dir)` 创建即删。
  版本比对读插件根 `interface.json` 的 `version` 与状态库协调会话登记时记下的版本（`start prepare` 起在运行配置里记 `pluginVersion`；旧库没有就跳过该项并注明）。
- `failure.resume_kit`：按登记 host 选恢复说明；Codex 版不调 `hooks.session_start` 的压缩提示，加身份重登与先跑 `status` 两句。`sessions` 每行加 `host`。
- `.codex-plugin/plugin.json` 的 `version` 与 `.claude-plugin/plugin.json`、`interface.json` 一致，由测试守住。

## 影响面

新增：`.codex-plugin/plugin.json`、`codex-skills/crew-dev/SKILL.md`、`module_crew/hostcheck.py`、`tests/test_codex_host.py`。
修改：`module_crew/store.py`、`start.py`、`failure.py`、`probe.py`／`__main__.py`（去掉「第一版只支持 Claude」、加子命令与参数）、`skills/crew-coordinator/SKILL.md`、`tests/test_skills.py`、README。不涉及界面。

## Task List

### Phase 1：登记与开工

- [ ] Task 1：状态库认 `codex-desktop`，协调会话仍只许 Claude（验收 4）
- [ ] Task 2：`start prepare --host codex` 与开工说明 Codex 段，Claude 路径逐字不变（验收 1、2、3）

### Checkpoint 1（report）：Phase 1 全绿、Claude 开工说明逐字比较通过，记入 todo 后继续

### Phase 2：预检与恢复

- [ ] Task 3：`module-crew host-check`（验收 5）
- [ ] Task 4：`resume-kit` 按宿主出说明、`sessions` 加 `host`（验收 6、7）

### Phase 3：打包与说明

- [ ] Task 5：`.codex-plugin/plugin.json` 与 Codex 版 crew-dev（验收 8）
- [ ] Task 6：协调会话 skill「Codex 模块会话」一节、`status` 提示、README（验收 9、10）

### Checkpoint 2（gate）：模块最终验收

- [ ] 全部测试全绿；10 条验收逐条对应测试；列出实际改动文件；Spec 若补改则附差异
- [ ] 本 Plan 获批即授权：每个任务完成后在 `main` 本地提交；不推送；不发版、不动冻结副本 `module-crew-release/`；实地开 Codex 会话不在本 Plan 内（演练里经用户同意再做）

## Risks and Mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| 改开工说明时误动 Claude 文本 | 高 | 先写逐字比较测试（Claude 开工说明、恢复说明与修订前一致），再改 |
| `host-check` 的写测试在沙箱外总能通过，测不出真实沙箱 | 中 | 测试用 `chmod` 把 git 目录设只读模拟；真实 Codex 沙箱放到演练实测（Spec 未决问题） |
| Codex 插件安装路径与 Claude 不同，开工说明里的绝对路径指向 Claude 副本 | 低 | Codex 会话只读这份副本；`host-check` 报出命令能否运行；冻结副本路径固定 |
