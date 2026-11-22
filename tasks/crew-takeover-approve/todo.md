# Todo: crew-takeover-approve

> 依据 `tasks/crew-takeover-approve/plan.md`。

- [x] Task 1：autonomyTier 退役与三个开关（Spec 决策 10、11；验收 11）——测试先红（4 个失败 1 个报错）后绿；`declared.enabled` 只认显式开关，`cadence_info` 去掉降档上限分支，升档建议整段删除，`tier restore` 退出码 3 给指引，新开关 `config set --digest`（Spec 写的是 `config --digest`，实际挂在现有 `config set` 下）；`test_autonomy_tier` 改写：删 StandardTest（3 个）、StandardKickoffTest、AdviceTest（4 个）、IncidentTest 的两个 restore 用例，改 ReadTest 两个、ExternalDegradeTest 的 restore 用例、StatusTest 一个，由新文件 RetireTest 等 8 个覆盖；`incident`／`degrade` 留到 Task 6 再改
- [x] Checkpoint 1（report）：退役就位——本模块与旧档位测试 36 个通过；声明范围、开工、合并、提前开工、批量交审与批准等回归测试 182 个通过
- [x] Checkpoint 0（gate）：上游发版（spec-guard 0.91.0／interface 1.15、delegate 接口 1.5）——本机已装 spec-guard 0.91.0、delegate 0.10.0（接口 1.5），恢复依据 C626；按真实接口修订 Spec（9e235b2，「上游实测」一节与变更记录），并按用户「批草案并改边界」改并行边界（09050b2），两处随最终验收复审
- [x] Task 2：`takeover.py` 读档位、`tier`／`--preflight`、`status` 接管一段（Spec 决策 1、2；验收 1、2）——实现先于测试，测试一次通过；临时去掉强制人批后测试转红，确认测到；每模块档位读 `/map --json`，项目档位读 `project_config.py show`；旧 `autonomy.preflight` 及 PreflightTest（3 个）删除，由新 preflight 两个测试覆盖；本模块与 probe／status 回归 68 个通过
- [x] Task 3：显示批准方式、批量交审排除 Codex 项、批准人不同自动分开批（Spec 决策 2、8；验收 3、8）——实现先于测试；`review add` 对 Codex 节点记虚拟审查者 `codex`（不发邮箱、不超时），`review batch`／`for_hub` 不提请 Codex 项、末尾加告知行，`start.review_cadence` 加模块参数、开工说明在批准人不同时写 separate 并加批准方式一行；回归时 `test_review_nearby` 一个用例转红（开工说明绕过了 /map 的节奏），已改为沿用 /map 读到的节奏
- [x] Checkpoint 2（report）：读档位与显示就位——本模块 17 个通过；交审、批量、收件箱、开工、提前开工、外包、轻任务、重开、契约等回归 299 个中 1 个失败已修，复跑本模块与审查就近 59 个通过
- [x] Task 4：`review codex`／`codex-note`：返工、超限、对得上（Spec 决策 3、4；验收 4、6）——实现先于测试；虚拟审查者 `codex`，阻断返工两轮、第 3 次仍阻断退出码 5 给【等待用户】草稿且不降档，缺 severity 按阻断，复审命令带 `--previous-report`，按 `scope.files` 的 sha256 对交审提交核对、对不上退出码 3；返工通知让模块会话先 `review-mark --state codex-reviewed` 记这一轮
- [x] Task 5：放行落地与记账、Codex 不可用、`review approve` 的回退（Spec 决策 5、6、7；验收 5、7、10）——`review._approve` 参数化共用落地（单独提交 bda2b32），写 `codex-approved --review`、记 `codex-approval`、不发【用户答复】；Codex 没结论退出码 5；`review approve` 对 Codex 项拒绝，新增 `review codex-fallback`（要原话）后照人批（Spec 已补变更记录）；按 mc-coord #22000（用户「取消 T628」）修好 spec-guard 0.91.0 新模板下 `review approve` 与 `merge run` 记 Spec 修订批准两处，复现测试 Template115Test、SpecRevision115Test 在修复前代码上分别报「不认识的占位符」与没记下修订批准，修复后通过
- [x] Checkpoint 3（report）：Codex 放行链路就位——本模块 26 个通过；交审、合并、收件箱、开工、提前开工、外包、轻任务、重开、最终验收拆分、旧档位、声明范围、检查账等回归 463 个通过
- [x] Task 6：出事收窄与 `tier degrade`（Spec 决策 9、10；验收 9）——实现先于测试；`incident` 内部改调 `takeover.narrow`（`--source module-crew --confirm`，归到模块且模块单独设过时模块与项目都收），收窄后在集成分支单独提交 `.agent/config.json` 并记为 module-crew 自己的提交；`incident` 加可选参数 `module`（签名兼容）；`tier degrade` 参数与退出码不变；测试中发现收窄提交会改集成分支的树、让基线检查重跑再降一格，已加去重（同一红基线、其后没有别的提交就不再收窄）；旧档位测试里 IncidentTest 等 4 个类（13 个用例）由 NarrowTest 等 9 个用例取代
- [x] Checkpoint 4（gate）：契约「放行」类型已发版——session-protocol v2.9 于 21eff81 发版（mc-coord #21922）；样例按用户答复 C630「甲：随模块合并」放在本分支 tests/fixtures/session-protocol/v2.9/（252 个文件，SHA256SUMS 全部通过）
- [x] Task 7：认「放行」通知、只放行 Spec 时发它（Spec 决策 12）——`protocol.py` 认类型「放行」（approved-by-review）、`missing-approval-node`、`notice.node`，契约版本钉到 2.9；`review._approve` 在 Codex 只放行一个节点时发放行类通知；契约样例 v2.2～v2.9 全过，本模块 ReleaseNoticeTest、NoticeRenderTest 通过
- [x] Task 8：skill、README、`module-crew sync` 后全量测试、本机实测（Spec 验收 12、13、1）——四份 skill 的档位一节改为接管档位，README 中英、docs/guide.md、docs/commands.md、docs/architecture.md 同步；sync 后集成分支仍是 b671c6f；第一次全量 1334 个中 2 个失败（文档里的旧称「用户答复」「协调会话」、interface.json 的 contract 仍是 2.8），修后（6a1e326）全量 1334 个全过（1774 秒）；本机实测：spec-guard 0.91.1 上 `tier --preflight` 退出码 0、`tier --json` 读到项目 none 与两个在用模块全人批；真跑一次 Codex `/delegate:review`（审本模块 Spec），报告字段与 `codex-note` 的读法一致、`scope.files` 的 sha256 等于已提交文件
- [x] Checkpoint 5（gate）：最终验收
- [x] 回告：经模块协调转告 ecosystem-lead 与 autopr-design（已发：ecosystem-lead #22043、autopr-design #22044，2026-11-22）

## 返工：M1 停点不通过（2026-11-22）

- [x] Task 9：「预先声明」以 spec-guard 判定为准——Plan 有没有预先声明改为读 spec-guard（`module_scope.py declared` 或 `/map --json` 的结论），格式错误按「有预先声明、人批」处理，不再自己解析；Plan 因此改回人批时，`review add` 登记行与 `review batch` 写出原因（M1 报告注意 1、11）——测试先红（8 个报错）后绿；`takeover.predeclares` 改为调 interface.json 的 `declaredScope`（在交审 worktree 读，worktree 的 Plan 与交审提交不同也按人批），退出码 0 且四个清单任一非空、退出码 4／2、调用失败超时均人批（读法依 mc-coord #22074、#22076）；交审事项记 `humanReason`，登记行写「Plan 改为人批：…」，`review batch` 写「批准方式：人批（…）」；Spec 决策 1 与变更记录已改（d356484），本模块 39 个通过
- [x] Task 10：Codex 轮次跨重交累计——「返工后才放行」计数、`review codex` 显示的第几次、审查编号 R-<次>、报告文件名都按模块＋节点累计，与 spec-guard 记的 round 一致；第 2 轮起命令带 `--previous-report <上一轮报告>`（M1 报告注意 2、3）——测试先红后绿；新增 `takeover._history`（同模块同节点、本轮重开之后各交审事项的 Codex 报告，按事项号排），`review codex` 的「第几次」、报告文件名、`--previous-report`，`codex-note` 的 R-<次>、放行记账的 `rounds` 都按它算，`reworked` 因此计入重交后放行；新用例 test_rounds_add_up_across_resubmissions（Plan 与只接管 Spec 两种设置下都跑）；本模块 41 个通过（fed3fc9）
- [x] Task 11：`tier restore` 不再要求 `--original(-file)`，无条件输出指引并退出 3（M1 报告注意 4）——测试先红后绿；`--original`／`--original-file` 改为可选（照收、忽略，不在帮助里列出），在打开状态库之前处理，指引写到标准输出、退出码 3；没有状态库的目录里实测同样退出码 3；本模块 41 个通过（9825088）
- [ ] Task 12：同步 skill 与文档、`module-crew sync` 后全量测试；用安装版重跑 M1 前由模块协调安排
- [ ] Checkpoint 6（gate）：返工最终验收
