# Spec: crew-codex-host

<!-- spec-guard: review approved ff38203b213d -->

> 能力图模块 `crew-codex-host`（第二版）。需求来源：`docs/requirements-record.md` B7（第二版 Codex 前置核对清单：`.git` 沙箱提权最关键、重启不加载、
> 身份丢失、只能提供 skill、钩子信任、压缩后重放；协调会话不放 Codex）与第 13 节。宿主事实取自 decision-inbox `docs/host-differences.md`
> （H1–H5、H7、H8、H10–H12）。用户 2026-10-18 在本会话确认 14 条假设（第 10 条选 a），并批准插入能力图。

## 目标

让一个批次里的模块会话可以开在 Codex 桌面版里（协调会话仍是 Claude 桌面版）：开工说明告诉 Codex 会话它要额外做的事，
一条只读预检命令在开工前查出 Codex 特有的障碍（`.git` 写不了、命令跑不了），协调会话知道 Codex 会话怎么叫醒、掉了身份怎么办、
提权弹窗要用户去点。Claude 模块会话的行为一律不变。

## 范围

- `.codex-plugin/plugin.json`：只提供 skill（Codex 插件只能提供 skill，H7），skill 目录 `codex-skills/`，内含 Codex 版 `crew-dev`。
- `start prepare --host codex`：本次开的模块都登记为 Codex 会话；开工说明加 Codex 段。要混用就按宿主分两次 prepare。
- 状态库会话登记的 `host` 增加取值 `codex-desktop`。
- 新命令 `module-crew host-check`（只读）：在模块 worktree 里运行，报告这个会话能否完成 module-crew 的工作。
- `resume-kit` 对 Codex 会话给 Codex 版的恢复说明。
- `sessions` 输出与只读出口增加 `host` 字段（只增不改）。
- 协调会话 skill、README 补 Codex 模块会话的做法；`status` 去掉「第一版只支持 Claude 桌面版」的提示。

不做：Codex 协调会话；Codex 命令行版作模块会话；跨机器；用 agent-relay 跨宿主建会话（开 Codex 会话由用户手动做）；Codex 钩子；
在模块 worktree 里写 AGENTS.md 或任何规则文件。

## 假设（用户 2026-10-18 已确认）

1. 只做 Codex 模块会话，协调会话只能是 Claude 桌面版；一个批次可以混用两种模块会话。
2. 只支持 Codex 桌面版（ChatGPT 应用里的 Codex），不支持命令行版、不跨机器。
3. 加 `.codex-plugin/plugin.json`，只提供 Codex 版 `crew-dev` skill；`module-crew` 不在 Codex 的 PATH 上，开工说明里写插件目录下的绝对路径。
4. `start prepare --host codex`（可按宿主分次）；会话登记 host 增加 `codex-desktop`；开工说明加 Codex 段。
5. 开 Codex 会话由用户手动做：新建任务、工作目录选模块 worktree、贴开工说明。
6. `.git` 沙箱（H11）：开工说明写明第一次提交前由用户在 Codex 会话里批准提权，能选「本会话一直允许」就选；加只读预检 `module-crew host-check`。
7. 权限宽窄按 Codex 沙箱档位比较（read-only < workspace-write < 完全放开）；module-crew 看不到档位，由协调会话请用户确认。
8. Codex 会话用 agent-relay 注册时带 `host:{app:"codex", sessionId}`；丢身份（H3）用原名重新注册，属于正常恢复、不算接管。
9. 叫醒交给 agent-relay；应用重启后未加载（H2）时如实显示 agent-relay 的状态，协调会话提醒用户点开。
10. Codex 钩子默认不运行（H8）：恢复提示写进开工说明与恢复说明（选 a），不在 worktree 落规则文件。
11. 用户批准只在协调会话给；Codex 模块会话只认协调会话转来的【用户答复】；提权弹窗只能用户在 Codex 会话亲手点，协调会话把它作为等待用户的事项交出去。
12. 验收：夹具测试；实地验证放进演练，开一个 Codex 模块会话从开工走到合并收尾，统计提权弹窗次数，实地验证经用户同意才开始。
13. Claude 模块会话行为不变；冻结的 0.1.1 不受影响，在 `main` 开发，完成后发新版本（如 0.2.0）。
14. 契约不改。

## 关键决策与取舍（请重点审）

1. **宿主按批次指定，不按模块逐个指定**：`start prepare a b --host codex`，一次 prepare 的模块用同一个宿主；要混用就分两次 prepare（名额与校验照常累计）。
   比在一条命令里给每个模块配宿主简单，开工批准事项也各记一条，用户看得清哪几个是 Codex。默认 `--host claude`，不带参数时行为与现在相同。
2. **Codex 版 skill 单独一份**（`codex-skills/crew-dev/SKILL.md`），不和 Claude 版共用一个文件加条件分支：两个宿主的叫醒、身份、提权、命令路径都不同，
   分开写模型读得清；共同的规则（只认协调会话答复、被挡住必须报、不改公共文件、获批后不自己勾末项）两份都写，`test_skills` 断言两份都含这些关键句。
3. **`host-check` 只读、不写状态库**：在当前 worktree 里依次查——
   - 这个 checkout 是登记过的在用模块会话（角色标记或会话登记）；
   - `module-crew` 自己能跑、版本与状态库里协调会话那份一致（取 `interface.json` 的 `version`）；
   - 能写 git 目录：在 `git rev-parse --git-dir` 下创建再删除一个临时文件（这是唯一的写动作，只碰 git 目录里一个自建的临时文件，不碰任何仓库内容）；
   - 能读状态库。

   每项给「通过／不通过＋原因＋怎么办」，退出码 0 全通过、3 有不通过、2 不在任何 module-crew 仓库里。agent-relay 是会话里的工具，命令行查不到，输出里提醒会话自己用 `bridge_agents` 确认身份。
4. **开工说明的 Codex 段固定文字**，内容依次是：先跑 `host-check`（绝对路径）；第一次提交会弹提权，请用户在本会话批准（能选一直允许就选）；
   注册邮箱名时带 `host:{app:"codex", sessionId: <CODEX_THREAD_ID>}`；读不到自己的消息就用原名重新注册（不是接管）；
   没有钩子，压缩或中断后先跑 `module-crew status` 再动手；加载 Codex 版 `crew-dev` skill。
5. **`resume-kit` 按会话登记的 host 出说明**：Codex 会话的恢复说明不含 Claude 的钩子提示，含上面第 4 条的身份与 `status` 两句。

## 接口约定

```bash
bin/module-crew start prepare <模块>… (--original <原话> | --original-file <文件>) [--host claude|codex] [--project-short <简称>] [--max N] [--json]
bin/module-crew host-check [--json]
```

- `start prepare --host codex`：输出与现在相同，每个模块多一行「宿主：Codex 桌面版（用户手动在 Codex 里开任务，工作目录选这个 worktree）」；`--host` 取值以外退出码 2。
- 会话登记：`{"role": "dev", "host": "codex-desktop", ...}`；协调会话仍只能是 `claude-desktop`（store 校验）。
- `host-check --json`：`{"checks": [{"id", "ok", "reason", "fix"}], "module": "<id>|null", "host": "codex-desktop|claude-desktop|null"}`。
- `sessions --json` 每行增加 `"host"`；`schemaVersion` 仍为 1（只增不改，crew-hub-bridge 契约允许）。

## 项目结构

```
.codex-plugin/plugin.json          新增：name、version（与 .claude-plugin 一致）、description、skills: ./codex-skills/
codex-skills/crew-dev/SKILL.md     新增：Codex 版模块会话 skill
module_crew/hostcheck.py           新增：host-check
module_crew/start.py               --host、开工说明 Codex 段
module_crew/store.py               HOSTS 增加 codex-desktop（协调会话仍只许 claude-desktop）
module_crew/failure.py             resume-kit 按 host 出说明；sessions 增加 host
module_crew/__main__.py            host-check 子命令、prepare --host
skills/crew-coordinator/SKILL.md   Codex 模块会话一节
tests/test_codex_host.py           新增
```

## 命令

```bash
python3 -m unittest discover -s tests -v
```

## 代码风格

与现有模块一致：只用标准库；命令判断、会话照做；文字给人看的部分用中文。

## 测试策略

- 夹具仓库里 `start prepare b --host codex`，检查登记、开工说明；`--host` 非法值；不带 `--host` 与现在逐字相同。
- `host-check`：在登记的 Codex worktree、未登记目录、仓库外各跑一次；把 git 目录设成只读（`chmod`）模拟沙箱写不了，断言该项不通过且原因含提权；测试结束恢复权限。
- `resume-kit`、`sessions --json` 对 Codex 会话的输出。
- `test_skills`：两份 crew-dev 都含共同关键句；Codex 版含提权、重新注册、`host-check`；`.codex-plugin/plugin.json` 与 `.claude-plugin/plugin.json` 版本一致。

## 边界

- **总是**：Claude 模块会话的开工说明、登记、恢复说明不变（逐字比较）。
- **先问**：实地开 Codex 会话做验证（演练里、经用户同意）。
- **从不**：替用户点提权；在 worktree 里写规则文件；把 Codex 作协调会话；`host-check` 写仓库内容或状态库。

## 验收标准

1. `start prepare b --host codex --original "开 b"`：b 登记 `host: codex-desktop`；开工说明含 `host-check` 绝对路径、提权说明、`host:{app:"codex"` 注册写法、重新注册、先跑 `module-crew status`、Codex 版 crew-dev；输出含「宿主：Codex 桌面版」。
2. 不带 `--host`（或 `--host claude`）时，登记与开工说明与修订前逐字相同；`--host foo` 退出码 2、什么都不写。
3. 同一批先 `prepare b --host codex`、再 `prepare c`：b 为 Codex、c 为 Claude，名额累计正确，两条开工批准事项。
4. 协调会话登记 `host: codex-desktop` 时 store 校验拒绝。
5. `host-check` 在登记的 Codex worktree：全部通过、退出码 0、`--json` 可解析；git 目录只读时「能写 git 目录」不通过、原因含提权、退出码 3；未登记的目录退出码 3；仓库外退出码 2；运行前后状态库与仓库内容不变。
6. `resume-kit b`（Codex）：不含 Claude 钩子提示，含重新注册与先跑 `status`；Claude 会话的恢复说明不变。
7. `sessions --json` 每行有 `host`，schemaVersion 仍为 1。
8. `.codex-plugin/plugin.json` 存在、版本与 `.claude-plugin/plugin.json` 一致、skills 指向 `./codex-skills/`；Codex 版 crew-dev 含共同关键句与 Codex 特有三句。
9. 协调会话 skill 有「Codex 模块会话」一节：用户手动开任务、`host-check`、提权弹窗作为等待用户的事项、叫醒交给 agent-relay、未加载提醒点开、丢身份让它重新注册、按沙箱档位核对权限。
10. `status` 不再显示「第一版只支持 Claude 桌面版」；全量测试通过。

## 未决问题

- Codex 桌面版提权弹窗有没有「本会话一直允许」这一档，以及 worktree 的 git 目录在仓库主 `.git` 下时提权是否一次就够：要在演练里实测，Spec 按「每次提交都可能要批」写说明。

## 文档建议

README「前提」表把宿主改为「协调会话 Claude 桌面版；模块会话 Claude 或 Codex 桌面版」，并加「Codex 模块会话」一节（安装 Codex 插件、开任务、提权）。
