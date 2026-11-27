# Implementation Plan: crew-design-mark-sync

<!-- spec-guard: review approved -->

> 依据：`spec/crew-design-mark-sync.md`（用户 2026-11-27 批准，答复「C898 A」，批准事项 C899 落地于集成分支 685dc7e）。任务清单：`tasks/crew-design-mark-sync/todo.md`。

## Overview

先写失败的测试，钉住技术方案落地时三条路径对 `reviewMark` 的调用（Task 1），再改 `review._approve` 的标记循环让它们变绿（Task 2）。
接着测写标记失败与低版本兜底（Task 3）、做变异检查（Task 4）。然后用本机 spec-guard 0.101.0 真跑一遍，看集成分支 `/map` 的 `designApproval`（Task 5）。
最后改文档与 crew-flow-v2 的变更记录（Task 6，公共文件），同步、跑检查（Task 7）。
每个任务在本模块分支本地提交；不推送、不发版。

## Architecture Decisions

- **只改 `review._approve` 的标记循环**：今天对 `design` 节点 `continue`。改为：
  - 免审放行（`codex.skip`）：仍跳过（Spec 决策 3）；
  - 第二审查者放行（`codex.design`）：`mark_args(..., "design", "reviewer-approved", codex["report"])`（Spec 决策 2）；
  - 其余（用户批，含各种「改由用户批」）：`mark_args(..., "design", "approved")`，不带报告（Spec 决策 1）。
  失败处理沿用循环里现有的分支（退出码 4、`_restore`；放行路径由 `codex_note` 现有的「落地失败」接住），不加新分支（Spec 决策 5）。
- **低版本判断放 `review.py`**：新增 `_design_mark_supported(doc)`，看 `reviewMark.command` 里 `--target` 的占位符有没有 `design`。没有就跳过，并在结果里加一行提示（Spec 决策 6）。
  `_mark_command` 的现有自检（拿 spec 拼一次命令）不动。
- **顺序**：标记循环按 `NODE_RANK` 排序后再跑，保证同批里需求的标记先写（Spec 决策 8）；`picked` 本身的顺序和其他用途不变。
- **`takeover.py` 预计不改**：`codex_note` 已把存下的报告路径作为 `codex["report"]` 传给 `_approve`。构建中发现要改再记进 todo。
- **测试放新文件 `tests/test_design_mark.py`**：在测试里把假 spec-guard 的 `hooks/review_mark.py` 换成一个记参数的版本（收 `--review`、认 `--target design`，把命令行写进日志文件，按环境变量模拟失败），用 interface 1.27 的 `reviewMark.command`。不改 `tests/helpers.py`。
  现有测试默认用 interface 1.1 的命令（`--target` 只有 `spec|plan|both`），会走低版本兜底：落地照旧，只多一行提示。所以不用改现有断言；构建中若有逐字比对输出的用例被这一行打破，在 todo 里点名再改。
- **真 spec-guard 不进单元测试**：Spec 测试策略里「真 spec-guard 一条」改为 Task 5 的本机实跑，证据写进 todo。原因：测试不读真实的 `~/.claude`（`ProbeCase`），CI 也没装 spec-guard，进单测只会永远跳过。

## 影响面

- 修改：`module_crew/review.py`。
- 测试：新增 `tests/test_design_mark.py`；现有测试预计不改。
- 公共文件（Task 6，发【公共变更请求】）：
  - `CHANGELOG.md`（未发版一节）；
  - `spec/crew-flow-v2.md`（只追加变更记录一行）；
  - `skills/crew-coordinator/SKILL.md`、`codex-skills/crew-coordinator/SKILL.md`：只在有「技术方案不写标记」一类说法时改，Task 6 先核对。
- 不新增依赖。

## Task List

- [ ] Task 1：先写失败的测试——三条落地路径（Spec 决策 1、2、3、8；AC1、AC2、AC3、AC6）
  - 做：`tests/test_design_mark.py`，夹具是新流程 normal 模块 b，用 interface 1.27 的 `reviewMark.command`，换用记参数的假 `review_mark.py`。用例：
    - 用户批技术方案（`review approve`）→ 调 `--target design --state approved --confirm`，不带 `--review`；标记和两份文件在同一个集成分支提交里；
    - 第二审查者放行（`codex_note` 无阻断）→ 调 `--target design --state reviewer-approved --review <状态库 codex/C<n>-r1.json> --confirm`；
    - 第二审查者没有审查者，用户改由自己批（`codex-fallback` 后 `review approve`）→ `approved`；
    - 免审放行 → 不调；
    - 需求与技术方案同批批准 → 需求的调用在前。
  - 验证：今天的代码上这些用例为红（技术方案的几条），免审那条为绿。
- [ ] Task 2：实现标记循环（同上）
  - 做：`review._approve` 按 Architecture Decisions 改；函数注释写 `crew-design-mark-sync decision N`。
  - 验证：Task 1 的用例全绿；新流程（`tests/test_flow_v2.py`）、批准（`tests/test_review_approve.py`、`tests/test_review_mark_compat.py`）、接管（`tests/test_takeover_approve.py`）测试通过。
- [ ] Task 3：失败与低版本兜底（Spec 决策 5、6；AC4、AC5）
  - 做：补用例并按需改代码：
    - 假 `reviewMark` 对 design 退出 2 → 用户批退出码 4、集成分支 `git status` 干净、HEAD 不动；
    - 放行路径 → `codex_note` 记 `landFailed`、给出交用户的下一步；
    - `reviewMark.command` 为 interface 1.1／1.15 写法 → 不调 design、照落地、结果有决策 6 的提示行。
  - 验证：用例通过。

### Checkpoint 1（report）：代码就位，本模块与相关测试通过，记入 todo 后继续

- [ ] Task 4：变异检查（AC8）
  - 做：临时改代码各跑一次再还原，不提交：
    - 循环对 design 恢复 `continue`；
    - 放行路径改写 `approved`；
    - 免审路径也写标记；
    - 去掉排序。
  - 验证：每处至少一个用例变红；结果写进 todo。
- [ ] Task 5：本机 spec-guard 0.101.0 实跑（AC1、AC2 的真 `designApproval`）
  - 做：在 scratchpad 建全新临时项目，用本机真装的 `map_view.py`、`review_mark.py`：一个 `tier=normal` 新流程模块，需求已批，技术方案与回归齐全。
    - 路径一：档位 `design=human`，经 module-crew 的 `_approve` 落地，看 `/map --json` 的 `designApproval`；
    - 路径二：档位 `design=reviewer`，用一份对得上的 design-v1 报告落地，看 `designApproval`。
    第二审查者的报告拿不到真的就手工造一份合乎 delegate design-v1 格式的报告，并在 todo 里写明。
  - 验证：路径一为 `approved`／`user`；路径二为 `approved`／`reviewer`，`sameVendor` 与报告一致。实跑命令与输出摘要写进 todo；对不上就停下，发【等待其他会话】。
- [ ] Task 6：文档与 crew-flow-v2 变更记录（Spec 范围第 6 条、决策 7；AC7）
  - 做：核对两份 crew-coordinator skill 有没有相关说法，然后发【公共变更请求】，内容包括：
    - `CHANGELOG.md`「未发版的变化」一行：技术方案落地时写 spec-guard 标记，用户批 approved、第二审查者放行 reviewer-approved、免审不写；旧的技术方案不自动补，手动补法照 Spec Q2；
    - `spec/crew-flow-v2.md` 末尾变更记录追加一行：2026-11-27，兑现「接口约定·写」里技术方案批准记录那一句，不推翻已批决定；来源本 Spec 与 C899；
    - skill 有相关说法时一并改。
  - 验证：模块协调回复后照它改，或 `module-crew sync` 取回；逐句核对与请求原文一致。
- [ ] Task 7：同步与检查（AC8）
  - 做：`module-crew sync`；`scripts/validate.sh --quick`（对不上号会退回全量，放后台）。
  - 验证：检查通过，结果写进 todo；与本模块无关的偶发失败单独重跑确认并照实写。

### Checkpoint 2（gate）：最终验收

- [ ] 回告：经模块协调告诉 ecosystem-lead 本模块已做（来源 #23580），并转告 Spec 未决 Q1（构建中改过技术方案会显示 revised，推荐另开一项）、Q2（旧的技术方案不自动补标记）；结果记在本项。

## 风险

- spec-guard 的真 `reviewer-approved` 会再核一遍报告与磁盘上的 design.md：module-crew 的 `_mismatch` 已核过同一份提交的 sha256，预计对得上。Task 5 实跑确认；对不上会落到「已放行但落地失败、交用户」，不会错放。
- 落地顺序：标记写在 `git add` 之前，和今天 Spec 标记一样进同一个提交。

## 中途会停下来问你的地方

- Task 5 实跑结果和 Spec 预期对不上（例如 spec-guard 拒收 module-crew 存下的报告）时停下，发【等待其他会话】给模块协调。
- Checkpoint 2 最终验收。

## 未决问题

无（Spec 的 Q1、Q2 按 Spec 处理，随回告转出）。
