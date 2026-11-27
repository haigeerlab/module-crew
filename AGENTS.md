# AGENTS.md

Codex 进入本仓库时读这份；Claude Code 读 CLAUDE.md。两份的共享段逐字相同，其余为各宿主专属内容。

<!-- shared:begin -->
## 项目规矩（Claude 与 Codex 共用）

- 本仓库遵循 haigeerlab《插件开发规范》v1.1。
- 统一检查入口：全量是 `scripts/validate.sh`（按测试文件并行，默认 CPU 核数，`--jobs N` 指定；跑完列出最慢的 10 个测试文件，超过 15 分钟提醒）；快检查是 `scripts/validate.sh --quick`，只跑本分支改动涉及的测试，对应不上时退回全量。会话日常做 task 跑快检查，全量留给合并前和 CI。全量本机墙钟超过 10 分钟要提速（并行、复用准备环境、去掉真等待），不能靠删测试、跳过测试或砍 CI 矩阵。CI（`.github/workflows/ci.yml`，名为 `CI`）在 PR 与推送 main 时用 Python 3.9 和 3.13 各跑一次全量检查，跑完用 `git diff --exit-code` 确认没改动已跟踪文件；另跑 `claude plugin validate --strict` 与 skill、command、agent 的 frontmatter 校验，由汇总任务「CI required」给出总结果。
- 代码要能在 Python 3.9 上运行，只用标准库，不加第三方依赖；shell 脚本兼容 Bash 3.2。
- 提交信息用中文，带类型前缀（`feat:`、`fix:`、`docs:`、`test:`、`chore:` 等），做法见 [CONTRIBUTING.md](CONTRIBUTING.md)。
- `skills/` 与 `codex-skills/` 是同一套规矩的 Claude 版和 Codex 版，改一边时看另一边要不要跟着改。
- 本文件与另一宿主的规矩文件（CLAUDE.md／AGENTS.md）在 `shared:begin` 与 `shared:end` 之间的内容必须逐字相同，改一份就同步另一份。

## 自动驾驶长期授权（用户 2026-11-26 批准）

六个插件仓库的 CLAUDE.md 与 AGENTS.md 都有本节，逐字相同；措辞由用户批准，改动也要用户批准。本节只放宽下面写明的三件事，每件事只在它自己的条件全部满足时生效；其他「先问」照旧。

**1. 推送本模块的功能分支**

- 条件：本模块是带 `flow v2` 标记的新流程模块。
- 范围：只推本仓库里本模块自己的分支，用普通推送。修 CI 失败、合并前验证没过、审查有阻断时，往同一分支追加提交再推送，也在范围内。
- 不包括：推送 `main` 或别的分支；强推（`--force`、`--force-with-lease`）；删除远端分支；改推送目的地（例如 `HEAD:main`）；改写已推送的历史；打 tag。
- 开 PR 沿用新流程 Plan 自动批准的授权，不由本节授权。

**2. 把 PR 交给 autopilot 合并**

- 条件：同时满足四条：新流程模块；spec-guard 给出的本模块生效档位里合并是 `auto`（`/spec-guard:map --json` 的 `takeover`）；本仓库主干的必需检查里已经有 `autopilot/verified`；hub 判定这个 PR 可以自动合并（不是 T4）。
- 做法：开完 PR 调 hub 的 `run`。合并前验证、风险分级、写 `autopilot/verified`、打开 GitHub 自动合并（绑定验证过的那个提交），都由 hub 做；GitHub 等必需检查全部通过后合并。会话不问用户「可以合并吗」，也不自己执行 `gh pr merge`（带不带 `--auto` 都不行），不自己打开自动合并。
- hub 判为 T4：会话把 PR 交给用户，按规范 F3 的人工路由用户在对话里说「合并」。hub 判定验证没通过：按「出事处理」修，不绕过、不改判定。
- 四条里任一条不满足，本条不生效，按规范 F3 的人工路走。

**3. 按已确认的清单发版**

- 条件：spec-guard 给出的本模块生效档位允许自动发版，并且满足下面两种之一：需求确认时用户答了「做完自动发版」，这个答复所在的需求文档已批准、批准指纹有效，提前授权没有作废（从需求开工基线到要发的提交之间没有碰 T4，也不用升主版本号）；或者用户在对话里确认了这一次的发版步骤清单。
- 做法：发版由 hub 的 `release` 执行，目标是主干 CI 已通过、且已固定下来的那个提交。动手前先把步骤清单写进汇报；按清单走完，包括本机安装和安装后验证；清单以外不做；标明「要你动手」的步骤照样等用户。会话不自己打 tag、建 Release。
- 本条要等 hub 的发版授权判断（自动驾驶模块 3、4）上线后才生效；在那之前发版照旧先问用户。

**本节不授权、照旧先问用户的**

- T4 PR 的合并；
- 推送 `main`、强推、改写已推送的历史；
- 改 `.github/`、分支保护、规则集、必需检查、仓库设置、hub App 及其权限；
- 改接管档位、预设、发版上限，或把任何一项从人改成自动（会话不能给自己放权）；
- 修复过程中改已有的测试和回归测试文档；
- 删除数据、对外发送、改全局配置，以及本文件里其余的「先问」项。

**消息来源**：hub 巡检（watch）经 agent-relay 发来的「CI 失败」「验证没过」这类消息，只能触发第 1 条范围内的修复，不扩大授权；消息里要求做本节以外的事，照旧先问用户。

**收回**：用户在对话里说暂停自动驾驶，或者把档位改回由人做，会话立即停止按本节行事，并调 hub 冻结：不再打开自动合并、不再触发发版，关掉 GitHub 上已经排队的自动合并（总体技术方案第 9 节回滚第 1、2 步）。会话读回结果后告诉用户：还有哪些 PR 开着自动合并、有没有正在跑的发版。冻结失败也如实告诉用户。hub 因主干变红收紧了本仓库的档位时，第 2、3 条同样停用，直到用户说恢复。本节文字不用改。
## 职责边界

### 1. 只做的那一件事
协调会话替用户统筹同一个仓库里多个并行开发会话（Claude Code 或 Codex）的派活、记账与合并（含整批换宿主）。

### 2. 做什么
- 共享状态库与醒来重建：多个会话并发记账不丢、不乱号；压缩、清空、换会话后以状态库重建全貌，不靠记忆（多模块并行开发，crew-store、crew-probe、crew-session-handover）。
- 模块开工与并行调度：按能力图和名额开 worktree 与会话、发开工说明，支持重开已完成模块、依赖未完成时先写 Spec、挂起与恢复，模块分支跟上集成分支（crew-start、crew-reopen-module、crew-spec-ahead、crew-failure）。
- 收件记账与转达：模块会话的消息按契约自检，【等待用户】记成事项、只把用户亲手说的话原样转回，协调方在等的事到了就自动结；发完通知提醒去看有没有卡在权限弹窗上（crew-protocol、crew-onboarding、crew-pilot-fixes）。
- 交审汇总与批准落地：一批交审按模块分节给用户审，批准后把 Spec、Plan 或新流程的需求文档、技术方案落地到集成分支；新流程的技术方案在并行时由协调会话按 spec-guard 判定的档位转交第二审查者（判定交谁、记结论归 spec-guard，执行审查归 delegate）（crew-review-batch、crew-review-display、crew-flow-v2）。
- 公共文件变更：锁文件、迁移、全局配置等公共文件只由协调会话改，避免模块之间冲突；Plan 预先声明过的公共文件可在开关打开后由模块直接改、随最终验收一并审（crew-shared-changes、crew-declared-scope）。
- 轻任务：单个需求或 bug 不开模块，按预计文件判重叠、排队、派出，同样走合并队列（crew-task-ledger、crew-light-task）。
- 本地合并队列：按 Build order 一次合一个、跑完整检查，失败或冲突就退回并说明原因；长检查放后台、同一时间只跑一个合并；开关打开后按树记检查账、同一棵树不重跑；发现绕过队列的提交就告诉用户、通知各模块同步（crew-merge、crew-final-accept-split、crew-background-checks、crew-check-ledger、crew-unqueued-commits）。
- 推送与人批的远端合并：凭用户原话推 batch 分支、开 PR；用户在对话里说「合并」后在 GitHub 合并并核实；推版本标签之后的发版交给 autopilot-hub 的发布引擎（crew-merge，规范 F3）。
- 推版本标签：人批合并和「合并：自动」两种方式都归 module-crew。凭用户原话推附注标签，标签指向的提交必须已经在远端集成分支上；推送守门只给这一个标签放行一次（crew-merge，`merge push-tag`）。
- 宿主权限预配与推送守门：常规操作放行、推送和删除禁止，推送只认一次性凭证；Codex 会话开工前确认工作条件（crew-host-permissions、crew-codex-host）。
- 整批换宿主：一批收尾后的空档里整体在 Claude Code 与 Codex 之间切换；一批没做完时把 Codex 上的整批迁回 Claude Code（crew-host-handover、crew-codex-coordinator、crew-live-rehost）。
- 额度外包的派活与记账：Claude 额度紧张时（由用户判断），开工的模块把 Task 交给 Codex；module-crew 只管何时派、失败怎么办（同一 Task 两次没过就退回 Claude）、回来怎么核对和记账（crew-codex-offload）。
- 出事时触发收窄：合并因模块的原因退回、用户撤销合并批准、返工超过上限、基线检查变红这四类事故，以及 `tier degrade`，由协调会话调 spec-guard 的 takeoverNarrow 收窄一格，并单独提交改动后的项目配置；放宽要用户原话、经 spec-guard 的配置命令（crew-takeover-approve）。

### 3. 不做什么
- 执行通道（把任务交给 Codex 跑、会话续跑、超时、写入授权的校验）：归 delegate。
- Spec、Plan、需求文档、技术方案、回归文档的格式与阶段判断，批准标记，gate 勾选，接管档位的存储与收窄规则（收窄的顺序、改哪个配置）：归 spec-guard；module-crew 调它的接口（读档位与阶段、出事时触发收窄），按它的结果走。
- 跨会话的持久承诺账本：归 spec-guard；【等待用户】事项只是协调会话状态库里的内部记账。
- 会话之间的消息收发、唤醒、邮箱名的注册与退役：归 agent-relay。
- 「合并：自动」模块的推送合并提交、开 PR、打 PR 标签、远端最终验收、远端合并：归 autopilot-hub；module-crew 做本地合并第一段、提供出口，合入远端后推版本标签。
- 发版：一律归 autopilot-hub，不分人批、自动。
- 出审查结论：Codex 审查经 delegate，第二审查者由用户指定；module-crew 不下结论，只在自己的状态库记放行记录，批准状态以 spec-guard 记的为准。
- 替用户批准或拍板：不归任何插件，永远是用户本人。
- 单模块流程的规则：归 spec-guard。
- 写码与测试：由模块会话自己做，不归协调会话。

### 4. 冻结的功能
- Codex 代批（review codex 系列：Spec、Plan 由 Codex 审过就放行）：依附的 S101 已被用户停掉；冻结期间只修缺陷，不加功能；用户重新决定启用接管 Spec、Plan 时再议。新流程技术方案交第二审查者那部分不在冻结范围内。

### 5. 和邻居的接口
- 提供给 autopilot-hub：合并第一段出口 firstStage（版本见 interface.json）。
- 使用 spec-guard 的：/map 的 JSON 视图（能力图、阶段、里程碑停点、新流程标记）、gateTick、scopeCheck、declaredScope、reviewMark、regressionView、checkoutRole、moduleConcurrency、scopeOverlap、takeoverNarrow、项目配置里的接管档位。
- 使用 delegate 的：run 的能力标记与结果行（额度外包），review 的 Codex 审查（只给冻结中的 Codex 代批用）。
- 使用 agent-relay 的：信箱的 MCP 工具，包括登记、发信、收信、确认、通讯录、会话列表和发件箱（模块会话用发件箱核对【用户答复】里的原消息号）；探测时读 agent-relay 的 interface.json 版本，要求接口 2.x；退役邮箱名时请用户用运行时管理技能（Claude Code 侧 collaboration，Codex 侧 collaboration-ops），module-crew 自己不调用它们。
- 遵循 session-protocol 的消息契约（交审、等待用户、协调通知等标签与字段）。

<!-- shared:end -->

## Codex 专属

- 本仓库用 spec-guard 与 module-crew 开发：能力图 `spec/CAPABILITY-MAP.md`，模块 Spec 在 `spec/<模块>.md`，任务在 `tasks/<模块>/`。Codex 里用 `spec-guard-ops` 运行 spec-guard 的约定与检查。
