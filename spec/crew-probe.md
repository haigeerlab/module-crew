<!-- spec-guard: review approved c7b1575395cc -->
# Spec: crew-probe

> 能力图模块 `crew-probe`。需求来源：`docs/requirements-record.md` 假设 3～6、第 4 节（分层与依赖）、第 7 节（`status` 随时重建全貌）、B2（开前基线须干净）。
> 假设见下文，用户 2026-10-18 已确认。

## 目标

在动手开工之前、以及任何时候想看全貌时，用一条只读命令回答两个问题：**这个项目现在能不能开并行**（依赖插件、接口版本、仓库前提），
以及**现在并行到哪了**（状态库里的会话与待办，spec-guard 的模块进度）。crew-start 开工前调用它的体检结果；会话中断或压缩后，
`status` 是从文件重建全貌的入口。

使用者是用户（`module-crew status`）和本插件的其他模块（Python 调用 `probe.run()`）。

## 范围

**范围内**

- `module_crew/probe.py`：依赖定位、读接口文件、运行 spec-guard 声明的 `/map --json`、仓库前提检查、汇总状态库。
- 命令 `module-crew status [--json]`。

**范围外**

- 任何写入：不建状态库、不改配置、不写角色标记、不开会话（分别归 crew-store、crew-start）。
- 判断模块能否开工、挑哪几个开（crew-start 读 `startable` 自己判断）。
- 宿主检测、agent-relay 运行时能力的实地探测（见假设 3、5）。

## 假设（用户 2026-10-18 已确认）

1. 依赖从 Claude 的插件安装记录 `~/.claude/plugins/installed_plugins.json` 找：项目级安装优先于用户级；目录 marketplace 读源码目录。思路同 decision-inbox `deps.py`，代码独立实现；测试用环境变量把记录指向夹具。
2. spec-guard 只读 `interface.json`（主版本 1）与其 `mapView` 声明的命令；本机现为 1.0，报「规划层未发版（需要 interface 1.1）」，作为 crew-start 的阻塞项；1.1 字段先用夹具测。
3. agent-relay 只读 `interface.json`，主版本须为 2；运行时能力以主版本为准，不实地探测。
4. 仓库前提：在 git 仓库里、不是裸仓库；git ≥ 2.31；集成基线干净 = 集成分支所在 checkout 的 `git status --porcelain` 为空；集成分支取状态库 config，没设时取当前分支。
5. 宿主不探测，`status` 里写明「第一版只支持 Claude 桌面版」。
6. `status` 只读：依赖体检 + 状态库在用会话与未关事项／请求／等待单数量 + `/map --json` 模块进度摘要；没建库显示「未建库」；`--json`；退出码 0 无阻塞、3 有阻塞、2 参数错。

## 关键决策与取舍（请重点审）

1. **体检结果是一张固定的检查项表，每项三态：`ok`／`blocker`／`warning`，外加原因与怎么办。** 检查项 id 固定（见接口约定），
   crew-start 按 id 取结果，不解析文字。「有没有阻塞」只看 `blocker`；`warning` 只提示（例如没建库、`/map` 报告有模块待审）。
2. **「规划层可用」= spec-guard `interface.json` 版本 ≥ 1.1，且 `/map --json` 顶层有 `startable`。** 两者缺一就是 `blocker`
   （检查项 `spec-guard-planning`），原因写明缺哪一个。spec-guard 规划层的字段名以它发版时的 `interface.json` 与 map-view 契约为准；
   本模块的 1.1 夹具按 `docs/spec-guard-additions.md` 的字段名写，**发版后对照真实输出改夹具**，这一条已列为未决问题。
3. **只运行一个外部命令：spec-guard `mapView.command`**，把 `<project-root>` 换成项目根目录，带超时（10 秒）。
   命令必须是 `python3` 开头、脚本路径在 spec-guard 安装目录之内，否则不运行、判 `blocker`（防止接口文件被篡改后执行任意命令）。
   除此之外只读文件和运行 `git`。
4. **集成基线检查找的是「集成分支被哪个 checkout 检出」**（`git worktree list --porcelain`），在那个 checkout 里看 `git status --porcelain`；
   集成分支没被任何 checkout 检出时判 `blocker`。不 `fetch`、不比远端。
5. **`status` 的退出码只由阻塞项决定**；状态库或 `/map` 读不出来时，对应部分写「读不出」和原因，其余照常输出。

## 接口约定

### 检查项

| id | 内容 | 不满足时 |
|---|---|---|
| `git` | 在 git 仓库、非裸仓库、git ≥ 2.31 | blocker |
| `agent-relay` | 已安装（项目级或用户级），`interface.json` 主版本 2 | blocker |
| `spec-guard` | 已安装，`interface.json` 主版本 1，`mapView` 命令合规且运行成功（退出码 0） | blocker（`/map` 退出码 3「没有能力图」也是 blocker） |
| `spec-guard-planning` | 见关键决策 2 | blocker |
| `baseline` | 集成分支被某个 checkout 检出且工作区干净 | blocker |
| `store` | 状态库已建 | warning（「未建库，crew-start 开工时会建」） |

### Python 接口

```python
from module_crew import probe

report = probe.run(project="/path/to/repo")   # 不写任何文件
report.blocked                                 # 有任一 blocker
report.checks["baseline"]                      # Check(id, state, reason, fix)
report.store                                   # None（未建库）或 {"sessions": [...在用会话], "open": {"item": 2, "request": 0, "ticket": 1}}
report.map                                     # None 或 /map --json 解析后的字典
report.to_json()                               # status --json 的输出
```

「未关」= 记录里 `state` 不是 `closed`（各记录种类的状态字段由后续模块定义；本模块只按这一约定计数，没有 `state` 的记录算未关）。

### 命令行

```bash
bin/module-crew status            # 中文概览：体检表、会话与待办、模块进度摘要、「第一版只支持 Claude 桌面版」
bin/module-crew status --json     # 同样内容的 JSON（schemaVersion 1）
```

退出码：`0` 没有阻塞项；`3` 有阻塞项；`2` 参数错或不在 git 仓库里。

### 依赖定位的环境变量（只给测试与排查用）

- `MODULE_CREW_PLUGINS_FILE`：替代 `~/.claude/plugins/installed_plugins.json`；`known_marketplaces.json` 取同目录。

## 项目结构

```text
module_crew/probe.py            本模块
module_crew/__main__.py         加 status 子命令
tests/fixtures/plugins/         假的安装记录与 spec-guard／agent-relay 安装目录（含 1.0 与 1.1 两种 spec-guard）
tests/test_probe_deps.py        依赖定位与接口版本
tests/test_probe_repo.py        git 与集成基线
tests/test_probe_status.py      汇总与命令行
```

## 命令

```bash
python3 -m unittest discover -s tests -v
```

## 代码风格

沿用前两个模块：代码与注释英文，输出中文；只用标准库；外部命令一律 `subprocess.run([...], capture_output=True, timeout=...)`，不用 shell。

## 测试策略

- 依赖：夹具里放假的 `installed_plugins.json` 与安装目录；假 spec-guard 的 `map_view.py` 只打印固定 JSON，分 1.0（无 `startable`）与 1.1（有）两种。
- 仓库：临时仓库加 worktree，构造「集成分支没被检出」「工作区有未提交改动」「有未跟踪文件」。
- 只读：每个测试前后对比项目目录与状态库目录的文件清单与修改时间。
- 另跑一次**本机真实环境**的冒烟（不入自动测试，结果写进验收记录）：应报 `spec-guard-planning` 为 blocker（本机 spec-guard 0.67.0 是 interface 1.0）。

## 边界

- **始终**：只读；外部命令带超时；命令路径限制在依赖安装目录内。
- **先问**：增加检查项或改检查项 id；运行 `mapView` 以外的依赖命令。
- **绝不**：读 spec-guard 的内部文件（`.agent/state.json`、`tasks/` 等）；写任何文件；`git fetch` 或访问网络。

## 验收标准

1. 安装记录里 agent-relay 有项目级与用户级两条时取项目级；只有别的项目的项目级安装时报「只装在别的项目里」，`agent-relay` 为 blocker。
2. agent-relay `interface.json` 为 2.0 → ok；1.0、3.0、文件缺失、JSON 坏 → blocker，原因各不相同。
3. spec-guard 1.0 夹具：`spec-guard` ok、`spec-guard-planning` blocker，原因含「需要 interface 1.1」；1.1 夹具且 `/map` 有 `startable` → ok；1.1 但 `/map` 没有 `startable` → blocker。
4. `mapView.command` 不以 `python3` 开头，或脚本路径跳出安装目录（`../`、绝对路径）→ 不运行、`spec-guard` 为 blocker；`/map` 超时、退出码 3、输出不是 JSON → blocker，原因各不相同。
5. 不在 git 仓库 → 退出码 2；裸仓库 → `git` blocker。
6. 集成分支（config 设定或当前分支）在 worktree 里检出且干净 → ok；有未提交改动或未跟踪文件 → blocker 并给出文件数；集成分支没被检出 → blocker。
7. 未建库 → `store` warning、`report.store` 为 None，退出码不受影响；已建库 → 在用会话列表与三类未关数量正确（`state` 为 `closed` 的不计）。
8. `status` 输出含体检表、会话与待办、模块进度（完成数／总数、进行中模块）与「第一版只支持 Claude 桌面版」；`--json` 可被 `json.loads`，`schemaVersion` 为 1；有 blocker 时退出码 3，否则 0。
9. 运行前后项目目录与状态库目录的文件清单和修改时间完全相同。
10. 本机真实环境冒烟：`status` 报 `spec-guard-planning` 为 blocker（spec-guard 0.67.0，interface 1.0），`agent-relay` 为 ok（0.6.1，interface 2.0）。

## 未决问题

- spec-guard 规划层发版后，`moduleConcurrency` 开关状态与 `startable` 的确切字段以它的 `interface.json`／map-view 契约为准；本模块的 1.1 夹具届时对照改一次（不阻塞本模块验收，阻塞第 7 关）。
  需要的话我可以现在就向 spec-guard 负责人确认字段名。

## 文档建议

README（crew-start 之后补）里写「先跑 `module-crew status`」以及每个 blocker 的处理办法；本模块输出的「怎么办」一栏就是这份内容的来源。
