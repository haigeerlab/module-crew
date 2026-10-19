# Todo: crew-host-permissions

测试命令：`python3 -m unittest discover -s tests -v`

- [x] Task 1：`permissions plan`（只读）
  - 验收：Spec 验收 1
  - 文件：`module_crew/permissions.py`、`module_crew/__main__.py`、`tests/test_permissions.py`

- [x] Task 2：`permissions apply`／`remove`（Claude 规则）
  - 验收：Spec 验收 2、3、9（Claude 部分）
  - 文件：`module_crew/permissions.py`、`module_crew/__main__.py`、`tests/test_permissions.py`

- [x] Task 3：Codex 规则文件与信任提示
  - 验收：Spec 验收 4、9（Codex 部分）
  - 文件：`module_crew/permissions.py`、`tests/test_permissions.py`

- [x] Checkpoint 1（report）：三种 checkout 下 plan／apply／remove 跑通，全量测试通过（2026-10-19，379 个测试通过；本机 codex-cli 0.162.1 用 `codex execpolicy check` 核对生成的规则：git push、rm -rf、git config --global 为 forbidden，git commit、git status、检查命令为 allow。偏差两处待最终验收复审：① 按项目「不删除文件」约束（tests/test_package.py），`remove` 不删 Codex 规则文件而是清空规则，凭证与钩子同样改为停用而不删除；② 记录放在运行配置 `config/main` 的 `permissions` 字段——状态库 config 只有 main 一个键）

- [x] Task 4：pre-push 钩子与放行凭证
  - 验收：Spec 验收 5、6、9（钩子部分）
  - 文件：`module_crew/prepush.py`、`module_crew/permissions.py`、`module_crew/merge.py`、`tests/test_prepush.py`

- [x] Task 5：prepare 跟随、实测清单与记录、status 显示
  - 验收：Spec 验收 7、8
  - 文件：`module_crew/start.py`、`module_crew/permissions.py`、`module_crew/__main__.py`、`tests/test_permissions.py`

- [x] Task 6：skill 与 README
  - 验收：Spec 验收 10
  - 文件：`skills/crew-coordinator/SKILL.md`、`skills/crew-dev/SKILL.md`、`codex-skills/crew-dev/SKILL.md`、`README.md`、`tests/test_skills.py`

- [x] Checkpoint 2（gate）：模块最终验收——全量测试全绿（验收 12）、验收逐条对应证据、验收 11 实地结果或「宿主未实测」、改动文件清单与提交号（2026-10-19 用户批准，同时批准构建中补改的 Spec：不删文件、记录放运行配置；全量 393 个测试通过；提交 dc51b57…d04fbad。验收 11 记为「宿主未实测」：用户定在冻结 0.4.0 前交给接入方案会话照共享笔记 crew-host-permissions-field-test.md 的步骤实测，结果补进本模块）

- [x] 验收 11 实地测试（2026-10-19，接入方案会话执行，用户在该会话亲口同意并确认全程无弹窗）：crew-rehearsal，代码 d5bb2dc；apply 给集成 checkout、alpha、beta 三份 settings.local.json 各追加放行 8 条、禁止 13 条；由接入方案会话代开 default 权限模式的测试会话（local_cd5cd580，alpha worktree）逐条跑：`module-crew status`、`git status`、`git add --dry-run .`、`bridge_agents` 直接运行，`git push --dry-run module-crew-probe HEAD` 被宿主拒（「Permission to use Bash with command git push --dry-run module-crew-probe HEAD has been denied.」）；`verify --record rh2-alpha --allowed ok --denied ok` 已记，status 显示「权限实测 2026-10-19 03:53：放行如预期、拒绝如预期」。结论：deny 在代开会话里生效。推送守门没装：crew-rehearsal 设了 core.hooksPath（.husky/_），「模块会话推送被钩子拒」一项测不了，推送只靠宿主禁止规则（本次已拦住）；LIVE-SAAS 也用 husky，情况相同，是否另想办法交用户定。测后由接入方案会话 permissions remove 并与备份比对（结果另报）。

- [x] Task 7（追加）：`remove` 后文件逐字还原——apply 记下原文件全文，remove 去掉追加条目后与原文件一致就写回原文，不再留下 module-crew 建的空 `deny`／`allow`／`permissions`（Spec 验收 9 范围内的修复；来源：接入方案会话实测 remove 后的观察，2026-10-19）

- [x] Task 8（0.5.0，R21 MC-1）：项目内安装依赖放行、全局安装仍禁止，Codex 规则同步；execpolicy 实测同时命中取 forbidden
  - 验收：Spec 验收 13
  - 文件：`module_crew/permissions.py`、`tests/test_permissions.py`、`README.md`

- [x] R21 MC-1 验收（2026-10-19 用户批准；全量 415 个测试通过）

- [x] Task 9（0.5.0，R21 MC-1 按决定 61 修订）：放行收窄为按锁文件或清单装的命令，加新包不写规则，全局安装禁止；Codex 同步；crew-dev skill 写明加新包先问一次
  - 验收：Spec 验收 13（修订后）
  - 文件：`module_crew/permissions.py`、`tests/test_permissions.py`、两份 crew-dev SKILL.md、`README.md`

- [x] Task 9 验收（2026-10-19 用户批准；全量 417 个测试通过；提交 9315f38、3dca76b；随 0.5.0 冻结）

- [x] Task 10（0.5.1，R21 MC-1 按决定 62 修订）：Claude 放行加新包（`npm install *`、`pnpm add *`、`yarn add *`、`uv add *`、`uv pip install *`、`.venv/bin/pip install *`），裸 `pip install` 仍不写规则；deny 补全全局安装（`npm|pnpm * -g|--global`、`yarn global *`、`uv * --system`）；Codex 加新包仍不写规则，forbidden 补 `npm i -g`、`--global`、`yarn global add`；README 同步
  - 验收：Spec 验收 13（0.5.1）
  - 文件：`module_crew/permissions.py`、`tests/test_permissions.py`、`README.md`

- [x] Task 10 验收（2026-10-19 用户批准；全量 417 个测试通过；提交 e3e5af4；随 0.5.1 冻结）

- [x] Task 11（0.5.2，决定 67）：README 与 crew-coordinator skill 去掉「ask 规则实测不弹」，改为「不可逆操作不能只靠弹窗（点一次『允许』就执行）」；skill 测试断言改新说法并断言旧说法不再出现；版本 0.5.2
  - 验收：Spec 验收 10（0.5.2 更正）
  - 文件：`README.md`、`skills/crew-coordinator/SKILL.md`、`tests/test_skills.py`、三处版本号

- [x] Task 11 验收（2026-10-19 用户批准；全量 418 个测试通过；提交 ba4dfac；随 0.5.2 冻结）
