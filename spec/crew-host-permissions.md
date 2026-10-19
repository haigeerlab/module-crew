# Spec: crew-host-permissions

<!-- spec-guard: review approved 596690ee8fea -->

> 能力图模块 `crew-host-permissions`（第四版，0.4.0 三个模块之二）。需求来源：`livesaas-integration/REQ-REVIEW-NEARBY.md` R16（用户决定 44 第①条、49）；
> decision-inbox 2026-10-19 实测：由别的会话用开会话工具代开的会话里，`.claude/settings.local.json` 的 ask 规则（如 `git push`）不弹确认就执行。
> 用户 2026-10-19 在本会话确认 19 条下一版假设（全部按推荐，第 13 条选 A）。契约 session-protocol v2.1 不变。

## 目标

模块协调和模块会话做第 44 条①范围内的常规操作时不再弹权限确认，用户不必回原会话「再说一遍」；推送、删除这类不可逆操作即使在宿主弹窗失灵的代开会话里也推不出去，
唯一的推送路径仍是凭用户原话的 `module-crew merge push`。module-crew 把规则写进宿主真正认的权限文件，并留下「宿主确实放行」的实测记录。

## 范围

- 新命令 `module-crew permissions plan|apply|verify|remove`：预览、凭用户原话写入、实测清单与结果记录、撤掉自己写的东西。
- Claude：写集成 checkout 与每个模块 worktree 的 `.claude/settings.local.json`（allow 常规操作、deny 不可逆操作）。
- Codex 模块 worktree：写 `.codex/rules/module-crew.rules`（`prefix_rule`，常规 allow、不可逆 forbidden），并检查项目是否受信任。
- git `pre-push` 钩子：拦模块 worktree 的推送，以及集成 checkout 上没有 `merge push` 一次性放行凭证的推送；`merge push` 推送前写凭证、用后标为已用（module-crew 不删文件）。
- `start prepare` 新建 worktree 时，若已 apply 过，自动写同一份规则。
- README、两份 crew-dev skill 与 crew-coordinator skill 写明：代开会话里宿主确认可能不弹，不可逆操作不能只靠弹窗。

不做：decision-inbox 的 join 写入与「去〈会话名〉点允许」提醒（归 decision-inbox）；替用户把项目设为 Codex 受信任（改全局配置，只提示）；
改宿主权限模式；全面改名（crew-glossary-rename）。

## 宿主事实（写 Spec 时查的官方文档，2026-10-19）

1. Claude Code：规则写在 `permissions.allow/ask/deny`，项目级本机文件是 `.claude/settings.local.json`；**先看 deny，再看 ask，再看 allow，第一条命中的决定**；
   deny 在 `bypassPermissions` 模式下也生效；Bash 规则 `Bash(git push *)` 匹配以 `git push` 开头的命令，复合命令（`&&`、`;`、`|`、子 shell、命令替换）里任一子命令命中 deny 即拒绝；
   只读 Bash 命令本来就不需要规则。（code.claude.com/docs/en/permissions、settings-reference、agent-sdk/permissions）
2. Codex：项目里的 `.codex/rules/*.rules` 用 `prefix_rule(pattern=[...], decision="allow"|"prompt"|"forbidden")`；**项目层（含 exec policy）只在项目受信任时生效**，
   不受信任时加载但禁用；`codex execpolicy check --rules <文件> <命令>` 可以静态检查一条命令落在哪个决定。（github.com/openai/codex：execpolicy/README.md、config/src/loader/mod.rs）
3. `CLAUDE.local.md`、`AGENTS.md` 只是规则文字，不改变宿主是否弹窗——所以需求原文写的「写进 CLAUDE.local.md」由本模块改为写权限文件（假设 10）。

## 假设（用户 2026-10-19 已确认，摘本模块相关的）

9. R16 的 join 写入与「去会话点允许」提醒归 decision-inbox；module-crew 只管集成 checkout 与模块 worktree 的权限预配和推送前检查。
10. Claude 写 `.claude/settings.local.json`；Codex 是否有项目级权限配置写 Spec 时查文档再定——查到有（宿主事实 2），本 Spec 定为写 `.codex/rules/module-crew.rules`（关键决策 3）。
11. `permissions plan` 预览、`permissions apply --original-file` 凭用户原话写入；合并已有内容不覆盖；文件没被 git 忽略就拒绝；`start prepare` 建 worktree 时复制同一份；
    放行清单为第 44 条①范围；推送、删除、联网安装、改全局配置一律不放行。
12. 「实测宿主放行」：`permissions verify` 给无害命令清单，模块协调开会话后让模块会话逐条跑、看它有没有进入「等待审批」，结果记进状态库；验收时在 crew-rehearsal 默认权限模式实跑并留证据。
13. A：模块 worktree 对推送、删除写 deny（不是 ask）；装 pre-push 钩子拦模块 worktree 推送与集成 checkout 上没有 `merge push` 放行凭证的推送；仓库设了 `core.hooksPath` 时不装并报出；deny 在代开会话里是否生效验收时实测。
14. README 与 skill 写明代开会话里宿主确认可能不弹，不可逆操作不能只靠弹窗。

## 关键决策与取舍（请重点审）

1. **放行与禁止清单是固定的，不读项目猜**：
   - Claude allow：`Bash(<module-crew 绝对路径> *)`（apply 时取正在运行的 `bin/module-crew` 绝对路径）、`Bash(git add *)`、`Bash(git commit *)`、`Bash(git status *)`、`Bash(git diff *)`、`Bash(git log *)`、`Bash(git show *)`、
     `mcp__agent-relay`（整个服务器）、运行配置里的检查命令 `checkCommand`（有才加，按「首个词 *」写，如 `Bash(pnpm test *)`）。
   - Claude deny：`Bash(git push *)`、`Bash(git push)`、`Bash(rm -rf *)`、`Bash(git reset --hard *)`、`Bash(git branch -D *)`、`Bash(git worktree remove *)`、`Bash(git config --global *)`、
     `Bash(npm install -g *)`、`Bash(pnpm add -g *)`、`Bash(pip install *)`、`Bash(brew install *)`、`Bash(curl * | sh)`、`Bash(curl * | bash)`。
   - spec-guard 命令不进 allow：它的入口路径带插件版本号（`.../spec-guard/0.72.0/hooks/...`），升级就失效；spec-guard 自己的权限由它的安装方式管。Spec 写明，不在本版解决。
   - 不写 ask：ask 在代开会话里实测不弹（需求依据），写了等于放行。
   - （0.5.0 修订，R21 MC-1；按用户决定 61 与 decision-inbox DI-2 对齐）**按锁文件或清单装依赖的命令放行**：`Bash(npm ci)`、`Bash(npm ci *)`、`Bash(npm install)`（只放不带参数的）、`Bash(pnpm install)`、`Bash(pnpm install --frozen-lockfile)`、`Bash(yarn install)`、`Bash(uv sync)`、`Bash(uv sync *)`、`Bash(pip install -r *)`、`Bash(.venv/bin/pip install -r *)`。**往项目里加新包的命令不写任何规则**（`npm install <包名>`、`pnpm add`、`yarn add`、`uv add`、`pip install <包名>`、`.venv/bin/pip install <包名>`）：需求原文要的是「先问」，但 module-crew 的模块会话由模块协调代开，代开会话里 ask 规则实测不弹确认（本 Spec 第 53 行「不写 ask」的依据），写成 ask 等于静默放行；所以不写规则、交给宿主的默认确认，再由 crew-dev skill 规定「Plan 没列的依赖先经模块协调问用户一次」，spec-guard 的 SG-5b 事后核对新增依赖。「不写规则时代开会话会不会弹默认确认」尚未实测，列入下一次实地测试。**全局安装仍禁止**：`npm install -g`、`pnpm add -g`、`brew install`；原先对裸 `pip install` 的整体禁止取消（它属于加新包，按上面不写规则）。deny 先于 allow。Codex 规则同样改：按锁文件装的 `allow`，加新包的不写规则，全局安装 `forbidden`；`codex execpolicy check` 实测 `npm install -g x` 为 forbidden、`npm install x` 无匹配。
2. **集成 checkout 与模块 worktree 用同一份**：模块协调也不该自己 `git push`——推送只走 `merge push`（它在子进程里推，不经宿主规则，靠用户原话把关）；
   收回 worktree 走 `merge cleanup`。所以两边 deny 相同，只是集成 checkout 多一个推送凭证的放行口（决策 5）。
3. **Codex 写 `.codex/rules/module-crew.rules`**：与 Claude 清单对应——常规操作 `decision = "allow"`，不可逆操作 `decision = "forbidden"` 并在 `justification` 写「推送只经模块协调的 merge push」；
   每条带 `match`／`not_match` 样例，宿主加载时自检。只写 `host` 为 codex 的模块 worktree。项目不受信任时规则不生效：`plan`／`verify` 读 `~/.codex/config.toml`（只读）报「项目未受信任，规则不会生效；
   要生效请你在 Codex 里信任该项目」，不替用户改全局配置。`verify` 有 `codex` 命令时跑 `codex execpolicy check` 静态核对清单里每条命令的决定。
4. **写入只合并、可撤销**：读已有文件（没有就新建），只往 `allow`／`deny` 列表追加缺的条目，不删不改别的键；写之前确认路径被 git 忽略（`git check-ignore`），没被忽略就整体拒绝、什么都不写；
   每个文件追加了哪些条目记进状态库（运行配置 `config/main` 的 `permissions` 字段：路径、条目、时间、用户原话；状态库 config 只有 main 一个键），`permissions remove --original-file` 只撤这些条目，别人加的不动；按项目「不删文件」的约束（`tests/test_package.py`），Codex 规则文件改为只剩说明的空规则，钩子改为空操作，文件留给用户手动删。JSON 读不出就拒绝，不覆盖。
5. **pre-push 钩子**（git 公共目录 `hooks/pre-push`，所有 worktree 共用）：
   - 只装在没有 `core.hooksPath`、也没有已存在的 `pre-push` 的仓库；任一存在就不装，`plan`／`apply` 输出「没装推送守门：<原因>，推送只能靠宿主 deny 规则」，由用户决定。
   - 钩子是一个只用标准库的 Python 脚本，第一行注释带 `module-crew pre-push` 标记（`remove` 凭它认）。逻辑：找不到 module-crew 状态库 → 放行（项目已不用 module-crew）；
     当前 checkout 是登记的模块 worktree → 拒绝，说明「模块会话不推送，做完发最终验收交审」；其他 checkout → 要有效的放行凭证，否则拒绝，说明「推送只经模块协调的 module-crew merge push（要用户原话）；你自己在终端推送可加 --no-verify」。
   - 放行凭证：`merge push` 在调用 `git push` 前写 `<状态库>/push-token.json`（目标远端分支、过期时间 2 分钟、随机串），钩子核对 stdin 里要推的远端引用与凭证一致、未过期、未用过，用掉即标为已用；`merge push` 结束（成功或失败）也标为已用。钩子里写死 module-crew 状态库与 worktree 目录（`crewDir`），不依赖插件位置与版本。
   - `--no-verify` 会跳过钩子：对 agent 由 deny 规则 `Bash(git push *)` 挡（复合命令也挡，宿主事实 1）；对用户本人是有意留的出口。Spec 写明这一层的局限。
6. **实测与记录**：`permissions verify [--host claude|codex]` 输出一份给模块会话照跑的清单——四条应放行（`module-crew status`、`git status`、`git add --dry-run .`、`bridge_agents`）
   与一条应被拒（`git push --dry-run module-crew-probe HEAD`：远端名不存在，就算宿主没拦也推不出去）。模块协调看完后用 `permissions verify --record <会话名> --allowed ok|prompted --denied ok|ran`
   记进状态库（带时间）；`status` 显示每个会话最近一次实测结果，没测过写「权限未实测」。命令本身不判断宿主行为，只记模块协调报来的观察。
7. **`start prepare` 跟随**：运行配置里有 `permissions.applied` 时，新建 worktree 后照同一清单写规则，输出一行「已写权限规则」；写失败（没被忽略等）不阻止开工，输出原因并在 `status` 标出。

## 接口约定

```bash
bin/module-crew permissions plan [--json]                                   # 只读：每个 checkout 要写什么、会不会被拒、钩子能不能装、Codex 信任状态
bin/module-crew permissions apply (--original <原话> | --original-file <文件>)  # 写规则、装钩子、记状态库
bin/module-crew permissions verify [--host claude|codex]                    # 输出实测清单（Codex 有 codex 命令时附 execpolicy 静态核对）
bin/module-crew permissions verify --record <会话名> --allowed ok|prompted --denied ok|ran
bin/module-crew permissions remove (--original <原话> | --original-file <文件>)  # 只撤 module-crew 写的条目；规则文件清空、钩子改为空操作
```

- `plan`：`0`；不在 module-crew 仓库 `2`。
- `apply`／`remove`：`0` 完成；`3` 原话为空、有文件没被 git 忽略、JSON 读不出、规则文件被别人改得认不出——这些情况什么都不写。钩子装不上不算失败，`0` 并写明原因。
- `verify --record`：`0` 记下；`3` 会话不是登记的在用会话、参数不合法。
- `merge push`：推送前写凭证；钩子拒绝时退出码 `4`，输出钩子的拒绝原因。

## 项目结构

```
module_crew/permissions.py   清单、合并写入、撤销、Codex 规则文本、信任读取、实测清单与记录
module_crew/prepush.py       pre-push 钩子脚本正文（装到 git 公共目录 hooks/pre-push）与凭证读写
module_crew/merge.py         push 前写凭证、结束时标为已用
module_crew/start.py         prepare 跟随写规则
module_crew/probe.py / __main__.py   permissions 子命令；status 显示实测结果
skills/crew-coordinator、skills/crew-dev、codex-skills/crew-dev   开会话后跑实测清单、代开会话里弹窗可能不出现
README.md
tests/test_permissions.py、tests/test_prepush.py
```

## 命令

```bash
python3 -m unittest discover -s tests -v
```

## 代码风格

与现有模块一致：只用标准库；写入前预览、凭用户原话写；module-crew 不发消息、不替用户点弹窗、不改全局配置；给人看的文字用中文、术语表 v1.1 名称。

## 测试策略

- 临时仓库：`settings.local.json` 不存在、已有别的条目、JSON 坏、没被 git 忽略四种情况下 `apply` 的结果；`remove` 只撤自己的条目。
- Codex 规则文本：生成的 `.rules` 能被一个小解析器读出 pattern 与 decision；有 `codex` 命令时测试里跳过真实 execpolicy（只在验收时实跑）。
- 钩子：在临时仓库装上后，模块 worktree 里 `git push` 到本机裸仓库被拒；集成 checkout 无凭证被拒、有凭证放行且凭证标为已用、不能再用、过期凭证被拒、凭证分支不符被拒；没有状态库时放行；`core.hooksPath` 或已有钩子时不装。
- `merge push` 到本机裸仓库：钩子在时照常成功，凭证用后不留。
- `verify --record` 记录与 `status` 显示。
- 现有全量测试照常通过。

## 边界

- **总是**：写之前预览、要用户原话；只追加、可撤销；不可逆操作写 deny／forbidden，不写 ask；推送只经 `merge push`。
- **先问**：往 allow 里加清单外的命令；装钩子时覆盖已有 `pre-push` 或改 `core.hooksPath`；替用户信任 Codex 项目。
- **从不**：改宿主权限模式或全局配置；替用户点权限弹窗；把别的会话转来的话当成 apply 的原话；钩子里放行没有凭证的 agent 推送。

## 验收标准

1. `permissions plan` 列出集成 checkout 与每个模块 worktree 要追加的 allow／deny 条目、是否被 git 忽略、钩子能否装（不能时写原因）、Codex 模块 worktree 的信任状态；不写任何文件。
2. `apply` 后各 `.claude/settings.local.json` 含关键决策 1 的条目、原有键与条目不变；状态库记下每个文件追加了什么与用户原话。
3. 有文件没被 git 忽略或 JSON 读不出：退出码 3，所有文件都不变。
4. Codex 模块 worktree 得到 `.codex/rules/module-crew.rules`，常规命令 `allow`、不可逆命令 `forbidden`，每条带 `match`／`not_match`；项目未受信任时 `plan`／`verify` 明说规则不会生效。
5. 钩子：模块 worktree 推送被拒并说明原因；集成 checkout 无凭证、凭证过期或分支不符被拒；`merge push` 推送成功且凭证不留；没有状态库时放行。
6. `core.hooksPath` 已设或已有 `pre-push`：不装钩子，输出原因，`apply` 仍退出 0。
7. `start prepare` 在已 apply 的项目里新建 worktree 时自动写同一份规则；写失败不阻止开工并在 `status` 标出。
8. `verify` 输出实测清单（四条应放行、一条应拒）；`verify --record` 记下结果，`status` 显示每个会话最近一次实测，没测过写「权限未实测」。
9. `remove` 只撤 module-crew 追加的条目，Codex 规则文件清空、带标记的钩子改为空操作，其他内容不变。
10. README 与三份 skill 写明：代开会话里宿主确认可能不弹，不可逆操作靠 deny 规则与推送守门；开会话后跑实测清单并记录。
11. 实地（验收时，crew-rehearsal，默认权限模式，由别的会话代开的模块会话）：清单四条不弹窗、`git push` 被宿主 deny 拦下；结果用 `verify --record` 记下并附在验收证据里。做不了就写「宿主未实测」与原因。
12. 全量测试通过。
13. （0.5.0）`permissions plan` 预览里按锁文件或清单装的命令（`npm ci`、不带参数的 `npm install`、`pip install -r <文件>` 等）在放行里；加新包的命令（`npm install <包名>`、`pnpm add`、`pip install <包名>` 等）既不在放行也不在禁止里；全局安装（`npm install -g`、`pnpm add -g`、`brew install`）在禁止里。Codex 规则经 `codex execpolicy check` 核对：`npm ci` 为 allow、`npm install x` 无匹配、`npm install -g x` 为 forbidden。

## 未决问题

- spec-guard 命令进不了 allow（路径带版本号）：本版只写明；要不要请 spec-guard 提供不带版本号的稳定入口，留给用户决定是否向 spec-guard 提需求。
- deny 在代开会话里是否生效：文档说 deny 在任何模式下都生效，但 ask 的实测结果和文档也不一致，以验收 11 的实测为准；若 deny 也失效，推送仍由钩子挡，删除类操作写进验收结论交用户决定。

## 文档建议

README 新增「权限预配」一节：`permissions plan → apply → 开会话后 verify → record`、清单内容、钩子与 `--no-verify` 的说明、Codex 要先信任项目；命令表加 `permissions`。
回告：发版后告诉 decision-inbox 插件会话 module-crew 侧的权限预配已就位（它的 join 写入可以引用），随最终验收列出。

## 变更记录

- 2026-10-19：`remove` 与放行凭证由「删除」改为「清空规则／钩子改空操作／凭证标为已用」；记录位置写明为运行配置 `config/main` 的 `permissions` 字段。原因：构建中全量测试 `tests/test_package.py` 的项目约束「module-crew 源码不调用删除」与状态库 config 只认 main 一个键；来源：构建 Task 3、Task 4 时发现，随最终验收交用户复审。
- 2026-10-19：关键决策 1 改为项目内安装依赖放行、全局安装仍禁止（含 Codex 规则），写明「只装 Plan 列出的依赖」不在权限层；加验收 13（0.5.0）。原因：R21「模块打转」MC-1（原先整类禁止 `pip install` 与 DI-1 冲突）；来源：监测会话转达用户决定 58–60，用户 2026-10-19 在本会话确认 6 条假设。
- 2026-10-19：MC-1 改为按锁文件或清单装的放行、加新包不写规则（交宿主默认确认加 skill 先问）、全局安装禁止，取代上一条修订里「项目内安装一律放行」；验收 13 随之改。原因：用户决定 61 要求 MC-1 与 decision-inbox DI-2 对齐（加新包先问）；因代开会话里 ask 规则不弹，用户 2026-10-19 在本会话选方案 C（不写 ask）；来源：监测会话转达决定 61。
