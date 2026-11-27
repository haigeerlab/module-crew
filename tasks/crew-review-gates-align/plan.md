# Implementation Plan: crew-review-gates-align

<!-- spec-guard: review approved -->

> 依据：`spec/crew-review-gates-align.md`（用户 2026-11-27 批准，事项 C881「C881 A」，落地于集成分支 2409189）。任务清单：`tasks/crew-review-gates-align/todo.md`。

## Overview

先做 `review add` 对缺审查记录的新流程需求拒收（Task 1），再在它读到的审查状态上做交用户时的展示与 `review show --review-diff`（Task 2，依赖 Task 1 的读取入口），
`review approve` 认出 `requirement-unreviewed`（Task 3），普通需求无第二审查者交用户批（Task 4，与前三项互不依赖）。
最后改文档与 crew-flow-v2 的变更记录（Task 5，公共文件），同步、跑检查、用本机 spec-guard 0.100.0 实测（Task 6）。
每个任务先写失败的测试、看到红再实现到绿，在本模块分支本地提交；不推送、不发版。

## Architecture Decisions

- **读取入口放 `flow.py`**：新增 `flow.requirement_review(worktree, module_id) -> dict | str | None`，在模块 worktree 上直接调 `probe.run_map`（不走 `takeover._map` 的缓存，Spec 决策 3），返回该模块行的 `requirementReview`；读不出返回原因字符串，老流程或字段缺失返回 None。只判 `status == "missing"`，其余一律放行。
- **拒收在 `review.add` 的 `reasons` 里加**：节点为 `spec`、`interface` 时调用，`missing` 时追加一条原因（三条命令按 Spec 决策 2，含 `/spec-guard:review-mark` 的完整参数），走现有退出码 3、什么都不记；读不出时把提示行放进收下后的 `out.lines`。
- **差异照 spec-guard 原话**：`review.requirement_diff(worktree, module_id)` 用 `mark_args` 拼 `reviewMark --target spec --state approved`（不带 `--confirm`）在模块 worktree 上跑，取「Changes since the review」之后的差异块，或「nothing changed」「cannot be shown」那一行；不自己算差异。
  批次展示、决策收件箱交审卡（`_hub_item`）、`review show --review-diff` 三处共用它；只对 `requirementReview` 不为 null 的模块出这一行，老流程展示逐字不变。
- **`review approve` 只加一句**：`_approve` 写标记失败时，输出首行以 `requirement-unreviewed` 开头就在「已停下」之后加 Spec 决策 6 的说明；还原逻辑不动。
- **`codex_note` 不再分档位**：删掉 `_no_reviewer` 后的放行分支，两档都进 `no_reviewer_draft`；草稿的现状一句按 `module(...).tier` 选文字（`important` 照旧、其余写「spec-guard 记为未审（unreviewed），由你批」）。`UNREVIEWED` 常量与 `released_by` 对旧事项的展示保留。

## 影响面

修改：`module_crew/flow.py`、`module_crew/review.py`、`module_crew/takeover.py`、`module_crew/__main__.py`（`review show --review-diff`）。
测试：`tests/test_flow_v2.py`（`test_no_reviewer_releases_unreviewed` 按 Spec 范围第 7 条改，其余新增）、`tests/test_review_add.py`、`tests/test_review_approve.py`、`tests/test_review_display.py`（只新增用例）；夹具如需给 `reviewMark` 预览造输出，改 `tests/helpers.py` 的假 spec-guard（只加不改）。
公共文件（Task 5，发【公共变更请求】）：`skills/crew-dev/SKILL.md`、`codex-skills/crew-dev/SKILL.md`、`skills/crew-coordinator/SKILL.md`、`codex-skills/crew-coordinator/SKILL.md`、`spec/crew-flow-v2.md`（只追加变更记录一行）、`CHANGELOG.md`（未发版一节）。
不新增依赖。

## Task List

- [ ] Task 1：`review add` 拒收缺审查记录的新流程需求（Spec 决策 3、4；AC1、AC2、AC3）
  - 做：`flow.requirement_review`；`review.add` 对 `spec`／`interface` 节点判 `missing` 拒收、读不出时照收加提示行
  - 验证：夹具 `requirementReview.status` 为 missing／reviewed／not-required／null／缺字段，加 `/map` 读不出；spec 与 interface 各测；missing 退出码 3、状态库无新事项、原因里有三条命令；同一 worktree 先拒收、改夹具为 reviewed 后能收下；变异：删掉 missing 判定、改读集成分支（`takeover._map(checkout)`），用例变红
- [ ] Task 2：交用户时附审查记录与审查后的改动差异（Spec 决策 5；AC4）
  - 做：`review.requirement_diff`；批次展示与 `_hub_item` 加「需求审查」一行与差异；`review show C<n> --review-diff`
  - 验证：codex／host／none 三种记录各一行写法；预览输出的差异原样出现，「nothing changed」「cannot be shown」照写；老流程模块的批次与卡片文字与改动前逐字相同（快照比对）；变异：去掉差异块，用例变红
- [ ] Task 3：`review approve` 认出 `requirement-unreviewed`（Spec 决策 6；AC5）
  - 做：`_approve` 失败分支加说明
  - 验证：假 `reviewMark` 退出码 2 且输出 `requirement-unreviewed: …` 时，结果有决策 6 的说明、集成分支 `git status` 干净；其他失败输出不变
- [ ] Task 4：普通需求没有第二审查者交用户批（Spec 决策 7；AC6）
  - 做：`codex_note` 去掉未审放行分支；`no_reviewer_draft` 按档位选现状一句；`test_no_reviewer_releases_unreviewed` 改为断言送用户
  - 验证：normal + `selection = none` 退出码 5、`tasks/b/design.md` 不在集成分支、草稿过 `protocol check` 且含「spec-guard 记为未审」；important 原用例不改、通过；有审查者的路径原用例通过；变异：恢复按档位分支，用例变红

### Checkpoint 1（report）：代码就位，本模块相关测试（交审收件、批准、展示、新流程）通过，记入 todo 后继续

- [ ] Task 5：文档与 crew-flow-v2 变更记录（Spec 范围第 6 条；AC7）
  - 做：发【公共变更请求】：两份 crew-dev skill「新流程模块」一节加「需求交审前先审一轮」与三条路；两份 crew-coordinator skill 第 275／289 行去掉「未审放行」、改为交用户批，并补一句 `review add` 会拒收没审过的需求；`spec/crew-flow-v2.md` 末尾变更记录追加一行（2026-11-27，推翻假设 A3 前半句与决策 7「普通需求记为『未审』放行」，原因 spec-guard 1.27 sg-review-rules 第 12 条，来源本 Spec 与 C881）；`CHANGELOG.md` 记三处行为变化
  - 验证：模块协调回复后照它改或 `module-crew sync` 取回；文档测试通过；Claude 版与 Codex 版说法一致
- [ ] Task 6：同步、检查与本机实测（AC8；Spec 未决 Q2）
  - 做：`module-crew sync`；`scripts/validate.sh --quick`；本机 spec-guard 0.100.0 实测：临时项目造一个 `tier=normal` 新流程模块，没有记录时真 `/map` 给 missing、`review add` 拒收；用 `review-mark --state no-reviewer --reason` 记一行后能收下，真 `reviewMark` 预览的差异出现在展示里；记下 worktree 上跑预览有没有弹权限确认
  - 验证：快检查通过；实测结果写进 todo；弹了权限就按 Spec Q2 发【公共变更请求】

### Checkpoint 2（gate）：最终验收

- [ ] 回告：经模块协调把 Spec 未决 Q1（module-crew 落地技术方案批准时不写 spec-guard 的 design 标记，推荐另开一项）转告 ecosystem-lead；结果记在 todo 末项
