# Spec: crew-stall-signals

<!-- spec-guard: review approved 29fae42ba48e -->

> 能力图模块 `crew-stall-signals`（第四版，0.4.0 三个模块之一）。需求来源：`livesaas-integration/REQ-REVIEW-NEARBY.md` R14（用户决定 49）；
> 0.3.0 冻结时用户定 R14 放下一版。用户 2026-10-19 在本会话确认 19 条下一版假设（全部按推荐）。
> 契约：session-protocol v2.1 不变；本模块只在 `sessions --json` 增加字段，`schemaVersion` 仍为 1。

## 目标

决策收件箱能判断「某个模块是不是卡住了」并主动问用户换路，而 module-crew 只提供判断所需的事实：模块多久没有产出提交、
同一个节点被拿到用户面前问了几次、模块报来过哪些【等待用户】。module-crew 不设阈值、不下「卡住」的结论、不生成待决事项。

## 范围

- `sessions --json` 每行新增 `startedAt`、`commits`、`asks`、`returns`、`waitUser` 五个字段（只增不改）。
- 人看的 `module-crew sessions` 与 `module-crew status` 各加事实行。
- `spec/crew-hub-bridge.md` 的 sessions 契约一节加一句指向本 Spec 的新字段（追加变更记录）。

不做：阈值与「卡住」判断、待决事项、选项（归 decision-inbox）；列出可开工模块（decision-inbox 读 spec-guard `/map --json`）；
挂起流程（沿用现有 `module-crew suspend`，它让模块在自己 worktree 跑 spec-guard 的 module-suspend）。

## 假设（用户 2026-10-19 已确认，摘本模块相关的）

1. 三个新模块按 crew-stall-signals → crew-host-permissions → crew-glossary-rename 排在 crew-review-nearby 之后；本模块先做。版本 0.4.0；契约 v2.1 不变。
2. module-crew 只给事实，不设阈值；「默认半天」「N=3」由决策收件箱配置与判断（与 `failure.sessions` 的「no thresholds, no verdicts」一致）。
3. 提交事实：模块分支上不在集成分支里的提交——最新一个的提交号与提交时间、领先几个；开工时间另给，用来算「开工以来一次都没提交」。
   worktree 读不到时这些为 null 并附原因，整条命令不因此退出 2。
4. 「同一问题」按「模块＋节点（Spec、Plan、接口、最终验收）」认：每个节点问过用户几次、对应哪些 C 号、最近一次时间；
   另列模块发来的【等待用户】及其「要你决定」首行，是不是同一个问题由决策收件箱判断。
5. 挂起沿用现有命令；可开工模块由决策收件箱读 spec-guard。
6. 人看的 `sessions`（不带 `--json`）与 `status` 也加「最近提交：X 前」「同一节点问过你 N 次」两行事实。
7. 新写的给人看的文字用术语表 v1.1 名称（模块协调、提请批准、集成分支、等待记录 W 等）；旧文字的全面改名由 crew-glossary-rename 做。

## 关键决策与取舍（请重点审）

1. **提交事实以 worktree 的 HEAD 对集成分支为准**：`git -C <worktree> rev-list --count <集成分支>..HEAD` 得 `ahead`，
   最新提交 `last` 取「开工以来 HEAD 第一父链上、又不在集成分支第一父链上的最新一个提交」：
   `git -C <worktree> rev-list --first-parent --since=<startedAt> HEAD` 依次取，跳过 `rev-list --first-parent --since=<startedAt> <集成分支>` 里出现过的，第一个就是 `last`（提交号与 committer date，带时区）。
   这样模块合进集成分支之后（`ahead` 变 0）`last` 仍是模块自己的最后一次提交，不会被当成「开工以来没有提交」；同步时快进到集成分支的提交不算模块产出；没有 `startedAt` 时退回 `<集成分支>..HEAD` 的最新一个。
   用 HEAD 而不是分支名，因为模块会话就在这个 worktree 里提交；集成分支名取运行配置 `integrationBranch`。
   模块按同步通知把集成分支合进来产生的合并提交也算产出——它确实是模块会话的动作；不另行区分，Spec 写明。
2. **开工时间取会话登记事件**：`startedAt` = 事件日志里这个会话名最近一次 `registered` 事件的时间（`start prepare` 写入；换会话 `takeover` 不改它）。
   会话记录本身不加字段，状态库格式不变。
3. **「问过你」只数真正到了用户面前的交审**：某个 C 号（`kind: review`）计一次，当且仅当它进过提请批准（被某条 `hub-batch` 记录的 `reviews` 列出）
   或由用户答复关闭（`closedReason: answered`）。返工（审查者退回、不经用户）不计；被新交审取代（`superseded`）而且从没到过用户面前的不计。
   没配决策收件箱时，模块协调在会话里给用户看 `review batch` 不留记录，所以「还没答」的那次不计，答了才计——Spec 写明这个差别，
   不为此新增记录。
4. **合并退回单列**：最终验收批准后在合并检查失败退回的，按 `merge-approval` 的 `closedReason: returned` 列进 `returns`，带 `returnKind`（`env`／`module`）。
   退回后的重交是新的 C 号，到用户面前时照第 3 条再计一次，不重复计退回本身。
5. **【等待用户】原样列出不归并**：`waitUser` 列这个模块会话发来的所有 `wait-user` 事项（开着的和关了的），每条给 C 号、状态、关闭原因、
   「要你决定」第一行、时间；不做文字相似度归并。
6. **字段失败不连坐**：某个模块的 git 读不到（worktree 不存在、不是 git 仓库、集成分支不存在）只让它的 `commits` 为 `{"ahead": null, "last": null, "error": "<原因>"}`，
   其他字段与其他模块照常；整条命令仍按 crew-hub-bridge 的约定只在状态库读不到时退出 2。
7. **契约文档放在哪**：新字段的定义写在本 Spec 的「接口约定」；`spec/crew-hub-bridge.md` 的 sessions 契约一节追加一句「0.4.0 起新增字段见 spec/crew-stall-signals.md」并记变更记录。
   `interface.json` 的 `sessions.contract` 仍指向 crew-hub-bridge，只升 `version`。

## 接口约定

### sessions --json 新字段（只增不改，schemaVersion 仍为 1）

```json
{"schemaVersion": 1,
 "sessions": [{"module": "b", "relayName": "shop-b", "...": "现有字段不变",
   "startedAt": "2026-10-19T09:00:00+08:00",
   "commits": {"ahead": 3, "last": {"commit": "<40 位>", "at": "2026-10-19T11:20:05+08:00"}, "error": null},
   "asks": [{"node": "spec", "count": 1, "refs": ["C12"], "ats": ["2026-10-19T09:40:00+08:00"], "lastAt": "2026-10-19T09:40:00+08:00"},
            {"node": "final", "count": 3, "refs": ["C20", "C26", "C31"],
             "ats": ["2026-10-19T10:05:00+08:00", "2026-10-19T13:30:00+08:00", "2026-10-19T15:02:00+08:00"], "lastAt": "2026-10-19T15:02:00+08:00"}],
   "returns": [{"ref": "C22", "returnKind": "env", "at": "2026-10-19T13:10:00+08:00"}],
   "waitUser": [{"ref": "C24", "state": "open", "closedReason": null, "decide": "要不要再试一次", "at": "2026-10-19T14:00:00+08:00"}]}]}
```

- `startedAt`：没有登记事件时 null。
- `commits.ahead` 是还没合进集成分支的提交数；`last` 与 `ahead` 无关，开工以来模块自己一次都没提交时才为 null（合入集成分支后 `ahead` 为 0、`last` 仍有值）；读不到时 `ahead`、`last` 都为 null，`error` 一行原因。
- `asks`：只列计过数的节点，按 Spec、Plan、接口、最终验收排；`node` 用现有节点代码（`spec`／`plan`／`interface`／`final`），`refs` 按编号升序；`ats` 与 `refs` 一一对应，`ats[i]` 是 `refs[i]` 那次交审进提请批准或被答复的时间（两者都有取较晚的），供决策收件箱按时间窗口计数；`lastAt` 为 `ats` 中最晚的一个。
- `returns`、`waitUser`：按编号升序；没有为 `[]`。
- 时间一律 ISO 8601 带时区，与现有 `lastActivity` 同格式。
- （0.5.0，R21 MC-3）`answers`：这个模块每次收到用户答复的事实，按时间排：`[{"ref": "C24", "at": ISO, "commitsAfter": 0, "ticksAfter": 0}]`。答复取这个模块的交审、【等待用户】、合并批准里带 `answer.answeredAt` 的记录；`commitsAfter` 是从这次答复到下一次答复（最后一次到现在）之间模块 worktree 第一父链上的模块自有提交数（口径同 `commits.last`）；`ticksAfter` 是同一段里 `tasks/<模块>/todo.md` 已勾选项增加了几个（段首取答复时刻 HEAD 第一父链上最近一个提交里的版本，段尾取下一次答复时刻的版本，最后一段取工作区）。只给事实，「答了 2 次进度没动」由决策收件箱判断。worktree 读不到时 `commitsAfter`、`ticksAfter` 为 null。

### 人看的输出

`module-crew sessions` 每个模块在现有四行后加：

```
  最近提交：2026-10-19 11:20（2 小时前），未合入集成分支 3 个        # 没有：开工以来没有提交（开工 5 小时前）；读不到：最近提交读不到：<原因>
  问过你：Spec 1 次、最终验收 3 次（C20、C26、C31）；合并退回 1 次   # 都没有：问过你：无
```

`module-crew status` 的模块行各加一句「最近提交 X 前」与「同一节点最多问过你 N 次」（N 为 0 时不写）。

退出码与现在相同。

## 项目结构

```
module_crew/failure.py    sessions() 加五个字段；render_sessions 加两行
module_crew/commits.py    或新文件 module_crew/stall.py：读 worktree 提交事实、数「问过你」（实现时按内聚择一）
module_crew/probe.py      status 模块行加事实
spec/crew-hub-bridge.md   契约一节加一句与变更记录
interface.json            version 0.4.0（三个模块做完一起升，见 Plan）
tests/test_stall_signals.py
```

## 命令

```bash
python3 -m unittest discover -s tests -v
```

## 代码风格

与现有模块一致：只用标准库；只读，不写状态库、不写 git；git 调用用现有的子进程封装；给人看的文字用中文、术语表 v1.1 名称。

## 测试策略

- 临时仓库夹具（`tests/helpers.py`）：建集成分支与一个模块 worktree，分别在「没提交」「2 个提交」「worktree 被删」「集成分支不存在」下检查 `commits`。
- 状态库夹具：同一模块同一节点 3 个交审——一个进过 `hub-batch`、一个被用户答复、一个返工后被取代且没到过用户面前——`asks` 计 2；
  另一节点没到过用户面前不出现。
- `merge-approval` 退回两次（`env`、`module`）进 `returns`；`wait-user` 开着一条、取代一条都进 `waitUser`，`decide` 为首行。
- 现有 `sessions --json` 的契约测试原样通过（老字段不变），新增字段的键与类型测试。
- 人看的 `sessions` 与 `status` 文字快照。

## 边界

- **总是**：只读；某个模块读不到不影响别的模块；字段只增不改。
- **先问**：在 module-crew 里加阈值、「卡住」判断或主动通知；改 `schemaVersion`；为「问过你」新增记录种类。
- **从不**：替决策收件箱生成待决事项；挂起或恢复模块；改已有字段的含义。

## 验收标准

1. 模块 worktree 有 2 个不在集成分支里的提交：`commits.ahead` 为 2，`last.commit`、`last.at` 是最新那个的提交号与提交时间；没有提交时 `ahead` 0、`last` null；模块合入集成分支后 `ahead` 0、`last` 仍是模块自己的最后一次提交；同步时快进到集成分支不产生 `last`。
2. worktree 不存在或集成分支不存在：该模块 `commits.error` 写明原因、`ahead`／`last` 为 null，其他模块与其他字段正常，退出码 0。
3. `startedAt` 等于这个会话 `registered` 事件的时间；`takeover` 之后不变。
4. 同一模块同一节点：进过提请批准的、被用户答复的各计一次，只经返工又被取代的不计；`refs`、`ats`（与 `refs` 一一对应）、`count`、`lastAt` 正确，节点顺序 Spec、Plan、接口、最终验收。
5. 没配决策收件箱时，用户在模块协调亲手批准的交审计入 `asks`。
6. 合并退回进 `returns` 并带 `returnKind`；重交的新 C 号到用户面前时在 `asks` 再计一次。
7. `waitUser` 列出模块发来的全部【等待用户】（开着与关了的），`decide` 为「要你决定」第一行。
8. 现有 `sessions --json` 字段与 `schemaVersion: 1` 不变，crew-hub-bridge 的契约测试照常通过；状态库读不到时仍退出 2、stdout 为空。
9. `module-crew sessions` 每个模块多两行事实（最近提交、问过你），`status` 模块行带「最近提交 X 前」；文字用术语表 v1.1 名称。
10. 全量测试通过。
11. （0.5.0）`answers` 每次用户答复一条：答复后有提交的那段 `commitsAfter` 大于 0，答复后只勾了 todo 的那段 `ticksAfter` 大于 0、`commitsAfter` 为 0，连续两次答复后都没动的两段都为 0；字段名发版前经决策收件箱确认。

## 未决问题

- 换会话接管后，「开工时间」是否应该改为接管时间：暂定不改（模块的开工时间不因换会话而变）；决策收件箱如需接管时间，可从事件日志另加字段，届时再提。

## 文档建议

README 里说明 `sessions --json` 字段的那一条（现第 121 行）补上新字段并链接本 Spec；不在本模块改其他 README 文字（全面改名在 crew-glossary-rename）。
回告：本模块发版后告诉 decision-inbox 插件会话新字段可用（随最终验收列出）。

## 变更记录

- 2026-10-19：`asks` 每项加 `ats`（与 `refs` 一一对应的时间），接口约定与验收 4 随之补一句；老字段不变。原因：decision-inbox 的停滞触发条件「同一件事 24 小时内报了 3 次」需要每次的时间，累计次数与最后时间不够；来源：decision-inbox 插件会话回复（选 B），用户 2026-10-19 批准修订。
- 2026-10-19：`commits.last` 改为「开工以来 HEAD 第一父链上、不在集成分支第一父链上的最新提交」，与 `ahead` 脱钩；人看的文字「开工以来 N 个提交」改为「未合入集成分支 N 个」；验收 1 补两种情况。原因：验收 11 实地测试时发现已合入的模块 alpha（8a2fe79 已合入 main）显示「开工以来没有提交」，决策收件箱会据此误报停滞；来源：接入方案会话报告疑点，用户 2026-10-19 选「冻结前先修」。
- 2026-10-19：加 `answers` 字段（每次用户答复之后的提交数与 todo 勾选增量）与验收 11（0.5.0）。原因：R21「模块打转」MC-3，供决策收件箱 DI-6①「用户答了 2 次进度没动」使用；来源：监测会话转达用户决定 58–60，用户 2026-10-19 在本会话确认 6 条假设。
