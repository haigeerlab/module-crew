# Todo: crew-stall-signals

测试命令：`python3 -m unittest discover -s tests -v`

- [x] Task 1：提交事实与开工时间（`startedAt`、`commits`）
  - 验收：Spec 验收 1、2、3
  - 文件：`module_crew/stall.py`、`module_crew/failure.py`、`tests/test_stall_signals.py`

- [x] Task 2：问过你、合并退回、等待用户（`asks`、`returns`、`waitUser`）
  - 验收：Spec 验收 4、5、6、7
  - 文件：`module_crew/stall.py`、`module_crew/failure.py`、`tests/test_stall_signals.py`

- [x] Checkpoint 1（report）：新字段齐全；现有 sessions 契约测试原样通过、状态库读不到仍退出 2（验收 8）（2026-10-19，全量 361 个测试通过；`tests/test_hub_output.py` 的契约与 `test_unreadable_exits_2_with_reason` 未改动照常通过）

- [x] Task 3：人看的 `sessions` 与 `status`；crew-hub-bridge 契约一句与变更记录；README 第 121 行
  - 验收：Spec 验收 9
  - 文件：`module_crew/failure.py`、`module_crew/probe.py`、`spec/crew-hub-bridge.md`、`README.md`、`tests/test_stall_signals.py`

- [x] Checkpoint 2（gate）：模块最终验收——全量测试全绿（验收 10）、验收逐条对应测试、改动文件清单与提交号（2026-10-19 用户批准，同时批准 crew-hub-bridge Spec 的追加修订；版本号定为 0.4.0；全量 364 个测试通过；提交 9c43617、79e69a2、657b5eb）

- [x] 回告：把 sessions --json 新字段说明发给 decision-inbox 插件会话确认字段名（用户 2026-10-19 要求）——2026-10-19 已用桌面版跨会话消息发给「Decision-inbox 插件第 3 阶段能力图」，请它回 A 照用或 B 改名；等回复，要改名就在发版前给本模块追加任务。发版后再告知新字段可用

- [x] Task 4（追加）：`asks` 每项加 `ats`（与 `refs` 一一对应的时间）
  - 验收：Spec 验收 4（修订后）
  - 来源：decision-inbox 回复选 B，用户 2026-10-19 批准修订
  - 文件：`module_crew/stall.py`、`tests/test_stall_signals.py`

- [x] Task 5（追加）：`commits.last` 改为开工以来第一父链上的最新提交，合入后不再显示「开工以来没有提交」
  - 验收：Spec 验收 1（修订后）、9
  - 来源：验收 11 实测时接入方案会话发现，用户 2026-10-19 批准冻结前先修
  - 文件：`module_crew/stall.py`、`module_crew/failure.py`、`tests/test_stall_signals.py`

- [x] Task 6（0.5.0，R21 MC-3）：`sessions --json` 加 `answers`（每次用户答复后的提交数与 todo 勾选增量）；发版前请决策收件箱确认字段名
  - 验收：Spec 验收 11
  - 文件：`module_crew/stall.py`、`module_crew/failure.py`、`tests/test_stall_signals.py`、`spec/crew-hub-bridge.md`（契约一节加一句）

## 外部审查意见

<!-- spec-guard: external-review declined -->
用户 2026-10-19 在最终验收时表示不做外部审查。

- [x] R21 MC-3 验收（2026-10-19 用户批准；全量 415 个测试通过）

- [x] Task 4（0.8.1，接入协调 2026-10-20 报 `sessions --json` 超过 decision-inbox 的 15 秒上限，用户同意先修再装）：同一次 `sessions` 里同一条 git 查询只问一次；
  每个模块的首父链只读一次，答复前后 todo 的勾选数按时间在 Python 里挑提交，所有要读的 todo 用一个 `git cat-file --batch` 读完；`commit_facts` 用一条 `git log` 同时拿提交和时间。输出不变
  - 验收：crew-rehearsal 真实数据改前改后输出逐项一致（7 个模块、27 个答复；`ago` 随时间变化除外）；git 进程 137 → 36，同负载下 3.07 s → 0.92 s；新测试卡住每模块 git 进程不随答复数增长（≤6）
  - 文件：`module_crew/stall.py`、`module_crew/failure.py`、`tests/test_stall_signals.py`、`README.md`、三处版本号


- [x] Task 4 验收（0.8.1；2026-10-20 用户批准；全量 458 个测试通过；提交 e8818d3）
