# Spec: crew-review-gates-align

> 能力图模块 `crew-review-gates-align`。需求来源：模块 crew-review-rules-follow 的未决问题 Q1、Q2（`spec/crew-review-rules-follow.md`），ecosystem-lead #23522（用户在其会话「合成一项，对齐 spec-guard」）；用户 2026-11-27 在 mc-coord 批准排期、插入与开工（「合成一项，发版后排」「现在开始」「确认插入」），开会话依据：用户批准事项 C879。
> 上游：spec-guard 0.99.0／0.100.0（interface 1.27，模块 `sg-review-rules`，规则 1～5「需求文档先审一轮」、规则 12「没有审查者就交用户批」）。本机 2026-11-27 实测：spec-guard 已是 0.100.0，`interface.json` 为 `1.27`，构建不用等升级。
> 依赖 `crew-review-batch`（`review add`／`review approve`／交审展示）、`crew-flow-v2`（新流程的节点与第二审查者）、`crew-review-rules-follow`（重要需求无审查者交用户批）。现状取自本分支源码。
> 本模块是老流程模块（不带流程标记）：Spec → Plan → todo。改的是 module-crew 对**别的**新流程模块的处理，本仓库自己的模块不受影响。

## 目标

关卡怎么判一律以 spec-guard 为准，补上两处对不上的地方：

1. **新流程需求先审一轮**：spec-guard 1.27 要求新流程 `normal`／`important`（按生效档位）的需求文档在用户确认前有一条审查记录，没有就 `reviewMark --target spec --state approved` 以 `requirement-unreviewed` 拒绝。
   module-crew 要做到：模块会话交需求前先审一轮；`review add` 收到缺审查记录的需求就拒收并说明怎么补；交用户时附上审查后的改动差异；`review approve` 万一被拒，说清原因。
2. **普通需求的技术方案没有第二审查者时交用户批**：今天 `review codex-note` 记「未审放行」，spec-guard 对同一情形记 `designApproval.status = unreviewed`（「the user approves it」，sg-review-rules 第 12 条）。改为与重要需求一样交用户批。
   **这推翻 `crew-flow-v2` 的一条已批决定**：假设 A3 前半句「普通需求记『未审』放行、由回归兜底」与决策 7 的对应一句；本模块在 `spec/crew-flow-v2.md` 末尾「变更记录」补一行。

## 现状

- `module_crew/review.py:67` `add`：新流程判定用 `flow.tier`，读的是**集成分支**的 `/map --json`；对节点 `spec` 只查文件、不看需求审查。新模块的需求文档在批准前只在模块分支上，集成分支读不到它的流程标记，所以第一次交需求时 `tier` 往往为空（按老模块处理）。
- `module_crew/review.py:1443` 起 `_approve`：对 `spec`／`interface` 节点在集成分支跑 `reviewMark --target spec --state approved --confirm`；失败时只报「写批准标记失败，已停下：<前 200 字>」并还原，不认 `requirement-unreviewed`。
- `module_crew/takeover.py:774-785` `codex_note`：技术方案报告 `reviewer.selection == "none"` 时，`important` 送用户（`no_reviewer_draft`，crew-review-rules-follow 决策 5），其余档位记 `UNREVIEWED`「未审：本机没有可用的第二审查者，由回归测试兜底」并放行。
- `module_crew/takeover.py:83` `_map` 的缓存键只含 `.agent/config.json` 与能力图的修改时间，不含模块 Spec；模块会话补了审查记录后再读，会拿到旧结果。
- spec-guard 1.27 `/map --json` 每个模块行有顶层字段 `requirementReview`：老流程为 null；新流程为 `{required, status, records}`，`status` 取 `not-required`／`missing`／`reviewed`；`tier` 已是生效档位（`bug`、`small` 被规则抬升时为 `important`）。
- spec-guard 1.27 的三种记录：`reviewMark --target spec --state codex-reviewed --review <delegate 报告>`（Codex 审）、`--state host-reviewed --blocking N`（宿主全新子会话审，「外部审查意见」一节要有内容）、`--state no-reviewer --reason "<一行原因>"`（没有可用审查者）。只审一轮，记过再记会被 `requirement-review-recorded` 拒绝。
- `reviewMark --target spec --state approved` 不带 `--confirm` 时（预览），对已审的需求打印「Changes since the review (show this diff to the user verbatim)」与差异，或「nothing changed since the review」，或取不到的原因。
- crew-dev 两份 skill 的「新流程模块」一节只写「需求先单独交」，没有先审一轮；crew-coordinator 两份 skill 第 275／289 行写「`codex-note` 记『未审放行』，由回归兜底」。

## 范围

**范围内**

1. 模块会话交需求前先审一轮：crew-dev 两份 skill 写明三条路与顺序（决策 1、2）。
2. `review add` 对缺审查记录的新流程需求拒收并说明原因（决策 3、4）。
3. 交用户时附审查记录与审查后的改动差异（决策 5）。
4. `review approve` 认出 `requirement-unreviewed`，给出能照做的说明（决策 6）。
5. `codex_note`：普通需求没有第二审查者时与重要需求一样交用户批（决策 7）。
6. 文字：crew-dev、crew-coordinator 两份 skill（Claude 版与 Codex 版）；`spec/crew-flow-v2.md` 变更记录补一行；`CHANGELOG.md`。
7. 测试：`tests/test_flow_v2.py` 里钉住「普通需求未审放行」的 `test_no_reviewer_releases_unreviewed` 按新决定改（它钉的就是被推翻的决定），另加新用例；`review add`／`review approve`／展示的新用例。

**范围外**

- 需求审查本身怎么审、记录怎么写、哪些档位要审：归 spec-guard，module-crew 只读 `requirementReview` 和 `reviewMark` 的结果。
- module-crew 落地技术方案的批准时不写 spec-guard 的技术方案标记（`reviewMark --target design`，`review.py:1443` 注释「spec-guard records no mark for a design (yet)」）：今天就有的出入，见未决问题 Q1，不由本模块改。
- 冻结中的 Codex 代批（Spec、Plan 由 Codex 审过就放行）：不碰。需求审查记录（`codex-reviewed`）只是一轮审查，不是放行，批准仍是用户。
- 契约（session-protocol）与 `interface.json`：不变。
- 老流程模块、bug／小改动（未被抬升）的需求：照旧，不审、不拦。

## 关键决策与取舍（请重点审）

1. **谁审、在哪审：模块会话交审前在自己的 worktree 里做。** spec-guard 的记录要写在模块分支的需求文档里、绑定当时的文本，所以由写需求的模块会话发起，审完按意见改、提交，再发【交审】。
   审查者不是模块会话自己：Codex（delegate）或宿主新开的全新子会话（不带本会话上下文），符合「写的会话不审自己」。
   取舍：另一种做法是像技术方案那样由模块协调发起（`review codex C<n>`）；但那条路对 Spec 节点属于冻结中的 Codex 代批，复用会把冻结的功能带回来，不选。
2. **三条路照 spec-guard 的顺序**（crew-dev 写明）：
   - 有 delegate 且 Codex 可用：`/delegate:review --backend codex` 审 `spec/<模块>.md`（只读），报告存成文件，`/spec-guard:review-mark --target spec --state codex-reviewed --review <报告> --confirm`；
   - 否则开一个全新子会话审（Claude Code 用子代理，Codex 用新开的子任务），结论写进需求文档「外部审查意见」一节，`--state host-reviewed --blocking <阻断条数> --confirm`；
   - 都不行：`--state no-reviewer --reason "<一行原因>" --confirm`。
   只审一轮；按意见改完后交审，「要点」里写「需求审查：<谁审的>，阻断 N 条；采纳了哪些、哪些没采纳及原因」（这是要点里的一行文字，不是新的契约字段）。
   这一步是 spec-guard 的硬关卡、不是可选的复核，所以**不再单独问用户要不要审**：用户批准模块开工就包括它（见假设 A1）。
3. **`review add` 怎么判：只看 spec-guard 在模块 worktree 上给的 `requirementReview.status`。** 节点为 `spec` 或 `interface` 时，在模块的 worktree 上读一次 `/map --json`（不走缓存），取该模块行：
   - `status == "missing"` → 拒收，什么都不记；
   - `reviewed`、`not-required`、字段为 null（老流程）或没有这个字段（spec-guard 低于 1.27）→ 照今天收；
   - worktree 上的 `/map` 读不出 → 照今天收，另起一行提示「读不到 spec-guard 的需求审查状态：<原因>，批准时由 spec-guard 判」，不替它判。
   module-crew 不自己看档位、不数记录行，档位抬升也由 spec-guard 算进 `required`。
4. **拒收说明写什么**：「<模块> 的需求文档还没有审查记录（spec-guard requirementReview: missing），用户确认前要先审一轮」，再列决策 2 的三条命令；要点「先审一轮，改完提交后重新发【交审】」。退回走今天的拒收通道（退出码 3），不新增消息类型。
5. **交用户时附什么**：`review batch` 与发往决策收件箱的交审卡，对新流程需求加一行「需求审查：<codex／宿主子会话／没有审查者（原因）>，阻断 N 条」（取自 `requirementReview.records`），并在模块 worktree 上跑 `reviewMark --target spec --state approved` 的**预览**（不带 `--confirm`，不写文件），把它打印的「审查后的改动差异」原样附上；预览说没改动或取不到，就照它的话写。
   `review show C<n> --review-diff` 单独看这份差异。
6. **`review approve` 被拒**：`reviewMark` 输出以 `requirement-unreviewed` 开头时，在今天的「已停下、已还原」之后加一句「spec-guard 拒绝：这份需求还没审过一轮（多半是交审之后记录被改掉了）；用 review answer C<n> 退回模块先审一轮，不要绕过」。其他失败照今天。
7. **普通需求没有第二审查者：交用户批。** `codex_note` 对技术方案报告 `reviewer.selection == "none"` 不再分档位，一律走今天给重要需求的那条路：不放行，记 `codex-unavailable`，退出码 5，给【等待用户】草稿。
   草稿的现状一句改为按档位说：重要需求照旧「这是重要需求」；普通需求写「本机没有可用的第二审查者，spec-guard 记为未审（unreviewed），由你批」。选项不变（A 你来批这一版／B 装好第二审查者后重跑）。
   `UNREVIEWED` 文字保留，只用于展示升级前已经「未审放行」的旧事项，新事项不再产生。

## 接口约定

- **读**：`/map --json`（模块 worktree 上）每个模块行的 `requirementReview`（1.27）；`reviewMark --target spec --state approved` 预览的输出与退出码 2 的 `requirement-unreviewed`。
- **写**：不变。module-crew 不替模块写需求审查记录；记录由模块会话用 `/spec-guard:review-mark` 写。
- **协议**：不变；交审「要点」里多一行文字，不是新字段。
- **`interface.json`**：不变。

## 项目结构

- 改：`module_crew/review.py`（`add` 的需求审查判定、`_approve` 的拒绝说明、`show --review-diff`、批次展示）、`module_crew/takeover.py`（`codex_note`、`no_reviewer_draft`；给 worktree 读 `/map` 的不走缓存入口）、`module_crew/flow.py`（如判定放这里）、`module_crew/__main__.py`（`--review-diff` 参数）。
- 改：`skills/crew-dev/SKILL.md`、`codex-skills/crew-dev/SKILL.md`、`skills/crew-coordinator/SKILL.md`、`codex-skills/crew-coordinator/SKILL.md`、`CHANGELOG.md`、`spec/crew-flow-v2.md`（只追加变更记录一行）。
- 改测试：`tests/test_flow_v2.py`；新增或扩展 `review add`／`approve`／`show` 的测试文件（Plan 定）。

## 命令

```bash
module-crew check quick
scripts/validate.sh --quick
```

## 代码风格

照仓库现有写法：标准库、Python 3.9 可运行、函数注释写来源（`crew-review-gates-align decision N`）、给用户的文字用中文。

## 测试策略

- `review add`：夹具 `/map` 给 `requirementReview.status` 为 `missing`／`reviewed`／`not-required`／null／缺字段，加 `/map` 读不出；节点 `spec` 与 `interface` 各测；`missing` 拒收且状态库不变、说明里有三条命令。
- 缓存：同一 worktree 先 `missing` 拒收、补记录后再交能收下（证明不走缓存）。
- 展示：批次与交审卡有「需求审查」一行；预览打印的差异原样出现；没改动、取不到两种情形照写。
- `approve`：`reviewMark` 返回 `requirement-unreviewed` 时有决策 6 的说明，集成分支还原。
- `codex_note`：`normal` 无审查者 → 退出码 5、不落地、草稿写「spec-guard 记为未审」；`important` 回归不变；有审查者的路径不变。
- 变异：删掉 `missing` 判定、改成读集成分支、`codex_note` 恢复按档位分支，各让对应测试变红。
- 其余现有测试除范围第 7 条点名的一条外不改、全绿。

## 边界

- **会做**：范围内 1～7。
- **先问再做**：module-crew 替模块写需求审查记录；改契约或 `interface.json`；动冻结的 Codex 代批。
- **不做**：范围外列出的事；自己判断哪份需求要审、审得够不够。

## 验收标准

- **AC1** 新流程需求 `requirementReview.status == "missing"`：`review add` 拒收（退出码 3），状态库不变，说明里有决策 2 的三条命令。
- **AC2** `reviewed`、`not-required`、null、缺字段：`review add` 与今天相同；worktree 上 `/map` 读不出时照收并带提示行。
- **AC3** 模块补了审查记录后重新交审能收下（不读旧缓存）。
- **AC4** 新流程需求的批次展示与交审卡有「需求审查」一行和 spec-guard 预览给出的改动差异（或它说的没改动／取不到）；`review show C<n> --review-diff` 单独给出这份差异。老流程模块的展示逐字不变。
- **AC5** `review approve` 碰到 `requirement-unreviewed`：停下、还原，并给出决策 6 的说明。
- **AC6** 普通需求的技术方案报告 `reviewer.selection == "none"`：`codex-note` 退出码 5、不落地、给【等待用户】草稿（「spec-guard 记为未审，由你批」）；重要需求结果不变。
- **AC7** `spec/crew-flow-v2.md` 末尾变更记录有本次推翻 A3 前半句与决策 7 对应一句的一行；crew-dev 两份 skill 写了先审一轮，crew-coordinator 两份 skill 不再写「未审放行」。
- **AC8** 变异测试全部变红；`module-crew check quick` 通过。

## 并行边界

- 独占：`spec/crew-review-gates-align.md`、`tasks/crew-review-gates-align/`、`module_crew/review.py`、`module_crew/takeover.py`、`module_crew/flow.py`、`module_crew/__main__.py`、`tests/test_flow_v2.py`
- 公共：`skills/`、`codex-skills/`、`CHANGELOG.md`、`spec/crew-flow-v2.md`（只追加变更记录；发【公共变更请求】）

## 并行说明

能力图上本模块排在最后、串行；挂起的 `crew-takeover-merge` 也改 `takeover.py`、`review.py`，恢复前不会同时改。

## 要你确认的假设

- **A1** 需求审查是 spec-guard 的硬关卡，模块会话交需求前直接做（含调 `/delegate:review` 或开子会话），不再每次单独问用户；用户批准模块开工即包括这一步。项目 CLAUDE.md「可提议用 `/delegate:review`，用户同意后再发起」那条指的是可选的复核，不管这一步。
- **A2** `review add` 只看 spec-guard 在模块 worktree 上给的 `requirementReview.status`，读不出时照收、由批准时的 `reviewMark` 把关。
- **A3** 普通需求没有第二审查者时交用户批，与重要需求同一条路（决策 7）；不再有「未审放行」。
- **A4** 审查记录由模块会话写，module-crew 不代写。

## 未决问题

- **Q1** module-crew 落地技术方案的批准时不写 spec-guard 的技术方案标记（`--target design` 的 `approved`／`reviewer-approved`／`no-reviewer`），spec-guard 那边的 `designApproval` 可能一直显示待批。这是 crew-flow-v2 起就有的出入，和本模块的「以 spec-guard 为准」同方向，但改动面另成一块（落地、合并、阶段判断都要跟）。推荐：**另开一项**，由 mc-coord 记单、用户排期；不并进本模块。
- **Q2** 决策 5 的预览要在模块 worktree 上跑 `reviewMark`；它只预览不写文件，但宿主可能对这条命令弹权限确认。推荐：构建时实测，弹了就按现有【公共变更请求】把它加进放行规则，不另开模块。

## 文档建议

crew-dev、crew-coordinator 两份 skill 随本模块改（范围第 6 条）；README 没有需求审查与「未审放行」的说法，不用改。项目没有文档基线。

## 变更记录
