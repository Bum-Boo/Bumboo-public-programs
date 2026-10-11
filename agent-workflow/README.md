# Agent workflow tools

Local Markdown project context, advisory task leases, reproducible command receipts and an optional subscription CLI orchestration queue. Python 3.10+ on Linux; project state stays in your own vault.

## Install and check

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python -m unittest -v
(cd components/agent-task && ../../.venv/bin/python -m unittest -v)
export AGENT_WORKFLOW_PYTHON="$PWD/.venv/bin/python"
export PATH="$PWD/bin:$PATH"
export AGENT_TASK_VAULT=/absolute/path/to/your/vault
agent-context --vault "$AGENT_TASK_VAULT" preview
agent-task --vault "$AGENT_TASK_VAULT" list
```

Vault layout: `00_System/Now.md` is derived from `30_Projects/<project>/00 현재 상태.md`. State frontmatter requires project, status, done, summary, next, updated and agent; aliases is optional. `done` is user controlled. `refresh` refuses manual board changes and never omits projects to fit the byte budget. Start with the synthetic `examples/vault`.

Generate a local spec with `python3 examples/make-offline-spec.py > /tmp/offline.json`, then `agent-verify run /tmp/offline.json --out /absolute/new-receipt-directory` executes declared argv checks and records source/log hashes. Review commands first: this is not a sandbox or credential scrubber.

Task leases are local and advisory, not distributed locking. Optional Claude hooks can be installed by the separately invoked `components/agent-task/install_claude_hooks.py`; it preserves existing hooks and backs up settings. No hooks or timers are installed automatically. Keep this checkout at a stable path if installing hooks.

## Optional orchestration

`agent-orchestrate` requires already authenticated subscription Codex and Claude CLIs. Remote checks currently require an independently configured `~/.local/bin/agent-remote` with a personal host alias `himmel`; that adapter, backup tooling and private host configuration are not bundled. Review-only jobs without checks can run locally. Systemd units expect wrappers installed in `~/.local/bin` and are opt-in. Do not point jobs at unreviewed inputs or copy credentials into jobs. See `orchestration.md` for queue behavior.

MIT applies to this repository code. PyYAML is a separately installed dependency under its own license. No user vault, secrets, personal examples or runtime state is distributed.
