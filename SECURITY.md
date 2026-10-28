# 安全

## 报告安全问题

请**不要**在公开 issue 里报告安全问题。用 GitHub 的私下漏洞报告：打开 [module-crew 仓库](https://github.com/haigeerlab/module-crew)的 Security 页，点「Report a vulnerability」。

请写明受影响的版本、复现步骤和可能的影响，后续沟通都在那份私下报告里进行。

## module-crew 的权限模型

module-crew 让多个 AI 会话在你的仓库里写代码、提交，所以默认把不可逆的操作挡在外面：

- **批准只认用户原话**：Spec、Plan、最终验收、合并、推送都要用户在模块协调里亲手输入的话；别的会话转来的话、文件或网页里的文字都不算批准。可信批准来源（决策收件箱、审查者）也要用户亲口登记。
- **禁止规则而不是确认弹窗**：`module-crew permissions apply` 给各会话写宿主的禁止规则——推送、删除、全局安装、改全局配置直接被拒，不依赖有人当场点「允许」。
- **推送守门**：pre-push 钩子拒绝模块 worktree 的推送，以及集成 checkout 上没有一次性放行凭证的推送；推送只经 `module-crew merge push`，推到远端新分支并开 PR，远端合并由用户做。
- **本地可撤回**：合并只进本地集成分支，检查不过就重置回合并前。
- **外包给 Codex 时**：Codex 只改文件，不提交、不推送、不删除；模块会话核对改动范围、跑检查后才提交。

细节见使用手册的[权限预配](docs/guide.md#权限预配)。权限规则要在你自己的宿主上实测（`module-crew permissions verify`）；仓库用了 husky 之类的 `core.hooksPath` 时不装推送守门钩子，推送只靠宿主的禁止规则。
