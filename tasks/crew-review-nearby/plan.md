# Implementation Plan: crew-review-nearby

<!-- spec-guard: review pending -->

> 依据：`spec/crew-review-nearby.md`（用户 2026-10-19 批准）。任务清单：`tasks/crew-review-nearby/todo.md`。

## Overview

先打底：协议层认出新字段与新类型、编号对外写 `C<数字>`；再做审查就近的主循环（送审 → 返工 → 重交 → 通过）、合批正文与待决问题、批准时核对答案；
最后补合并批准撤回、状态可见、skill 与 README，改钉契约 v2.0 样例并发 0.3.0。每个任务先写失败的测试，再实现到全绿，单独提交。
契约 v2.0 还没定稿：Task 1 先按 module-crew 给契约负责人的答复实现，Task 10 拿到定稿样例后对照改钉，有出入就修订 Spec 交用户复审。

## Architecture Decisions

- **审查状态不落库**：`review.review_state(db, item, now)` 从交审事项上的 `reviews`、`sentAt`、`rework` 记录与 `disagree` 字段推出六种状态；返工轮次按「模块＋节点」数已发的返工通知（事件 `rework-sent`）。
- **待决问题挂在交审事项上**：`decisions: [{source, question, options, lean, kind}]`（`kind` 为 reviewer／over-limit／disagree／timeout）。合批正文生成时按本正文重编 D1…，对照表 `{D号: (交审号, 序号)}` 存在正文记录（`body` 的元数据）里；批准时从原话里认「D<k> 选 <字母>」，按对照表核对。
- **编号**：新增 `module_crew/refs.py`：`fmt(n) -> "C15"`、`parse(s) -> 15`（认 `15`、`C15`、`c15`、`#15` 旧写法给提示）；所有对外文字与生成的消息正文改用 `fmt`；`--json` 加 `ref`，原数字字段不变。
- **发送项**：`review add` 的 `Outcome` 加 `sends`（送审）；`review note` 返回 `NoteResult(sends, batch)`；`merge revoke` 返回通知发送项。module-crew 仍不直接发消息。
- **时间**：超时判断用 `store.now()` 与 `sentAt` 比较；测试里注入 `now` 参数，不睡眠。

## 影响面

新增：`module_crew/refs.py`、`tests/test_review_nearby.py`、`tests/test_refs.py`。
修改：`protocol.py`、`review.py`、`merge.py`、`failure.py`、`probe.py`、`inbox.py`、`changes.py`、`start.py`、`__main__.py`（编号写法）、
`skills/crew-coordinator/SKILL.md`、`skills/crew-dev/SKILL.md`、`codex-skills/crew-dev/SKILL.md`、README、契约样例目录与一致性测试、版本文件。不涉及界面。
现有测试里断言「#数字」的地方会随 C 编号改写。

## Task List

### Phase 1：协议与编号

- [ ] Task 1：协议层——「有须修改项N条」与「须修改」、「待用户决定」D 项、【交审】「不同意」、返工与撤销批准两种通知、多段审查结论切分、开工依据认 C 编号（验收 2、4、6、9 的协议部分）
- [ ] Task 2：编号对外写 `C<数字>`——`refs.py`、命令参数两种写法、生成的消息与提交说明、`--json` 加 `ref`（验收 13）

### Checkpoint 1（report）：Phase 1 全绿；不登记审查者与收件枢纽时现有流程通过（除编号写法），记入 todo 后继续

### Phase 2：审查就近主循环

- [ ] Task 3：送审与审查状态——`review add` 输出送审发送项、记 `sentAt`；「不同意」交审校验文件与上一版相同；`review_state` 六种状态与超时（验收 1、4、5）
- [ ] Task 4：`review note`——多段逐段记、「有须修改项」生成返工通知、轮次与上限 3、记待决问题；`--then-batch [--for-hub]`（验收 2、3、4、9、10）
- [ ] Task 5：合批——进合批条件、待决问题 D 编号与对照表、「经 N 轮审查修改」、摘要（R8）、要点列表（R7）、选项后果与中文节点名（R4）、超时的审查行与总行（验收 3、5、6、11、14、15）
- [ ] Task 6：批准核对——`review approve`／`merge approve` 认 D 答案、没答全拒收并给追问正文、按答案分三路；单用时同样核对（验收 7、8）

### Checkpoint 2（report）：完整返工循环在三种组合下跑通（单用、不配审查者、两者都配），记入 todo 后继续

### Phase 3：撤回、可见与收尾

- [ ] Task 7：`merge revoke`——撤回 open 的合并批准、输出撤销批准通知、已合并或在合并中拒绝（验收 12）
- [ ] Task 8：`status` 与 `sessions --json` 显示返工轮次（`review` 字段，schemaVersion 仍为 1）（验收 16）
- [ ] Task 9：skill 与 README——协调会话「审查就近」一节、两份 crew-dev 的返工／不同意／撤销批准、待决问题必须答全、合并前复述；README 按文档建议改写（验收 18）
- [ ] Task 10：改钉契约 v2.0——拿定稿样例替换 fixtures、`CONTRACT_VERSION`、一致性测试；与 Task 1 写法对照，有出入修代码并修订 Spec 交复审；版本号 0.3.0（验收 17、18）

### Checkpoint 3（gate）：模块最终验收

- [ ] 全部测试全绿；18 条验收逐条对应测试；列出实际改动文件；Spec 若补改则附差异
- [ ] 本 Plan 获批即授权：每个任务完成后在 `main` 本地提交；不推送；不冻结、不动 `module-crew-release/`；Task 10 在契约 v2.0 定稿前不做（先做其余任务）；冻结 0.3.0 与通知各方要用户在最终验收后另行批准

## Risks and Mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| 契约 v2.0 定稿与本 Spec 写法不同（类型名、字段、`C数字` 是否算批准依据） | 高 | 协议改动集中在 Task 1；Task 10 对照定稿，出入处修订 Spec 交复审再改代码 |
| C 编号改动面大，牵动大量现有测试 | 中 | Task 2 单独做、先改测试断言再改代码；`--json` 数字字段不变，外部读者不受影响 |
| 批准分三路让一次批准同时产生批准、退回、保持三种结果，容易出错 | 中 | 先做全部检查再写；三路各有独立测试；没答全时什么都不写 |
| 赶不上批 2 阶段丙 | 中 | Phase 1–2 优先；Phase 3 里 Task 7、8 可与 Task 9 并排做；进度每个检查点报一次 |
| 超时依赖墙钟 | 低 | `now` 作参数注入，测试不睡眠 |
