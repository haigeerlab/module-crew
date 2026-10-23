# Todo: crew-host-handover

> 依据 `tasks/crew-host-handover/plan.md`。

- [x] Task 1：store 放开模块协调的 Codex 宿主与 `hostHandover` 校验（Spec 验收 8）——测试先红后绿；Codex 模块协调必须带 hostHandover，原「Codex 协调被拒」的旧测试仍成立（8c9efd1）
- [x] Task 2：`coordinator handover --check` 收尾条件清单（Spec 验收 1 检查部分）——先写逻辑与测试，CLI 测试先红后绿；`--check` 加入写命令守门的只读豁免（47ec6b9）
- [x] Task 3：`coordinator handover --to` 登记、事件与交接说明（Spec 验收 1～4）——测试先红后绿；事件按现有命名为 `session.coordinator-handover`（Spec 写的 `coordinator.handover` 不符合「种类.动作」格式，最终验收时随 Spec 变更记录报）；原话另存为文件供 `bind --takeover --original-file` 直接用；交接说明措辞已按 agent-relay PR #154 实测核对（27a38fa）
- [x] Task 4：集成 checkout 权限跟随模块协调宿主（Spec 验收 2、3 权限部分）——测试先红后绿；权限相关已有测试全过（d12be1e）
- [x] Task 5：`bind --takeover` 宿主核对（Spec 验收 5）——测试先红后绿；crew-session-handover 测试照常通过（0ed23a7）
- [x] Checkpoint 1（report）：交接链路就位——test_host_handover 28 个测试与相关已有测试通过
- [ ] Task 6：开工与派任务的宿主跟随模块协调（Spec 验收 6、7）
- [ ] Task 7：收尾提示与 status 字段（Spec 验收 9）
- [ ] Task 8：README、skill、crew-codex-host 变更记录、全量测试（Spec 验收 10、11）
- [ ] Checkpoint 2（gate）：最终验收
- [ ] 回告：ecosystem-lead（模块 A 就位、`--to codex` 等模块 B）
