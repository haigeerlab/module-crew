# Todo: crew-protocol

测试命令：`python3 -m unittest discover -s tests -v`

- [x] Task 1：复制样例、`SOURCE`、指纹核对与一致性测试框架
  - 验收：Spec 验收 1；样例目录与 session-protocol 78da46f 逐字节相同；改一个字节测试失败（用临时副本验证）
  - 验证：`python3 -m unittest discover -s tests -p test_protocol_conformance.py -v`
  - 文件：`tests/fixtures/session-protocol/v1.1/**`、`tests/test_protocol_conformance.py`、`module_crew/protocol.py`（空壳）

- [x] Task 2：通用切分与简单类型
  - 验收：wait-session 2、resumed 3、withdraw 1、user-reply 4、unknown 1 份解析样例逐键一致
  - 验证：同上
  - 文件：`module_crew/protocol.py`、`tests/test_protocol_conformance.py`

- [x] Task 3：【等待用户】
  - 验收：wait-user 12 份解析样例逐键一致
  - 验证：同上
  - 文件：`module_crew/protocol.py`、`tests/test_protocol_conformance.py`

- [x] Task 4：v1.1 三种与不支持的两种
  - 验收：review-request 6、shared-change-request 4、coordination-notice 5 份逐键一致；Spec 验收 7
  - 验证：同上
  - 文件：`module_crew/protocol.py`、`tests/test_protocol_conformance.py`

- [x] Checkpoint 1（report）：全部测试全绿，38 份解析样例通过、跳过项列出，记下命令与结果后继续
  - 记录：`python3 -m unittest discover -s tests -v` → Ran 43 tests, OK；解析样例对照 37 份通过，跳过 review-conclusion 4 份与契约缺陷 unknown/unknown-kind 1 份（2026-10-18）

- [ ] Task 5：生成函数
  - 验收：Spec 验收 3、4、5、6
  - 验证：`python3 -m unittest discover -s tests -p "test_protocol_*.py" -v`
  - 文件：`module_crew/protocol.py`、`tests/test_protocol_conformance.py`、`tests/test_protocol_render.py`

- [ ] Task 6：`protocol check` 与无 I/O 扫描
  - 验收：Spec 验收 8、9
  - 验证：`python3 -m unittest discover -s tests -p "test_p*.py" -v`
  - 文件：`module_crew/__main__.py`、`tests/test_protocol_cli.py`、`tests/test_package.py`

- [ ] Task 7：session-protocol 一致性说明登记
  - 验收：Spec 验收 10；只改 `conformance/README.md` 的 module-crew 一行，工作区改动，提交等最终验收
  - 验证：`git -C ~/Documents/haigeerlab/session-protocol diff`
  - 文件：`~/Documents/haigeerlab/session-protocol/conformance/README.md`

- [ ] Checkpoint 2（gate）：模块最终验收——全部测试全绿、10 条验收标准逐条对应测试、列出实际改动文件与 session-protocol 差异；停下等用户确认

## 待你决定

- 契约缺陷：v1.0 样例 `unknown/unknown-kind.txt` 用【交审】当「认不出的标签」，v1.1 把【交审】定成了正式类型，这份样例在 v1.1 下期望结果不成立。一致性测试暂把它列为「契约缺陷」跳过，待你决定怎么修契约（发现于 Task 2，2026-10-18）。
