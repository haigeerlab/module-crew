<!-- spec-guard: review approved 20ecf128cd5b -->
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

**范围外**

- 判断改动是否在已批准 Spec 范围内、是否需要问用户（协调会话判断；命令只给提示）。
- 替协调会话改文件；推送；已批准 Spec 的变更记录（协调会话按 spec-guard 规则写）。

## 假设（用户 2026-10-18 已确认）

1. `change add` 记成 `request`（文件、改什么、为什么、是否完全停住）；完全停住时为发件人开等待单（在等协调会话）；发件人须登记，重复提交只记一次。
2. 命令按路径打「要问用户」提示：锁文件／包清单（新增依赖）、CI 配置（`.github/`、`.gitlab-ci.yml` 等）、迁移（路径含 `migration`）、与另一条未处理请求改同一文件；范围内外由协调会话读 Spec 判断。
3. 协调会话在集成 checkout 里改；`change land <编号>` 核对改动只涉及该请求列出的文件，单独提交（提交信息写请求编号），关请求与等待单，生成消息。
4. 回复请求方：同步基线类【协调通知】，首行「回复：#原请求号」，依据「公共变更请求 #N 已在集成基线提交 <提交号>」；其他在用模块各一条同步基线通知（不带回复行）。
5. 要问用户：协调会话在自己对话里问；同意就 `land` 并记下用户原话；不同意用 `change answer` 生成【用户答复】、关请求，不碰基线。
6. 按到达顺序处理；`change list` 只读列出未处理请求、提示与冲突。
7. 影响已批准 Spec 时由协调会话追加变更记录（写进 skill）。

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
- **提交信息与提交钩子**（2026-10-18 修订）：提交信息一律以 `chore(crew): ` 开头（符合 Conventional Commits，首行不超过 100 字符），后面照旧写中文说明与编号；提交失败且仓库启用了提交钩子时，原因写「提交钩子拒绝：<钩子输出首行>」，不并入其他原因。（2026-10-18 修订）请求摘要在提交信息里截到 40 字。


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
bin/module-crew change land <编号> [--original <原话> | --original-file <文件>]
bin/module-crew change answer <编号> (--original <原话> | --original-file <文件>)
```

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


## 未决问题

无。

## 文档建议

README 增加「公共文件怎么改」一小节；本模块不另写文档。

## 变更记录

- 2026-10-18：`change land` 的提交信息加 `chore(crew): ` 前缀、摘要截到 40 字，提交钩子拒绝时单独标原因；增加对应验收。原因：module-crew 的提交过不了前端的 commitlint；来源：联合演练批 2 准备（前端 husky 跑 `@commitlint/config-conventional`，lint-staged 对全部暂存文件跑 `oxfmt --check`），用户 2026-10-18 批准先修再发 0.1.1。
