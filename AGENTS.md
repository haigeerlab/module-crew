# AGENTS.md

Codex 进入本仓库时读这份；Claude Code 读 CLAUDE.md。两份的共享段逐字相同，其余为各宿主专属内容。

<!-- shared:begin -->
## 项目规矩（Claude 与 Codex 共用）

- 本仓库遵循 haigeerlab《插件开发规范》v1.1。
- 统一检查入口：`scripts/validate.sh` 跑全量测试，`scripts/validate.sh --quick` 只跑本分支改动涉及的测试。CI（`.github/workflows/ci.yml`，名为 `CI`）在 PR 与推送 main 时用 Python 3.9 和 3.13 各跑一次全量检查。
- 代码要能在 Python 3.9 上运行，只用标准库，不加第三方依赖；shell 脚本兼容 Bash 3.2。
- 提交信息用中文，带类型前缀（`feat:`、`fix:`、`docs:`、`test:`、`chore:` 等），做法见 [CONTRIBUTING.md](CONTRIBUTING.md)。
- `skills/` 与 `codex-skills/` 是同一套规矩的 Claude 版和 Codex 版，改一边时看另一边要不要跟着改。
- 本文件与另一宿主的规矩文件（CLAUDE.md／AGENTS.md）在 `shared:begin` 与 `shared:end` 之间的内容必须逐字相同，改一份就同步另一份。
<!-- shared:end -->

## Codex 专属

- 本仓库用 spec-guard 与 module-crew 开发：能力图 `spec/CAPABILITY-MAP.md`，模块 Spec 在 `spec/<模块>.md`，任务在 `tasks/<模块>/`。Codex 里用 `spec-guard-ops` 运行 spec-guard 的约定与检查。
