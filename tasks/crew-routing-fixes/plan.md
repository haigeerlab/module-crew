# Implementation Plan: crew-routing-fixes

<!-- spec-guard: review approved -->

> 依据：`spec/crew-routing-fixes.md`（用户 2026-10-20 批准）。任务清单：`tasks/crew-routing-fixes/todo.md`。

## Overview

先实测会话 id 在压缩、重开后是否不变（钩子方案的前提，不成立就停下改方案），再做三处代码修复：审查者负责范围、挂起模块跳过同步基线、会话身份登记与钩子核对。
最后改 skill、README 与版本号。每个任务先写失败的测试，再实现到全绿，单独在 `main` 本地提交，不推送。

## Architecture Decisions

- **审查者范围**：`config.main.sources` 里 lead 行加 `scope: {"modules": [..] | "all", "nodes": [..] | "all"}`。`sources.add` 对 lead 要求两项都给，对 hub 拒绝；
  新增 `sources.set_scope(db, name, modules, nodes, original)`；`sources.covers(row, module, node)` 判定。命令行「全部」与 `all` 都认。
  `review._reviewers(db, module, node)` 只返回覆盖的 lead；没有 `scope` 的旧行不返回，`review.add` 另输出一行「审查者 X 没登记负责范围，未送审」。
  登记时与已有 lead 范围重叠只输出提示。`source list`（含 `--json`）带范围。
- **挂起跳过**：`changes.land` 的循环加 `sess.get("suspended")` 跳过，请求方例外（与「等最终验收」的例外同一处判断）。
  `failure.resume` 在找 `item.merged` 事件之外，再找挂起之后的 `request.landed` 事件，待办合成一句「挂起期间合入了 …、落地了公共变更 C<N>（<提交>）：先同步…」。
- **身份登记**：会话登记加可选字段 `hostSession: {"sessionId", "hostSessionId", "boundAt"}`（`store._validate_session` 校验类型）。
  新命令 `module-crew bind <邮箱名>`：从环境变量 `CLAUDE_CODE_SESSION_ID`、`CLAUDE_CODE_HOST_SESSION_ID` 读取；都没有就拒绝（退出码 3）。
  规则按 Spec 关键决策 5；`takeover` 在同一事务里清掉 `hostSession`。`start` 登记模块协调时顺带写它自己的 `hostSession`。
  开工说明「邮箱名」那一行之后加「先运行 module-crew bind <邮箱名>」；恢复说明在「用同一个名字注册」之后加同样一步；Codex 段不加（没有钩子）。
- **钩子核对**：`detect(cwd)` 不变（仍回答「这个目录属于哪条登记」）；新增 `matches(role, payload)`：payload 的 `session_id` 等于登记的 `sessionId`，
  或环境变量 `CLAUDE_CODE_HOST_SESSION_ID` 等于登记的 `hostSessionId`，才算对上。`run_hook` 把 payload 传下去：
  对上照旧；对不上时 SessionStart 只给那一句（文字见 Spec 关键决策 6），UserPromptSubmit 返回空。
- **status**：会话一栏对没有 `hostSession` 的在用会话标「未登记身份」；`sessions --json` 不改（契约字段不动）。

## 影响面

修改：`module_crew/sources.py`、`module_crew/review.py`、`module_crew/changes.py`、`module_crew/failure.py`、`module_crew/hooks.py`、`module_crew/store.py`、
`module_crew/start.py`、`module_crew/probe.py`（status 一栏）、`module_crew/__main__.py`（`source add` 参数、`source scope`、`bind`）、三份 skill、`README.md`、版本号。
新增：`tests/test_routing.py`。修改测试：`tests/test_sources.py`、`tests/test_review_add.py`、`tests/test_hooks.py`、`tests/test_skills.py` 等受新必填参数影响的用例。
不新增依赖，不改契约与 `interface.json`，不涉及界面。

## Task List

### Checkpoint 0（gate）：实测前停下问你

  - 要做的事：在 scratchpad 里建一个临时仓库，装一个只把 payload 的 `session_id` 和 `CLAUDE_CODE_HOST_SESSION_ID` 写进文件的钩子，
    开一个新的桌面版会话，压缩一次，再关掉、在桌面版里重开同一会话，看两次记下的值。
  - 为什么停：要新开会话、在临时目录写钩子配置。

- [ ] Task 1：实测会话 id 稳定性（Spec 验收 6），结果写进 todo。`session_id` 会变就停下，把改法交你决定；钩子里读不到 `CLAUDE_CODE_HOST_SESSION_ID` 就去掉这条备用核对
- [ ] Task 2：审查者负责范围——`source add --modules/--nodes` 必填、`source scope`、`source list` 显示、`review add` 只送覆盖的审查者、旧登记不送并提醒、重叠提示
  - 验收：Spec 验收 1、2
  - 文件：`module_crew/sources.py`、`module_crew/review.py`、`module_crew/__main__.py`、`tests/test_routing.py`、受影响的旧测试
- [ ] Task 3：`change land` 跳过挂起模块（请求方例外），`resume` 补写挂起期间落地的公共变更
  - 验收：Spec 验收 3
  - 文件：`module_crew/changes.py`、`module_crew/failure.py`、`tests/test_routing.py`

### Checkpoint 1（report）：两处收件收窄就位，全量测试通过，记入 todo 后继续

- [ ] Task 4：身份登记——`hostSession` 字段与校验、`module-crew bind`、`takeover` 清身份、`start` 登记协调时写身份、开工说明与恢复说明加 `bind`、`status` 标「未登记身份」
  - 验收：Spec 验收 5
  - 文件：`module_crew/store.py`、`module_crew/hooks.py`（takeover）、`module_crew/start.py`、`module_crew/failure.py`（恢复说明）、`module_crew/probe.py`、`module_crew/__main__.py`、测试
- [ ] Task 5：钩子按会话核对——对上照旧，对不上 SessionStart 一句、每轮不注入；重放 38932d81／cb182a33 与 alpha 三个会话的场景
  - 验收：Spec 验收 4
  - 文件：`module_crew/hooks.py`、`tests/test_hooks.py`、`tests/test_routing.py`
- [ ] Task 6：三份 skill 写 `bind` 与审查者范围；README 写 0.9.0 的变化；版本 0.9.0；全量测试与旧称扫描
  - 验收：Spec 验收 7
  - 文件：`skills/crew-coordinator/SKILL.md`、`skills/crew-dev/SKILL.md`、`codex-skills/crew-dev/SKILL.md`、`README.md`、版本号、`tests/test_skills.py`

### Checkpoint 2（gate）：最终验收

- [ ] 回告：把完成情况发给总协调（local_d7434023）

## 风险

- Task 1 实测若显示重开会话 `session_id` 会变，钩子方案要改（例如只认桌面版会话 id），Task 4、5 的设计随之调整，先回 Spec 复审。
- `source add` 加必填参数会让现有 lead 登记的测试与 skill 示例一起改；漏改的地方由全量测试兜住。
- 升级后已在跑的会话失去角色注入，要靠 `status` 的「未登记身份」提醒跑 `bind`。
