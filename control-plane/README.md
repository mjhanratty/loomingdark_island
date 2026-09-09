# Looming Dark control-plane CLI

Planner and explicitly gated local worker dispatcher for approved task packets.
It validates required fields, applies `control-plane/ROUTING.yaml`, prints a
deterministic worker/run-class plan, and can prove local CLI dispatch through
isolated worker adapters.

## One-command execution

From the repository root:

```bash
python3 scripts/ldi --dry-run tasks/examples/valid-editor-tooling.yaml
```

JSON only:

```bash
python3 scripts/ldi --json --dry-run tasks/examples/valid-editor-tooling.yaml
```

Self-test (valid and invalid cases):

```bash
python3 scripts/ldi --self-test
```

Worker discovery:

```bash
python3 scripts/ldi --workers
```

Cursor discovery uses the current `agent` executable. Actual Cursor execution is
constructed as `agent -p --output-format json --trust --workspace <repo> <prompt>`
with a compact prompt that points to a temporary structured instruction file.

`--trust` remains required for non-interactive workspace trust under current
Cursor CLI semantics. It is not a substitute for `--force`/`--yolo`: command
approval still follows project allowlist/deny rules in `.cursor/cli.json`. There
is no documented safer headless alternative that both skips the trust prompt and
preserves allowlist gating, so the control plane keeps `--trust` and relies on
repository permissions for shell hardening.

Live dispatch is opt-in and requires an approved task packet. Packets with a
`proof_task` field receive actual structured task instructions; older proof
packets without `proof_task` retain the repository-safe version-probe behavior.

```bash
python3 scripts/ldi --execute tasks/examples/valid-live-dispatch-proof.yaml
python3 scripts/ldi --execute tasks/examples/valid-actual-task-execution-proof.yaml
```

Equivalent direct invocation:

```bash
python3 control-plane/ldi.py --dry-run tasks/examples/valid-editor-tooling.yaml
```

`--execute` does not grant permission to use paid generation APIs. Reports are
written under `reports/` and separate worker invocation status from task
acceptance status.

Worker instructions use compact repository-relative context references instead
of embedding full authoritative documents. Workers must read the listed files
locally before editing. LOW and MEDIUM instructions also include
`context_budget` metadata with a bounded task-specific file count (at most 5
for LOW, 10 for MEDIUM, or fewer when the packet names a narrower set).

## Cursor command policy

Project-level Cursor CLI permissions live in `.cursor/cli.json` and apply only
to this repository. Routine read-only inspection commands used repeatedly by
workers (`git status`/`diff`/`log`/`show`/`rev-parse`/`merge-base`/`rev-list`/
branch inspection, `git stash list`, `ls`, `cat`, `head`, `tail`, `test`, and
grep-style readers) are narrowly allowlisted so common diagnostics do not spam
approvals or waste tokens.

Write, install, network-installer, and destructive shell families remain gated
or explicitly denied (`rm`, `sudo`, `chmod`, package-manager installs, curl/wget
install vectors, `git clean`, hard reset, force push). Deny rules take
precedence over allow rules. The policy intentionally avoids broad allowances
such as `Shell(git)`, `Shell(gh)`, `Shell(python3)`, or `Shell(*)`.

Security limitation: Cursor matches shell permissions by command base and
optional `command:args` globs. Indirect install/destroy paths (for example
`python3 -m pip install`, or destructive actions wrapped in `bash -c`) are not
fully enforceable by these patterns alone and still require task ownership,
worker instructions, and human review.

## Output

A valid plan always includes:

- `task_id`
- `worker`
- `run_class`
- exclusive-ownership / conflict status
- `next_action`

A live report includes:

- worker and run_class
- adapter and command identity
- start/end state
- exit status
- stdout/stderr summaries
- task result
- files changed when determinable
- validation results
- report path

Human-readable text is followed by an equivalent JSON document. Invalid task
input exits nonzero and prints a useful error.

## Runtime

Python 3 standard library plus PyYAML, which is expected to already be present.
This tool does not install packages.
