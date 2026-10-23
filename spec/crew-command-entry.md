<!-- spec-guard: review approved b035f6eb5a04 -->

# Spec: crew-command-entry

> 能力图模块 `crew-command-entry`（第七版第 1 个）。需求来源：`docs/requirements-record.md` 第 16 节第 10、11 条（用户 2026-10-22 选 A「固定启动脚本」、同意修第 11 项）。
> 依赖 `crew-codex-host`（Codex 开工说明）、`crew-host-permissions`（Codex 权限规则）、`crew-recovery-hooks`（Claude 会话的命令入口由钩子注入，0.11.1）。标「新」的是写 Spec 时补的实现取舍，请重点审。

## 目标

Codex 会话没有钩子，开工说明里写死的 `<插件目录>/bin/module-crew` 带版本号，升级后不会换，会一直跑旧版本（O8 在 Codex 上的同一个问题）。
改成给 Codex 一个不带版本号、永远转到当前安装那份 module-crew 的固定入口。
另外，`bin/module-crew` 用 `python3 -m module_crew` 启动时当前目录排在最前，在 module-crew 源码仓库里运行时加载的是仓库自己的代码而不是这份插件的代码，一并修掉。

## 范围

**范围内**

- 固定启动脚本 `<git公共目录>/module-crew/bin/module-crew`：每次运行读 Claude 的插件安装记录，找到当前装的 module-crew，转给它的 `bin/module-crew` 执行。
- `start prepare`、`coordinator up` 写入（或更新）这个脚本。
- Codex 开工说明、Codex 权限规则、Codex 版 crew-dev skill 改用它。
- `bin/module-crew` 改为先把插件目录排在模块搜索路径最前面再启动。

**范围外**

- ~~Claude 会话：照旧用钩子注入的命令入口（crew-recovery-hooks 决策 7），开工说明与 Claude 权限规则不改。~~（2026-10-23 起改入范围，见关键决策 6）
- 这一版之前已经开工的 Codex 会话：它们记着的旧路径不会自己换，由模块协调转告一次（README 写明）；这一版不做自动通知。
- Codex 自己安装 module-crew（现在 Codex 会话用的是 Claude 装的那份，不变）。

## 假设

1. Codex 会话在默认沙箱里能读 `~/.claude/plugins/` 下的安装记录、能执行 `.git` 目录下的脚本（只读执行，不写 `.git`）；第一次实测时核对，不通就停下交用户决定。
2. 安装记录与目录型市场的定位规则沿用 `probe.find_plugin`：项目级安装优先于用户级；目录型市场取它登记的源目录（`known_marketplaces.json`）。
3. 机器上有 `python3`（module-crew 本来就要求）。

## 关键决策与取舍（请重点审）

1. **（新）启动脚本是一份独立的 Python 文件，不依赖 module-crew 包**：它要先找到 module-crew 在哪，所以不能 import module-crew。内容来自包里的模板 `module_crew/launcher.py`
   （只用标准库），原样写到状态库目录的 `bin/module-crew`，首行 `#!/usr/bin/env python3`，权限 755。定位逻辑与 `probe.find_plugin` 各有一份，由一条测试保证两边对同样的安装记录选出同一个目录。
2. **找不到就明说，不猜**：安装记录读不出、格式不对、没装 module-crew、装的目录里没有 `bin/module-crew` 时，标准错误输出一句中文原因，退出码 2；不退回任何写死的旧路径。
   找到了就 `exec` 那份 `bin/module-crew`，参数原样传，退出码原样返回。环境变量 `MODULE_CREW_PLUGINS_FILE` 照旧可以指定安装记录（测试用）。
3. **什么时候写**：`start prepare` 与 `coordinator up` 每次运行时比对，内容不同（第一次、或新版本改了模板）才原子替换写入，相同就不动。状态库「不删除」的约束照旧：只写不删。
4. **Codex 那边全部改指它**：Codex 开工说明里的命令路径、`host-check`、`status` 三处，Codex 权限规则的放行前缀，Codex 版 crew-dev skill 的说明，都改为这个固定路径。
   ~~Claude 会话不改。~~（2026-10-23 起 Claude 会话也改，见决策 6）`permissions apply` 重写 Codex 规则文件时自然换成新路径。
5. **（新）`bin/module-crew` 的修法**：改为 `python3 -c` 一段很短的引导：把插件目录插到 `sys.path` 最前面、把 `sys.argv[0]` 设为 `module-crew`，再用 `runpy` 以 `__main__` 运行 `module_crew` 包。
   当前目录仍在搜索路径里（排在插件目录之后），其他行为不变。不改成直接运行 `module_crew/__main__.py`：那样包目录会排在最前，包里的文件名可能盖过标准库。
6. **Claude 会话也改用固定入口**（2026-10-23 新增，0.12.1）：
   - Claude 权限规则的放行条目由 `Bash(<插件目录>/bin/module-crew *)` 改为 `Bash(<固定入口> *)`；`permissions apply` 写规则前先写（或更新）固定入口，输出多一行同决策 3 的「固定入口：<路径>（已写入／没有变化）」。
     `permissions verify` 实测清单里的 `module-crew status` 也写固定入口。已写进规则文件的旧条目不动（`remove` 照旧按记录撤）。
   - SessionStart 注入的命令入口（crew-recovery-hooks 决策 7）改为固定入口：状态库里已有固定入口时写「module-crew 命令入口：`<固定入口>`（固定入口，转到本机当前安装的 module-crew；本次钩子来自版本 <版本>）」；
     还没有时（这一版之前开工、之后没跑过 `start prepare`／`coordinator up`／`permissions apply`）照旧写本次运行的插件目录下的 `bin/module-crew`，并提示跑一次 `permissions apply` 或 `coordinator up` 写出固定入口。钩子只读不写，也不 import `launcher`（钩子不 import `subprocess` 的约束不变），路径按决策 1 的位置自己拼。
   - 自检（crew-probe 决策 6）判断 Claude 规则是否过期，改为看有没有放行固定入口。
   - 这样以后升级插件不用再跑 `permissions apply`；改成这一版后，已写过规则的 checkout 要凭用户原话再跑最后一次。
   - 取舍：固定入口按安装记录转发，Claude 会话跑的是「装着的那份」而不是「宿主加载钩子的那份」；升级后没重开的会话会直接跑到新版，这和 Codex 会话一样，也正是重开会话想要的结果。

## 接口约定

- 新文件：`<git公共目录>/module-crew/bin/module-crew`（可执行，不进事件日志）。
- 启动脚本退出码：成功时等于转给的那条命令的退出码；找不到 module-crew 时 `2`。
- `start prepare`、`coordinator up` 的输出多一行「Codex 会话的固定入口：<路径>（已写入／没有变化）」。

## 项目结构

```text
module_crew/launcher.py       新：启动脚本模板（独立、只用标准库）与写入函数
module_crew/start.py          prepare 写启动脚本；codex_lines 改用固定入口
module_crew/coordinator.py    up 写启动脚本
module_crew/permissions.py    Codex 规则的放行前缀改用固定入口
bin/module-crew               引导改为插件目录排最前
codex-skills/crew-dev/SKILL.md
tests/test_command_entry_codex.py
```

## 命令

```bash
python3 -m unittest discover -s tests
PYTHONPATH=tests python3 -m unittest test_command_entry_codex
```

## 代码风格

沿用现有模块：代码与注释英文，输出中文；只用标准库；git 带超时、不经 shell。

## 测试策略

- 写入：`start prepare` 后脚本存在、可执行、内容等于模板；再跑一次修改时间不变；模板变了再跑时被替换。
- 转发：假安装记录指向假插件目录（`bin/module-crew` 是打印参数与退出码的小脚本）→ 参数原样、退出码原样；项目级优先于用户级；目录型市场取源目录。
- 找不到：记录缺失、JSON 坏、没装、目录里没有 `bin/module-crew` 各一次 → 退出码 2、中文原因。
- 一致：同样的几组安装记录，启动脚本与 `probe.find_plugin` 选出同一个目录。
- Codex：Codex 开工说明与 Codex 规则里是固定入口，不含插件目录路径；Claude 开工说明不变。
- 源码仓库：在一个放了假 `module_crew` 包的目录里运行 `bin/module-crew status`，跑的是插件自己的代码。
- 回归：全量测试通过。

## 边界

- **始终**：找不到就报错退出，不退回写死的路径；只写不删。
- **先问**：让启动脚本在找不到时退回某个版本；改 Claude 会话的入口做法；给已开工的 Codex 会话自动发换入口的通知。
- **绝不**：启动脚本里写死带版本号的路径；启动脚本 import module-crew 包；删除状态库里的文件。

## 验收标准

1. `start prepare` 与 `coordinator up` 后，`<git公共目录>/module-crew/bin/module-crew` 存在、可执行、内容等于模板；内容相同时再跑不重写，模板变了才替换；输出写明已写入或没有变化。
2. 启动脚本按安装记录转给当前装的 module-crew：参数与退出码原样；项目级优先于用户级；目录型市场取登记的源目录；切换安装记录指向另一个版本后，同一个启动脚本跑的就是那个版本。
3. 安装记录缺失、读不出、没装 module-crew、装的目录里没有 `bin/module-crew`：退出码 2，标准错误输出中文原因。
4. 同样的安装记录，启动脚本与 `probe.find_plugin` 选出同一个目录。
5. Codex 开工说明的三处命令、Codex 权限规则的放行前缀、Codex 版 crew-dev skill 都写固定入口，不含插件目录的路径；Claude 开工说明~~与 Claude 权限规则~~不变（Claude 权限规则见验收 8）。
6. 在放了假 `module_crew` 包的目录里运行 `bin/module-crew`，跑的是插件自己的代码；`--help` 等输出里的程序名是 `module-crew`。
7. 全量测试通过；本机实测：在一个开过工的临时仓库里运行启动脚本 `status`，报的版本等于本机安装的版本。
8. （2026-10-23）`permissions apply` 写出固定入口，Claude 规则的放行条目是 `Bash(<固定入口> *)`，不含插件目录路径；`permissions verify` 清单里的 `module-crew status` 是固定入口；`status` 对放行了固定入口的规则不报过期，只放行旧插件路径的照旧报。
9. （2026-10-23）SessionStart 注入：状态库有固定入口时命令入口是它、附本次钩子的版本；没有时是本次插件目录下的 `bin/module-crew` 并提示怎样写出固定入口；`hooks.py` 仍不 import `subprocess`。

## 未决问题

- 假设 1（Codex 沙箱能读安装记录、能执行 `.git` 下的脚本）要等第一次在 Codex 会话里实测才能确认；本机现在没有 Codex 模块会话在跑，这一版先用测试与本机实测，Codex 实测记为「未验证」。

## 文档建议

README「Codex 模块会话」一节改写命令入口：开工说明给的是状态库里的固定入口，升级后不用换；这一版之前开工的 Codex 会话要由模块协调转告一次新入口。CHANGELOG 随发版写。

## 变更记录

- 2026-10-23：新增关键决策 6 与验收 8、9，改范围外第一条、决策 4 与验收 5：Claude 权限规则放行与钩子注入的命令入口都改用状态库里的固定入口；发热修 0.12.1。原因：放行条目带插件版本号，0.11.1 起每次升级都要凭用户原话重跑 `permissions apply`，否则每条命令弹权限框（第 4 次，spec-guard 负责人在 sg-coord 实测 0.12.0 报告）；来源：用户 2026-10-23 在本会话批准发 0.12.1，本修订待复审。
