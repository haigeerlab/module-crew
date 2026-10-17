# Todo: crew-recovery-hooks

测试命令：`python3 -m unittest discover -s tests -v`

- [x] Task 1：角色判断与静默
  - 验收：Spec 验收 1；验收 2、4 的识别部分（含子目录）
  - 验证：`python3 -m unittest discover -s tests -p test_hooks.py -v`
  - 文件：`module_crew/hooks.py`、`tests/test_hooks.py`

- [x] Task 2：提示文字、四档状态、压缩核对
  - 验收：Spec 验收 2、3、4、5
  - 验证：同上
  - 文件：`module_crew/hooks.py`、`tests/test_hooks.py`

- [x] Checkpoint 1（report）：全部测试全绿，记下命令与结果后继续
  - 记录：`python3 -m unittest discover -s tests -v` → Ran 190 tests in 84.806s OK（2026-10-18）

- [ ] Task 3：`hook` 子命令、`hooks.json`、异常静默与耗时
  - 验收：Spec 验收 6、7
  - 验证：同上
  - 文件：`hooks/hooks.json`、`module_crew/__main__.py`、`module_crew/hooks.py`、`tests/test_hooks.py`

- [ ] Task 4：`takeover`
  - 验收：Spec 验收 8
  - 验证：同上
  - 文件：`module_crew/hooks.py`、`module_crew/__main__.py`、`tests/test_hooks.py`

- [ ] Checkpoint 2（gate）：模块最终验收——全部测试全绿、8 条验收标准逐条对应测试、附提示样例与耗时、列出实际改动文件；停下等用户确认

## 记录

- 2026-10-18 发现 crew-review-batch 的缺陷：`review approve` 在集成分支提交带评审标记的 Spec／Plan，模块分支上是同名不带标记的文件，模块同步集成分支或最终合并时出现 add/add 冲突（临时目录复现：`CONFLICT (add/add): Merge conflict in spec/b.md`）。本模块测试按「同步时取集成分支版本」模拟，修法交用户决定。
- 2026-10-18 spec-guard 负责人通知 checkout-role 定稿（0.68.0）：`hooks/checkout_role.py show|set --module <id>|set --coordinator|clear [--confirm] --project <checkout 根>`，标记在各 checkout 自己的 git 目录、worktree 间不共享；`/map --json` 模块 `worktree` 字段定稿；interface 1.1 入口键名待 crew-interface。影响 crew-start（开 worktree 后设角色）与本模块的角色判断（未决问题）。
