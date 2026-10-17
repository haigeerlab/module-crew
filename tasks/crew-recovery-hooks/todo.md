# Todo: crew-recovery-hooks

测试命令：`python3 -m unittest discover -s tests -v`

- [x] Task 1：角色判断与静默
  - 验收：Spec 验收 1；验收 2、4 的识别部分（含子目录）
  - 验证：`python3 -m unittest discover -s tests -p test_hooks.py -v`
  - 文件：`module_crew/hooks.py`、`tests/test_hooks.py`

- [ ] Task 2：提示文字、四档状态、压缩核对
  - 验收：Spec 验收 2、3、4、5
  - 验证：同上
  - 文件：`module_crew/hooks.py`、`tests/test_hooks.py`

- [ ] Checkpoint 1（report）：全部测试全绿，记下命令与结果后继续

- [ ] Task 3：`hook` 子命令、`hooks.json`、异常静默与耗时
  - 验收：Spec 验收 6、7
  - 验证：同上
  - 文件：`hooks/hooks.json`、`module_crew/__main__.py`、`module_crew/hooks.py`、`tests/test_hooks.py`

- [ ] Task 4：`takeover`
  - 验收：Spec 验收 8
  - 验证：同上
  - 文件：`module_crew/hooks.py`、`module_crew/__main__.py`、`tests/test_hooks.py`

- [ ] Checkpoint 2（gate）：模块最终验收——全部测试全绿、8 条验收标准逐条对应测试、附提示样例与耗时、列出实际改动文件；停下等用户确认
