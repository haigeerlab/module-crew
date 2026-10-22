<!-- spec-guard: review approved 95209d55ef03 -->

# Spec: crew-review-display

> 能力图模块 `crew-review-display`（第七版第 4 个，最后一个）。需求来源：`docs/requirements-record.md` 第 16 节第 1～4、13 条（用户 2026-10-22 确认；第 13 条选 A）。
> 依赖 `crew-review-batch`（提请批准正文）、`crew-contract-v26`（C 待定编号、答复块、「验收结果」）。标「新」的是写 Spec 时补的实现取舍，请重点审。

## 目标

模块协调给用户看的审批消息，和 spec-guard 在单会话里呈现的样子一致、内容可核对：最终验收列出真实的改动、提交与依赖，Spec 中途改过就附差异；
开工、公共变更请求、卡住选做法三类请示有固定骨架；多模块并行时独占重叠按交审中的 Spec 真实比对，比不了就照实说「未比对」，不再误报「无」。

## 范围

**范围内**

1. **最终验收呈现**：`review batch`（含 `--for-hub`）在最终验收节点，从交审时的模块分支提交生成，按 spec-guard `reviewKinds.final` 的小项顺序：
   做了什么、验收结果、改了哪些文件、Spec 中途改过吗；「改了哪些文件」一项依次是文档表、代码文件表（新增／修改／删除与行数，Plan「会改哪些文件」以外的标「超出 Plan」）、
   提交表（短号与标题）、新增依赖表（没有写「无」）；Spec 中途改过时原样附差异（crew-merge 决策 10 记下的 `specRevised`）。
2. **三种请示模板**：开工（`start plan` 提请开工）、公共变更请求（`change add` 提请批准）、卡住选做法（模块发来「类型：卡住选做法」的【等待用户】）给用户看的正文，骨架同 spec-guard：
   标题行「<模块> · <节点> · <编号>」、固定小项、之后「注意」「推荐理由」「批了会怎样」三行（注意没有写「无」）、一个最短复制块（契约 v2.6 答复块写法）。
3. **多模块分节**：几个模块合在一条消息时按模块分节、按 Build order 排（现有行为，加测试守住）。
4. **skill**：crew-coordinator 写明决定内容一律写在下一步框之前的正文里；框的按钮至多对应前两块，其余复制块写在框前正文。
5. **独占重叠**（第 13 条）：
   - 先改误报：本批有交审中的 Spec 还没落到集成分支时，「并行边界重叠」不写「无」，写「未比对：<模块…> 的 Spec 还在交审中」；
   - 装的 spec-guard 声明了 `scopeOverlap`（interface 1.10）时，用 `git show` 把交审提交里的 Spec 存成临时文件，以 `--spec <模块>=<文件>` 传入、同时带 `--project <集成 checkout>`，
     报出 `conflicts`（模块、路径）与 `errors`（照实列出）；没有这个声明时写「未比对：spec-guard 低于 1.10」。

**范围外**

- 改 spec-guard 的小项定义或判定规则；自己解析 Spec 的独占清单。
- 改审查者、模块会话的消息写法（契约已定）。
- 推送、发版。

## 假设

1. spec-guard `reviewKinds.final` 的四个小项在 interface 1.x 内只增不改（它的声明写明 add-only）；module-crew 按声明里的顺序取，不写死。
2. 「文档」= 路径在 `docs/`、`README*`、`CHANGELOG*`、`*.md`（`spec/`、`tasks/` 除外）；其余为代码文件。`spec/`、`tasks/` 不进两张表（Spec 另附差异）。
3. 「新增依赖」只能从依赖清单文件的改动看出：`package.json`、`pyproject.toml`、`requirements*.txt`、`go.mod`、`Cargo.toml`、`Gemfile` 里新增的行；锁文件不列。识别不了的清单照实写「<文件> 有改动，请看差异」。
4. scopeOverlap 随 spec-guard 0.84.0 发版；本机装上之前只能用测试里的假 spec-guard 验证这一路，实测记为「未验证」直到装上。
5. 三种请示目前都在会话里问用户（决策收件箱只收交审卡）；本模块不新增给决策收件箱的卡类型。

## 关键决策与取舍（请重点审）

1. **（新）最终验收的四张表都从版本库算**：比对范围是集成分支与交审提交的合并基点到交审提交（`git diff --numstat <base>..<commit>`、`git log --oneline <base>..<commit>`），不信模块自己写的统计；
   模块写的「改动统计」照旧保留在交审原文里。
2. **（新）超出 Plan 的判定**：取集成分支上已批准的 `tasks/<模块>/plan.md` 里出现的路径（反引号包着的路径、或「会改哪些文件」那一节的行），代码文件不在其中就标「超出 Plan」；Plan 里读不出路径时整列写「无法判断（Plan 没写文件）」，不猜。
3. **三种模板共用一个渲染函数**，字段名照 spec-guard 的 `reviewKinds` 与契约 v2.6；开工的固定小项是「开哪些模块」「各自的 worktree 与分支」「会话从哪个宿主开」，公共变更是「改哪些文件」「为什么要改」「谁在等」，
   卡住选做法沿用契约的「出了什么事」与模块给的选项。
4. **重叠比对的结论分三种写法**：有冲突「⚠️ 并行边界重叠：…」；比对过、没冲突也没错误「并行边界重叠：无（已按交审中的 Spec 比对）」；比不了「未比对：<原因>」。只有第二种才写「无」。
5. **临时文件放状态库目录下的 `tmp/`**，用完覆盖不删（状态库不删除的约束）；同名按交审号命名，下次覆盖。

## 接口约定

- `review batch [--json]`：`--json` 的每个最终验收项增加 `display`：`{"docs": [...], "code": [...], "commits": [...], "dependencies": [...], "specDiff": str | null}`；
  批次增加 `overlap`：`{"state": "conflicts" | "none" | "unchecked", "conflicts": [...], "errors": [...], "reason": str | null}`。
- `start plan`、`change add`、`inbox add`（卡住选做法）的输出多一段「给用户看的正文」。
- 退出码不变。

## 项目结构

```text
module_crew/present.py      新：最终验收四张表、三种模板、重叠结论
module_crew/review.py       batch／for-hub 调用 present；scopeOverlap 调用
module_crew/start.py, changes.py, inbox.py, __main__.py   三种模板接入
skills/crew-coordinator/SKILL.md、README.md
tests/test_review_display.py
```

## 命令

```bash
python3 -m unittest discover -s tests
PYTHONPATH=tests python3 -m unittest test_review_display
```

## 代码风格

沿用现有模块：代码与注释英文，输出中文；只用标准库；git 带超时、不经 shell。

## 测试策略

- 最终验收：模块改了一个文档、两个代码文件（其中一个不在 Plan 里）、删一个文件、改 `package.json` 加一个依赖、两个提交 → 四张表内容、超出 Plan 标记、依赖表都对；改过 Spec 时附差异；Plan 没写文件时那一列写无法判断。
- 三种模板：各生成一次，标题行、固定小项、三行、复制块齐全，复制块按答复块写法、没有占位符。
- 分节：两个模块合一条时按 Build order 分节。
- 重叠：交审中的 Spec 未落集成分支、spec-guard 没有 scopeOverlap → 「未比对」；假 spec-guard 声明 1.10 并返回冲突 → 列出冲突；返回 errors → 照实列出且不写「无」；比对无冲突无错误 → 「无（已按交审中的 Spec 比对）」。
- 回归：全量测试通过。

## 边界

- **始终**：统计从版本库算；比不了就写「未比对」；临时文件不删、只覆盖。
- **先问**：给决策收件箱新增卡类型；自己解析 Spec 独占清单。
- **绝不**：在没有比对时写「并行边界重叠：无」；把模块自报的统计当成事实列表。

## 验收标准

1. 最终验收的提请批准正文按「做了什么、验收结果、改了哪些文件、Spec 中途改过吗」排；「改了哪些文件」含文档表、代码文件表（新增／修改／删除与行数，超出 Plan 的标出）、提交表、新增依赖表（无写「无」），数据取自版本库；Spec 中途改过时附差异。
2. Plan 里读不出文件路径时，「超出 Plan」一列写「无法判断（Plan 没写文件）」。
3. 开工、公共变更请求、卡住选做法三种请示的正文有标题行「<模块> · <节点> · <编号>」、固定小项、「注意」「推荐理由」「批了会怎样」三行与一个最短复制块，复制块没有占位符。
4. 几个模块合一条消息时按模块分节、按 Build order 排。
5. crew-coordinator skill 写明决定内容写在下一步框之前、按钮至多对应前两块。
6. 交审中的 Spec 没落到集成分支、且没有 scopeOverlap 时写「未比对」而不是「无」；有 scopeOverlap 时按交审提交里的 Spec 比对，冲突与 errors 照实列出，只有比对过且两者皆空才写「无（已按交审中的 Spec 比对）」。
7. 全量测试通过；scopeOverlap 的本机实测在 spec-guard 0.84.0 装上后补做，之前记为「未验证」。

## 未决问题

- 无。

## 文档建议

README「一次完整流程」的最终验收一步写明提请批准里会列哪几张表；「审查就近与决策收件箱」写明并行边界重叠的三种结论。CHANGELOG 随发版写。
