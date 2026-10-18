# Implementation Plan: crew-host-permissions

<!-- spec-guard: review approved -->

> 依据：`spec/crew-host-permissions.md`（用户 2026-10-19 批准）。任务清单：`tasks/crew-host-permissions/todo.md`。

## Overview

先做只读的 `permissions plan`（清单、各 checkout 能不能写、钩子能不能装、Codex 信任状态），再做 Claude 规则的合并写入与撤销，然后 Codex 规则，
再做 pre-push 钩子与 `merge push` 的放行凭证，最后接上 `start prepare`、实测清单与记录、`status`、skill 与 README。
每个任务先写失败的测试，再实现到全绿，单独在 `main` 本地提交。

## Architecture Decisions

- **新文件 `module_crew/permissions.py`**：`checkouts(db, project)` 列出集成 checkout 与在用模块 worktree（带 host）；`claude_entries(cfg)`、`codex_rules(cfg)` 生成固定清单；
  `plan()` 只读；`apply()`／`remove()` 先对所有目标做完检查，全部能写才写（任一拒绝什么都不写）；`verify_list(host)`、`record()`。
- **记录放进现有 `config` 种类**：键 `permissions`，内容 `{applied, original, at, files: {路径: {allow: [...], deny: [...]}}, codexRules: [...], hook: {installed, path, reason}, verified: {会话名: {allowed, denied, at}}}`。
  不新增记录种类，状态库格式不变。
- **module-crew 自己的路径**：`Path(__file__).resolve().parents[1] / "bin" / "module-crew"`（与 `hostcheck.ROOT` 同法），写成 `Bash(<绝对路径> *)`。
- **git 忽略检查**：`git -C <checkout> check-ignore -q <相对路径>`，返回 0 才算忽略；`.codex/rules/module-crew.rules` 同样检查。
- **Codex 信任读取**：只读 `~/.codex/config.toml`（`CODEX_HOME` 优先），用标准库 `tomllib` 找 `[projects."<路径>"] trust_level = "trusted"`；读不到按「未知」报。测试用环境变量指向临时文件。
- **新文件 `module_crew/prepush.py`**：钩子正文是一个只用标准库的 Python 脚本字符串（首行 `#!/usr/bin/env python3`，第二行 `# module-crew pre-push`），
  装到 `git rev-parse --git-common-dir`／`hooks/pre-push` 并设可执行；凭证 `<状态库>/push-token.json` 的写、读、删函数供 `merge.push` 与钩子共用（钩子脚本内联同样的读法，不 import module_crew）。
- **`merge.push`**：`git push` 前写凭证（远端分支 `refs/heads/<新分支>`、过期 = 现在 + 120 秒、随机串），`finally` 里删除；钩子拒绝时 git 失败，按现有「推送失败」路径退出 4 并带出 stderr。

## 影响面

新增：`module_crew/permissions.py`、`module_crew/prepush.py`、`tests/test_permissions.py`、`tests/test_prepush.py`。
修改：`module_crew/merge.py`（push 写删凭证）、`module_crew/start.py`（prepare 跟随）、`module_crew/__main__.py`（`permissions` 子命令、status 显示实测）、
三份 skill、`README.md`。会写用户项目里被 git 忽略的 `.claude/settings.local.json`、`.codex/rules/module-crew.rules` 与 git 公共目录的 `hooks/pre-push`——只在 `apply` 凭用户原话时写，测试全在临时仓库。不涉及界面。

## Task List

### Phase 1：清单与 Claude 规则

- [ ] Task 1：`permissions plan`（只读）——列 checkout、各自要追加的 allow／deny、是否被 git 忽略、钩子能否装与原因、Codex 信任状态；`--json`（验收 1）
- [ ] Task 2：`permissions apply`／`remove` 的 Claude 部分——合并追加、全有或全无、记 `config/permissions`、只删自己追加的条目（验收 2、3、9 的 Claude 部分）
- [ ] Task 3：Codex 规则——`.codex/rules/module-crew.rules` 生成（allow／forbidden、match／not_match）、只写 codex 模块 worktree、信任状态提示、`remove` 删文件（验收 4、9 的 Codex 部分）

### Checkpoint 1（report）：plan／apply／remove 在临时仓库三种 checkout（集成、Claude 模块、Codex 模块）下跑通，全量测试通过，记入 todo 后继续

### Phase 2：推送守门

- [ ] Task 4：pre-push 钩子与放行凭证——钩子正文、`apply` 安装（`core.hooksPath` 或已有钩子时不装并写原因）、`remove` 凭标记删除、`merge push` 写删凭证；本机裸仓库实推测试（验收 5、6、9 的钩子部分）

### Phase 3：跟随、实测与文档

- [ ] Task 5：`start prepare` 跟随写规则；`permissions verify` 实测清单（Codex 有 `codex` 命令时附 `codex execpolicy check`）；`verify --record`；`status` 显示每个会话最近一次实测或「权限未实测」（验收 7、8）
- [ ] Task 6：三份 skill 与 README——代开会话里宿主确认可能不弹、开会话后跑实测清单并记录、推送只经 merge push、Codex 要先信任项目；README「权限预配」一节与命令表（验收 10）

### Checkpoint 2（gate）：模块最终验收

- [ ] 全量测试全绿（验收 12）；验收逐条对应测试名与结果；列出实际改动文件与提交号
- [ ] 验收 11（实地）：按项目约定，演练执行交给接入方案会话（「module-crew 接入 LIVE-SAAS 方案」）。最终验收时给出可照做的实测步骤；做了就附 `verify --record` 结果，没做就写「宿主未实测」与原因，由用户决定是否先验收
- [ ] 本 Plan 获批即授权：每个任务完成后在 `main` 本地提交；不推送；不在任何真实项目里运行 `permissions apply`；不升版本号、不冻结、不动 `module-crew-release/`；最终验收通过后直接写 crew-glossary-rename 的 Spec 交审

## Risks and Mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| 钩子挡住 `merge push` 自己 | 高 | Task 4 用本机裸仓库实推：有凭证成功、凭证不留；无凭证被拒 |
| 宿主不按文档执行 deny（像 ask 那样） | 中 | 钩子兜底推送；验收 11 实测；删除类失效时写进验收结论交用户 |
| 用户本人手动推送被钩子拦 | 低 | 拒绝信息写明「你自己推送可加 --no-verify」；`remove` 可卸 |
| `settings.local.json` 被用户手改后 `remove` 认不出 | 低 | 只删状态库记着的条目字符串，找不到的跳过并列出 |
| Codex 规则语法随版本变化 | 中 | 每条带 match／not_match 让宿主加载时自检；验收时有 `codex` 就跑 execpolicy check |
| `tomllib` 需 Python 3.11+ | 低 | 读不到按「信任状态未知」报，不报错退出 |

## Open Questions

无。
