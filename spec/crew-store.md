<!-- spec-guard: review approved 45f344b847dd -->
# Spec: crew-store

> 能力图模块 `crew-store`。需求来源：`docs/requirements-record.md` 第 7 节（恢复五原则与状态库内容）、B2（认领 = 角色标记，变更请求、等待单、消息记录用状态库）、
> 假设 1（同一台 Mac）。假设见下文，用户 2026-10-18 已确认。

## 目标

给后面 9 个模块打底：搭好插件骨架，并在项目的公共 git 目录下提供可靠的状态库——运行配置、会话登记、待用户决定事项（含原话）、
公共变更请求、等待单、发出的正文，以及只追加的事件日志。协调会话和各模块会话在不同 worktree 里同时读写同一份状态库；
任何会话中断、压缩或被替换后，都能只凭这些文件重建全貌（对话里不留唯一副本）。

使用者是本插件的其他模块（Python 调用）；用户只通过只读的 `store check` 排查。

## 范围

**范围内**

- 插件骨架：`.claude-plugin/plugin.json`（名 `module-crew`，版本 `0.0.1`，只有元数据，不注册命令、技能或钩子）。
- Python 包 `module_crew`，本模块只含 `store.py`、CLI 入口与 `bin/module-crew`。
- 定位状态库：`git rev-parse --path-format=absolute --git-common-dir` 下的 `module-crew/`；任一 worktree 里定位到同一处。
- 通用记录机制：记录种类、编号分配、事件追加、快照读写、从日志重建、正文文件。
- 命令 `store init`（建库）与只读的 `store check`。

**范围外**

- 各种记录的业务字段与状态流转（事项由 crew-review-batch 等定，请求由 crew-shared-changes 定，等待单由 crew-onboarding／crew-failure 定）；
  本模块只校验记录的通用外壳。
- `status` 总览与依赖体检（crew-probe）；消息解析与生成（crew-protocol）；spec-guard 的角色标记（由 spec-guard 写）。
- 任何删除、清理、归档功能。

## 假设（用户 2026-10-18 已确认）

1. Python 3 标准库，无第三方依赖；测试 `python3 -m unittest discover -s tests -v`；包名 `module_crew/`，入口 `bin/module-crew`；代码注释英文、给人看的提示中文。
2. JSON 文件 + 只追加的 `events.jsonl`；文件锁 `fcntl.flock`，写临时文件 → `fsync` → `os.replace`（同 decision-inbox `store.py`）。
3. 以事件日志为准；快照只是缓存，坏了或丢了能从日志重建；日志坏行只报告，不覆盖、不自动修复。
4. 一个项目一条编号序列，事项、请求、等待单、正文共用，写作 `#N`；与 agent-relay 邮箱号是两套。
5. 协调会话与模块会话都可能写，靠文件锁串行；状态库只在本机，不入版本库，不跨机器。
6. 不删除：更正和关闭都追加事件，没有删除接口。
7. 只做库接口与只读 `check`；`status` 归 crew-probe。

## 关键决策与取舍（请重点审）

1. **事件携带记录全文，快照可完全由日志算出。** 每次写记录都追加一条事件，`data.record` 是写入后的**整条记录**（不是差量）。
   于是任何种类的快照 = 对日志按 `(种类, 键)` 取最后一条事件的 `record`。这让「以日志为准」不依赖各领域自己的重放规则；
   代价是日志更大（一条事项被改 5 次就存 5 份全文），按本插件的规模（一批 ≤3 个模块、几十到几百条记录）可以忽略。
2. **编号与事件序号都从日志算，不另存计数文件。** 下一个编号 = 日志中已出现的最大编号 + 1；下一个 `seq` = 最大 `seq` + 1。
   分配编号必须在同一事务里写出带这个编号的记录，否则编号不算用掉（事务回滚后同一个号会再被分出去）。
   好处是少一个会和日志打架的文件；代价是每次开事务要读一遍日志（几百行，毫秒级）。
3. **快照落后或缺失时读者在内存里补算，不写盘；写事务结束时写出最新快照。** 快照的 `lastSeq` 小于日志最大 `seq` 时，读接口把多出的事件叠上去后返回，并给一条警告；`check` 报告落后条数。
4. **快照损坏时改名留证，然后重算。** 快照文件无法解析或版本不认识：读接口从日志重算并给警告；下一个写事务先把坏文件改名为
   `state/<种类>.json.corrupt-<时间>`（不删除），再写新快照。**日志**损坏不同：坏行跳过并警告，`check` 退出码 3，绝不改写日志。
   版本不认识的**日志行**同样跳过并警告。
5. **记录种类固定六种**，写死在 `store.py`，新增要改本 Spec：

   | 种类 | 键 | 用途 |
   |---|---|---|
   | `config` | 固定 `main` | 运行配置（项目简称、集成分支、同时进行上限等，字段由使用模块定） |
   | `session` | agent-relay 名字 | 会话登记 |
   | `item` | 编号 | 待用户决定事项与用户原话 |
   | `request` | 编号 | 公共变更请求 |
   | `ticket` | 编号 | 等待单 |
   | `body` | 编号 | 发出的正文（全文存成文件，记录里放路径与指纹） |

6. **正文是不可变文件。** `bodies/<编号>.txt` 写一次就不再改；记录里存相对路径、字节数与 `sha256`。用于 agent-relay 的 `bodyFile`，
   也让「发出的正文」在换会话后仍能原样重发或核对。
7. **会话登记只校验外壳。** `role` 只能是 `coordinator`／`dev`（session-protocol 角色代码）；同一时刻只有一个 `active` 的 `coordinator`；
   `dev` 必填 `module` 与 `worktree`（绝对路径），同一 `module` 同一时刻只有一个 `active` 的 `dev`；`host` 只能是 `claude-desktop`（第一版）。
   换会话 = 把旧条目改为 `retired` 并写新条目，旧条目不删。
8. **权限收紧**：目录 `0700`、文件 `0600`（里面有用户原话）。

## 接口约定

### 目录与文件

```text
<git-common-dir>/module-crew/      0700
├── meta.json                      {"version": 1, "createdAt": "..."}
├── events.jsonl                   事件日志，只追加；唯一的事实来源
├── state/<种类>.json              快照：{"version": 1, "lastSeq": 41, "records": {"<键>": {...}}}
├── bodies/<编号>.txt              发出的正文，不可变
└── .lock                          库锁（fcntl.flock），内容为空
```

- 所有 JSON 顶层带 `"version": 1`；`meta.json` 版本不认识或无法解析：读写都拒绝，文件不改。
- 时间一律 ISO 8601、带本机时区偏移、精确到秒，例如 `2026-10-18T13:36:05+08:00`。
- 不在 git 仓库里（`git rev-parse` 失败）时报错退出，不在别处建目录。

### 事件日志一行

```json
{"v": 1, "seq": 41, "at": "2026-10-18T13:36:05+08:00", "type": "item.created", "key": "12", "actor": "shop-coord", "data": {"record": {}}}
```

- `seq`：从 1 递增，不跳号不重复。
- `type`：`<种类>.<动作>`；种类必须是六种之一，动作是小写字母、数字、连字符，由使用模块定义；本模块只校验格式。
- `key`：记录键（字符串；编号类种类为十进制编号）。`actor`：会话的 agent-relay 名字，或 `user`、`system`。
- `data.record`：写入后的整条记录（JSON 对象）；`data` 里其他键由使用模块定义，本模块原样存取。

### Python 接口（其他模块只通过这些用）

```python
from module_crew import store

db = store.open_store()                       # 按当前目录定位；未 init 时抛 StoreNotFound
with db.transaction(actor="shop-coord") as tx: # 持库锁；退出时先追加事件，再写快照
    n = tx.allocate_number()                  # 13
    tx.put("item", str(n), {...}, action="created")
    body = tx.write_body(n, "【交审】\n...")   # 返回 {"path": "bodies/13.txt", "bytes": 87, "sha256": "..."}
    tx.warnings                               # 事务开始时发现的问题

store.get(db, "item", "12")                   # 不加锁的只读；没有返回 None
store.records(db, "session")                  # {键: 记录}
store.events(db, key="12", kind="item")       # 该记录的全部事件，按 seq 排序
store.read_body(db, 13)                       # 读正文并核对 sha256，不符抛 StoreCorrupt
```

- 事务内抛异常：日志、快照、正文目录都与事务前逐字节相同（正文先写临时文件，提交时才改名）。
- 事务里没调用写方法：不改任何文件。
- 同一事务里对同一记录 `put` 多次：每次各追加一条事件。

### 命令行

```bash
bin/module-crew store init      # 建库；已存在时不改任何文件，退出码 0 并说明「已存在」
bin/module-crew store check     # 只读：路径、版本、事件条数、下一个编号、各种类记录数、快照落后条数、坏行与损坏文件
```

`bin/module-crew` 等价于 `python3 -m module_crew`。退出码：`0` 正常；`2` 不在 git 仓库、未 init、参数不合法；
`3` 发现坏行、损坏文件或正文指纹不符（`check` 照常打印其余信息）。快照落后只警告，退出码仍为 0。

## 项目结构

```text
.claude-plugin/plugin.json   Claude Code 清单（只有元数据）
bin/module-crew              CLI 包装脚本
module_crew/                 Python 包，只用标准库
  __init__.py
  __main__.py                CLI 入口：python3 -m module_crew
  store.py                   本模块
tests/
  helpers.py                 建临时 git 仓库与 worktree
  test_store.py              单元、并发与崩溃测试
docs/                        需求文档（已有）
```

## 命令

```bash
python3 -m unittest discover -s tests -v
```

没有构建步骤。

## 代码风格

```python
class StoreCorrupt(StoreError):
    """A store file exists but cannot be trusted; keep it as evidence."""

def _atomic_write_json(path: Path, doc: dict) -> None:
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=2, sort_keys=True)
        f.flush()
        os.fsync(f.fileno())
    os.chmod(tmp, 0o600)
    os.replace(tmp, path)
```

- 代码、标识符、注释用英文；给用户看的输出与报错用中文。
- 只用标准库；类型标注写全；异常类集中在 `store.py` 顶部，都继承 `StoreError`。
- JSON 写出 `ensure_ascii=False`，中文原样保存。

## 测试策略

- 标准库 `unittest`；每个测试在临时目录里 `git init` 一个真实仓库，需要时 `git worktree add`，不碰任何真实项目。
- 并发用 `multiprocessing` 起真实多进程，并且分别从主 checkout 与 worktree 里打开状态库。
- 崩溃用人工构造的文件模拟（日志多出事件而快照未写、日志末尾半行、快照非法 JSON）。
- 不追求覆盖率数字；下面每条验收标准至少对应一个测试。

## 边界

- **始终**：所有写入走库锁；写前检查 `meta.json` 版本；损坏文件留证不删；测试只在临时仓库里跑。
- **先问**：新增记录种类或顶层文件；改事件日志格式；引入第三方依赖。
- **绝不**：删除、截断、轮转状态文件或日志；改写日志里已有的行；把状态写进任何被 git 跟踪的路径。

## 验收标准

1. 在临时仓库里 `store init`：建出 `<git-common-dir>/module-crew/`（`0700`），含 `meta.json`、`events.jsonl`（均 `0600`）；再跑一次不改任何文件内容与修改时间，退出码 0。
2. 从该仓库的一个 `git worktree` 里 `open_store()` 得到同一路径；`git status` 在主 checkout 与 worktree 里都看不到状态库文件。
3. 不在 git 仓库里、或未 init 时：`store check` 退出码 2，不新建任何目录。
4. 两个 checkout 里共 20 个进程，各在独立事务里分配 50 个编号并各写一条 `item`：得到 1～1000，无重复无遗漏；日志 `seq` 1～1000 连续。
5. 事务内抛异常后：日志、快照、`bodies/` 与事务前逐字节相同；下一次分配得到同一个编号。
6. 删掉 `state/item.json`：`get` 与 `records` 结果与删除前相同（从日志重算）；下一次写事务后快照重新出现且 `lastSeq` 等于日志最大 `seq`。
7. 构造「日志 `seq` 到 42、`item` 快照 `lastSeq` 为 41」：读接口返回含第 42 条的结果并给警告；`check` 报告「快照落后于日志 1 条：item」、退出码 0。
8. 把 `state/item.json` 改成非法 JSON：读接口照常返回（从日志重算）并警告；下一个写事务后原文件以 `item.json.corrupt-<时间>` 原样存在，新快照正确。
9. `events.jsonl` 末尾追加半行：读接口跳过它并警告，`check` 退出码 3；下一次追加的新事件独占完整一行，可被读出；半行原样留在文件中。
10. 种类不在六种之内、动作格式不对、`record` 不是对象：`put` 被拒，什么都不写。
11. 会话登记：两个 `active` 的 `coordinator`、同一 `module` 两个 `active` 的 `dev`、`dev` 缺 `module` 或 `worktree` 或 `worktree` 不是绝对路径、`role` 为 `hub`、`host` 为 `codex-desktop`——都被拒；把旧 `dev` 改为 `retired` 后可以登记同一 `module` 的新 `dev`。
12. `write_body` 写出的文件内容与入参逐字节相同、指纹正确；改动正文文件一个字节后 `read_body` 抛 `StoreCorrupt`，`check` 退出码 3。
13. `meta.json` 版本改成 2：读写都拒绝，文件不变。
14. 插件清单是合法 JSON，`name` 为 `module-crew`；`module_crew/` 没有标准库以外的 import，代码里没有对状态库文件调用 `unlink`、`rmtree`、`truncate`（测试扫描断言）。

## 未决问题

无。

## 文档建议

本模块不需要用户文档；`store check` 的输出说明并入能力图评审时定的 README（crew-start 之后补）。
