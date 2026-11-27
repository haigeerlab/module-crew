# Implementation Plan: crew-review-rules-follow

<!-- spec-guard: review approved -->

> 依据：`spec/crew-review-rules-follow.md`（用户 2026-11-27 批准，事项 C854「C854 A」，落地于集成分支 d918ab6）。任务清单：`tasks/crew-review-rules-follow/todo.md`。

## Overview

两件互不依赖的改动各一个 Task：里程碑停点按 `blocking` 停（Task 1），重要需求的技术方案按档位走（Task 2），再处理重要需求遇到没有审查者时的去向（Task 3，依赖 Task 2）。
最后改文档与 crew-flow-v2 的变更记录（Task 4，公共文件），同步、跑检查、用本机 spec-guard 0.99.0 实测（Task 5）。
每个任务先写失败的测试、看到红再实现到绿，在本模块分支本地提交；不推送、不发版。

## Architecture Decisions

- **停点提示不进 `warnings`**：`start.Proposal` 加 `notes: list[str]`，放不阻塞停点的提示；`warnings` 会让 `prepare` 拒绝，所以不复用。`start plan` 的文字与 `--json` 输出都带 `notes`，`prepare` 的结果行也带。
- **`milestone_stop` 返回值扩成三项**（阻塞项、警告、提示），调用处只有 `start.plan` 一处；`blocking is False` 才走提示，其余照今天。
- **`_design` 只照 spec-guard 字段**：删掉 `tier == "important"` 一支，改为在读 `takeover.design` 前判 `takeover.designForcedBy == "important"` → `("human", DESIGN_IMPORTANT)`；`DESIGN_IMPORTANT` 常量保留（旧版 spec-guard 仍会用到）。
- **无审查者的去向按档位分**：`takeover.codex_note` 里 `_no_reviewer` 分支先查模块档位，`important` 不调 `review._approve`，改出送用户的【等待用户】草稿（沿用 `unavailable_draft` 的写法与选项，原因写「本机没有可用的第二审查者，重要需求的技术方案由你批」）；`normal` 照旧未审放行。

## 影响面

修改：`module_crew/start.py`、`module_crew/__main__.py`（`start plan` 打印与 `--json` 加 `notes`）、`module_crew/takeover.py`。
测试：`tests/test_start_plan.py`、`tests/test_start_prepare.py`、`tests/test_flow_v2.py`（第 292 行断言按 Spec 改，其余新增）。
公共文件（Task 4，发【公共变更请求】）：`skills/crew-coordinator/SKILL.md`、`codex-skills/crew-coordinator/SKILL.md`、`spec/crew-flow-v2.md`（只追加变更记录一行）、`CHANGELOG.md`（未发版一节加两行）。
不新增依赖；`present.py` 若不用改就不动。

## Task List

- [ ] Task 1：里程碑停点按 `blocking`（Spec 决策 1、2；AC1、AC2）
  - 做：`milestone_stop` 读 `blocking`；`Proposal.notes`；`start plan` 文字、`--json`、`prepare` 结果带提示行
  - 验证：`blocking` 为 false 时提议照常、带提示、`prepare` 退出码 0；true、缺字段、非布尔（如 `"false"`、`0`）阻塞且 `prepare` 退出码 3；`error: unreadable` 照旧；变异：把判断改成真值判断（`not stop.get("blocking")`）或删掉，用例变红
- [ ] Task 2：重要需求的技术方案按档位（Spec 决策 3、4；AC3、AC4）
  - 做：`_design` 删 `important` 强制，加 `designForcedBy` 判断；`tests/test_flow_v2.py:292` 改为按档位断言
  - 验证：`important` × `takeover.design` reviewer／human／缺失三种，加 `designApproval.status = not-required` 免审，结果与 `normal` 相同；`designForcedBy = important` 送用户并显示「重要需求：技术方案由用户批」；变异：恢复 `important` 强制，用例变红
- [ ] Task 3：重要需求没有可用审查者时送用户（Spec 决策 5；AC5）
  - 做：`codex_note` 的无审查者分支按档位分
  - 验证：`important` + `reviewer.selection = none` 不放行、返回送用户的草稿且草稿过 `protocol check`；`normal` 照旧未审放行并发开工通知；变异：去掉档位判断，用例变红

### Checkpoint 1（report）：代码就位，本模块相关测试（开工计划与准备、新流程、接管）通过，记入 todo 后继续

- [ ] Task 4：文档与 crew-flow-v2 变更记录（Spec 范围第 4 条；AC6）
  - 做：发【公共变更请求】改两份 crew-coordinator skill 的「技术方案谁批」一句、Claude 版「里程碑停点」一句加 `blocking`、Codex 版补同一句；`spec/crew-flow-v2.md` 末尾变更记录追加一行（2026-11-27，推翻「重要需求的技术方案永远人批」及决策 7、A3 后半句，原因 spec-guard 0.99.0 sg-review-rules，来源本 Spec 与 C854）；`CHANGELOG.md` 记这两处行为变化
  - 验证：模块协调回复后照它改；文档测试通过；两份 skill 说法一致
- [ ] Task 5：同步、检查与本机实测（AC7）
  - 做：`module-crew sync`；`scripts/validate.sh --quick`（检查账未开时）；本机 spec-guard 0.99.0 实测：临时项目的 `/map --json` 造一个 `blocking=false` 的停点与一个 `important` 新流程模块，`start plan` 与 `takeover` 读真输出
  - 验证：快检查通过；实测结果写进 todo

### Checkpoint 2（gate）：最终验收

- [ ] 回告：经模块协调把 Spec 未决 Q1～Q3（`requirementReview` 另开一项、未审放行与 spec-guard 的出入、`takeover.notes` 文字矛盾）转告 ecosystem-lead 与 sg-coord；结果记在 todo 末项
