# module-crew

A plugin that lets several Claude Code or Codex desktop sessions **develop several modules of one project in parallel**.

[中文](README.md) | English

> Version 0.21.0 · License [MIT](LICENSE)
>
> Only this README is in English. The other documents linked below (user guide, command reference, architecture, changelog) are in Chinese.

## What it solves

[spec-guard](https://github.com/haigeerlab/spec-guard-plugin) drives a project one module at a time along its capability map (Spec → Plan → implementation). When there are many independent modules, that serial flow and one-by-one review slow everything down.
module-crew adds a runtime layer on top of it:

- **One module coordinator (模块协调)** runs the show: opens modules, keeps the books on incoming messages, relays the user's decisions, owns the integration branch and shared files, and merges.
- **One session per module (模块会话)**: each works in its own git worktree, writes its Spec, Plan and code, and talks only to the coordinator.
- **Every approval comes from the user**: Spec, Plan, final acceptance, merge and push all need the user's own words typed into the coordinator. Words relayed by another session never count as approval.
- **Interruptions are recoverable**: after a crash, a context compaction or a fresh session, work resumes from the state store, not from chat memory.

```text
user ──approves in own words──> module coordinator (integration checkout)
                                  │  ▲   agent-relay messages
                                  ▼  │
          module session A (worktree A)   module session B (worktree B) …
                                  │
        state store (module-crew/ in the git common dir, shared by all worktrees)
```

There are also light tasks (轻任务: a single feature or bug that skips the Spec but still goes through the merge queue), an optional reviewer and decision inbox, moving the whole crew to Codex between batches, and quota offload that hands a module's implementation to Codex. See the [user guide](docs/guide.md).

## Requirements

| Dependency | Requirement |
|---|---|
| Host | Claude Code desktop (Code tab); module sessions may also run in Codex desktop, and between batches the coordinator can move to Codex desktop with `coordinator handover`. All sessions on the same Mac |
| [agent-relay](https://github.com/haigeerlab/agent-relay) | Required, interface major version 2. Sessions exchange messages through it |
| [spec-guard](https://github.com/haigeerlab/spec-guard-plugin) | Required, 0.68.0 or later (planning layer, interface 1.1), with spec-guard's local multi-spec convention enabled in the project (`spec/CAPABILITY-MAP.md`). Declared scope, autonomy tiers and quota offload need 0.85.0 or later (interface 1.11) |
| [delegate](https://github.com/haigeerlab/delegate-plugin) | Optional, only for quota offload: 0.8.0 or later (interface 1.3) |
| session-protocol | The message format contract between sessions; module-crew pins v2.8 (enforced by module-crew's built-in parser, nothing to install) |
| Project | A git repository that can host worktrees, with one full check command that runs locally; it decides whether a merge passes |
| Runtime | Python 3 (standard library only; developed and tested on 3.10) |

## Install

**Claude Code**: this repository ships its own plugin marketplace manifest (`.claude-plugin/marketplace.json`, marketplace name `module-crew-local`). Install agent-relay and spec-guard first, then:

```bash
claude plugin marketplace add haigeerlab/module-crew
```

```bash
claude plugin install module-crew@module-crew-local
```

You can also install from a local clone: `claude plugin marketplace add /path/to/module-crew`.

- On first use Claude Code asks whether to trust the plugin's hooks. **Say yes**, otherwise the role hints are not injected after a compaction or a new session.
- After a plugin update, run `/clear` once in each session in use (or open a new session) to pick up the new hooks and skills.

**Codex** (only needed for Codex module sessions, or to move the coordinator to Codex): install the same version of this plugin in Codex (`.codex-plugin/plugin.json`, which provides the Codex `crew-dev` and `crew-coordinator` skills), then quit the ChatGPT app completely and reopen it. Back up `~/.codex/config.toml` before changing Codex plugins.

Then run the health check in your project:

```bash
bin/module-crew status
```

It checks seven things — git, agent-relay, spec-guard, whether spec-guard is enabled in the project, spec-guard's planning layer, the integration branch and the state store — and explains any blocker.

## Getting started

1. **Make a coordinator**: in the session you want to coordinate, say "upgrade this session to module coordinator" (「把本会话升级为模块协调」); it runs `module-crew coordinator up`.
2. **Open modules**: the coordinator's `module-crew start plan` proposes modules from the capability map; once you agree, `module-crew start prepare <module>…` creates worktrees and kickoff notes. Open a new session in each worktree and paste its kickoff note.
3. **Spec and Plan**: each module session sends a review request (【交审】); the coordinator batches them for you. After you approve, it runs `module-crew review approve`, and module sessions start building once they get the kickoff notice.
4. **Merge**: when a module is done it asks for final acceptance; after you approve, the coordinator's `module-crew merge run` merges it into the local integration branch and runs the full check, sending it back automatically if the check fails.
5. **Push**: once you authorize it, `module-crew merge push` pushes to a new remote branch and opens a PR. Merging on the remote is always up to you.

The full flow, every step in detail and what to do when things go wrong are in the [user guide](docs/guide.md).

## Project switches

All off by default; the coordinator turns them on only with the user's own words. With them off, nothing changes.

| Switch | What it does | Details |
|---|---|---|
| `declaredScope` (declared scope) | Shared files declared up front in a module's Plan are edited directly on the module branch and reviewed at final acceptance | [User guide](docs/guide.md#声明范围declaredscope) |
| `checkLedger` (check ledger) | Day to day only the quick check runs, recorded per tree hash; the full check runs only in the merge queue | [User guide](docs/guide.md#检查记账checkledger) |
| `autonomyTier` (autonomy tier) | `strict` (default) / `standard` / `relaxed`: how review cadence and message digests loosen; steps down automatically after an incident | [User guide](docs/guide.md#自治档位autonomytier) |
| `codexOffload` (quota offload) | When Claude quota is tight, modules opened afterwards hand their Tasks to one Codex session; the module session checks and commits | [User guide](docs/guide.md#额度外包codexoffload) |

## Documentation (in Chinese)

| Document | Contents |
|---|---|
| [User guide](docs/guide.md) | Terms, roles, the full flow, project switches, light tasks, reopening modules, Codex and host handover, reviews and the decision inbox, permission setup, troubleshooting, known limits |
| [Command reference](docs/commands.md) | What each command does, who runs it where, whether it needs the user's words, exit codes |
| [Architecture](docs/architecture.md) | Components, state store, messages and approvals, merging and checks, upstream interfaces and outputs |
| [Changelog](CHANGELOG.md) | Changes by version |
| [Contributing](CONTRIBUTING.md) | Reporting issues, developing and committing |
| [Security](SECURITY.md) | How to report a security issue |

`docs/` also holds a few development records (requirements record, pilot report and so on). They are not updated with releases; the documents above describe current behaviour.

## Development

```bash
python3 -m unittest discover -s tests -v
```

This repository is itself built with spec-guard and module-crew: requirements and designs live in `spec/`, tasks in `tasks/`. See [Contributing](CONTRIBUTING.md).

## License

[MIT](LICENSE) © 2026 haigeerlab
