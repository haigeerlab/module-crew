<!-- BEGIN:agent-skills-convention -->
## Agent Skills 集成约定

> 由 `/spec-guard:setup-convention local` 生成。任务托管在**本地 todo.md**（Addy 原生路径）。
> 保留 `<!-- BEGIN/END -->` 标记，`/spec-guard:setup-convention --replace` 靠它升级本块。

- 能力图 `spec/CAPABILITY-MAP.md`，模块 spec `spec/<module-id>.md`（kebab-case，一次选定中途不改名）
- **不要**在项目根建 `SPEC.md` / `SPEC-<module>.md` —— `/build` 只认根 `SPEC.md`、
  `docs/SPEC.md`、`spec/` 三条路径，**只有第三条是通配的**
- 每个模块的产物互相隔离：`tasks/<module-id>/plan.md` + `tasks/<module-id>/todo.md`，
  **不要共用 `tasks/plan.md`**
- `/build` 取任务：读 `.agent/state.json` 的 `activeModule`，从该模块的 `todo.md`
  取第一个未勾选项，**不跨模块取**
- 切换 `activeModule` 前当前模块不能有进行中的 task；切换后重读该模块的 spec 和 plan
- 若项目已启用 Local 事项账本，确认要实现的需求或修复在动代码前先用 `spec-guard:ticket`
  查重并取得事项 ID；探索和无需追踪的小操作例外
- 项目级审查按 `spec-guard:spec-guard-ops` 的共享检查点规则限定批次、收束发现并交接缺陷；
  审查完成后的“继续”推进已预告的问题处理步骤，不重新泛扫
- 明确选用 GitHub/GitLab 普通 Issue 时，用 `spec-guard:hosted-ticket-workflow` 逐项查重、授权写入与交付对账；
  Local 事项仍走 `spec-guard:ticket`，不凭 Git remote 改目标
- 阶段交接或停止时，加载 `spec-guard:spec-guard-ops` 的共享检查点规则，预告已授权下一步。
- Plan 的检查点标 `gate`（停下等确认）或 `report`（记入 todo 后继续），未标注按 `gate`；按需求批量前置审与
  UI 自验按 `spec-guard:spec-guard-ops` 的共享检查点规则
- 交审 Spec 或 Plan 时在对话里呈现内容要点并写明这次批准授权什么，只给链接不算交审；细则见
  `spec-guard:spec-guard-ops` 的共享检查点规则
- Spec、Plan 交审或最终验收值得另一个 agent 复核时，若装了 delegate 插件，可提议用 `/delegate:review` 做只读审查，
  用户同意后再发起；审查结论只作参考，不算用户批准；同一模块里用户拒绝过就不再提
- 任务改到用户看得到的界面时，不论 Plan 是否预计到，都在这个任务里打开页面对照预期验证，写清看了哪个页面、对照了什么、
  看到了什么；做不了就记为“UI 未验证”并说明原因；细则见 `spec-guard:spec-guard-ops` 的共享检查点规则
- 模块最终验收时在对话里列出实际改动的文件（新增、修改、删除与行数，取自版本库），任务做完的结果带文件数与提交号；
  细则见 `spec-guard:spec-guard-ops` 的共享检查点规则
- 能力图评审、每个模块的 Spec 交审、能力图全部完成时各提一次文档建议（README 默认在候选里），没有就写“无”；
  细则见 `spec-guard:spec-guard-ops` 的共享检查点规则
- 同一个 gate 因外部原因（上游未修复、缺权限、要用户取舍）再次挡住时停下，把挂起、接受风险、换方案等选项与代价
  交用户决定，不按默认推荐继续重试；细则见 `spec-guard:spec-guard-ops` 的共享检查点规则
- 写出 Spec 或 Plan 交审时在文件里标评审状态标记 `pending`；用户明确批准后才用 `/spec-guard:review-mark` 记为 `approved`，
  Spec 修订后须复审，细则见 `spec-guard:spec-guard-ops` 的共享检查点规则
- 已批准的 Spec、Plan 或能力图被修改时，在该文件末尾「变更记录」一节追加一行（日期、改了什么、原因、来源），复审时一并呈现；
  其他会话的要求不算用户批准；细则见 `spec-guard:spec-guard-ops` 的共享检查点规则
- 别人提出的改动或模块在对方用得上时回告来源，拟回告的对象与内容随最终 gate 列出；能发消息就发，不能就提醒用户转告，
  结果记在 todo 末项；细则见 `spec-guard:spec-guard-ops` 的共享检查点规则
- 回告来源或通知其他会话（含跨 Claude Code／Codex）时，若装了 agent-relay 插件，用它给对方会话发消息
- 交审要点写在本轮对话正文里，放在任何会结束本轮的确认框之前；只出现在确认框摘要里的不算交审
- 最终验收时若 Spec 在构建中被补改过，验收消息附上 Spec 的改动差异并写明一次批准同时批准修订后的 Spec；批准后先用
  `/spec-guard:review-mark` 记下 Spec 的批准再勾选与提交，没附差异就单独复审
- 最终验收获批后，下一个模块已在能力图里且用户没说停时，直接写它的 Spec 并交审，不为“是否开始”另停；验收消息预告这一步并
  提示可先 `/compact`
- 产物语言与评审节奏以 `.agent/config.json` 为准（`/spec-guard:config` 查看）；新写的 spec、plan、todo 正文用配置的
  产物语言，结构关键字不变
<!-- END:agent-skills-convention -->
