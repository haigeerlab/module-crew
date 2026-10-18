# Implementation Plan: crew-glossary-rename

<!-- spec-guard: review approved -->

> 依据：`spec/crew-glossary-rename.md`（用户 2026-10-19 批准）。任务清单：`tasks/crew-glossary-rename/todo.md`。

## Overview

先写旧称扫描测试并确认它在现状下失败（护栏先立），再做 W 前缀（唯一的显示逻辑改动），然后按「代码字符串 → 三份 skill → README 与命令帮助」逐块改到扫描通过，
最后升 0.4.0。只改文字，不改行为；每个任务改完跑全量测试，单独在 `main` 本地提交。

## Architecture Decisions

- **扫描测试** `tests/test_glossary.py`：用 `ast` 取 `module_crew/*.py`（不含 `protocol.py`）的字符串常量（含 f-string 的常量片段、docstring 除外——docstring 是给开发者看的英文），加 README、三份 SKILL.md 全文；
  先用正则去掉 `【[^】]*】` 与契约字段名（取自 `protocol.FIELDS` 的全部字段名后接「：」），再查 `OLD_TERMS`（Spec 关键决策 1 左列）；豁免是 `(词, 理由)` 列表，只放「评审节奏」「插件负责人」「契约负责人」这类术语表认可的写法。
  命中报「文件：原文前后 20 字」。
- **W 前缀**：`refs.py` 加 `wait_ref(n) -> "W<n>"` 与 `parse` 认 `W`；等待记录的显示处（`failure.render_sessions`、`inbox`、`ticket close` 输出、`status`）改用 `wait_ref`；
  `sessions --json` 与 `status --json` 中等待记录列表旁加 `ref`。交审等其他记录不变。
- **改名按文件做**：每个文件改完立刻跑它的相关测试；现有测试里断言旧文字的同步改成新文字，断言含义不变。
- **契约部分**：`protocol.py` 不动（验收 2 用 `git diff --stat <开始提交>..HEAD -- module_crew/protocol.py` 为空证明）；其他文件里的 `【…】` 与字段名不动。
- **版本**：`.claude-plugin/plugin.json`、`.codex-plugin/plugin.json`、`interface.json` 的 `version` 改 0.4.0；`tests/test_package.py` 的版本一致性测试照常通过。

## 影响面

修改：`module_crew/` 下除 `protocol.py` 外有给人看文字的文件（`__main__.py`、`start.py`、`review.py`、`merge.py`、`inbox.py`、`failure.py`、`hooks.py`、`changes.py`、`sources.py`、`probe.py`、`refs.py`、`stall.py`、`permissions.py`、`prepush.py` 等，以实际命中为准）、
三份 SKILL.md、`README.md`、三个版本文件、受影响的现有测试（约 5 个文件）。新增：`tests/test_glossary.py`。不涉及界面。

## Task List

### Phase 1：护栏与 W 前缀

- [ ] Task 1：旧称扫描测试——先失败，记下现状命中数（应与 Spec 盘点一致）；豁免清单带理由（验收 1 的护栏）
- [ ] Task 2：W 前缀——`refs` 认 W、等待记录显示 `W<号>`、`--json` 加 `ref`、`ticket close W25／C25／25`（验收 3）

### Phase 2：改名

- [ ] Task 3：`module_crew/*.py`（不含 `protocol.py`）给人看的字符串改名；契约标签第一次出现写「新名称（契约标签【旧】）」；同步现有测试的断言文字（验收 1 代码部分、2、5）

### Checkpoint 1（report）：代码部分扫描通过、契约一致性测试通过、`protocol.py` 无改动、全量测试通过，记入 todo 后继续

- [ ] Task 4：三份 SKILL.md 改名（含 description）；写明「你」指会话、用户的答复与待你决定的写法、契约标签照原样发（验收 1 skill 部分、4、5）
- [ ] Task 5：README 与命令帮助改名，加术语表链接与「0.4.0 的变化」；版本升 0.4.0（验收 1 全部、6）

### Checkpoint 2（gate）：模块最终验收（也是 0.4.0 的验收）

- [ ] 全量测试全绿（验收 8）；验收逐条对应证据；改动文件清单与提交号；需求逐项勾清单——R14（crew-stall-signals）、R16（crew-host-permissions，含验收 11 实测状态）、改名（本模块）（验收 7）
- [ ] 本 Plan 获批即授权：每个任务完成后在 `main` 本地提交；不推送；不冻结、不打标签、不动 `module-crew-release/`；冻结、抄送监测会话、验收 11 实测交接都在最终验收后另请用户批准

## Risks and Mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| 改到契约字段或标签，别的插件解析失败 | 高 | `protocol.py` 不动；扫描先剥标签与字段名；契约一致性测试与生成消息的 `protocol.parse` 自检必须通过 |
| 机械替换把语义改错（如「评审」拆审查／批准／验收） | 中 | 不做全局替换，逐处改；对照表里多义的词逐句判断 |
| 豁免清单越放越宽 | 中 | 每条带理由，最终验收列出全部豁免条目 |
| 改动面大，审查难 | 中 | 按文件分任务提交；最终验收给每个文件的改动行数，并附 `git diff --word-diff` 的抽样 |
| decision-inbox 依赖某段自由文字 | 低 | 它只按契约标签与字段解析；发版后回告 |

## Open Questions

无。
