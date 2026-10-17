<!-- spec-guard: review approved -->
# Implementation Plan: crew-protocol

> 依据：`spec/crew-protocol.md`（已批准，指纹 cb67cf42a743）。任务清单：`tasks/crew-protocol/todo.md`。

## Overview

先把契约样例钉进仓库并写好一致性测试框架（此时支持类型的样例全部失败），再按「通用切分 → 简单类型 → 【等待用户】 → v1.1 三种」
逐步让样例变绿；然后做生成函数和 `protocol check`；最后登记到 session-protocol 的一致性说明。每个任务先让对应样例或新测试失败，再实现到全绿，单独提交。

## Architecture Decisions

- 一致性测试是主测试：`tests/test_protocol_conformance.py` 遍历样例，每份样例一个 `subTest`；支持的类型由测试里的常量表决定，
  任务推进时逐步把类型加入表中（未加入的类型在输出里列为「本任务尚未覆盖」），到任务 4 结束时表与 Spec 一致。
- `protocol.py` 内部分三层：`_split`（开头的回复、结束、标签行）→ `_fields`（按本类型认识的字段名切分，续行原样）→ 每类型一个 `_check_<类型>`（必填、专项校验、结构化键）。
  `Message` 冻结 dataclass，`contract()` 只在调用时组装字典。
- 字段名表、类型标签表、问题代码按契约原文写成模块级常量；问题代码顺序按契约第 7 节（v1.1 三种）与 v1.0 样例的实际顺序。
- 生成函数先拼文本，再 `parse` 自检，不合格抛 `ValueError`（Spec 关键决策 3）。
- `__main__.py` 加 `protocol check` 子命令，读文件只发生在 CLI 层。

## 影响面

新增：`module_crew/protocol.py`、`tests/fixtures/session-protocol/v1.1/`（86 个样例文件 + `SHA256SUMS` + `SOURCE`）、
`tests/test_protocol_conformance.py`、`tests/test_protocol_render.py`、`tests/test_protocol_cli.py`。
修改：`module_crew/__main__.py`（加子命令）、`tests/test_package.py`（加 protocol.py 无 I/O 扫描）。
另一个仓库：`~/Documents/haigeerlab/session-protocol/conformance/README.md` 改一行（任务 7，提交前单独确认）。不涉及界面。

## Task List

### Phase 1：钉住契约

- [ ] Task 1：复制样例、`SOURCE`、指纹核对与一致性测试框架（验收 1）

### Phase 2：解析

- [ ] Task 2：通用切分与简单类型——【等待其他会话】【已恢复】【撤回】【用户答复】、`unknown`（验收 2 的对应部分）
- [ ] Task 3：【等待用户】——选项、推荐、你该回、是否完全停住、标记、多线范围、架构审查行、提示代码（验收 2 的 12 份）
- [ ] Task 4：v1.1 三种与不支持的两种（验收 2 的 15 份、验收 7）

### Checkpoint 1（report）

- [ ] 全部测试全绿；一致性测试 38 份解析样例全部通过、跳过项列出

### Phase 3：生成与命令

- [ ] Task 5：`render_user_reply`、`render_coordination_notice`（验收 3、4、5、6）
- [ ] Task 6：`protocol check` 与无 I/O 扫描（验收 8、9）

### Phase 4：登记

- [ ] Task 7：session-protocol 一致性说明登记 module-crew 一行（验收 10；该仓库的提交在最终验收里交你确认后再做）

### Checkpoint 2（gate）：模块最终验收

- [ ] 全部测试全绿；逐条对照 Spec 的 10 条验收标准，写明各由哪个测试覆盖
- [ ] 在对话里列出本模块实际改动的文件（新增、修改、删除与行数），以及 session-protocol 那一行的差异
- [ ] 本 Plan 获批即授权：任务 1～6 每个完成后在本仓库 `main` 做一次本地提交；任务 7 只改工作区，提交等最终验收批准；不推送、不建远端

## Risks and Mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| 契约文字与 v1.0 样例的实际行为有出入（v1.0 由 decision-inbox 代码得出） | 中 | 以样例为准实现；发现契约文字说不清的地方，记进 todo 交你决定是否改契约，不改样例 |
| 【等待用户】选项与范围的切分规则细节多 | 中 | 任务 3 单独成一个任务，12 份样例逐份对照，差异逐项打印 |
| 生成的【用户答复】与样例差一个空格或换行 | 低 | 逐字比较并在失败时打印 `repr` |
