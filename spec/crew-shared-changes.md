<!-- spec-guard: review approved bb57b8f7a09b -->

# Spec: crew-shared-changes

> 能力图模块 `crew-shared-changes`。需求来源：`docs/requirements-record.md` B3（公共文件变更）、B1（协调会话管集成基线与公共文件）、上游 Boundaries 的 Ask first；
> 契约 session-protocol v1.4（【公共变更请求】【协调通知】）。假设见下文，用户 2026-10-18 已确认。

## 目标

模块会话不改公共文件；要改时发【公共变更请求】。协调会话用命令记账、看分流提示、需要时问用户，然后在集成基线上单独提交这次改动，
回复请求方并通知所有在用模块同步基线。完全停住的请求方有等待单，改动落地时一并关掉。

## 范围

**范围内**

- `module_crew/changes.py` 与命令 `module-crew change add|list|land|answer`。
- `request` 记录的字段与流转；请求方完全停住时的等待单。
- `skills/crew-coordinator/SKILL.md` 增加「公共变更请求」一节、更新收件表退出码 4 的去向。
- （0.17.0）`change land` 一次落地多个已批请求，合成一个提交，落地前先跑检查、整批成败（关键决策 7）。
- （0.17.0）`change add` 认出锁文件改动时，提示项目登记的保护文件可能要连带改；名单用 `config set --protected-file` 凭用户原话写进运行配置（关键决策 8）。

**范围外**

- 判断改动是否在已批准 Spec 范围内、是否需要问用户（协调会话判断；命令只给提示）。
- 替协调会话改文件；推送；已批准 Spec 的变更记录（协调会话按 spec-guard 规则写）。
- （0.17.0）`change amend`（给已记账的请求补文件清单）；替项目猜保护文件（扫仓库、按文件名推断）；项目开关（假设 A4：批量落地与保护文件提示都不加开关）。

## 假设（用户 2026-10-18 已确认）

1. `change add` 记成 `request`（文件、改什么、为什么、是否完全停住）；完全停住时为发件人开等待单（在等协调会话）；发件人须登记，重复提交只记一次。
2. 命令按路径打「要问用户」提示：锁文件／包清单（新增依赖）、CI 配置（`.github/`、`.gitlab-ci.yml` 等）、迁移（路径含 `migration`）、与另一条未处理请求改同一文件；范围内外由协调会话读 Spec 判断。
3. 协调会话在集成 checkout 里改；`change land <编号>` 核对改动只涉及该请求列出的文件，单独提交（提交信息写请求编号），关请求与等待单，生成消息。
4. 回复请求方：同步基线类【协调通知】，首行「回复：#原请求号」，依据「公共变更请求 #N 已在集成基线提交 <提交号>」；其他在用模块各一条同步基线通知（不带回复行）。
5. 要问用户：协调会话在自己对话里问；同意就 `land` 并记下用户原话；不同意用 `change answer` 生成【用户答复】、关请求，不碰基线。
6. 按到达顺序处理；`change list` 只读列出未处理请求、提示与冲突。
7. 影响已批准 Spec 时由协调会话追加变更记录（写进 skill）。

## 0.17.0 修订的假设

来源：用户在 mc-coord 原话「0.17.0 需求就是这四件，前提假设 A1～A5 全按推荐」。A2～A4 是本模块用到的那几条；B1～B5 是写 Spec 时补的细节，**请审**。

- A2：批量落地前先跑检查：检查记账 `checkLedger` 开着跑快检查，没开跑完整检查 `checkCommand`；任一请求不满足或检查不过，整批不提交。
- A3：保护文件名单只认项目登记、凭用户原话写进运行配置；没登记只给通用提示，不猜。
- A4：不加项目开关。
- B1：A2 的检查只管批量（给了两个及以上编号）；单个编号的 `change land` 行为不变（检查记账没开时照旧不跑检查），已有用法和测试不受影响。
- B2：检查记账没开、又没有完整检查命令（`checkCommand` 由第一次 `merge run --check-command` 写入）时，批量落地拒绝；用户同意不检查时加 `--skip-check --original-file <原话文件>`。
  `--skip-check` 是 `--skip-quick-check` 的新名字，两个写法都认，单个编号照旧。
- B3：批量不和 `--partial`、`--from-module` 一起用；要部分落地或提前落地就逐条落。
- B4：锁文件按文件名认：`pnpm-lock.yaml`、`package-lock.json`、`yarn.lock`、`poetry.lock`、`uv.lock`、`Cargo.lock`、`go.sum`、`Gemfile.lock`；`uv.lock` 同时补进依赖提示的名单（只增不改）。
- B5：保护文件提示只是输出里的几行，不进 `hints`、不改变「要问用户」与否（锁文件本来就带 `dependency` 提示）。

## 关键决策与取舍（请重点审）

1. **`land` 的核对以 `git status --porcelain` 为准**：集成 checkout 里所有改动（含新增、删除、未跟踪）都必须在请求的文件清单内，且清单里至少一个文件真的变了；
   否则拒绝（退出码 3），什么都不提交。这样协调会话不会把别的改动混进这次提交。
2. **`land` 先提交、后记账**：`git add` 清单文件 → `git commit` → 一个状态库事务（关请求、关等待单、写通知正文）。提交失败就停（退出码 4），状态库不变，改动留在 checkout。
   提交信息里的请求编号就是请求记录自己的编号（已存在），不需要预先分配。
3. **用户原话是可选的**：`land --original-file` 给了就记进请求（「问过用户，用户同意」）；没给表示协调会话按范围内直接办。命令不判断该不该问（假设 2），
   但请求带「要问用户」提示而 `land` 没给原话时，输出里提醒一句，不拒绝。
4. **分流提示的规则写死在代码里、只增不改**：锁文件与包清单按文件名（`package.json`、`pnpm-lock.yaml`、`package-lock.json`、`yarn.lock`、`requirements*.txt`、
   `pyproject.toml`、`poetry.lock`、`Cargo.toml`、`Cargo.lock`、`go.mod`、`go.sum`、`Gemfile`、`Gemfile.lock`），CI 按前缀（`.github/`、`.gitlab-ci.yml`、`.circleci/`），
   迁移按路径里含 `migration`（不分大小写），冲突按「另一条 `open` 请求的文件清单有交集」。
5. **给请求方的回复用同步基线通知加「回复：#N」首行**：契约里协调会话没有别的回复类型；`render_coordination_notice` 生成后在前面加这一行，再用 `protocol.parse` 自检（契约第 2 节允许开头的回复行）。
6. **其他模块收到的是同一份依据、不带回复行的通知**；退役的会话不发。
- **提交信息与提交钩子**（2026-10-18 修订）：提交信息默认以 `chore(crew): ` 开头（符合 Conventional Commits，首行不超过 100 字符；0.9.4 起前缀是项目配置 `commitPrefix`，`start prepare --commit-prefix <值>` 设定，空字符串表示不加，没设过按默认），后面照旧写中文说明与编号；提交失败且仓库启用了提交钩子时，原因写「提交钩子拒绝：<钩子输出首行>」，不并入其他原因。（2026-10-18 修订）请求摘要在提交信息里截到 40 字。
7. **（0.17.0）`change land C96 C99`：几个已批请求合成一个提交，整批成败**（S43：LIVE-SAAS C96 改 `upstream-policy.json`、C99 改 `foundation-approval.sha256`，只能分两次提交，中间提交 `0d45639` 在 `check:upstream` 红着时做的）。
   - 先核对、后暂存：编号不重复；每条请求都存在且 `open`；每条请求清单里的文件都有改动；集成 checkout 的全部改动（含未跟踪）都在这几条清单的并集里。任一不满足退出码 3，什么都不暂存、不提交，状态库不变，输出逐条写出哪条请求、哪个文件不满足。
   - 再检查：暂存并集后，检查记账开着就对暂存的树跑快检查并记账（和单条落地同一个函数）；没开就在集成 checkout 跑完整检查 `checkCommand`（不经 shell、按 `checkTimeout` 限时，不记账）；都没有见假设 B2。
     检查不过（退出码 5）或没跑成（退出码 4）：不提交，文件保持暂存，请求全都开着，输出写清怎么重试或请用户同意跳过。
   - 一个提交：提交信息 `<前缀>公共变更请求 C96、C99（发件人1、发件人2）：<改什么1>；<改什么2>`，首行照旧不超过 100 字符（超出截断）；提交失败、超时、钩子拒绝的处理与单条相同（退出码 4，请求全都开着）。
   - 记账：每条请求关为 `landed`，记同一个提交号和 `batch: [96, 99]`，给了原话就每条都记；各自的等待单关闭。带「要问用户」提示的请求没给原话时照旧提醒一句。
   - 通知：每个在用模块会话一条同步基线通知，依据「公共变更请求 C96、C99 已在集成分支提交 <提交号>」。请求方的那条首行「回复：#<它在这批里编号最小的那条请求的原消息号>」；
     同一请求方在这批里还有别的请求时，输出里给出 `alsoAnswers`（其余原消息号），发送时一并关掉。跳过同步的规则与单条相同。
8. **（0.17.0）锁文件连带保护文件提示**：运行配置新增 `protectedFiles`（仓库相对路径的列表），用 `config set --protected-file <路径>`（可重复，整份替换）写入、`--clear-protected-files` 清空，都要用户原话，记进配置事件。
   路径必须是相对路径、不含 `..`，不检查是否存在。`change add` 记账成功、请求清单里有锁文件（假设 B4）时：
   - 登记过名单：列出名单里**不在**本请求清单内的保护文件——「锁文件改动（<锁文件>）：项目登记的保护文件可能要连带改：X、Y；要改就请请求方另发请求，和这条一起 `change land`」；全都在清单内就不提示。
   - 没登记：一行通用提示「锁文件改动（<锁文件>）：项目没登记保护文件（`config set --protected-file`）；如果有随锁文件校验的文件（哈希、审批清单等），问请求方要不要连带改」。不扫仓库、不按文件名猜。


## 接口约定

### 记录

```json
// request（键 = 编号）
{"state": "open", "from": "shop-b", "relayId": 4700, "text": "【公共变更请求】...", "files": ["package.json", "pnpm-lock.yaml"],
 "what": "...", "why": "...", "fullyStopped": true, "hints": ["dependency"], "ticket": 18,
 "closedReason": null, "commit": null, "answer": null}
// 落地后：state=closed, closedReason="landed", commit=<提交号>, answer={"original": ...} 或 null
// 被拒：state=closed, closedReason="declined", answer={"original": ..., "body": N}
```

提示代码：`dependency`、`ci`、`migration`、`conflict:<编号>`。

### 命令

```bash
bin/module-crew change add <文件> --from <邮箱名> --relay-id <M>
bin/module-crew change list [--json]
bin/module-crew change land <编号> [<编号> ...] [--original <原话> | --original-file <文件>] [--skip-check]
bin/module-crew change answer <编号> (--original <原话> | --original-file <文件>)
bin/module-crew config set (--protected-file <路径> [--protected-file <路径> ...] | --clear-protected-files) (--original <原话> | --original-file <文件>)
```

（0.17.0）`change land` 给两个及以上编号时按关键决策 7 整批落地，退出码同单条（`0` 成功；`3` 拒绝；`4` 检查没跑成或提交失败；`5` 检查不过）；
每条要发的消息另带 `alsoAnswers`（没有时不写）。批量记录：`{"state": "closed", "closedReason": "landed", "commit": "<同一提交>", "batch": [96, 99], ...}`。

- `change add`：`0` 已记账（或已记过），输出编号、提示与「要问用户」与否；`3` 拒收（不合格、未登记）；`2` 参数错。
- `change list`：`0` 有未处理请求；`3` 没有。
- `change land`：输出提交号与要发送的消息（收件人、`replyTo`（只有请求方有）、正文路径）；`0` 成功；`3` 请求不存在或已关闭、集成 checkout 的改动超出清单或没有改动；`4` 提交失败；`2` 参数错。
- `change answer`：输出收件人、`replyTo`、正文路径；`0` 成功；`3` 请求不存在或已关闭。

## 项目结构

```text
module_crew/changes.py
module_crew/__main__.py            加 change 子命令
skills/crew-coordinator/SKILL.md   加「公共变更请求」一节、更新收件表
tests/test_changes.py
```

0.17.0 修订只改这几个文件（不碰 crew-light-task 这轮要改的 `module_crew/tasks.py`、`module_crew/review.py`）：

| 文件 | 改哪里 |
|---|---|
| `module_crew/changes.py` | 新增 `LOCK_FILES`、`land_batch(project, numbers, original, skip_check)`、`protected_lines(files, cfg)`；`add` 在输出里加保护文件提示；`DEPENDENCY_FILES` 补 `uv.lock` |
| `module_crew/__main__.py` | `change land` 的 `number` 改为可多个，两个及以上走 `land_batch`，输出 `alsoAnswers`；`--skip-check` 与 `--skip-quick-check` 同义；`_config_set` 与 `config set` 解析器加 `--protected-file`、`--clear-protected-files` |
| `skills/crew-coordinator/SKILL.md` | 「公共变更请求」一节加批量落地与登记保护文件两段 |
| `tests/test_changes.py`、`tests/test_skills.py` | 新增测试 |

`__main__.py` 是两个模块共用的入口：本模块只动 `_change`、`_config_set` 和 `change`、`config set` 两段解析器，合并时如有冲突由后合并的一方 `module-crew sync` 解决。

## 命令

```bash
python3 -m unittest discover -s tests -v
```

## 代码风格

沿用前几个模块；解析走 `protocol`，状态走 `store` 事务，集成 checkout 用 `probe._checkout_of`。

## 测试策略

- 复用 crew-review-batch 的测试基类（两个模块会话 b、c 已开），在主 checkout（集成分支 main）上改文件后 `land`。
- 断言集成分支只多一个提交、只含清单文件，提交信息含请求编号；消息正文可被 `protocol.parse` 判为合格。

## 边界

- **始终**：只提交请求清单里的文件；先提交后记账；通知所有在用模块同步。
- **先问**：清单外的公共文件要一起改（让请求方补一条请求或由用户决定）。
- **绝不**：替协调会话改文件；推送；在模块分支上改动。

## 验收标准

1. 合格【公共变更请求】：记成 `request`，`open`，带文件、改什么、为什么、是否完全停住；完全停住时开一张等待单（`from` 为请求方，`waitingFor` 为协调会话），记录里存等待单编号。
2. 拒收且不写：未登记或已退役的发件人；不合格消息。同一 `--relay-id` 重复提交只记一次。
3. 提示：改 `package.json` 给 `dependency`；改 `.github/workflows/ci.yml` 给 `ci`；改 `db/migrations/001.sql` 给 `migration`；与另一条未处理请求同改 `tsconfig.base.json` 时两条都给 `conflict:<对方编号>`；`change add` 输出「要问用户」。
4. `change list` 按到达顺序列出未处理请求及提示；没有时退出码 3。
5. `change land`：集成分支多一个提交，只含清单内被改的文件，提交信息含请求编号；请求关为 `landed` 并记提交号；对应等待单关闭（原因 3）；
   给请求方一条带「回复：#原请求号」的同步基线通知、给其他在用模块各一条不带回复行的同步基线通知，正文都能被 `protocol.parse` 判为合格；退役会话不收。
6. `land` 拒绝（退出码 3，什么都不提交、状态库不变）：集成 checkout 有清单外的改动或未跟踪文件；清单文件都没变；请求不存在或已关闭。
7. 带「要问用户」提示的请求 `land` 时没给原话：照常落地，输出提醒；给了原话：记进请求。
8. `change answer`：生成【用户答复】给请求方、请求关为 `declined`、等待单关闭（原因 3），集成基线不变。
9. `inbox add` 收到合格【公共变更请求】仍返回 4；协调会话 skill 收件表写明「改用 `change add`」，并有「公共变更请求」一节：`change add` → 看提示与 Spec 范围决定是否问用户 → 在集成 checkout 改 → `change land` 或 `change answer` → 按输出发送 → 影响已批准 Spec 时追加变更记录。
- 集成 checkout 装只认 `类型(范围): ` 开头的 commit-msg 钩子时 `change land` 照常提交；钩子拒绝时退出码 4、请求不关、输出含「提交钩子拒绝」。（2026-10-18 修订）
（0.9.4）`commitPrefix`：没设过时三类提交（公共变更、批准、合并）都以 `chore(crew): ` 开头，和以前一字不差；`start prepare --commit-prefix ""` 后不加前缀；设成 `feat(crew): ` 后按它写；首行仍不超过 100 字符。

### 0.17.0 修订的验收

10. 批量落地：两条 `open` 请求（不同请求方，其中一条完全停住）各自清单的文件都改了，`change land <a> <b>` 后集成分支只多一个提交，只含两份清单里的文件，提交信息含 `C<a>、C<b>`；两条请求都是 `landed`、同一提交号、`batch` 为 `[a, b]`；等待单关闭；
    两个请求方各收一条带自己「回复：#原消息号」的同步基线通知，其他在用模块各一条不带回复行的，正文都能被 `protocol.parse` 判为合格。
11. 同一请求方的两条请求一起落地：它只收一条通知，`replyTo` 是编号小的那条的原消息号，`alsoAnswers` 是另一条的。
12. 整批拒绝（退出码 3，集成分支没有新提交、没有暂存、状态库不变）：其中一条已关闭或不存在；其中一条的清单文件没改；有两份清单之外的改动；编号重复；与 `--partial` 或 `--from-module` 一起用。
13. 落地前检查：检查记账开着时对暂存的树跑快检查并记账，快检查不过退出码 5、不提交、请求全开着；没开且有 `checkCommand` 时跑完整检查，不过退出码 5、不提交、检查账里不多记录；
    没开又没有 `checkCommand` 时退出码 3，加 `--skip-check --original-file` 后照常落地并在每条请求上记下跳过检查的原话；`--skip-check` 没给原话退出码 3。
14. 单个编号的 `change land` 行为不变：已有的 `change land` 测试全部照旧通过；`--skip-quick-check` 仍可用。
15. 保护文件提示：`config set --protected-file a.sha256 --protected-file policy.json --original-file <文件>` 后配置里是这两个路径、配置事件带原话；
    请求改 `pnpm-lock.yaml` 和 `policy.json` 时 `change add` 只提示 `a.sha256`；两个都在清单里时不提示；没登记时给通用提示一行；请求不含锁文件时没有这类提示；
    `--protected-file ../x` 或绝对路径退出码 3、配置不变；`--clear-protected-files` 清空；「要问用户」与否不变。
16. 协调会话 skill 的「公共变更请求」一节写明：几条已批请求要一起进基线时用 `change land <编号> <编号> ...`（整批成败、先检查）；按用户原话用 `config set --protected-file` 登记保护文件。

## 未决问题

无。

## 文档建议

README 增加「公共文件怎么改」一小节；本模块不另写文档。
（0.17.0）README 的公共文件一节补一句：几条已批请求可以 `change land` 一次落地；保护文件名单用 `config set --protected-file` 登记。

## 变更记录

- 2026-10-18：`change land` 的提交信息加 `chore(crew): ` 前缀、摘要截到 40 字，提交钩子拒绝时单独标原因；增加对应验收。原因：module-crew 的提交过不了前端的 commitlint；来源：联合演练批 2 准备（前端 husky 跑 `@commitlint/config-conventional`，lint-staged 对全部暂存文件跑 `oxfmt --check`），用户 2026-10-18 批准先修再发 0.1.1。
- 2026-10-22：提交前缀从写死的 `chore(crew): ` 改为项目配置 `commitPrefix`（默认值不变、可设为空），只为 LIVE-SAAS 的 commitlint 写死的规矩不再强加给所有项目；行为对现有项目不变。来源：本会话职责边界审查第 1 条，用户 2026-10-22 选「默认仍是 chore(crew): ，可配置；各自追加到对应模块」。
- 2026-10-27：加入一次落地多个公共变更请求（关键决策 7，验收 10～14）与锁文件连带保护文件提示（关键决策 8，验收 15、16），补 0.17.0 假设 A2～A4、B1～B5 与改动文件表；评审标记改回 pending。原因：S43（LIVE-SAAS C96、C99 只能分两次提交，中间提交在检查红着时做的）；来源：用户在 mc-coord 原话「0.17.0 需求就是这四件，前提假设 A1～A5 全按推荐」（开工批准 C277）。
