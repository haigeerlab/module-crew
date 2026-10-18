<!-- spec-guard: review approved -->
# Implementation Plan: crew-hub-bridge

> 依据：`spec/crew-hub-bridge.md`（已批准）。任务清单：`tasks/crew-hub-bridge/todo.md`。

## Overview

先做来源白名单与统一校验，再把各批准入口接上来源并提供对照查询；然后做审查行与交枢纽正文；再做只读出口与 interface.json；最后改 skill。
依赖契约 v1.6 的部分（lead 转交、把枢纽答复转给模块）单独放在最后一个阶段，v1.6 发版前停在 gate 不做。每个任务先写失败的测试再实现到全绿，单独提交。

## Architecture Decisions

- `module_crew/sources.py`：`add/remove/list`（写运行配置 `sources`，要用户原话）、`check(db, name, item, relay_id, text) -> SourceInfo`、`map_item(db, H)`、`map_crew(db, n)`。
- hub 来源在 v1.6 发版前按现行【用户答复】解析（`protocol.parse` 类型 `user-reply`，事项号等于 `--source-item`），v1.6 定稿后对照修订；lead 来源在 v1.6 前一律拒绝并写明原因。
- 各批准入口不改原有签名：在 `__main__` 统一解析 `--source*`，`self` 时原话照旧；非 `self` 时由 `sources.check` 给出用户原话与 `source` 字典，入口只多收一个可选的 `source` 参数写进 `answer`。
- 审查结论记在交审事项的 `reviews` 列表；`--for-hub` 用 `protocol` 的已有能力自检。
- `sessions --json` 包一层 `{"schemaVersion": 1, "sessions": [...]}`，stage 枚举由 `hooks._stage` 的结果映射；`interface.json` 由一致性测试守住。

## 影响面

新增：`module_crew/sources.py`、`interface.json`、`tests/test_sources.py`、`tests/test_hub_output.py`。
修改：`module_crew/__main__.py`、`review.py`、`merge.py`、`start.py`、`changes.py`、`failure.py`、`inbox.py`、`hooks.py`、两份 SKILL.md、`tests/test_skills.py`、`tests/test_failure.py`（sessions 输出形状）、README。不涉及界面。

## Task List

### Phase 1：来源与对照

- [ ] Task 1：来源白名单与 `sources.check`（验收 1，验收 3 的校验部分）
- [ ] Task 2：批准入口接来源、`source map`（验收 2、3、4）

### Phase 2：审查行与交枢纽正文

- [ ] Task 3：`review note` 与 batch 审查行（验收 6）
- [ ] Task 4：`review batch --for-hub`（验收 7）

### Checkpoint 1（report）

- [ ] 全部测试全绿（含所有现有测试，验证不带 `--source` 时行为不变）

### Phase 3：只读出口与 skill

- [ ] Task 5：`sessions --json` 契约与 `interface.json`（验收 8、9）
- [ ] Task 6：两份 skill 措辞与「接入收件枢纽」一节、README（验收 11）

### Checkpoint 2（gate）：v1.6 前的阶段验收

- [ ] 全部测试全绿；验收 1–4、6–9、11 逐条对应测试；列出实际改动文件；验收 5、10 写明「等 v1.6」
- [ ] 本 Plan 获批即授权：每个任务完成后在 `main` 本地提交；不推送；阶段验收后重装本地插件

### Phase 4：按 v1.6 对照（v1.6 发版后才开始）

- [ ] Task 7：改钉契约 v1.6（导出样例、`CONTRACT_VERSION`）、hub 来源按 v1.6 对照、lead 来源（验收 3、5）
- [ ] Task 8：把枢纽答复转给模块与发给枢纽的【已恢复】、crew-dev 核对（验收 10）

### Checkpoint 3（gate）：模块最终验收

- [ ] 全部测试全绿；11 条验收逐条对应测试；Spec 若按 v1.6 修订则附差异；列出实际改动文件

## Risks and Mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| 改动面广（所有批准入口），破坏现有行为 | 高 | 来源解析集中在 `__main__` 与 `sources.check`；不带 `--source` 的现有测试全部重跑 |
| v1.6 条文与临时的 hub 解析不同 | 中 | hub 解析隔离在 `sources.check` 一处；Phase 4 对照修订并复审 Spec |
| sessions 输出形状改变影响现有调用者 | 低 | 只有 `sessions --json` 包一层；文字输出不变；测试同步 |
