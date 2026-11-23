# Implementation Plan: crew-takeover-approve

<!-- spec-guard: review approved -->

> 依据：`spec/crew-takeover-approve.md`（用户 2026-11-21 批准，事项 C607「C607 A」）。任务清单：`tasks/crew-takeover-approve/todo.md`。

## Overview

先做不依赖上游的部分：autonomyTier 退役、三个开关独立、`tier restore` 改指引（Task 1）。再停在一个 `gate` 等 spec-guard 0.91.0（interface 1.15）与 delegate 接口 1.5 发版，
发版后按真实接口读接管档位、显示批准方式、分开批（Task 2、3），接 Codex 审查与返工（Task 4）、放行落地与记账、Codex 不可用（Task 5），出事收窄（Task 6）。
「放行」类【协调通知】要等 session-protocol 契约发版，单独排在后面（Task 7）。最后改 skill、README、同步后跑全量测试并实测（Task 8）。
每个任务先写失败的测试、看到红再实现到绿，在本模块分支本地提交；不推送、不发版。每个任务都验证「不接管时输出与今天相同」。

## Architecture Decisions

- **新文件 `module_crew/takeover.py`** 集中读档位、每模块三项、批准方、收窄入口调用；其他文件只加调用，减少和 `crew-takeover-merge` 的冲突面。读 spec-guard 的安全限制照 `autonomy.read`（固定参数列表、只认已知读法、脚本在安装目录内、`cwd` 设安装目录、带 `probe.MAP_TIMEOUT`、不经 shell），在集成 checkout 读，进程内按 `.agent/config.json` 修改时间缓存。
- **上游字段以真实接口为准**：Spec 假设 1、2 的字段名是推定的。Gate 0 通过后先读真实的 interface.json 与 delegate 报告样例，和 Spec 不同就改夹具与实现，在 Spec 末尾「变更记录」追加一行，随最终验收复审。
- **虚拟审查者 `codex`**：`review add` 判定节点由 Codex 放行时在交审事项上记 `reviewer`、`sentTo: ["codex"]`、`sentAt`；`review codex-note` 把报告转成和 `note` 相同的一行记录，抽出 `note` 里「记结论 → 返工或超限」那段为内部函数共用，上限参数化（人 3、Codex 2）。`_rounds` 按事项的 `reviewer` 计数，不和人工审查的轮次混。
- **对得上**：`codex-note` 用报告 `scope.fingerprint`（delegate 1.4 起的 `blob-pairs-v1`）与交审提交里每个文件的 blob 比对；比对方法按 delegate 发版说明实现，读不懂指纹按「对不上」拒收（宁严勿松）。
- **落地共用**：从 `review._approve` 抽出 `_land(project, picked, mark_state, record_kind, answer)`：写文件、写标记、提交、记批准事项、发通知；`review approve` 与 Codex 放行都走它，`review approve` 的行为与输出不变（现有测试守住）。
- **收窄**：`autonomy.incident`／`degrade` 签名与四个挂钩点不动，内部改调 `takeover.narrow(db, project, module_id_or_None, kind, ref, reason)`；去重仍用 `config/main.autonomy.incidentKeys`。调用失败只少一行提示，不影响调用方（同今天）。
- **退役**：`autonomy.read`／`effective`／`evidence`／`suggestion`／`suggestion_line`／`restore` 删除或改为不再被调用；`declared.enabled` 只认显式开关；`start.cadence_info` 去掉降档上限分支，`review_cadence` 加可选 `module` 参数（决策 8）；`merge.py` 去掉合入后的建议行。`config/main.autonomy` 里的旧记录保留不删。
- **新开关 `digest`**：照 `declaredScope` 的写法进 `module-crew config`，要原话，记事件。

## 影响面

新增：`module_crew/takeover.py`、`tests/test_takeover_approve.py`、测试夹具（假 spec-guard 1.15、假 delegate 报告）。
修改：`autonomy.py`、`review.py`、`start.py`、`declared.py`、`merge.py`（只去掉建议行）、`probe.py`（`status` 的 `store.takeover`）、`protocol.py`（Task 7）、`__main__.py`、
`tests/test_autonomy_tier.py`（按退役改写，改写清单随最终验收列出）、`skills/crew-coordinator/SKILL.md`、`codex-skills/crew-coordinator/SKILL.md`、`skills/crew-dev/SKILL.md`、`codex-skills/crew-dev/SKILL.md`、`README.md`。
不新增依赖；不改 `store.py`、`checks.py`、`interface.json`、版本号、CHANGELOG（发版时由模块协调写）。公共文件不碰。

## 构建开始时（不是 Task，开工通知到了就做）

- 经模块协调向 session-protocol 契约提需求：【协调通知】新增类型「放行」（Spec 决策 12）。发【等待其他会话】给 mc-coord，写明要的条文；契约要用户批准，结果回来前不做 Task 7。

## Task List

- [ ] Task 1：autonomyTier 退役与三个开关（Spec 决策 10 的 `tier restore`、决策 11；验收 11、验收 9 的 restore 部分）
  - 做：`declared.enabled` 只认显式开关；`cadence_info` 去掉降档上限分支；去掉升档建议（`tier`、`status`、`merge run`）；`tier restore` 只输出指引、退出码 3；`config --digest on|off` 要原话；旧 `autonomyTier` 非 strict 时 `tier`、`status` 写迁移提示
  - 验证：1.14 夹具报 `relaxed` 时开工说明、`review batch`、`declared.enabled` 不受影响；`declaredScope` 没设为假；`config --digest` 没原话退出码 3；`test_autonomy_tier` 按退役改写后全过；开工、声明范围、合并回归测试通过

### Checkpoint 1（report）：退役就位，相关测试通过，记入 todo 后继续

### Checkpoint 0（gate）：上游发版

- [ ] 本机装好 spec-guard 0.91.0（interface 1.15 有 `takeover`）与 delegate 接口 1.5：没发版就停在这里，发【等待其他会话】给 mc-coord（在等 sg-coord、delegate-owner 发版）；发版后读真实接口，与 Spec 假设 1、2 不同处改 Spec 并记变更记录，再继续

- [ ] Task 2：`takeover.py` 读档位；`tier [--json]`、`tier --preflight`；`status` 接管一段与 `store.takeover`（Spec 决策 1、2；验收 1、2、10 的显示部分）
  - 验证：1.15 夹具四种项目档、模块单独设、`forcedHuman` 读对；低于 1.15、读法不同、脚本跑不成按人批带原因；不接管时 `status` 逐字不变、`store.takeover` 为 null；preflight 0.91.0 退出码 0、0.90.1 退出码 3
- [ ] Task 3：开工说明与交审登记行写批准方式；批量交审排除 Codex 项并加告知行；批准人不同自动分开批（Spec 决策 2、8；验收 3、8）
  - 验证：Spec 人批 Plan Codex（及反过来）在 `reviewCadence=combined` 下仍 separate；Codex 项不进给用户的批次与决策收件箱卡片；强制人批写原因

### Checkpoint 2（report）：读档位与显示就位，相关测试与开工、批量交审回归测试通过，记入 todo 后继续

- [ ] Task 4：`review codex`、`review codex-note` 的记结论、返工与超限、对得上（Spec 决策 3、4；验收 4、6）
  - 验证：有阻断返工第 1、2 轮，第 3 次仍阻断退出码 5 带 A／B 草稿、不挂降档；缺 `severity` 按阻断；只有建议走放行；复审命令带 `--previous-report`；指纹或内容对不上退出码 3 不记；人工审查者的返工上限仍是 3
- [ ] Task 5：放行落地（`_land`、`codex-approved` 标记、`codex-approval` 记账、开工通知）；Codex 不可用；`review approve` 对 Codex 项的拒绝与用户选 B 后的人批（Spec 决策 5、6、7；验收 5、7、10）
  - 验证：夹具记下标记调用参数为 `codex-approved`；提交信息写「Codex 放行事项」；没有【用户答复】发出；Spec 与 Plan 都批了发开工通知、依据写放行事项号；报告缺失／坏／失败／部分覆盖退出码 5；`review approve` 现有测试全过

### Checkpoint 3（report）：Codex 放行链路就位，本模块测试与审查就近、批量交审、外包、提前开工回归测试通过，记入 todo 后继续

- [ ] Task 6：出事收窄与 `tier degrade`（Spec 决策 9、10；验收 9）
  - 验证：四类出事按「合并 → Plan → Spec」降一格（夹具看收窄入口收到的参数）；全人批不调；同一事项只降一次；归到模块且模块单独设过时模块与项目都收窄；`tier degrade` 参数与退出码不变；收窄失败只多一行提示、合并与返工结果不变

### Checkpoint 4（gate）：契约「放行」类型

- [ ] session-protocol 已发版并含【协调通知】类型「放行」：没发就停在这里（其余已完成的照常保留），发【等待其他会话】；用户若决定不改契约，改为请用户定替代做法再继续

- [ ] Task 7：`protocol.py` 认「放行」；只放行 Spec 时发「放行」通知（Spec 决策 12；验收 5 的放行通知部分）
  - 验证：`protocol check` 认新类型且「依据」缺放行事项编号时报错；separate 下 Codex 放行 Spec 只发「放行」、不发开工；契约样例逐条通过
- [ ] Task 8：四份 skill、README；`module-crew sync` 合入集成分支后后台跑全量测试；本机实测 `takeover` 读取与一次真实 `/delegate:review` 报告进 `codex-note`（Spec 验收 12、13、1）

### Checkpoint 5（gate）：最终验收

- [ ] 回告：完成情况经模块协调转告 ecosystem-lead 与 autopr-design（S101 合并方案第 2 节 module-crew 的批准部分已实现；`crew-takeover-merge` 可开工）

## Risks

| 风险 | 影响 | 缓解 |
|---|---|---|
| 上游字段名与 Spec 推定不同 | 返工夹具与实现 | Gate 0 先读真实接口再写码；差异记变更记录、随最终验收复审 |
| 上游迟迟不发版 | 模块停在 Gate 0 | Task 1 不依赖上游先做完；停住时照规则发【等待其他会话】，必要时请模块协调挂起本模块 |
| 抽 `_land` 改坏 `review approve` | 人批流程出错 | 抽取前后 `review approve` 现有测试逐字通过；抽取单独一次提交 |
| 退役让现有 `test_autonomy_tier` 大面积变红 | 难判断是否误伤 | 改写逐条列清单（删、改、留），随最终验收给出 |
| 指纹比对算法读错 | 误拒或误收 | 读不懂一律拒收；用 delegate 真实报告做一次实测（Task 8） |
| 契约不批「放行」类型 | Task 7 做不了 | Checkpoint 4 停下请用户定替代做法，不擅自借用其他通知类型 |

## 返工：M1 停点不通过（2026-11-22）

用户在 M1 停点判定不通过（原话「不通过，重开修」）。依据沙箱实跑报告 `module-crew-m1-sandbox/M1-REPORT.md`（提交 02a5acd）的注意 1～4、11。均在已批准 Spec 的范围内（修正行为与 Spec 描述不符之处），Plan 批准标记不改回 pending：

- 注意 11（要紧）：module-crew 自己解析「预先声明」，`- 无（…）` 被判为没有预先声明而交 Codex 放行；spec-guard 判为格式错误、要人批。改为以 spec-guard 的判定为准（Task 9）。注意 1：改回人批时说明原因（Task 9）。
- 注意 2、3：返工重交换了 C 号，轮次与「返工后才放行」计数从 1 重新数，第二轮不带 `--previous-report`。改为按模块＋节点累计（Task 10）。
- 注意 4：`tier restore` 已退役仍要求原话参数（Task 11）。
- 注意 5～7（措辞、`review batch` 仍列出审查中项、preflight 依赖状态库）不改代码；如需与草案对齐，改用法草案或 Spec 的措辞，随返工最终验收一并呈现。

若改动需要修订 Spec（例如 Task 9 改变决策 1 的读法），照常在 Spec「变更记录」追加并随返工最终验收复审。

## 返工：M1、M2 停点不通过（2026-11-23，第 3 轮）

用户在 M1、M2 停点判定不通过（原话「按推荐继续」，推荐为「M1、M2 都判不通过，两个模块原地重开修」）。依据 0.24.1 安装版沙箱实跑报告 `module-crew-m2-sandbox/M1-M2-REPORT.md`（提交 8dc41d5） 的问题 A～G、I、K 与注意 5、7。均为修正已批准 Spec 描述的行为（返工能走通、上限与 spec-guard 一致、提示准确），Plan 批准标记不改回 pending；做法改变 Spec 决策的，照常在 Spec「变更记录」追加，随返工最终验收复审。

- 问题 A（严重）：第 2 轮起的 `--previous-report` 被 delegate 以 `previous_report_scope_mismatch` 拒绝（返工必然换提交），所有返工路径都失败（Task 13）。
- 问题 C（严重）：module-crew 允许审 3 轮，spec-guard 0.92 两轮阻断后拒收 `codex-approved`（`codex-rounds-exhausted`）；落地失败还在集成 checkout 留下未跟踪文件、事项卡住（Task 14）。
- 问题 G：Codex 看不到 Spec／Plan 引用的项目已有文件（如 `scripts/check.sh`），一轮接一轮阻断（Task 15）。
- A、C、G 的做法依赖上游约定：mc-coord 已问 delegate-owner（#22261）与 sg-coord（#22260），答复由模块协调转来；先做 Task 16、17，Checkpoint 7 收到答复再做 Task 13～15。
- 问题 B、D、E、F、I 与 K 中的编号混用（Task 16），注意 5、7 与用法草案对齐（Task 17）。
- 上游答复（spec-guard，sg-coord #22262）：两轮上限是 spec-guard 有意的硬上限（spec/codex-approval.md 假设 6、AC2；`review_mark.py` 的 `ROUND_CAP = 2`），只数「有阻断」的轮次；与之一致的做法是两轮阻断后直接转人批、不审第 3 轮。spec-guard 不打算放宽。Task 14 按此做。
- 上游答复（delegate，delegate-owner #22282，按 delegate 0.10.0／接口 1.5 代码并 `--dry-run` 核过）：
  - A·最终验收：`--previous-report` 只用于范围对得上的复审（delegate spec/review-recheck.md A9：`scope.paths` 的 include／exclude、`baseline.mode` 相同，commits 模式下 `baseline.from` 也相同，只有 `to` 可前进）。做法：`--base` 固定写第一轮报告的 `scope.baseline.from`（完整提交号，不写分支名）；每轮显式给同样的 `--paths`（可以是目录），只让 `--head` 前进。显式 paths 以外的改动不进审查。
  - A·Plan 审查（快照）：delegate 规格缺口（快照 from = to = 当时 HEAD，返工后必然对不上），放宽要 delegate 的用户先定。在那之前第 2 轮起不带 `--previous-report`，把上一轮阻断逐条写进审查说明请 Codex 逐条核对；轮次由 module-crew 自己记。最终验收里写明这是暂行做法。Task 13 按此做。
  - G：`--spec`／`--plan` 可重复、接受仓库里任何文件，进 `context_files`（按 `to` 提交读入、`scope.files` 带 sha256，不进补丁、不进 `scope.fingerprint.paths`、不参与 A9 比较）；不能落在 `--exclude` 里（否则 `context_file_excluded`），一次审查文件总数上限 256。审查说明另加一句「context_files 只用来核实 Spec/Plan 的引用，不对它们本身提发现」。只写说明而不带文件不推荐。Task 15 按此做。
