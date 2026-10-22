# Implementation Plan: crew-contract-v26

<!-- spec-guard: review approved -->

> 依据：`spec/crew-contract-v26.md`（用户 2026-10-22 批准）。任务清单：`tasks/crew-contract-v26/todo.md`。

## Overview

先钉夹具（复制契约 92309e7 的 `fixtures/` 为 v2.6、测试按 v2.6 跑），再改解析（C 待定编号、新小项名、【交审】points），然后改生成（按登记版本编 C 或 D、
答复块一块一件事、只用交审号），接着改名「验收结果」与登记 2.6，最后改 skill 与 README、跑全量、回报契约负责人。
每个任务先写失败的测试、看到红再实现到绿，单独在 `main` 本地提交，不推送、不发版。

## Architecture Decisions

- **夹具**：`tests/fixtures/session-protocol/v2.6/` 原样复制契约仓库 92309e7 的 `fixtures/`（含 SHA256SUMS，另写 SOURCE 记提交号）；`test_protocol_conformance` 的版本表加 v2.6 并改为默认版本，样例数按 SHA256SUMS 实数。
- **解析**：`_DECISION_HEAD_RE` 的编号改为 `D\d+|C\d+-\d+`；问题代码沿用原样拼接编号。`WAIT_KINDS` 的 Spec、Plan 小项名单加新名（新旧都在名单里，`points` 记写的那个名）。
  【交审】解析调用同一个 `_points`，小项名单按「节点」取（Spec、Plan、接口提案、最终验收各一份，最终验收含「验收结果」）。`CONTRACT_VERSION = "2.6"`。
- **编号**：`review.numbered_decisions(b, style)` 返回同样的三元组，`style` 为 `"c"` 时编 `C<交审号>-<序号>`（序号按该交审里的出现顺序从 1 起），`"d"` 时照旧 D 连续编号。
  `style` 由 `sources` 决定：有登记的决策收件箱且 `hub_protocol(row) >= 2.6` → c；登记低于 2.6 → d；没有收件箱 → c。`hub_protocol` 认 2.6。
- **答法**：`_ANSWER_RE` 认 `D\d+` 与 `C\d+-\d+` 两种；`split_decisions` 对每个待定问题同时查它的 C 号与本批 D 号，答到其一就算答了。
- **答复块**：新函数 `review.reply_blocks(entries) -> list[str]`：每件事一块，「<交审号> <字母>」后接「；<待定编号> <倾向字母>」；`_hub_item` 的「你该回」与会话复制块都用它；另一种答法单独一块；不生成带占位符的块。
- **内部号**：检查 for-hub 正文、【用户答复】、【等待用户】里的「已批准」「已合入」措辞，换成交审号；命令行输出不动。
- **改名**：`review.EVIDENCE` 改为认「验收结果」与「验收标准与证据」两个标题，拒收提示写新名；skill 只写新名。
- **登记**：`sources.PROTOCOLS` 加 `"2.6"`。

## 影响面

新增：`tests/fixtures/session-protocol/v2.6/`、`tests/test_contract_v26.py`。修改：`module_crew/protocol.py`、`review.py`、`sources.py`、`__main__.py`、
三份 skill、`README.md`，以及跟着调整断言的已有测试。不新增依赖，不改 `interface.json`、版本号。

## Task List

- [ ] Task 1：钉住 v2.6 夹具，全部样例按期望解析（含 C 待定编号、新小项名、【交审】points），`CONTRACT_VERSION` 2.6（Spec 验收 1、2、3）
- [ ] Task 2：待定问题按登记版本编 C 或 D，答复两种都认；`PROTOCOLS` 加 2.6（Spec 验收 4、7 的登记部分）

### Checkpoint 1（report）：解析与编号就位，相关测试通过，记入 todo 后继续

- [ ] Task 3：答复块一块一件事；给用户看的字段只用交审号（Spec 验收 5）
- [ ] Task 4：「验收结果」改名，新旧都收（Spec 验收 6）
- [ ] Task 5：三份 skill、README，全量测试与旧称扫描（Spec 验收 6、7）

### Checkpoint 2（gate）：最终验收

- [ ] 回告：完成情况发给总协调（local_d7434023）；钉住的契约版本与实现情况回报契约负责人（local_e1431df1）
