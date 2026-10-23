# Spec: crew-reopen-module

> 能力图模块 `crew-reopen-module`（第九版）。需求来源：接缝 S18——LIVE-SAAS 后台要修订两个已完成模块（tenant-onboarding、site-operations）。
> spec-guard 的口径（sg-coord，账本 DHW69MR）：修订已完成模块按 workflow-checkpoints.md「返工与小模块」原地重开——在原 `tasks/<id>/todo.md` 追加未勾任务、`plan.md` 补一节，模块回到进行中；
> 范围内返工不改 Plan 批准，超出原范围把 Plan 改 pending 重新交审；`/map` 把它算 `in_progress`，不进 `startable`。module-crew 只认 `/map --json` 现有字段，不要 spec-guard 新字段。
> 依赖 `crew-start`（prepare、开工说明）、`crew-light-task`（`task` 角色与名额只数 `dev`）、`crew-session-handover`（会话登记、按会话编号认身份）。标「新」的是写 Spec 时补的取舍，请重点审。

## 目标

用户点名一个已经做完、又被 spec-guard 原地重开的模块时，模块协调能用现有的 `start prepare` 给它开一个新的模块会话：
worktree 从集成分支最新处开、登记一条新的会话、用一个没退役过的新邮箱名，开工说明写明「这是重开修订，只做 todo 新加的未勾项」。
重开后的模块走和新模块一样的交审、合并、收回流程，旧一轮的批准与合并记录不干扰新一轮。

## 范围

**范围内**

1. `start prepare <模块>` 接受「可重开」的模块（判据见决策 1），不新增命令。
2. 分支处理：旧模块分支是集成分支的祖先就快进到集成分支顶端再开 worktree；不是祖先就拒绝、交用户决定；没有旧分支就照常从集成分支切。
3. 会话登记：新开一条 `dev` 登记，邮箱名 `<简称>-<模块 id>-r<轮次>`；登记上记下这一轮从哪个事项号起算。
4. 新一轮只看新一轮的记录：按模块查合并批准、交审、批准的地方，对重开的模块只算本轮起算号之后的事项（决策 4）。
5. 开工说明加「重开修订」一段（决策 5）。
6. `start plan`：可重开的模块不提议，但在「不能开的原因」里写「已重开，要用户点名」。
7. `crew-coordinator` skill（Claude 与 Codex 两份）的「开工」一节加重开的做法；`crew-dev` skill 加一句「重开修订只做新加的未勾项」。

**范围外**

- 在 spec-guard 里重开模块（追加 todo、补 plan 一节、改 Plan 评审状态）：由用户按 spec-guard 的做法先做好，module-crew 只读结果。
- 退役旧邮箱名：仍由用户在 agent-relay 里做（与 `merge cleanup` 现有提示相同）。
- 旧分支不是集成分支祖先时的处理（合并、改名、删除）：只拒绝并说明，交用户决定。
- 轻任务的重开（轻任务没有 todo，返工另记 bug 任务，`crew-light-task` 决策 9 已有）。

## 假设（请逐条确认）

1. **重开由用户在 spec-guard 里先做好**：module-crew 不写 todo、plan 和评审标记；`prepare` 时 `/map` 已经显示该模块 `in_progress`。
2. **（改了建议做法）识别「可重开」不要求 `review` 为 pending／revised**：建议做法里的判据有「review.spec/plan 为 pending 或 revised」，但 spec-guard 的口径是「范围内返工不改 Plan 批准」，
   那时两项都是 `approved`，按原判据就开不了。所以判据改为：`status = in_progress`、`worktree = null`、`progress.done < progress.total`、`firstTickAt` 非空（以前勾过，说明不是没开始的模块），
   且状态库里没有该模块在用的 `dev` 会话。`review` 只决定开工说明怎么写（决策 5），不决定能不能开。
   用 `progress` 而不用 `gates`：返工追加的是普通 task，不一定有新的 gate；`gates` 在没有检查点的模块里是 `null`。
3. **用户点名即授权**：`start prepare <模块> --original <原话>` 里的原话就是批准；不另设确认。重开的模块占一个名额，和新模块一样受上限约束。
4. **旧会话必须已收回**：旧一轮的 `dev` 会话还在用（没跑 `merge cleanup`）时拒绝，提示先收回。不做「接着用旧会话」：旧会话的上下文、邮箱名和 worktree 都按已合入处理过了。
5. **快进只动本地分支引用**：旧分支是集成分支祖先时，`git branch -f <id> <集成分支>` 等价于快进，不丢提交；不推送、不删分支。
6. **轮次从状态库算**：`r<轮次>` = 该模块历来的 `dev` 登记条数 + 1（第一次重开是 `r2`）。模块在 module-crew 之前就做完、状态库里没有登记时也从 `r2` 起，免得与可能存在的旧邮箱名撞。
7. **构建前仍要等模块协调的话**：Plan 要重新交审时，照常等 Spec／Plan 批准后的开工类【协调通知】；Spec、Plan 都还是 `approved`（范围内返工）时，用户点名重开就是开工批准，开工说明写明可以直接开始（决策 5）。

## 关键决策与取舍（请重点审）

1. **（新）可重开的判据**（假设 2）：`/map --json` 模块条目同时满足 `status == "in_progress"`、`worktree is None`、`progress.done < progress.total`、`firstTickAt` 非空；状态库里没有该模块 `status: active` 的 `dev` 登记。
   `prepare` 对不在 `startable.modules` 的模块逐个套这个判据：满足就按重开处理（输出写「按重开处理」），不满足就照旧拒绝「不在可开工列表」，并说明差哪一条。
   同一次 `prepare` 可以同时开新模块和重开的模块。
2. **分支**（每个重开的模块，校验阶段就判定，不满足的整次拒绝、什么都不写）：
   - 没有 `refs/heads/<id>`：和新模块一样 `git worktree add -b <id> <路径> <集成分支>`；
   - 有，且 `git merge-base --is-ancestor <id> <集成分支>` 成立：落地时 `git branch -f <id> <集成分支>`，再 `git worktree add <路径> <id>`；
   - 有，但不是祖先（旧分支上有没合进来的提交）：退出码 3，写出多出来的提交数与「交用户决定：合进集成分支、换名保留，或确认丢弃后再重开」，什么都不写。
   - 旧分支正被别的 worktree 检出：退出码 3（git 不允许一个分支检出两次）。
   worktree 路径与新模块相同（`<crewDir>/<id>`），目录已存在照旧拒绝。
3. **（新）新登记与新邮箱名**：登记键（也是邮箱名）`<简称>-<id>-r<轮次>`，字段与新模块相同，另加 `reopen: {"round": <轮次>, "since": <开工批准事项号>, "review": {"spec": …, "plan": …}}`
   （`review` 记 `prepare` 时 `/map` 的值）。`store` 校验 `reopen` 的形状；同一模块仍只能有一个在用的 `dev`（现有规则不变）。
   旧邮箱名不复用：已退役的名字要 `reactivate`、要用户同意，带后缀的新名直接能注册。
4. **（新）新一轮只看新一轮的记录**：重开模块的在用会话带 `reopen.since` 时，凡是「按模块查」的历史判断，只算事项号大于 `since` 的事项。涉及（以现有代码为准，Plan 里逐个列）：
   `hooks` 的阶段判断、`start` 的已合入与名额（`_merged_modules`、`_counted_devs`、`_why_not`）、`merge` 的 `no_sync`／`cleanup`／补勾最终验收、`review` 的已批节点与轮次、`stall` 的退回计数。
   做法是在 `store` 加一个取「本轮起算号」的小函数，各处在原有过滤上加一个条件；没有 `reopen` 的模块行为逐字不变。
   不这么做的后果：旧一轮的合并批准是 `merged`，新会话一开就会被当成「已合入」——不占名额、阶段显示「已合入」、`merge cleanup` 会提前收回、不收同步通知。
   阶段判断里，`reopen.review` 两项都是 `approved` 时，本轮视为 Spec、Plan 已批，阶段从「构建」起算。
5. **开工说明「重开修订」一段**（加在「这一步只做」之前，`render_kickoff` 多一个参数）：

   ```text
   这是重开修订（第 <轮次> 轮）：模块 <id> 已经做完过，spec-guard 已把它原地重开。只做 tasks/<id>/todo.md 里新加的未勾项，已勾的不要重做；
   plan.md 里新补的一节说明这次为什么返工。旧的模块分支已快进到集成分支（或：从集成分支新切），旧一轮的邮箱名已退役，不要用。
   ```

   「这一步只做」按 `/map` 的 `review` 写：
   - Spec 为 `pending`／`revised`：照新模块的写法（先交 Spec，Spec 批了再交 Plan；`combined` 按项目节奏）；
   - 只有 Plan 为 `pending`／`revised`：「这一步只做：把 tasks/<id>/plan.md、todo.md 发【交审】（节点 Plan）；Plan 批准后收到开工类【协调通知】再构建。」
   - 两项都是 `approved`：「Spec 与 Plan 仍是批准状态（范围内返工）。先 module-crew sync，再从 todo 第一个未勾项开始构建，不用等开工通知；做完发最终验收【交审】。」
   去掉「收到开工类【协调通知】之前不要开始构建」一行只在第三种情况。
6. **`start plan`** 不提议可重开的模块（`startable` 本来就不含它），`_why_not` 对它写「已重开（第 <轮次> 轮待开），要用户点名：start prepare <id>」，代替现在的「spec-guard 的当前模块（…）」。
7. **事项记录**：开工批准事项（`kind: "start"`）另记 `reopened: [<模块 id>…]`；事件不新增种类。

## 接口约定

```bash
bin/module-crew start prepare <模块 id>… (--original <原话> | --original-file <文件>) [--json]   # 命令不变，接受可重开的模块
```

- 退出码含义不变：`3` 校验不过、什么都没写（新增原因：旧分支不是集成分支祖先、旧会话未收回、不满足可重开判据）；`4` 中途失败。
- `prepare` 输出每个重开模块一段，多两行：「按重开处理（第 <轮次> 轮）」与分支处理结果（「旧分支已快进到 <提交>」或「没有旧分支，从集成分支新切」）。`--json` 的每个模块加 `reopen: {round, branch: "fast-forwarded"|"created"}`，新模块没有这个键。
- 状态库：`session` 可选字段 `reopen: {"round": int ≥ 2, "since": int ≥ 1, "review": {"spec": str, "plan": str}}`；`item`（`kind: "start"`）可选字段 `reopened: [str]`。只增不改。

## 项目结构

```text
module_crew/start.py              判据、分支处理、登记、开工说明「重开修订」一段、plan 的原因
module_crew/store.py              reopen 字段校验；取本轮起算号
module_crew/hooks.py              阶段判断按本轮
module_crew/merge.py              no_sync、cleanup、补勾按本轮
module_crew/review.py             已批节点、轮次按本轮
module_crew/stall.py              退回计数按本轮
skills/crew-coordinator/SKILL.md、codex-skills/crew-coordinator/SKILL.md、skills/crew-dev/SKILL.md、README.md
tests/test_reopen_module.py
```

## 命令

```bash
python3 -m unittest discover -s tests
PYTHONPATH=tests python3 -m unittest test_reopen_module
```

## 代码风格

沿用现有模块：代码与注释英文，输出中文；只用标准库；git 调用带超时、参数列表、不经 shell；`/map` 一律走 `probe.run()`。

## 测试策略

- 用 crew-probe 的插件夹具造 `/map`：重开的模块 `in_progress`、`worktree: null`、`progress` 未满、`firstTickAt` 有值，`review` 三种组合。
- 每个测试建临时仓库：模块分支已合入（祖先）、有未合入提交（非祖先）、没有分支三种。
- 状态库预置旧一轮：已退役的 `dev` 登记、`merged` 的合并批准、已批的 Spec／Plan 交审。
- 端到端：重开 → 新会话 bind → 阶段 → 交最终验收 → 批准 → `merge run` → `merge cleanup`，每一步不被旧一轮记录误判。
- 回归：全量测试通过；没有 `reopen` 的模块行为不变。

## 边界

- **始终**：只在用户点名时重开；分支只快进、不改写；旧一轮记录保留不动。
- **先问**：旧分支不是祖先时怎么处理；复用旧邮箱名（`reactivate`）；不收回旧会话就重开。
- **绝不**：在 spec-guard 里写 todo、plan 或评审标记；删分支、强推；自动退役邮箱名。

## 验收标准

1. 夹具里模块 `x` 满足可重开判据、旧分支 `x` 是集成分支祖先、旧会话已退役：`prepare x --original "重开 x"` 退出码 0；分支 `x` 指向集成分支顶端，worktree `<crewDir>/x` 检出 `x`；
   登记 `<简称>-x-r2`（`dev`，`reopen.round = 2`、`since` = 开工批准事项号、`review` 与夹具一致）；开工批准事项带 `reopened: ["x"]`；输出含「按重开处理（第 2 轮）」与「旧分支已快进」。
2. 旧分支 `x` 上有集成分支没有的提交：退出码 3，输出写明提交数与交用户决定；分支、worktree、状态库都不变。没有旧分支时从集成分支新切，输出写「从集成分支新切」。
3. 不满足判据的各种情况（`status` 不是 `in_progress`、`worktree` 非空、`progress` 已满、`firstTickAt` 为空、旧 `dev` 会话仍在用）：退出码 3，写明差哪一条，什么都不写。
4. 第三次开（已有 `-r2` 的退役登记）：邮箱名为 `<简称>-x-r3`。状态库里没有任何 `x` 的登记时为 `-r2`。
5. 开工说明逐行比对三种 `review` 组合：都含「重开修订」一段；只有 Plan pending 时写 Plan 交审；都 approved 时写「先 module-crew sync…不用等开工通知」且没有「之前不要开始构建」一行；Spec pending 时与新模块写法相同。
6. 新一轮只看新一轮：旧一轮有 `merged` 的合并批准时，新会话占名额（`start plan` 空位少 1）、钩子阶段不是「已合入」、`merge run` 后各模块同步通知照常含 `x`（`no_sync` 不排除）、`merge cleanup x` 在本轮合入前拒绝；
   本轮合入后 `merge cleanup x` 成功并退役 `-r2`。`review` 两项 approved 时钩子阶段从「构建」起算；Plan pending 时为「写 Spec 与 Plan」一类的交审阶段。
7. `start plan`：可重开的模块不在提议里；没有可开的模块时 `reasons` 里它的原因是「已重开…要用户点名」。
8. 同一次 `prepare` 开一个新模块和一个重开的模块：两个都完成，新模块的登记与开工说明与改前逐字相同。
9. skill：`crew-coordinator`（两份）「开工」一节写明重开的做法（先在 spec-guard 重开、确认旧会话已收回、点名 prepare、旧邮箱名由用户退役）；`crew-dev` 有「重开修订只做新加的未勾项」。
10. 全量测试通过。

## 并行边界

- 独占：`module_crew/start.py`、`module_crew/store.py`、`module_crew/hooks.py`、`module_crew/merge.py`、`module_crew/review.py`、`module_crew/stall.py`、`skills/crew-coordinator/SKILL.md`、`codex-skills/crew-coordinator/SKILL.md`、`skills/crew-dev/SKILL.md`、`README.md`、`tests/test_reopen_module.py`
- 公共：测试资源

## 并行说明

- 轻任务 T62 正在改 `module_crew/start.py`（S22：开工说明加装依赖命令）。本模块构建要等 T62 合入、模块协调发开工通知后开始，开工先 `module-crew sync`；Spec、Plan 期间不改代码。

## 未决问题

1. 假设 2 改了建议做法的判据（不看 `review`，改看 `progress`、`firstTickAt`），请确认。
2. 假设 7／决策 5：Spec、Plan 都还是 `approved` 时，用户点名重开即视为开工批准、不再等开工通知——推荐这样（范围内返工本来不送审）；也可以改为仍等模块协调发开工通知。

## 文档建议

README「出状况时怎么办」或「一次完整流程」后加「修订已完成的模块」一条（spec-guard 原地重开 → `merge cleanup` 已做 → `start prepare <id>` → 用户退役旧邮箱名）；CHANGELOG 随发版写入第九版。

## 变更记录
