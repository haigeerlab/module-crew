# 更新记录

各版本的变化，最新的在前。README 只写最新一版。

## 0.14.1 的变化（热修）

- 提交类的 git 调用不再写死 30 秒超时：`change land`、`review approve`、`merge run` 的合并提交，以及合并收尾的两次提交（记下修订后 Spec 的批准、勾选最终验收），超时改用项目的 `checkTimeout`（默认 1800 秒，与完整检查同级）；只读的 git 调用仍是 30 秒（S28）。
- git 在独立的进程组里运行，超时就结束整组（先 SIGTERM 让 git 清掉 `index.lock`，5 秒后 SIGKILL），钩子启动的子进程不会留在后台。
- 超时一律退出码 4，并给出恢复提示：`change land` 的文件仍是暂存状态、请求仍开着，确认没有 `.git/index.lock`、钩子进程已结束、集成 checkout 里除清单文件外没有别的改动后，直接重跑同一条 `change land`，不用先取消暂存；`review approve` 把集成 checkout 还原、交审仍开着；合并提交中止合并、集成分支不变、合并批准仍开着；合并收尾报「合并提交已在集成分支、检查已通过、状态库未记合并，不要重跑 merge run，交模块协调」，不自动重试。
- 接口与契约不变（`interface.json` 1.0、session-protocol v2.6），状态库不变。
- 升级后：在用的 Claude 会话在原会话里 `/clear` 一次；Codex 侧重新装本插件并完全退出 ChatGPT 再打开。0.14.0 下因超时中断、文件还暂存着的公共变更请求，升级后按上面那条直接重跑 `change land`。钩子确实超过 30 分钟的项目，把 `checkTimeout` 调大。

## 0.14.0 的变化（LIVE-SAAS 演练修复）

- 已开工的项目也能改提交前缀：`module-crew config set --commit-prefix <值> --original-file <原话文件>`，凭用户原话改 module-crew 自己提交信息的前缀（空字符串表示不加），不用再借 `start prepare`；项目的 commitlint 不认 `chore(crew):` 时用它（S23）。
- `review approve` 遇到集成分支已经是批准内容、没有差异时不再提交，把当前 HEAD 记为基线，照常闭合交审、发答复与开工通知；批准标记写不上仍报失败（S23）。
- 提交被钩子拒时，`review approve`、`change land` 与合并后补记 Spec 批准都附上钩子的退出码和最后 10 行；`review batch` 比对并行边界的临时 Spec 改放系统临时目录、比完即删，不再写 `.git`（S19、S21）。
- 开工说明第一步按项目根的锁文件给出装依赖命令（`pnpm install --frozen-lockfile`、`npm ci`、`uv sync` 等）；`host-check` 新增「提交钩子」一项，试跑 pre-commit，跑不通报最后几行（S22）。
- `host-check` 认轻任务会话的登记；版本一项改为和固定入口当前转到的版本比，本机升级后不再误报（S24）。
- 换宿主：交接说明在新宿主的规则文件没被 git 忽略时多一步「加进 .gitignore 再重跑 permissions apply」，「在 Codex 里信任项目」提到贴开场文字之前；`status --json` 的 `host` 按登记的模块协调宿主输出；`permissions plan` 没有模块协调登记时提示先 `coordinator up`（S20）。
- crew-coordinator skill（Claude、Codex 两份）写明：批准一律走 `review approve`，失败就停下报给用户，不手工补提交，不把提交信息包装成给用户的推荐回复（S25）。README 写明模块协调也能换到 Codex（S17）。
- 状态库只增字段，不用迁移；接口与契约不变（`interface.json` 1.0、session-protocol v2.6）。
- 升级后：在用的 Claude 会话在原会话里 `/clear` 一次；Codex 侧重新装本插件并完全退出 ChatGPT 再打开。commitlint 拒 `chore(crew):` 的项目，由模块协调凭用户原话跑一次 `config set --commit-prefix`。Codex 上的模块协调跑它要申请沙箱外运行：Codex 版 crew-coordinator skill 的清单里还没列这条命令，第一次会被沙箱拒绝，照实申请一次提权即可（下一版补进 skill）。

## 0.13.0 的变化（第八版：空档换宿主）

- 空档整体换宿主：一批模块和轻任务都收尾、没有未结事项时，`merge cleanup` 与 `status` 提示「本批已收尾，具备换宿主的条件」；用户说换后 `coordinator handover --check` 逐条核对条件，`coordinator handover --to codex|claude --original-file <原话文件>` 改模块协调登记的宿主、给集成 checkout 追加新宿主的权限规则、生成逐步交接说明（每步写去哪个会话、做什么、做完的样子）。`bind --takeover` 核对调用者宿主与登记一致；模块协调在 Codex 时开工与派任务默认 Codex、拒绝 `--host claude`。
- 模块协调能在 Codex 桌面版上运行：新增 Codex 版 crew-coordinator skill（每轮开头重新注册→`status`→读收件箱、写命令申请沙箱外运行、请用户手动开任务）；`status` 在 Codex 里首行认出本线程是不是模块协调；`host-check` 在集成 checkout 按模块协调查；沙箱拒绝写 `.git`、找不到插件时报错带补句；`merge run --detach` 把合并连同锁交给后台子进程，`merge result [--wait]` 取结果（与前台逐字一致）。
- 修复：已登记的会话不再算进「没登记的会话」（S7）；Spec 以接口提案交审时批完 Plan 照常发开工通知（S14）；轻任务会话派出时也写上权限规则、`module-crew sync` 能在轻任务 worktree 里跑（S15、S16）；crew-coordinator skill 写明合并只走 `merge run`（S1）。
- 状态库只增字段（`hostHandover`、合并记录的 `detached`／`adopted` 等），不用迁移；接口与契约不变（`interface.json` 1.0、session-protocol v2.6）。
- 升级后：在用的 Claude 会话在原会话里 `/clear` 一次；想用 Codex 做模块协调或模块会话的，在 Codex 里装上本插件并完全退出 ChatGPT 再打开。在 Codex 上实际跑一批、来回换一次宿主还没实测（见「尚未验证」）。

## 0.12.1 的变化（热修）

- Claude 会话也改用状态库里的固定入口 `<git公共目录>/module-crew/bin/module-crew`：`permissions apply` 先写出它，Claude 规则放行它而不再放行带版本号的插件路径；钩子注入的「module-crew 命令入口」也是它（状态库还没有固定入口时照旧给插件路径，并提示跑一次 `permissions apply` 或 `coordinator up`）。以后升级插件不用再重跑 `permissions apply`。
- 升级后：已写过权限规则的项目，凭用户原话再跑最后一次 `module-crew permissions apply`；在用的会话在原会话里 `/clear` 一次，拿到新的命令入口。
- README 的契约版本更正为 v2.6。

## 0.12.0 的变化（第七版：换手与呈现）

- 命令入口：Codex 会话改用状态库里不带版本号的固定入口 `<git公共目录>/module-crew/bin/module-crew`，每次转给当前安装的那份，升级后不用换；`bin/module-crew` 不再让当前目录里的代码盖过插件自己的代码。
- 会话换手：钩子按会话编号认身份，模块协调在别的目录也收到角色提示与命令入口；`bind <邮箱名> --takeover` 一步接手模块协调（要用户原话），旧会话随即失效；模块协调的写命令只认登记的会话，别的会话退出码 7；`status` 标出「← 本会话」。重开请在原会话里 `/clear` 或退出应用再打开，不要新开会话。
- 契约钉到 session-protocol v2.6：待定问题按登记的决策收件箱版本编 `C<交审号>-<序号>` 或 D，两种答法都认；答复块一块只答一件事；最终验收的「验收结果」改名（旧名照收）；可登记 `--protocol 2.6`。
- 提请批准的呈现：并行边界重叠用交审中的 Spec 经 spec-guard `scopeOverlap`（接口 1.10）比对，比不了写「未比对」，只有比对过才写「无」；最终验收按 spec-guard 的小项列出文档、代码（超出 Plan 的标出）、提交、新增依赖四张表，Spec 中途改过附差异；开工、公共变更请求、卡住选做法三种请示用同一个骨架。
- 升级后：在用的会话在原会话里 `/clear` 一次；模块协调的写命令若被拒（退出码 7），经用户同意在当前会话 `bind <邮箱名> --takeover`；已开工的 Codex 会话由模块协调转告一次新入口。

## 0.11.3 的变化（热修）

- `merge push` 的推送用完整检查的超时（`checkTimeout`，默认 30 分钟），项目的 pre-push 钩子跑检查不再被 30 秒掐断；超时或推送失败一律退出码 4、给出可读原因，不再抛 Python 栈。
- `merge push-plan` 的 PR 目标：`--pr-base` → 配置 `prBase` → 远端有跟踪分支的集成分支 → 远端默认分支；提交只列相对目标多出的那些；都取不到时退出码 3，请用户用 `--pr-base <分支>` 指定（`push` 同样可带）。
- 升级后：在用的 module-crew 会话在原会话里 `/clear` 或退出应用再打开（不要新开会话）。

## 0.11.2 的变化（热修）

- Plan 交审带着修订过的 Spec 时，`review add` 提醒附上 Spec 的改动差异（`review show C<号> --spec-diff`），`review approve` 一次记下 Spec 与 Plan 两份批准；只差批准标记的 Spec 不再从模块分支拷过来，集成分支上已批准的那份保持原样。原来只写 Plan 标记会被 spec-guard 拒绝，重跑还会用旧标记盖掉补好的 Spec。
- `review approve` 中途失败（写标记失败、提交被拒）时把集成 checkout 还原：原有的文件恢复成集成分支上的内容，这次新建的文件只取消暂存、不删，在输出里列出。
- 升级后：在用的 module-crew 会话在原会话里 `/clear` 或退出应用再打开（不要新开会话）。

## 0.11.1 的变化（热修）

- 构建中修订过的 Spec，合入时替用户记下批准：`review add` 比对模块分支与集成分支上的 Spec，不一样就提醒附上差异（`review show C<号> --spec-diff`）；`merge approve` 记下一并批准；`merge run` 合入通过检查后经 spec-guard 的 reviewMark 在集成分支记下批准，单独一个提交，记不上只报告。原来要人手动补 review-mark。
- 命令入口跟着插件走：钩子在会话启动、压缩、清空时给出「module-crew 命令入口：<当前加载的插件目录>/bin/module-crew（版本 X）」，skill 与开工说明不再写具体路径；`status` 新增检查项 `module-crew`，正在运行的版本和装着的不同时报阻塞；权限规则只放行旧路径时提示再跑 `permissions apply`。原来模块协调会一直用第一次记下的旧版本路径，升级后修复不生效。
- 升级后：在用的会话重开一次；写过权限规则的项目凭用户原话再跑一次 `module-crew permissions apply`。Codex 会话没有钩子，新路径由模块协调转告。

## 0.11.0 的变化（第六版：一个模块协调管所有派活）

- 轻任务的完整流程：`task dispatch` 派出、轻任务会话交回、和模块同一个合并队列（bug 任务优先）、升格／缩小／取消；契约钉到 session-protocol v2.5（「任务」字段与 T 前缀）。
- 修正：会话唯一性规则不再把两个轻任务会话当成同一个模块的会话。
- 合并放后台跑：`merge run` 拿合并锁，跑的时候 `change land`、`review approve` 等写命令退出码 6；进程不在了的锁在集成 checkout 干净时自动清；`status` 显示正在跑的合并。
- 不经合并队列的提交：module-crew 记下自己认得的集成分支顶端，之后别人直接提交的会在 `status`、`unqueued`、`merge run` 里报一次，并通知各模块同步；不拦、不撤回。

## 0.10.2 的变化（热修）

- `change land` 不再把只改了一部分清单文件的公共变更请求当成已落地关掉：清单里还有文件没改时默认拒绝并列出它们；用户同意先落地已改的部分时加 `--partial --original-file <原话文件>`，请求保持打开，通知里写明还剩哪些，改完再 `change land` 才关闭。来源：spec-guard 试用（C42）。

## 0.10.1 的变化（热修）

- `module-crew status` 在 Python 3.10 下遇到 UTC 时区的提交（GitHub 网页合并、CI 提交）不再崩溃：git 把这类时间写成 `…Z`，3.10 的解析认不出，现在先换成 `+00:00`。来源：spec-guard 试用（K9F9VF1）。
- 模块会话的任务列表跟着 todo 推进：`crew-dev` skill（Claude 与 Codex 两版）要求开始构建时按 todo 条目列任务列表、每勾一项 todo 就推进一项。原来只在开工时列一次，用户看到列表停住会以为会话卡住了。来源：spec-guard 试用。

## 0.10.0 的变化（第六版第一步：模块协调按会话开关）

- **装了不等于开了**：用户在某个会话里明说，`module-crew coordinator up --short <简称> --original-file <原话文件>` 才把它升级为本项目的模块协调；一个仓库最多一个，第二个会话要升级会被拒并告诉你接管办法。前提同开工体检，但不要求能力图。`coordinator down` 可以关掉（没有在用的模块会话时）。
- **没有模块协调时插件完全安静**：钩子对任何会话都不注入。
- **有模块协调时，别的普通会话提醒一次**：它第一次回复你时顺带说「这个项目已有模块协调，派活与合入一般由它安排；在这里直接改也可以，只是不经合并队列」，之后照你的意思做、不再重复；模块协调下一轮也会告诉你有这个会话。插件不拦它。
- **`/clear` 之后身份自动接上**：清空会换会话编号（2026-10-22 实测）。新增的 `SessionEnd` 钩子留下交接记录：命令行版把登记转给同一目录 30 秒内以 clear 开始的新会话；桌面版绑定时记下桌面版会话编号（`CLAUDE_CODE_HOST_SESSION_ID`，清空后不变），旧进程结束后同目录、同编号的新会话接上登记（桌面版里实测通过）。
- 多模块并行默认上限从 3 改为 2（已开工项目的上限不变）。
- 体检新增 `spec-guard-enabled`（项目有没有 `.agent/config.json`）；`status` 加「模块协调」「没登记的会话」两段。
- 轻任务记录：`module-crew task add` 记下单个需求或 bug（T 编号，任务单写做什么、预计改哪些文件、做到什么程度算完）；预计文件和在做的任务或模块分支已改的文件重叠就排队，`task next` 按 bug 在前提为可开；`status` 加「任务」段。派会话做轻任务的流程在下一步补上。
- 钩子开始写状态库，只写「见到」记录、清空交接记录与登记字段，等锁最多 2 秒，失败就不说话。

## 0.9.7 的变化（职责边界审查修复）

- 体检读 Claude 插件安装记录时，结构和预期不同（宿主可能改了格式）就照实报出路径和哪里不对，不再误报「本机没有安装」；条目缺 `installPath` 时也不会再把当前目录当成安装目录。
- 写死 spec-guard 路径约定的地方加了说明（spec-guard 的接口没有给路径字段）。

## 0.9.6 的变化（职责边界审查修复）

- 合并后勾最终验收改由 spec-guard 来勾：`merge run` 和 `merge tick` 调 spec-guard 接口 1.7 的 gateTick，module-crew 不再自己找「唯一未勾项」。spec-guard 不肯勾时把它的短码原样报出来、不自己改；装的 spec-guard 低于 1.7 时不勾，提示升级后用 `merge tick` 补勾。需要 spec-guard 0.83.0 及以上才会自动勾。

## 0.9.5 的变化（职责边界审查修复）

- 审查超时、模块不同意审查意见、返工满 3 次时，模块协调给的「倾向 B」各写一句为什么稳妥，卡片的「推荐理由」也带上；不再写「取稳妥的一边；模块协调不替你判断」。这条规则归 module-crew，决策收件箱照原样显示。
- 提请批准的卡片一律按 v2.3 起的写法生成，v2.2 卡片删掉：登记 hub 不写 `--protocol` 按 2.4，`--protocol 2.2` 被拒；以前登记为 2.2 或没写的，`source list` 显示「按 2.4 发」，不用重新登记。解析器照样认旧写法。

## 0.9.4 的变化（职责边界审查修复）

- 提交信息的前缀改成项目配置 `commitPrefix`：默认仍是 `chore(crew): `，`start prepare --commit-prefix <值>` 设定，空字符串表示不加。原来写死，是为第一个试点项目的 commitlint 定的规矩。
- 停滞信号的「已勾选项」口径以 spec-guard 为准，代码和 Spec 里写明为什么自己读历史版本；行为不变。
- 各版本的变化移到 [CHANGELOG.md](CHANGELOG.md)；「尚未验证」按现状重写。
- 测试不再受运行环境里会话变量的影响。

## 0.9.3 的变化（审查修复）

- `change land` 和 `merge run` 用同一条规则决定谁不收同步基线：已批准合并在队列里的、已合并的、等最终验收的、挂起中的都不发。原来 `change land` 会通知已批准合并的模块，照做后合并被拒、用户批过的验收作废。
- `bind` 只能在登记对应的目录里运行（模块会话在自己的 worktree，模块协调在集成 checkout）；登记模块协调身份要带用户原话（`--original-file`），`start prepare` 时的自动登记不变。集成 checkout 里的陌生会话不再被提示「先运行 bind」。

## 0.9.2 的变化

- `review note` 只认收到这条交审的审查者：发件人不在送审对象里（包括这条交审没有送审）时拒收、什么都不写，说明里写清 C<N> 送给了谁；和 0.9.0 的「按负责范围送审」配成一对。

## 0.9.1 的变化（演练修复）

- 模块协调自开的等待记录 `--about C<N>`，在 `review approve`、`merge approve` 答到这个交审时也会自动关，并给出「你开的等待记录 W<号> 等的事已发生」一行；原来只有 `answer` 认 C 编号，批准命令只认收件箱事项号 #H，在本会话亲口批准时一条都不关。
- 交决策收件箱的卡片收齐审查建议：审查结论的要点里有「建议N：」行时，「注意」写全部建议原文；原来只取要点第一行，审查者先写总评时建议进不了卡片。

## 0.9.0 的变化（收发对象收窄）

- 【交审】只送给负责这个模块和节点的审查者，不再抄送给所有审查者：`source add <名> --kind lead` 必须带 `--modules <模块,…|全部>` 与 `--nodes <spec,plan,interface,final|全部>`，`source list` 显示范围。之前登记、没有范围的审查者不再收交审，`review add` 会提醒；用 `source scope <名> --modules … --nodes …` 补上。
- 公共变更落地后的同步基线通知不发给挂起中的模块（提出这条请求的模块照常收到回复），恢复时 `resume` 的通知会写明挂起期间落地的公共变更。
- 钩子按会话认身份：会话自己运行 `module-crew bind <邮箱名>` 登记（开工说明、恢复说明里都有这一步，模块协调跑 `start prepare` 时自动登记）；只有登记的那个会话才被注入「你是模块协调／你是模块 X 的模块会话」，同一目录里的其他会话只在启动时收到一句「你不是它的登记会话」。升级后已在跑的会话要各跑一次 `bind`，`status` 里标「未登记身份」。`takeover` 会清掉旧身份，新会话再 `bind`。

## 0.8.1 的变化

- `module-crew sessions --json` 少起 git 进程：同一条查询只问一次，答复前后的 todo 一次读完。crew-rehearsal 上从 137 个降到 36 个，输出不变。起因：机器负载高时它跑到 15～40 秒，超过决策收件箱的 15 秒上限，按模块判断停滞就失灵。

## 0.8.0 的变化（阶段丙补修，R22）

- 模块交了最终验收、还在等结果时，`merge run`、`change land` 不再给它发同步通知——同步会改动它的分支，让用户已经批过的验收作废；最终验收被退回或用户答 B 时，模块改完先 `module-crew sync` 再重交。
- `merge approve` 记新的合并批准时，同一模块还开着的旧批准自动作废，命令输出里说明；和 0.6.0 的「重交审作废旧批准」一起，合并队列里每个模块至多一个批准。
- 权限预配给模块 worktree 放行 worktree 内的编辑（`Edit(//<worktree>/**)`，覆盖 Write），并禁止编辑它的 `.claude/`；集成 checkout 不变。已经 apply 过的项目，重新跑一次 `permissions apply` 补上。
- 消息格式升到 session-protocol v2.4：【等待用户】紧跟「要点」带「模块：<模块 id>」（线级事项写「无」）；`review batch --for-hub` 自动写，`source add --protocol` 可写 2.4。旧版收件箱照收这一行。
- 协调 skill：发请示前先查后问，已答过、已亲口批过的不再提请；提请批准只发 for-hub 正文，不手写、不跨模块合并。

## 0.7.0 的变化（决策卡片字段）

- 消息格式升到 session-protocol v2.3：`protocol check` 认识「类型」的九种取值（能力图审阅、Spec、Plan、Spec 与 Plan、中途检查点、最终验收、接口提案、卡住选做法、去会话操作）、
  「注意」「推荐理由」「批了会怎样」三个字段，以及各类要点里的固定小项。v2.2 的写法照旧合格。
- `source add <名> --kind hub --protocol 2.3` 登记决策收件箱支持的版本（不写按 2.2），`source list` 显示。
  **登记的 hub 全是 2.3 时**，`review batch --for-hub` 才写「类型」「注意」「推荐理由」「批了会怎样」，「批准会发生什么」不再写在要点里；否则与 0.6.0 一字不差。
- **升级顺序**：先把决策收件箱升到 v2.3，再经用户同意 `source remove` 后 `source add … --protocol 2.3` 重新登记；顺序反了，v2.2 的收件箱会把带新「类型」的请示整条退回。
- 协调 skill 与模块 skill 写明卡住选做法、能力图审阅、中途检查点按类别写，接口提案交审写「改了哪个接口」「哪些模块要跟着改」。

## 0.6.0 的变化（演练修复）

- 新命令 `module-crew sync`（模块会话在自己的 worktree 里跑）：把集成分支合进模块分支，本模块的 Spec 与 tasks 冲突自动取集成分支版本，别的冲突留给模块解决（退出码 2）。
  开工、同步基线、恢复通知改为「单独执行 `module-crew sync`」，不再叫模块自己敲 `git merge`——它不在放行范围里，写法稍有不同（如 `git merge main --no-edit`）就会弹窗。
- 新命令 `module-crew review show C<号> [--submission]`（只读）：输出审查原文全文与 sha256；返工通知和开工通知里写明这条命令，模块不再去集成 checkout 的 git 目录里找原文。
- 撤回合并批准时，已经被重交审取代的交审不再重新打开；最终验收重交审时，旧的合并批准自动作废，不再排在合并队列里挡住新批准。
- 新命令 `module-crew wait add`：模块协调把自己发出的【等待其他会话】记账；所等事项的答复转达时，命令输出给出要发的【已恢复】并关掉记录。
- 发给模块会话的命令，输出末尾提醒核对对方是否停在权限弹窗；协调 skill 写明派活后用 agent-relay 查会话状态，卡住就报「去会话操作」。

## 0.5.3 的变化

- `permissions plan`／`apply` 提示别处的 ask 或禁止规则会盖过 module-crew 写的放行（读 checkout 自己的设置、worktree 的主 checkout 设置、用户设置与托管设置，只读不改），每条写成「⚠️ 会被盖过：<放行> ← <文件> 的 ask｜禁止 <规则>」。起因：集成 checkout 里别的插件写的 ask `Bash(npm install *)` 盖过了模块 worktree 的放行，模块 worktree 的会话也读主 checkout 的本地设置。

## 0.5.2 的变化（决定 67）

- 文字更正：去掉「代开会话里 ask 确认不会出现、写 ask 就等同放行」的说法（E3 会话记录显示 ask 会弹、是被点了允许）；不可逆操作仍写禁止，理由改为一次「允许」就会执行。规则行为不变。

## 0.5.1 的变化（决定 62：装包放宽）

- 权限预配：往项目里加新包也放行（`npm install <包名>`、`pnpm add`、`yarn add`、`uv add`、`uv pip install`、`.venv/bin/pip install`），新增依赖由 spec-guard SG-5 在最终验收列出；裸 `pip install <包名>` 仍交宿主默认确认；全局安装禁止补全到 `-g`／`--global` 在任意位置、`yarn global`、`uv --system`（代价：`npm ls -g` 这类只读查询也被拒）。Codex 侧加新包仍不写规则（前缀规则挡不住后置的 `-g`）。
- skill：去掉「Plan 没列的依赖只问一次」，加新包直接装。

## 0.5.0 的变化（R21 模块打转）

- 权限预配：按锁文件或清单装依赖放行，加新包不写规则（宿主默认确认＋先问一次），全局安装仍禁止；Codex 规则同步。
- skill：已批范围内直接做、不讨小许可、小步骤不送审、Plan 没列的依赖只问一次；碰到宿主确认经模块协调告诉用户去哪个会话点什么。
- 契约钉到 session-protocol v2.2：模块会话碰到宿主确认时发「类型：去会话操作」的【等待用户】，模块协调原样转给决策收件箱（没有就直接告诉用户去哪点）。
- `sessions --json` 加 `answers`：每次「你的答复」之后的提交数与 todo 勾选增量，供决策收件箱判断打转。

## 0.4.1 的变化

- 评审节奏优先读 spec-guard（0.73.0 起）`/map --json` 的顶层 `reviewCadence`，`status` 写明来源；spec-guard 较旧时照旧读 `.agent/config.json`。
- `permissions remove` 把 `.claude/settings.local.json` 逐字还原为 apply 之前的原文。

## 0.4.0 的变化

- **停滞事实出口**（R14）：`sessions --json` 每个模块加开工时间、最近一次产出提交、同一节点问过你几次（带每次的时间）、合并退回、模块报来的【等待用户】；只给事实，判断与提问归决策收件箱。见 [spec/crew-stall-signals.md](spec/crew-stall-signals.md)。
- **权限预配与推送守门**（R16）：`module-crew permissions plan|apply|verify|remove`，把常规操作写进宿主认的放行规则，推送、删除等写成禁止，再用 pre-push 钩子守住推送；推送只经 `merge push`。见下文「权限预配」与 [spec/crew-host-permissions.md](spec/crew-host-permissions.md)。
- **术语改名**：README、skill、命令说明与输出按术语表 v1.1；等待记录编号改写 `W<号>`（命令参数 `W25`、`C25`、`25` 都认）。契约标签、字段名、命令与选项名不变，状态库照旧可用。
