# Looming Dark control-plane CLI

Dry-run planner for approved task packets. It validates required fields, applies
`control-plane/ROUTING.yaml`, and prints a deterministic worker/run-class plan.
It does **not** invoke Cursor, Codex, Unity, Meshy, Tripo, or paid services.

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

Equivalent direct invocation:

```bash
python3 control-plane/ldi.py --dry-run tasks/examples/valid-editor-tooling.yaml
```

`--execute` is rejected. This version is dry-run only.

## Output

A valid plan always includes:

- `task_id`
- `worker`
- `run_class`
- exclusive-ownership / conflict status
- `next_action`

Human-readable text is followed by an equivalent JSON document. Invalid task
input exits nonzero and prints a useful error.

## Runtime

Python 3 standard library plus PyYAML, which is expected to already be present.
This tool does not install packages.
