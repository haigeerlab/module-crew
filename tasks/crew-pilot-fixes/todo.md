# Todo: crew-pilot-fixes

> 依据 `tasks/crew-pilot-fixes/plan.md`。

- [x] Task 1：`module-crew sync`（Spec 验收 1～4）——提交 aea9740；`tests/test_sync.py` 5 例通过
- [x] Task 2：通知与 crew-dev skill 改写「跑 module-crew sync」（Spec 验收 5）——提交 61bc2cb；开工回归测试改用 sync 实跑 add/add 冲突
- [x] Checkpoint 1（report）：sync 与新措辞跑通，全量测试通过（2026-10-19，428 个测试全过）
- [x] Task 3：`review show` 与通知里的审查原文行（Spec 验收 6、7）——提交 ba962f2
- [x] Task 4：撤回不重开已取代交审、重交审作废合并批准（Spec 验收 8、9）——提交 079686f
- [x] Task 5：`wait add` 与【已恢复】提示（Spec 验收 10）——提交 a215963；C<N> 走 `answer`，#N 走带来源的批准与答复（`_closing_send`）；review／merge 对 C 号的直接答复不触发（协调会话自己等 C 号事项的情形只经 answer）
- [x] Task 6：派活后核对权限弹窗的提醒（Spec 验收 11）——提交 3dfcd95
- [x] Task 7：README、版本 0.6.0、全量测试（Spec 验收 12）——提交 c1c4c96；全量 442 个测试：首轮 441 过、旧称扫描抓到 1 处「审批」，改后重跑通过
- [ ] Checkpoint 2（gate）：实地验证前停下问用户
- [ ] Task 8：实地验证（Spec 验收 13）
- [ ] Checkpoint 3（gate）：最终验收
- [ ] 回告：结果告诉 di-p0-tester（local_bbdaaaab）
