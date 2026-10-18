<!-- spec-guard: review approved 2c5fd3b1032f -->
# Spec: crew-start

> 能力图模块 `crew-start`。需求来源：`docs/requirements-record.md` B2（开工）、B1（协调会话放 Claude 桌面版）、A5（就绪与排序）、假设 7（上限默认 3）。
> 依赖 spec-guard 0.68.0 规划层（`/map --json` 的 `startable` 等字段已于 2026-10-18 定稿，未发版）。假设见下文，用户 2026-10-18 已确认。

## 目标

在扩张点（≥2 个模块可同时开工）上，让协调会话用两步把几个模块会话开起来：先算出「可以开哪几个」交用户一次决定，用户答应后由命令把
worktree、会话登记、开工说明一次准备好，协调会话再用桌面版的开会话工具把它们开起来。开出来的模块会话先写 Spec 与 Plan 交审，收到开工通知才构建。

## 范围

**范围内**

- `module_crew/start.py` 与命令 `module-crew start plan`、`module-crew start prepare`。
- 运行配置（`config/main`）的字段：`projectShort`、`integrationBranch`、`maxModules`、`crewDir`。
- 开工说明正文的生成；开工批准事项（`item`，`kind: "start"`）。
- `skills/crew-coordinator/SKILL.md` 增加「开工」一节。

**范围外**

- 打开会话本身（协调会话调用桌面版工具）；邮箱注册（模块会话按开工说明自己注册）。
- Spec／Plan 的批量审批与开工类【协调通知】（crew-review-batch）；冲突裁决（crew-review-batch）。
- 写 spec-guard 角色标记：等 spec-guard 的 `checkoutRole` 入口定稿后另行补上（见未决问题）。

## 假设（用户 2026-10-18 已确认）

1. 开会话由协调会话用桌面版工具做（同时打开「做完一轮叫醒我」），Python 只做准备；第一版只支持 Claude 桌面版。
2. 两个命令：`start plan` 只读（先跑 probe，有阻塞就报；否则按 Build order 从 `startable.modules` 取前 N 个，N = 上限减在用模块会话数，给出提议）；
   `start prepare <模块…> --original <原话>` 在用户答应后执行：建库（如未建）、写运行配置、建 worktree、登记会话、生成开工说明、把原话记为开工批准事项。
3. 分支名 = 模块 id，从本地集成分支切；worktree 放 `<仓库所在目录>/<仓库名>-crew/<模块 id>`。
4. 开工说明只让模块会话写 Spec 与 Plan 并发【交审】，收到开工类【协调通知】才构建。
5. 开工说明只给任务、接口、全局约束。
6. 角色标记等 spec-guard `checkoutRole`；之前只在状态库登记角色并报告「角色标记待 spec-guard 0.68.0」。
7. 模块会话权限模式不高于协调会话：写进协调会话 skill，命令不管。
8. `startable.modules` 照单全收；冲突处理归 crew-review-batch。
9. probe 有任一阻塞项时 `prepare` 拒绝、什么都不写；0.68.0 发版前只用夹具测，第 7 关用真实版本。

## 关键决策与取舍（请重点审）

1. **`prepare` 先全部校验、再逐个模块落地，每个模块一个事务；中途失败就停，已完成的保留，可以重跑。**
   校验项：probe 无阻塞；每个模块都在 `startable.modules` 里；没有在用的同名模块会话；worktree 目录与同名分支都不存在；数量不超过空位。
   落地顺序（每个模块）：`git worktree add -b <模块 id> <路径> <集成分支>` → 状态库事务（登记会话、写开工说明正文）。
   `git worktree add` 是状态库之外的副作用，没法和事务绑在一起；所以失败时**不删已建的 worktree**（遵守不删除原则），
   重跑时已登记的模块会被「已有在用会话」挡住、跳过；只建了 worktree 没登记的，会被「目录已存在」挡住，输出里写明怎么处理（交用户决定）。
2. **开工批准用一条已答的事项留证**：`item`，`kind: "start"`，`state: "closed"`，`closedReason: "answered"`，记下用户原话、模块清单与时间；
   开工说明里引用这个编号。以后 crew-review-batch 的开工类【协调通知】引用的是批量审批的事项编号，不是这一条（这一条只批准「开会话写 Spec」）。
3. **协调会话自己的登记也由 `prepare` 补上**：状态库里没有在用的 `coordinator` 时登记 `<项目简称>-coord`。crew-onboarding 的收件核对依赖它。
4. **运行配置第一次 `prepare` 时写定**：`projectShort` 必须由参数给出（小写字母、数字、连字符，2～20 位），之后不可再改（改名会让邮箱名对不上）；
   `integrationBranch` 取当前分支；`maxModules` 默认 3，可用 `--max` 改；`crewDir` 按假设 3 算出。后续 `prepare` 读配置，不再接受这几个参数。
5. **开工说明正文是状态库里的不可变正文**（crew-store 的 `body`）；`prepare` 输出每个模块的 worktree 路径、邮箱名、正文路径，协调会话把正文原样作为新会话的第一条消息。

## 接口约定

### 命令

```bash
bin/module-crew start plan [--json]
bin/module-crew start prepare <模块 id>… (--original <原话> | --original-file <文件>) [--project-short <简称>] [--max <N>] [--json]
```

- `start plan` 输出：空位数、提议开的模块（按 Build order，最多空位数个）及其职责、`conflicts`（如有，原样列出）、阻塞项（如有）。退出码 `0` 有可开的模块；`3` 有阻塞或没有可开的；`2` 参数错。
- `start prepare` 输出：每个模块一段（worktree、分支、邮箱名、开工说明正文路径）、批准事项编号、「角色标记待 spec-guard 0.68.0」提示。
  退出码 `0` 全部完成；`3` 校验不过，什么都没写；`4` 中途失败，已完成的模块列出，失败原因写明；`2` 参数错。

### 开工说明正文（模板）

```text
你是 module-crew 的模块会话，负责模块 <id>：<职责>。
先加载 crew-dev skill，照它的规则做；规则不要抄进这个 worktree 的 CLAUDE.md。

工作目录：<worktree 路径>（分支 <id>，从集成分支 <集成分支> 切出）
邮箱名：<项目简称>-<id>，用 agent-relay bridge_register 注册，wake: "auto"
协调会话：<项目简称>-coord（你只和它说话）
开会话依据：用户批准事项 #<编号>

这一步只做：用 /spec 写 spec/<id>.md 与 tasks/<id>/plan.md、todo.md，写好后给协调会话发【交审】（节点 Spec、Plan 各一条，或接口提案）。
收到开工类【协调通知】之前不要开始构建。

接口：<所依赖模块的 Spec 路径，逐行；没有写「无」>
全局约束：不改公共文件（要改发【公共变更请求】）；被挡住发【等待其他会话】；发出前 module-crew protocol check。
```

## 项目结构

```text
module_crew/start.py
module_crew/__main__.py          加 start plan、start prepare
skills/crew-coordinator/SKILL.md 加「开工」一节
tests/test_start_plan.py
tests/test_start_prepare.py
```

## 命令

```bash
python3 -m unittest discover -s tests -v
```

## 代码风格

沿用前几个模块；probe 结果一律走 `probe.run()`，不另读 spec-guard；git 调用带超时、不用 shell。

## 测试策略

- 用 crew-probe 的插件夹具（spec-guard 1.1、`moduleConcurrency: on`、`startable`），每个测试建临时仓库。
- `prepare` 的失败中途：用一个已存在的目录挡住第二个模块，验证第一个模块完成、第二个未登记、退出码 4。
- 开工说明正文与模板逐行比对；正文能从状态库按编号读回且指纹正确。

## 边界

- **始终**：先校验后落地；用户原话原样记录；只开 `startable.modules` 里的模块。
- **先问**：超过上限开模块；删除或重建已有 worktree；改 `projectShort`。
- **绝不**：自己打开会话或注册邮箱；读 spec-guard 内部文件；推送或改远端。

## 验收标准

1. 夹具 `startable.modules = [b, c, d]`、上限 3、无在用模块会话：`start plan` 提议 b、c、d；已有 1 个在用模块会话时只提议 b、c；`--json` 可解析。
2. probe 有阻塞（基线不干净、规划层不可用）：`start plan` 退出码 3 并列出阻塞；`start prepare` 退出码 3，仓库与状态库（含未建库的情况）都不变。
3. `prepare b c --original "开这两个" --project-short shop`：未建库时建库；写运行配置；建出 `<父目录>/<仓库名>-crew/b`、`…/c` 两个 worktree，分支 b、c 从集成分支切出；
   登记 `shop-coord`（coordinator）与 `shop-b`、`shop-c`（dev，worktree 为绝对路径）；记一条 `kind: "start"` 的已答事项含原话与模块清单；每个模块一份开工说明正文。
4. 校验不过的各种情况——模块不在 `startable.modules`、超过空位、已有在用会话、目录或分支已存在、`projectShort` 不合法或与已有配置不同——退出码 3，什么都不写（git 与状态库都不变）。
5. 第二个模块的目录被预先占用：第一个模块完成、第二个未登记也未建分支，退出码 4，输出写明已完成的模块与原因；去掉占用后重跑第二个模块成功，第一个被跳过而不是重复建。
6. 开工说明正文与模板一致：含模块 id 与职责、worktree 路径、邮箱名、协调会话名、批准事项编号、所依赖模块的 Spec 路径（依赖取 `/map --json` 的模块依赖）、只写 Spec 与 Plan 的要求。
7. 第二次 `prepare` 不带 `--project-short` 也能用配置；带了不同的值被拒。
8. `crew-coordinator` skill 有「开工」一节：`start plan` → 问用户一次 → `start prepare` → 用桌面版开会话工具在 worktree 里开会话、第一条消息用开工说明正文、打开完成提醒 → 检查权限模式不高于本会话。

## 未决问题

- spec-guard 的 `checkoutRole` 入口（写角色标记）还没设计。定稿后在本模块补「`prepare` 后调用 `checkoutRole`」与对应验收，按变更记录复审。
- `/map --json` 里每个模块的依赖字段名以 spec-guard 0.68.0 实际输出为准（现行 0.67.0 为 `dependsOn`，验收 6 按它写）。

## 文档建议

README 的「一次完整流程」从这里开始写：`status` → `start plan` → 问用户 → `start prepare` → 开会话。crew-review-batch 完成后补全。

## 变更记录

- 2026-10-18：空位计算与名额检查不再数挂起的模块会话（会话登记 `suspended` 非空）；运行配置 `mode` 为 `serial` 时，`start plan` 把「已退回串行」列为阻塞、`start prepare` 退出码 3 拒绝开新模块（沿用原有退出码含义）。原因：crew-failure 要求挂起不占名额、用户可随时退回串行；来源：`spec/crew-failure.md`（用户 2026-10-18 批准），随 crew-failure 最终验收复审。
