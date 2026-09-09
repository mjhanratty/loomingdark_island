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

Live dispatch is opt-in and requires an approved task packet:

```bash
python3 scripts/ldi --execute tasks/examples/valid-live-dispatch-proof.yaml
```

Equivalent direct invocation:

```bash
python3 control-plane/ldi.py --dry-run tasks/examples/valid-editor-tooling.yaml
```

`--execute` does not grant permission to use paid generation APIs. This milestone
uses a repository-safe local CLI version probe through the selected worker
adapter and writes a structured report under `reports/`.

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
- report path

Human-readable text is followed by an equivalent JSON document. Invalid task
input exits nonzero and prints a useful error.

## Runtime

Python 3 standard library plus PyYAML, which is expected to already be present.
This tool does not install packages.
