# Spec: crew-final-accept-split

<!-- spec-guard: review approved 89fb559f4808 -->

> 能力图模块 `crew-final-accept-split`（排在 `crew-docs` 之后，Build order 最后一个）。开会话依据：用户批准事项 C355。
> 需求来源：接缝 S48（plugin-ecosystem SEAMS.md；livesaas-fe-coord #12249 → ecosystem-lead #12250 → mc-coord #12260）。
> LIVE-SAAS 前端的 N1、N4 最终验收（C149、C148）用户只批「有限验收」、明确不批合并；module-crew 0.18.0 没有这条路径，
> 模块协调只能用 `review answer` 登记，事项被关成通用的 `answered`，和「要求修改」分不开，之后要合并还得重新交审。
> 依赖 `crew-docs`：文档按它整理后的 `docs/guide.md`、`docs/commands.md` 改。标「新」的是写 Spec 时补的取舍，请重点审。

## 目标

最终验收的批准拆成两步，各有专门的命令和状态：

1. **接受验收**：用户说「验收通过（或有限验收通过），但先不合并」。模块协调用新命令 `merge accept` 记下用户原话；交审事项不关闭，进入「已接受验收、待授权合并」状态；不进合并队列，集成分支不变。
2. **授权合并**：用户之后补一句「授权合并 C<号>」。模块协调对同一个交审事项照常 `merge approve`，不用模块重新交审；排进合并队列，后面和今天一样。

用户一次就批准合并时，照旧直接 `merge approve`（接受验收与授权合并一起记下）。
`review answer` 对最终验收只用于「要求修改」（退回）。两份 crew-coordinator 技能（Claude、Codex）、两份 crew-dev 技能和对外文档按这个说法改写，不再出现「批准一律走 `review approve`」「批准即授权合入」这种会把用户没给的合并授权扩大的写法。

## 范围

**范围内**

1. 新命令 `module-crew merge accept <C号>… --original(-file)`（模块协调）：记接受验收。
2. 交审事项的新状态 `accepted`，以及它在批量交审、同步、阶段提示、状态与停滞检测、重交审、退回里的行为（见关键决策 2～6）。
3. `merge approve` 收「已接受验收」的事项（今天只收 `open`）。
4. `review approve` 对最终验收的拒绝提示、`review answer` 对最终验收的输出提示改写（关键决策 7）。
5. 决策收件箱里最终验收卡片的选项（按 D1）。
6. 技能：`skills/crew-coordinator/SKILL.md`、`codex-skills/crew-coordinator/SKILL.md`、`skills/crew-dev/SKILL.md`、`codex-skills/crew-dev/SKILL.md` 里涉及最终验收批准的条文。
7. 文档：`docs/commands.md`（新命令、`merge approve`、`review answer` 的说明）、`docs/guide.md`（流程与出状况里加「只接受验收、暂不合并」）。
8. 测试：新增 `tests/test_final_accept.py`；改动波及的现有测试照实更新。

**范围外**

- 已经被 `review answer` 关掉的 C149、C148：不做迁移命令；按已转给 livesaas-fe-coord 的过渡办法（模块用原提交重新交最终验收，`review add` 收下后 `merge approve`、`merge run`）处理。
- 「撤回接受验收」专门命令：用户改主意要修改，用 `review answer` 退回即可（关键决策 5）。
- 已接受验收的长期提醒、超时：不做（`status` 里看得到即可）。
- session-protocol 契约、决策收件箱、spec-guard 的任何改动；`sessions --json` 的字段与阶段枚举（关键决策 6）。
- 发版：版本号、CHANGELOG 新条目、`plugin.json` 由模块协调另经用户批准做。

## 假设（请逐条确认）

1. **「接受验收」只针对最终验收**（含轻任务的最终验收），Spec、Plan、接口提案没有这个区分，照旧 `review approve`。
2. **授权合并要用户原话**：`merge approve` 对已接受验收的事项同样要 `--original(-file)`；接受验收时的原话不能当授权合并用，代码不从原话里猜意图（判断「这句话是不是授权合并」是模块协调读原话的责任，技能里写清）。
3. **授权合并针对接受时的那个提交**：接受验收之后模块分支又有提交，照今天的规则 `merge run` 报「交审之后又有提交，须重新交审」；重新交审作废旧的接受验收。
4. **已接受验收的模块照旧占着模块会话**：会话不收回、不退役，不收同步通知（同步会产生新提交、让接受作废）；名额照算。是否允许先收回 worktree 见 D2。
5. **待决问题在接受验收时答**：交审带待定问题（审查不同意、超时等）时，`merge accept` 和 `merge approve` 一样要求答全；之后授权合并不再问一遍。
6. **模块会话收到「只接受验收」的答复时停在原地**：不勾 todo 末项、不再提交、不重发交审，等授权合并或退回；这一条写进两份 crew-dev 技能和阶段提示。
7. **不需要新依赖**，测试照现有方式 `python3 -m unittest`。

## 待用户决定（D 编号）

- **D1 决策收件箱里的最终验收卡片要不要加「只接受验收」选项**：
  - 推荐 A：加。卡片选项变成「A：批准（验收并授权合并）／B：退回修改／C：只接受验收，暂不授权合并」；用户选 C，模块协调转达时用 `merge accept`。好处是 S48 这种情况有明确的格子可选，不靠用户写自由文字。卡片格式仍是契约 v2.3 的选项写法，不用改契约。
  - B：不加。卡片维持 A／B；用户在 B 或自由文字里写「只验收不合并」时，模块协调照原话用 `merge accept`。改动最小，但容易再出 S48 的情况。
- **D2 已接受验收、还没授权合并的模块，能不能先 `merge cleanup` 收回 worktree**：
  - 推荐 A：不能。`merge cleanup` 对它退出码 3，提示「已接受验收、待授权合并，收回后合并要重新开会话」。等授权合并、合入后再收。
  - B：能。收回 worktree、保留分支；之后授权合并照样 `merge approve`、`merge run`（合并只看分支，不要会话）；但合并失败退回时没有会话接，需要重新开会话（`start prepare` 重开）。适合「验收了，合并可能要等很久」的情况。

## 关键决策与取舍（请重点审）

1. **命令放在 `merge` 下，叫 `merge accept`（新）**：最终验收的答复今天就归 `merge`（`review approve` 对最终验收退出 3、指向合并），接受验收与授权合并是同一个交审事项的两步，放在一起好记。
   参数和 `merge approve` 相同：可一次给多个 C 号，任一不合格什么都不写（退出码 3）；输出一条或多条【用户答复】发给模块，照转等待记录的【已恢复】。
   不用 `review accept`：那样同一件事分在两个命令组里。
2. **新状态 `accepted`，不是关闭（新）**：交审事项从 `open` 变成 `accepted`，带 `acceptance` 字段（原话、时间、来源、转给模块的【用户答复】正文号），事件记 `accepted`。不建合并批准事项，不进 `merge queue`。
   不用「关闭 + 新的 closedReason」：S48 的要求就是事项不关闭；而且关闭后 `merge approve` 会拒收，回到今天的问题。
3. **`merge approve` 收 `open` 或 `accepted`**：对 `accepted` 的事项不再核对待决问题（接受时已答全），合并批准事项照今天建，另记 `acceptedBy`（接受时的那条记录）；交审事项照今天关成 `answered`，`answer` 里同时留下接受与授权两段原话。
   对 `open` 的事项行为不变（一次批准 = 接受 + 授权）。
4. **`accepted` 在各处的行为**：
   - `review batch`、`review batch --for-hub`：不列（已经有用户的答复），不再提请批准。
   - 同步：算在「等最终验收」里，`merge run`、`change land`、`unqueued --notify` 都不给它发同步通知（同步会改分支、让接受作废）。
   - 阶段提示（模块会话的钩子）：新增一句「最终验收已接受（交审事项 C<号>），用户暂未授权合并：停在当前停点，不要再提交，等授权合并或退回」。
   - `module-crew status`：在用模块一行写「已接受验收、待授权合并（C<号>，接受于 <时间>）」；事项计数照算（它没关闭）。
   - 停滞检测：接受验收算作用户已答复，不报「等用户」卡住。
5. **离开 `accepted` 的三条路**：`merge approve`（授权合并）；`review answer`（用户改主意要修改：关成 `answered`、模块按意见改，与今天退回相同）；同一模块重新发最终验收【交审】（`review add` 把它关成 `superseded`，与今天的 `open` 相同）。不另做「撤回接受」。
6. **`sessions --json` 不加新阶段值（新）**：已接受验收的模块导出时和「最终验收已交审」用同一个值（今天两者都落在 `build`），不改导出的枚举，决策收件箱不用跟着改。新的阶段文字只出现在钩子与 `status`。
7. **提示文字**：`review approve` 对最终验收的拒绝改成「交审事项 C<号> 是最终验收：批准合并用 `merge approve`，只接受验收用 `merge accept`，要求修改用 `review answer`」；`review answer` 对最终验收照常执行，输出多一行「已按要求修改退回；如果用户只是接受验收、不批合并，应该用 `merge accept`（这次已经退回，要改须模块重新交审）」。代码不读原话判断意图。
8. **决策收件箱卡片**（按 D1 选 A 时）：`review batch --for-hub` 生成的最终验收卡片多一个选项「C：只接受验收，暂不授权合并」，「选了会怎样：记下验收结论，不合并、集成分支不变；之后你说一句授权合并就排进合并队列」；「你该回」仍推荐 A。Spec、Plan 的卡片不变。
9. **技能改写**（四份，Claude 与 Codex 两版内容对应）：
   - crew-coordinator「交审与批准」：命令块里 `review answer` 的注释保留「要求修改」，并写明对最终验收只用于要求修改；「批准一律走 `review approve`」改为只说 Spec、Plan、接口提案；最终验收一节把「用户批准（批准即授权合入本地集成分支）」改成按原话分三种：批准合并 → `merge approve`；只接受验收、不批合并 → `merge accept`；要求修改 → `review answer`；拿不准原话属于哪种就回头问用户，不往大里读。再加一条：已接受验收的事项，用户补授权合并时直接 `merge approve`，不用模块重新交审。
   - crew-dev「收到答复」：收到只接受验收的【用户答复】时停在原地，不勾、不提交、不重发交审，等授权合并或退回。
10. **改的范围限在必要处**：`merge.py`（accept、approve 收 accepted、awaiting_final）、`review.py`（拒绝提示、answer 提示、for-hub 卡片选项）、`hooks.py`（阶段）、`__main__.py`（子命令与输出）、`stall.py` 与 `status` 相关读取；其余状态逻辑不动。

## 接口约定

### 命令

- `merge accept <C号>… --original <原话> | --original-file <文件>`（模块协调；在 `_LOCKED` 之外，和 `merge approve` 一样不需要合并锁）。
  - 退出码：0 记下；2 读不到原话文件；3 拒绝、什么都没写（不是最终验收、事项已关闭或已接受、待决问题没答全——这时照 `merge approve` 列出要再问的问题）。
  - 输出：每个 C 号一行「C<号> 已接受验收，暂不合并（集成分支不变）；用户补授权合并后 `merge approve C<号>`」，接着「收件人／replyTo／正文文件」三行（与 `merge approve` 相同），最后照发等待记录的【已恢复】。
- `merge approve <C号>…`：参数与输出不变；对 `accepted` 的事项不核对待决问题。

### 记录

- 交审事项（`kind: review`, `node: final`）：`state` 新增取值 `accepted`；新增字段 `acceptance: {original, answeredAt, source…, body}`。
- 合并批准事项（`kind: merge-approval`）：新增字段 `acceptedBy`（接受验收那次的时间与正文号；一次批准的为 `null`）。
- 事件：`item.accepted`。

## 项目结构（要改的文件）

| 文件 | 改什么 |
|---|---|
| `module_crew/merge.py` | 新 `accept()`／`accept_many()`；`_approve_one` 收 `accepted`；`awaiting_final` 包括 `accepted` |
| `module_crew/review.py` | `add` 取代 `accepted`；`answer` 收 `accepted`；`_approve` 对最终验收的拒绝提示；for-hub 最终验收卡片选项 C（按 D1） |
| `module_crew/hooks.py` | 新阶段文字 `STAGE_ACCEPTED` 与判断 |
| `module_crew/failure.py` | `stage_code` 把新阶段映射到现有值 |
| `module_crew/stall.py` | 接受验收算作用户已答复 |
| `module_crew/__main__.py` | `merge accept` 子命令与输出；`review answer` 对最终验收的提示行；`status` 的一行（按 D2 时 `merge cleanup` 的拒绝） |
| `skills/crew-coordinator/SKILL.md`、`codex-skills/crew-coordinator/SKILL.md` | 关键决策 9 |
| `skills/crew-dev/SKILL.md`、`codex-skills/crew-dev/SKILL.md` | 关键决策 9 |
| `docs/commands.md`、`docs/guide.md` | 新命令与流程 |
| `tests/test_final_accept.py`（新） | 见验收标准 |

## 命令

```bash
python3 -m unittest discover -s tests
python3 -m unittest tests.test_final_accept
```

## 代码风格

照现有代码：标准库、`dataclass` 结果、拒绝用 `AnswerRefused`、一次事务内全成或全不写；注释英文、简短，写依据（如 `# crew-final-accept-split: …`）。

## 测试策略

单元测试用 `tests/helpers.py` 现有的状态库与 git 夹具；先写失败的测试再改。CLI 行为用现有 `_run` 风格的子进程测试。技能、文档的说法用文字断言（与 `tests/test_skills.py`、`tests/test_docs.py` 同法）。

## 边界

- 始终：接受验收与授权合并各要一段用户原话；任一编号不合格整批不写。
- 先问：原话看不出是接受验收、授权合并还是要求修改（技能里写：回头问用户）。
- 绝不：把接受验收当授权合并；对已接受验收的模块发同步通知；按倾向替用户答待决问题。

## 验收标准

1. AC1：`merge accept C<n>` 对 `open` 的最终验收：事项变 `accepted`、记下原话，不建合并批准、`merge queue` 为空，集成分支 HEAD 不变，输出【用户答复】。
2. AC2：之后 `merge approve C<n>` 成功：建合并批准（带 `acceptedBy`），交审事项关成 `answered` 且留两段原话；不再要求答待决问题；`merge run` 照常合入。
3. AC3：`merge accept` 拒绝（退出码 3、状态库不变）：不是最终验收、已关闭、已接受、待决问题没答全；多编号里一个不合格整批不写。
4. AC4：`accepted` 的事项不出现在 `review batch` 与 `--for-hub`；`merge run` 与 `change land` 不给该模块发同步通知。
5. AC5：同一模块重新 `review add` 最终验收时旧的 `accepted` 事项关成 `superseded`；`review answer` 对 `accepted` 的事项成功并关成 `answered`。
6. AC6：模块会话的阶段提示为新文字；`sessions --json` 的阶段值与「最终验收已交审」相同；`status` 显示「已接受验收、待授权合并」；停滞检测不把它报成等用户。
7. AC7：`review approve` 对最终验收的拒绝提示同时点名 `merge approve`、`merge accept`、`review answer`；`review answer` 对最终验收的输出多那一行提示。
8. AC8（按 D1）：A 时最终验收 for-hub 卡片有选项 C，通过 `protocol check`；Spec、Plan 卡片不变。B 时卡片不变。
9. AC9（按 D2）：A 时 `merge cleanup` 对已接受验收的模块退出码 3；B 时允许，且之后 `merge approve`、`merge run` 仍能合入。
10. AC10：四份技能不再有「批准一律走 `review approve`」（未限定节点的写法）和「批准即授权合入」；都写明 `merge accept` 与三种答复的分法；crew-dev 写明收到只接受验收时停在原地。`tests/test_skills.py` 覆盖。
11. AC11：`docs/commands.md` 有 `merge accept`；`docs/guide.md` 有「只接受验收、暂不合并」；`tests/test_docs.py` 通过。
12. AC12：全部测试通过。

## 并行边界

只改上面「项目结构」表里的文件；不改 `spec/` 下其他模块的 Spec、能力图、`interface.json`、插件清单。

## 未决问题

- 无（D1、D2 待用户决定）。

## 文档建议

`docs/guide.md` 的「完整流程」最终验收一步和「出状况」各加一条「只接受验收、暂不合并」（范围内第 7 条已含）；`docs/commands.md` 加 `merge accept`；README 无需改（入门命令不涉及）；CHANGELOG 随发版写入。

## 变更记录
