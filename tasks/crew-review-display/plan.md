# Implementation Plan: crew-review-display

<!-- spec-guard: review pending -->

> 依据：`spec/crew-review-display.md`（用户 2026-10-23 批准，假设照写）。任务清单：`tasks/crew-review-display/todo.md`。

## Overview

先改掉「并行边界重叠：无」的误报并接上 scopeOverlap（风险最高、已有试用实例），再做最终验收的四张表，然后做三种请示模板，最后补分节测试、skill 与 README、跑全量。
每个任务先写失败的测试、看到红再实现到绿，单独在 `main` 本地提交，不推送、不发版。

## Architecture Decisions

- **新文件 `module_crew/present.py`**：只放「怎么呈现」的纯函数与少量 git 读取：`overlap(project, db, items) -> dict`、`final_tables(project, db, rec) -> dict`、`render_request(kind, head, points, notes, block) -> list[str]`。
  `review.batch` 与 `_hub_item` 调用它；`start`、`changes`、`inbox` 只调 `render_request`。
- **重叠**：`probe.find_plugin` + `read_interface` 取 spec-guard 声明；有 `scopeOverlap`（接口 ≥ 1.10）时，用 `probe.safe_command` 组命令，把每份交审中的 Spec（`git show <commit>:spec/<模块>.md`）写到
  `<状态库>/tmp/C<交审号>-spec.md`（原子覆盖、不删），以 `--spec <模块>=<文件>` 传入并带 `--project <集成 checkout>`，超时同 `MAP_TIMEOUT`；退出码非 0 或 JSON 读不出 → `unchecked`，原因照写。
  没有声明时：本批有交审中的 Spec 未落集成分支 → `unchecked`「spec-guard 低于 1.10」；都已落 → 沿用进度表的 `startable.conflicts`，写成「无（已按集成分支上的 Spec 比对）」或冲突。
- **最终验收四张表**：基点 `git merge-base <集成分支> <交审提交>`；`git diff --numstat -M --diff-filter=ADMR` 与 `--name-status` 得到增删改与行数；`git log --format='%h %s' <base>..<commit>`；
  依赖：对清单文件取 `git diff -U0` 的新增行，`package.json` 只认 `dependencies`／`devDependencies` 等块里的 `"名": "版本"` 新行，其余清单按各自行格式取包名；认不出写「有改动，请看差异」。
  「超出 Plan」：读集成分支上的 `tasks/<模块>/plan.md`，收集反引号里的路径与「会改哪些文件」一节的行。
- **for-hub 的最终验收卡**：在现有「要点」前部（R17 的证据之后）插入四张表的文字版；`--json` 加 `display`。
- **三种模板**：标题行、固定小项、三行、复制块由 `render_request` 统一排；复制块用 `review.reply_blocks`。

## 影响面

新增：`module_crew/present.py`、`tests/test_review_display.py`。修改：`review.py`、`start.py`、`changes.py`、`inbox.py`、`__main__.py`、`skills/crew-coordinator/SKILL.md`、`README.md`，以及按需调整断言的已有测试。
不新增依赖，不改契约、`interface.json`、版本号。

## Task List

- [ ] Task 1：并行边界重叠三种结论；交审中的 Spec 未落集成分支时「未比对」；有 scopeOverlap 时按交审提交里的 Spec 比对（Spec 验收 6）
- [ ] Task 2：最终验收四张表、超出 Plan、Spec 差异，进 batch 与 for-hub 卡（Spec 验收 1、2）

### Checkpoint 1（report）：重叠与最终验收就位，相关测试通过，记入 todo 后继续

- [ ] Task 3：开工、公共变更请求、卡住选做法三种模板（Spec 验收 3）
- [ ] Task 4：多模块分节测试、crew-coordinator skill、README（Spec 验收 4、5）
- [ ] Task 5：全量测试与旧称扫描（Spec 验收 7）

### Checkpoint 2（gate）：最终验收

- [ ] 回告：完成情况发给总协调（local_d7434023）；重叠接入情况告诉 spec-guard 负责人（local_0a689563）
