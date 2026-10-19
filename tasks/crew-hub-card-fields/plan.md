# Implementation Plan: crew-hub-card-fields

<!-- spec-guard: review pending -->

> 依据：`spec/crew-hub-card-fields.md`（用户 2026-10-19 批准，8 条假设照推荐）。任务清单：`tasks/crew-hub-card-fields/todo.md`。

## Overview

先把解析器升到 v2.3 并钉住契约样例（之后的生成都靠它自检），再给来源登记加 `--protocol`，然后改 `review batch --for-hub` 的生成，最后改三份 skill、README 与版本号。
每个任务先写失败的测试，再实现到全绿，单独在 `main` 本地提交，不推送。

## Architecture Decisions

- **样例**：从 session-protocol 6b8810e 的 `fixtures/` 整套复制到 `tests/fixtures/session-protocol/v2.3/`（带 `SOURCE`、`SHA256SUMS`），v2.2 目录保留；一致性测试对两套都跑，v2.2 那套照旧要求 97 份全过。
- **解析器**：`protocol.FIELDS["wait-user"]` 加「注意」「推荐理由」「批了会怎样」；`_go_to_session` 扩为按名称表认九种「类型」（中文名 → 代码），审批类按契约表按书写顺序切出 `points`（`name` 规范写法、`text` 含续行）；`CONTRACT_VERSION = "2.3"`。去会话操作的必填检查不变。
- **版本开关**：来源记录加 `protocol` 字段（`"2.2"`／`"2.3"`，旧记录没有就是 2.2）；`sources.hub_protocol(db)` 在登记的 hub 来源全部为 2.3 时返回 2.3，否则 2.2（一个都没有也是 2.2）。
- **生成**：`review._hub_item` 按 `hub_protocol` 分两条路——2.2 路径一字不改；2.3 路径在「要点」后依次加「类型」「注意」「推荐理由」（有才写）「批了会怎样」，并从要点里去掉「批准会发生什么」段和依赖未就绪行。
  「批了会怎样」与「选项与我的建议」里 A 的「选了会怎样」都由 `_what_happens`／`_consequence` 生成，同源。
- **2.2 写法回归**：Task 3 动代码前，先用现有代码生成一份 Spec、一份最终验收的提请批准正文存成夹具，2.2 路径逐字比对。

## 影响面

修改：`module_crew/protocol.py`、`module_crew/sources.py`、`module_crew/review.py`、`module_crew/__main__.py`（`source add --protocol`、`source list`）、
`skills/crew-coordinator/SKILL.md`、`skills/crew-dev/SKILL.md`、`codex-skills/crew-dev/SKILL.md`、`README.md`、`interface.json`（`contract` 2.3）、三处版本号。
新增：`tests/fixtures/session-protocol/v2.3/`、`tests/test_card_fields.py`、2.2 回归夹具。修改测试：`tests/test_protocol_conformance.py`、`tests/test_skills.py`。
不新增依赖，不改状态库格式（来源记录多一个字段）。不涉及界面。

## Task List

### Phase 1：契约与开关

- [ ] Task 1：解析器升到 v2.3——九种类型、三个选填字段、`points`；复制 v2.3 样例并让一致性测试跑两套；`interface.json` 的 `contract` 改 2.3
  - 验收：Spec 验收 1
  - 验证：`tests/test_protocol_conformance.py` 两套样例全过（v2.2 照旧 97 份）；新样例的 `waitKind`、`points` 与期望结果一致
  - 文件：`module_crew/protocol.py`、`tests/fixtures/session-protocol/v2.3/`、`tests/test_protocol_conformance.py`、`interface.json`
- [ ] Task 2：`source add <名> --kind hub --protocol 2.2|2.3`、`source list` 显示版本、`sources.hub_protocol()`
  - 验收：Spec 验收 6
  - 验证：登记、显示、只认两个取值、旧记录按 2.2、有一个 hub 是 2.2 就按 2.2
  - 文件：`module_crew/sources.py`、`module_crew/__main__.py`、`tests/test_card_fields.py`

### Checkpoint 1（report）：解析器与开关就位，全量测试通过，记入 todo 后继续

### Phase 2：生成卡片字段

- [ ] Task 3：`review batch --for-hub` 的 2.3 写法——类型（Spec／Plan／接口提案／最终验收／Spec 与 Plan）、注意（须修改／附建议／无响应／无，依赖未就绪移入）、推荐理由（有事实才写）、批了会怎样；2.2 写法逐字不变
  - 验收：Spec 验收 2～5
  - 验证：先存 2.2 回归夹具；四种节点各一条、`combined` 一条；「注意」四种来源各一例；正文全部过 `protocol check`；2.2 逐字比对
  - 文件：`module_crew/review.py`、`tests/test_card_fields.py`、回归夹具

### Phase 3：skill、文档与版本

- [ ] Task 4：crew-coordinator skill 写模块协调自提请示（卡住选做法、能力图审阅）按类别与小项写，并写明「决策收件箱升到 v2.3 后改来源登记」；两份 crew-dev skill 写中途检查点、卡住选做法的类别与小项，接口提案【交审】要点写「改了哪个接口」「哪些模块要跟着改」
  - 验收：Spec 验收 7
  - 文件：三份 skill、`tests/test_skills.py`
- [ ] Task 5：README 写 0.7.0 的变化与升级步骤；版本 0.7.0；全量测试与旧称扫描
  - 验收：Spec 验收 8
  - 文件：`README.md`、三处版本号

### Checkpoint 2（gate）：最终验收

- [ ] 回告：结果告诉 di-p0-tester（local_bbdaaaab）与契约负责人（local_a9d06942）

## 风险

- 契约样例里的期望结果键若有 module-crew 没实现的（如别的消息的新键），一致性测试会先红：只实现 v2.3 新增的 `waitKind`、`points`，其余按现有规则比对。
- 「推荐理由」写得太少：只写能确定的事实，宁缺不编；精简与措辞由决策收件箱处理。
