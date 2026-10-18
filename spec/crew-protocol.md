<!-- spec-guard: review approved 94f3a4e6e7bf -->

# Spec: crew-protocol

> 能力图模块 `crew-protocol`。需求来源：`docs/requirements-record.md` B4（消息）、第 8 节（共用契约）；契约 session-protocol v1.5（提交 246e138）。
> 假设见下文，用户 2026-10-18 已确认。

## 目标

让 module-crew 的协调会话与模块会话说同一种话：按 session-protocol v1.5 严格解析收到的消息、生成协调会话发出的消息，
并用契约自带的样例证明两边与契约一致。后面的 crew-onboarding、crew-start、crew-review-batch、crew-shared-changes 都只通过本模块读写消息正文。

使用者是本插件的其他模块（Python 调用），以及在发送前自检的会话（`module-crew protocol check`）。

## 范围

**范围内**

- `module_crew/protocol.py`：`parse`、`render_user_reply`、`render_coordination_notice`，纯函数，无 I/O。
- 钉住契约 v1.5：样例复制到 `tests/fixtures/session-protocol/v1.5/`，一致性测试。
- 只读命令 `module-crew protocol check <文件>`。
- 把本插件的接入情况写进 session-protocol 的 `conformance/README.md`「各插件现状」表（该仓库唯一改动，验收时一并交审）。

**范围外**

- 发消息、收消息、等待单、事项编号（crew-onboarding 及之后的模块；本模块不碰状态库与 agent-relay）。
- 生成多线【用户答复】、【答复告知】，解析【答复告知】（第一版用不到，见关键决策 2）。【审查结论】自 crew-review-nearby 起校验（2026-10-19 修订）。
- 判断答复是否有效（原消息号是不是收到方自己发的）：需要状态库，归 crew-onboarding。

## 假设（用户 2026-10-18 已确认）

1. 钉住 v1.5：复制 `fixtures/` 到 `tests/fixtures/session-protocol/v1.5/`，记来源提交 246e138；先核对 `SHA256SUMS`，再逐份对照期望结果，只比期望结果里出现的键。
2. 解析：【等待用户】【等待其他会话】【已恢复】【撤回】【交审】【公共变更请求】（协调会话收）、【用户答复】【协调通知】（模块会话收）、【审查结论】（协调会话收，2026-10-19 修订）、认不出的消息；【答复告知】跳过并在一致性说明里写明。
3. 生成：只生成协调会话发出的单线【用户答复】与【协调通知】；【协调通知】用「生成后再解析与输入一致」测；模块会话的消息由会话自己写、发送前用解析器自检。
4. 独立实现，不复制、不依赖 decision-inbox 的代码；契约第 2 节的切分规则照契约写。
5. 纯函数无 I/O；只读命令 `module-crew protocol check <文件>`，退出码 0 合格、3 不合格、2 参数错。

## 关键决策与取舍（请重点审）

1. **一个通用的「契约视图」作为测试与调用方的共同语言。** `Message.contract()` 返回契约第 12 节定义的那个字典
   （`type`、`valid`、`replyTo`、`end`、`markers`、`item`、`fields`……以及 v1.1 的 `submission`、`changeRequest`、`notice`）。
   一致性测试直接拿它和期望结果比；其他模块也用它的字段，不另设一套属性名。代价是字段名是契约里的 camelCase，与 Python 习惯不一致，换来的是「契约怎么写、代码就怎么读」。
2. **认得全部 10 种标签，但只对支持的 9 种做校验。** 【答复告知】解析为对应类型代码、`supported` 为假、只做通用字段切分、
   不给问题代码；调用方见到 `supported` 为假就当「第一版不处理」。这样不会把它们误判成 `unknown-kind`，也不用自造契约外的问题代码。
3. **生成函数在输入不合法时直接抛 `ValueError`，不生成带问题的消息。** 例如开工类【协调通知】的依据里没有 `#N`、类型不是四种之一、
   用户原话为空、选项原文不以字母开头。生成结果出门前再用 `parse` 自检一次，不合格也抛错——协调会话发出的消息永远合格。
4. **用户原话一字不改。** `render_user_reply` 不去首尾空白、不合并空行；原话含换行时按契约续行规则原样保留（续行不加缩进）。
5. **样例的指纹核对放在测试里，不放在运行时。** 运行时不读样例文件；升级契约 = 换一份目录、改 `SOURCE`、跑通测试。

## 接口约定

```python
from module_crew import protocol

msg = protocol.parse(text)
msg.kind          # "review-request"；认不出为 "unknown"
msg.supported     # 本插件是否校验这种类型（answer-notice 为 False）
msg.ok            # 没有问题代码
msg.problems      # ("missing-end", "missing-field:要点", ...) 问题代码，按契约顺序
msg.hints         # ("brief-thin", ...)
msg.contract()    # 契约第 12 节的 parse 字典

protocol.render_user_reply(item=12, original="12 A 先接微信支付", answered_at="2026-10-17T10:10:00+08:00",
                           option_text="A：先接微信支付", source_relay_id=4540)
# 【用户答复】\n事项：#12（你的原消息 #4540）\n用户原话：12 A 先接微信支付\n选项 A 原文：A：先接微信支付\n答复时间：...\n

protocol.render_coordination_notice(kind="start", basis="用户批准事项 #7（crew-store 的 Spec 与 Plan）",
                                    todo="在本 worktree 按 tasks/crew-store/plan.md 开始构建")
# 【协调通知】\n类型：开工\n依据：...\n要你做什么：...\n
```

- `kind` 取契约代码 `start`／`sync-baseline`／`interface-change`／`wrap-up`／`returned`，输出写中文标签；开工类与退回类的「依据」必须有 `#N`。
- 所有生成结果以单个换行结尾；字段值里的换行原样保留。

### 命令行

```bash
bin/module-crew protocol check <文件>   # 打印类型、问题代码与提示代码；0 合格，3 不合格，2 文件读不到或参数错
```

`unknown` 与不支持的类型都按不合格（退出码 3）处理，并写明原因。

### 样例目录

```text
tests/fixtures/session-protocol/v1.5/
├── SOURCE          来源：仓库路径、提交号 246e138、复制日期
├── SHA256SUMS      原样复制
└── <类型>/*.txt|*.json   原样复制（43 份样例、86 个文件，含本模块跳过的类型）
```

## 项目结构

```text
module_crew/protocol.py              本模块
module_crew/__main__.py              加 protocol check 子命令
tests/fixtures/session-protocol/v1.5/  契约样例（只读）
tests/test_protocol_conformance.py   指纹核对 + 逐份对照
tests/test_protocol_render.py        生成与往返
tests/test_protocol_cli.py           protocol check
```

## 命令

```bash
python3 -m unittest discover -s tests -v
```

## 代码风格

沿用 crew-store：代码、标识符、注释英文，给人看的输出中文；只用标准库；类型标注写全。

```python
@dataclass(frozen=True)
class Message:
    kind: str
    supported: bool
    problems: tuple[str, ...]
    hints: tuple[str, ...]
    ...

    @property
    def ok(self) -> bool:
        return not self.problems
```

## 测试策略

- 一致性：遍历样例目录，对每份 `.json` 按「类型是否支持 × 有无 `parse`／`generate`」决定比较或跳过，跳过的写进测试输出；
  任一样例对不上就失败，并打印期望与实际的差异。
- 生成：契约里的 `user-reply` 生成样例逐字比较；【协调通知】四种类型各一个往返测试，外加非法输入抛错。
- 不追求覆盖率数字；下面每条验收标准至少对应一个测试。

## 边界

- **始终**：先改契约再改实现；契约样例只复制不修改。
- **先问**：在契约之外新增问题代码或字段；改钉住的契约版本。
- **绝不**：就地修改样例文件或 `SHA256SUMS`；在 `protocol.py` 里读写文件、调用 git 或 agent-relay；修改用户原话。

## 验收标准

1. `tests/fixtures/session-protocol/v1.5/` 与 session-protocol 246e138 的 `fixtures/` 逐字节相同；`SHA256SUMS` 全部核对通过；改动任一样例一个字节，一致性测试失败。
2. 支持的 8 种类型及 `unknown` 的全部 `parse` 期望结果（v1.0 的 wait-user 12 份、user-reply 4 份、wait-session 2 份、resumed 3 份、withdraw 1 份、unknown 1 份，v1.1 的 15 份，v1.3 新增的 wait-user 3 份，v1.4 新增的 wait-user 6 份与 user-reply 1 份，v1.5 新增的 coordination-notice 3 份，共 51 份）逐键一致。
3. `user-reply` 的 3 份单线生成样例（`single`、`free-text`、`original-whitespace`）逐字相同；`multiline-user-reply`、`answer-notice` 的生成样例被跳过，测试输出列出跳过项；`review-conclusion` 的 4 份解析样例自 2026-10-19 起参与比对（解析计数 68）。
4. 【协调通知】四种类型 `render` 后再 `parse`：合格，`notice.kind` 与入参一致，三个字段的值与入参相同。
5. `render_coordination_notice` 在类型不认识、开工类依据无 `#N`、任一字段为空时抛 `ValueError`；`render_user_reply` 在原话为空、编号不是正整数、选项原文不以字母开头时抛 `ValueError`。
6. 含换行与首尾空格的用户原话经 `render_user_reply` 再 `parse`，`fields["用户原话"]` 与原话逐字相同（首行首部空格按契约规则去掉的情况在测试里写明）。
7. 【答复告知】解析得到对应类型代码、`supported` 为假、没有问题代码；【审查结论】按契约校验（结论三种写法、节点、必填字段），见 crew-review-nearby。
8. `protocol check`：合格样例退出码 0；`review-request/bad-file-line.txt` 退出码 3 并打印 `bad-file-line`；`unknown-kind.txt` 退出码 3；文件不存在退出码 2。
9. `protocol.py` 不 import `module_crew.store`、`subprocess`，不调用 `open`（测试扫描断言）。
10. session-protocol `conformance/README.md` 的 module-crew 一行写明钉住 v1.5、解析与生成的类型及跳过项（交 session-protocol 契约负责人落地，用户 2026-10-18 选 A）。

## 未决问题

- 用户原话首行若以空格开头：契约第 2 节规定字段首行的值去掉冒号后的空白，会丢掉这些空格。按契约现状实现并在验收 6 里写明；
  是否需要契约补一条「用户原话首行原样保留」，留给你决定（不阻塞本模块）。

## 文档建议

无单独文档；`protocol check` 的用法写进 crew-onboarding 的模块会话 skill。

## 变更记录

- 2026-10-18：钉住的契约由 v1.1（78da46f）改为 v1.3（42fe5f6），样例目录改为 `tests/fixtures/session-protocol/v1.3/`，解析样例由 38 份增至 41 份；验收 10 的契约仓库提交改由契约负责人落地。原因：v1.1 的 `unknown/unknown-kind` 样例用了已成为正式类型的【交审】，契约负责人在 v1.2 修正，v1.3 又只增了 3 份过简要点样例；来源：用户在 crew-protocol 最终验收时选 A（契约缺陷交契约负责人，新版本发布后改钉）。
- 2026-10-18：钉住的契约由 v1.3（42fe5f6）改为 v1.4（e33c077），样例目录改为 `tests/fixtures/session-protocol/v1.4/`，解析样例 41→48 份、生成样例 2→3 份。原因：契约负责人把「架构审查」行取值与「用户原话」首行空白写进契约并补样例，只增不改、代码不用改；来源：用户 2026-10-18 批准升级。
- 2026-10-18：钉住的契约由 v1.4（e33c077）改为 v1.5（246e138），解析样例 48→51 份；【协调通知】增加「退回」类型（`returned`），解析与生成都要求退回类「依据」带 #编号。原因：crew-merge 需要退回通知，契约负责人按 module-crew 的需求新增；来源：用户 2026-10-18 批准（选 A）。
- 2026-10-18：改钉 session-protocol v1.8（c982bc3）：样例换为 `tests/fixtures/session-protocol/v1.8/`，【协调通知】类型增加挂起（suspend）、恢复（resume），挂起类必填「原因」，挂起、恢复类的「依据」必须有 #编号；生成函数加 `reason` 参数；解析计数 64。原因：crew-failure 需要挂起、恢复通知（第二轮试点问题 I）；来源：契约负责人发布 v1.8，第二轮试点修法用户 2026-10-18 批准。
- 2026-10-18：改钉 session-protocol v1.9（f47631b）：样例换为 `tests/fixtures/session-protocol/v1.9/`（与 v1.8 逐文件相同），`CONTRACT_VERSION` 改 1.9；解析 64、生成 3 不变。来源：契约负责人告知 v1.9，用户 2026-10-18 定为 0.1.2 待办，随 0.2.0 做。
- 2026-10-19：【审查结论】改为校验（`supported` 为真、解析出 `conclusion`，4 份样例参与比对，解析计数 68）；按契约 v2.0 对齐初稿增加「须修改」「待用户决定」字段、【交审】「不同意」、【协调通知】返工与撤销批准类型、`C<N>` 编号与多段切分 `split_sections`，标「待契约 v2.0 定稿」。改范围、关键决策 2、接口说明与验收 3、7。原因：crew-review-nearby 要据审查结论自动返工；来源：用户 2026-10-19 批准 crew-review-nearby 的 Spec 与 Plan（Task 1）。
