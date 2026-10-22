# Spec: crew-unqueued-commits

<!-- spec-guard: review approved dff0981ab934 -->

> 能力图模块 `crew-unqueued-commits`（第六版第 4 个）。需求来源：`docs/requirements-record.md` 第 14 节第 2 条后半（「发现不经队列合入的提交时告诉用户并照常通知各模块同步」，用户 2026-10-22 确认）。
> 依赖 `crew-merge`（合并队列）、`crew-coordinator-switch`（模块协调）。标「新」的是写 Spec 时补的实现取舍，请重点审。

## 目标

集成分支上出现了不是 module-crew 自己做的提交（有人在普通会话里直接提交、在终端里手动合并、从远端拉下来的提交），模块协调能发现，
告诉用户一次，并照常给在开发的模块和在做的轻任务发同步基线通知。插件不拦这些提交，也不撤回它们。

## 范围

**范围内**

- 记下「module-crew 最后一次认得的集成分支顶端」（下称「认得点」）：模块协调升级、开工、以及 module-crew 每次在集成分支上提交后更新。
- 新命令 `module-crew unqueued`：列出认得点之后、集成分支主线上的提交（只读）；`--notify` 生成同步通知并把认得点推进到当前顶端。
- `merge run` 合并前先检查：有不经队列的提交就照实列出、生成同步通知、推进认得点，然后照常合并（不挡合并）。
- `status` 多一行「集成分支上有 N 个不经队列的提交」（只读，不推进认得点）。
- skill 写明：看到这一行就告诉用户一次，运行 `unqueued --notify` 发出通知。

**范围外**

- 拦截或撤回这些提交；判断它们对不对。
- 远端 `fetch`：只看本地集成分支。
- 钩子里跑 git：钩子照旧只读文件。

## 假设

1. module-crew 在集成分支上提交的地方有四处：`merge run` 的合并提交、合并后勾最终验收的提交、`change land` 的公共变更提交、`review approve` 的批准标记提交。
2. 不经队列的提交可能是用户有意做的；module-crew 只告知、只通知同步，不要求用户解释。
3. 同步通知的收件人与跳过规则和合并后一样（`merge.no_sync`）；在做的轻任务也收。

## 关键决策与取舍（请重点审）

1. **（新）用「认得点」判断，不靠提交信息**：提交信息前缀可以配置，也可能被手写的提交模仿，不可靠。状态库 config 记 `integrationSeen`（提交号）。
   module-crew 自己在集成分支上提交后，同一个命令里把认得点更新为新顶端；`coordinator up`、第一次 `start prepare` 把它设为当时的顶端。
   不经队列的提交 = `git rev-list --first-parent <认得点>..<集成分支>`。认得点不在集成分支历史里（被改写过）时，照实报「认得点不在集成分支上」，只列顶端一个提交并请用户核对。
2. **只告知一次**：`unqueued --notify` 与 `merge run` 生成通知后把认得点推进到当前顶端，同一批提交不会再报。`status` 只读，不推进。
3. **通知内容**：同步基线类【协调通知】，「依据」写「集成分支上有 N 个不经合并队列的提交（<最早>～<最新> 的短号）」，「要你做什么」照现有同步步骤；轻任务的通知带「任务」。
4. **不挡合并**：`merge run` 发现后先通知、推进认得点，再合队首；合入后的完整检查本来就会把这些提交一起检查进去。
5. **旧项目**：没有认得点的已开工项目，第一次运行 `unqueued`、`status` 或 `merge run` 时，把当时的顶端设为认得点（`unqueued`、`merge run` 写入；`status` 只显示「还没有认得点，下次 merge run 或 unqueued 时记下」），不回头追查以前的提交。

## 接口约定

```bash
module-crew unqueued [--json]        # 只读：认得点、集成分支顶端、不经队列的提交（短号、作者、时间、标题）
module-crew unqueued --notify        # 生成同步通知（逐条列出收件人与正文路径），推进认得点
```

退出码：`0` 没有或已处理；`3` 有不经队列的提交但没加 `--notify`；`2` 参数错或没有状态库。
状态库：config `integrationSeen`；事件 `integration-seen`（带旧值、新值、来源命令）。

## 项目结构

```text
module_crew/unqueued.py      新：读认得点、列提交、通知、推进
module_crew/commits.py       提交成功后更新认得点的小函数
module_crew/merge.py, changes.py, review.py, coordinator.py, start.py   提交后或开工时更新认得点；merge run 合并前检查
module_crew/probe.py, __main__.py   status 一行、unqueued 子命令
skills/crew-coordinator/SKILL.md
tests/test_unqueued.py
```

## 命令

```bash
python3 -m unittest discover -s tests
PYTHONPATH=tests python3 -m unittest test_unqueued
```

## 代码风格

沿用现有模块：代码与注释英文，输出中文；只用标准库；git 带超时、不经 shell。

## 测试策略

- 认得点：升级、开工时设定；四处自己的提交之后都更新，所以它们不被报。
- 发现：在集成 checkout 手动提交两次 → `unqueued` 列出两个、退出码 3；`--notify` 给在用模块与在做的任务发同步通知（跳过规则同合并）、推进认得点，再跑为 0。
- `merge run`：手动提交后合队首——先通知再合并，认得点最后等于合并后的顶端。
- `status` 显示数量且不改状态库；旧项目没有认得点时的三种命令表现。
- 认得点不在历史里（`reset --hard` 到更早）时的提示。
- 回归：全量测试通过。

## 边界

- **始终**：只读本地 git；通知照现有跳过规则；只告知一次。
- **先问**：拦截或撤回不经队列的提交；在钩子里运行 git。
- **绝不**：改写集成分支历史；`fetch` 或访问网络。

## 验收标准

1. `coordinator up` 与第一次 `start prepare` 记下认得点；`merge run`、合并后的勾选、`change land`、`review approve` 提交后认得点等于新顶端，这些提交不会被报为不经队列。
2. 集成 checkout 里手动提交后，`unqueued` 列出这些提交（短号、作者、时间、标题），退出码 3，状态库不变。
3. `unqueued --notify` 给在用模块与在做的轻任务各发一条同步基线通知（跳过规则与合并后相同，轻任务带「任务」），推进认得点；再跑退出码 0。
4. 有不经队列的提交时 `merge run` 先列出并通知、再照常合并，认得点最后等于合并后的顶端。
5. `status` 显示「集成分支上有 N 个不经队列的提交」且不改状态库；没有认得点时显示待记下的提示。
6. 认得点不在集成分支历史里时照实提示并请用户核对。
7. 全量测试通过。

## 未决问题

- 用户在集成分支上有意直接改的东西（比如紧急修复），要不要提示「下次走轻任务」：这一版只告知事实，不加劝导。

## 文档建议

README「出状况时怎么办」加一条「集成分支上有不经队列的提交」；命令一览补 `unqueued`。
