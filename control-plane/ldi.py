#!/usr/bin/env python3
"""Looming Dark control-plane CLI (dry-run planner).

Reads a task packet, validates required fields, applies ROUTING.yaml, and
prints a deterministic execution plan without invoking workers or paid services.
"""

from __future__ import annotations

import argparse
import json
import sys
import unittest
from fnmatch import fnmatch
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError as exc:  # pragma: no cover - PyYAML is expected in the runtime
    raise SystemExit(
        "error: PyYAML is required but was not found in this runtime. "
        "This CLI does not install packages."
    ) from exc

REQUIRED_FIELDS = ("id", "status", "objective")
NON_LOCK_OWNERS = frozenset({"shared", "unassigned", "any", "none", "null"})
BROAD_PATHS = frozenset({"*", "**", "**/*", ".", "./", "/", "/**"})
NEXT_ACTION = (
    "dry-run only; do not invoke Cursor, Codex, Unity, Meshy, Tripo, or paid services"
)


class PlanError(Exception):
    """Invalid task input or unusable routing configuration."""


def repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def load_yaml_file(path: Path) -> Any:
    if not path.is_file():
        raise PlanError(f"file not found: {path}")
    try:
        text = path.read_text(encoding="utf-8")
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise PlanError(f"invalid YAML in {path}: {exc}") from exc
    except OSError as exc:
        raise PlanError(f"cannot read {path}: {exc}") from exc
    return data


def load_routing(root: Path) -> dict[str, Any]:
    path = root / "control-plane" / "ROUTING.yaml"
    data = load_yaml_file(path)
    if not isinstance(data, dict):
        raise PlanError("control-plane/ROUTING.yaml must be a mapping")
    workers = data.get("workers")
    routing = data.get("routing")
    if not isinstance(workers, dict) or not workers:
        raise PlanError("ROUTING.yaml is missing workers")
    if not isinstance(routing, list) or not routing:
        raise PlanError("ROUTING.yaml is missing routing rules")
    return data


def valid_workers(routing: dict[str, Any]) -> set[str]:
    return {str(name).lower() for name in routing["workers"].keys()}


def valid_run_classes(routing: dict[str, Any]) -> set[str]:
    classes: set[str] = set()
    for name, spec in routing["workers"].items():
        if isinstance(spec, dict):
            models = spec.get("preferred_models") or {}
            if isinstance(models, dict):
                classes.update(str(k).lower() for k in models.keys())
    for rule in routing["routing"]:
        if isinstance(rule, dict) and rule.get("run_class"):
            classes.add(str(rule["run_class"]).lower())
    return classes


def _is_blank(value: Any) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def _as_nonempty_str(value: Any) -> str | None:
    if _is_blank(value):
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, str):
        return value.strip()
    return None


def validate_required_fields(task: Any) -> dict[str, Any]:
    if not isinstance(task, dict):
        raise PlanError("task packet must be a YAML mapping")
    missing = [field for field in REQUIRED_FIELDS if _is_blank(task.get(field))]
    if missing:
        raise PlanError("missing required fields: " + ", ".join(missing))
    return task


def extract_task_class(task: dict[str, Any]) -> str | None:
    for key in ("task_class",):
        value = _as_nonempty_str(task.get(key))
        if value:
            return value
    scope = task.get("scope")
    if isinstance(scope, dict):
        value = _as_nonempty_str(scope.get("task_type"))
        if value:
            return value
    return None


def extract_locked_worker(task: dict[str, Any]) -> tuple[str | None, bool]:
    """Return (worker, locked).

    An explicit lock that is not a known worker is returned as-is with locked=True
    so the caller can reject it.
    """
    worker_field = task.get("worker")
    if isinstance(worker_field, str) and worker_field.strip():
        return worker_field.strip().lower(), True
    if isinstance(worker_field, dict):
        preferred = worker_field.get("preferred")
        value = _as_nonempty_str(preferred)
        if value:
            return value.lower(), True

    owner = _as_nonempty_str(task.get("owner"))
    if owner:
        normalized = owner.lower()
        if normalized not in NON_LOCK_OWNERS:
            return normalized, True
    return None, False


def extract_locked_run_class(task: dict[str, Any]) -> tuple[str | None, bool]:
    worker_field = task.get("worker")
    if isinstance(worker_field, dict):
        value = _as_nonempty_str(worker_field.get("run_class"))
        if value:
            return value.lower(), True
    value = _as_nonempty_str(task.get("run_class"))
    if value:
        return value.lower(), True
    return None, False


def match_routing_rule(routing: dict[str, Any], task_class: str | None) -> dict[str, Any] | None:
    if not task_class:
        return None
    needle = task_class.lower()
    for rule in routing["routing"]:
        if not isinstance(rule, dict):
            continue
        when = rule.get("when") or {}
        classes = when.get("task_class") if isinstance(when, dict) else None
        if isinstance(classes, list) and any(str(item).lower() == needle for item in classes):
            return rule
    return None


def _as_path_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        stripped = value.strip()
        if stripped.lower() in {"none", "null", ""}:
            return []
        return [stripped]
    if isinstance(value, list):
        out: list[str] = []
        for item in value:
            if isinstance(item, str):
                stripped = item.strip()
                if stripped.lower() not in {"none", "null", ""}:
                    out.append(stripped)
        return out
    return []


def collect_candidate_paths(task: dict[str, Any]) -> list[str]:
    paths: list[str] = []
    paths.extend(_as_path_list(task.get("allowed_files")))
    paths.extend(_as_path_list(task.get("allowed_changes")))
    paths.extend(_as_path_list(task.get("allowed_paths")))
    ownership = task.get("ownership")
    if isinstance(ownership, dict):
        paths.extend(_as_path_list(ownership.get("allowed_paths")))
        paths.extend(_as_path_list(ownership.get("write_locks")))
    # Preserve order but uniquify for deterministic output.
    seen: set[str] = set()
    unique: list[str] = []
    for path in paths:
        if path not in seen:
            seen.add(path)
            unique.append(path)
    return unique


def matches_exclusive_pattern(path: str, pattern: str) -> bool:
    normalized = path.replace("\\", "/").lstrip("./")
    patt = pattern.replace("\\", "/")
    if normalized in BROAD_PATHS:
        return True
    if fnmatch(normalized, patt) or fnmatch(normalized.split("/")[-1], patt):
        return True
    # Allowed entry is itself a glob that would cover an exclusive file.
    if any(ch in normalized for ch in "*?["):
        representative = patt.replace("*", "X")
        if fnmatch(representative, normalized):
            return True
        if patt.replace("*", "") and patt.replace("*", "") in normalized.replace("*", ""):
            # e.g. allowed **/*.unity vs exclusive *.unity
            if normalized.endswith(".unity") and patt.endswith(".unity"):
                return True
            if normalized.endswith(".prefab") and patt.endswith(".prefab"):
                return True
    return False


def detect_conflicts(paths: list[str], exclusive_patterns: list[str]) -> list[dict[str, str]]:
    matches: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for path in paths:
        for pattern in exclusive_patterns:
            if matches_exclusive_pattern(path, pattern):
                key = (path, pattern)
                if key not in seen:
                    seen.add(key)
                    matches.append({"path": path, "pattern": pattern})
    return matches


def plan_task(task_path: Path, root: Path | None = None) -> dict[str, Any]:
    root = root or repo_root()
    routing = load_routing(root)
    workers = valid_workers(routing)
    run_classes = valid_run_classes(routing)

    task = validate_required_fields(load_yaml_file(task_path))
    task_id = _as_nonempty_str(task.get("id"))
    assert task_id is not None

    task_class = extract_task_class(task)
    locked_worker, worker_locked = extract_locked_worker(task)
    locked_run_class, run_class_locked = extract_locked_run_class(task)

    if worker_locked and locked_worker not in workers:
        raise PlanError(
            f"invalid locked worker '{locked_worker}'; expected one of: "
            + ", ".join(sorted(workers))
        )
    if run_class_locked and locked_run_class not in run_classes:
        raise PlanError(
            f"invalid locked run_class '{locked_run_class}'; expected one of: "
            + ", ".join(sorted(run_classes))
        )

    rule = match_routing_rule(routing, task_class)
    if not worker_locked or not run_class_locked:
        if not task_class:
            raise PlanError(
                "task_class is required when worker or run_class is not explicitly locked"
            )
        if rule is None:
            raise PlanError(f"no routing rule matches task_class '{task_class}'")

    worker = locked_worker if worker_locked else str(rule["worker"]).lower()
    run_class = locked_run_class if run_class_locked else str(rule["run_class"]).lower()

    conflict_policy = routing.get("conflict_policy") or {}
    exclusive_patterns = []
    if isinstance(conflict_policy, dict):
        exclusive_patterns = [
            str(item) for item in (conflict_policy.get("exclusive_patterns") or [])
        ]
    conflict_matches = detect_conflicts(collect_candidate_paths(task), exclusive_patterns)
    exclusive = bool(conflict_matches)

    try:
        rel_task = str(task_path.resolve().relative_to(root.resolve()))
    except ValueError:
        rel_task = str(task_path)

    return {
        "ok": True,
        "dry_run": True,
        "task_id": task_id,
        "task_path": rel_task.replace("\\", "/"),
        "worker": worker,
        "run_class": run_class,
        "task_class": task_class,
        "worker_locked": worker_locked,
        "run_class_locked": run_class_locked,
        "exclusive_ownership_required": exclusive,
        "conflict_matches": conflict_matches,
        "next_action": NEXT_ACTION,
        "routing_file": "control-plane/ROUTING.yaml",
    }


def format_human(plan: dict[str, Any]) -> str:
    if plan.get("conflict_matches"):
        conflicts = ", ".join(
            f"{item['path']} ({item['pattern']})" for item in plan["conflict_matches"]
        )
        exclusive = f"yes ({conflicts})"
    else:
        exclusive = "no"
    lines = [
        "Looming Dark control-plane plan (dry-run)",
        "----------------------------------------",
        f"task_id: {plan['task_id']}",
        f"worker: {plan['worker']}",
        f"run_class: {plan['run_class']}",
        f"task_class: {plan.get('task_class') or '(none)'}",
        f"exclusive_ownership_required: {exclusive}",
        f"next_action: {plan['next_action']}",
    ]
    return "\n".join(lines)


def format_json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, indent=2, sort_keys=True) + "\n"


def run_self_test(root: Path) -> int:
    test_dir = root / "tests" / "control-plane"
    if not test_dir.is_dir():
        print("error: tests/control-plane is missing", file=sys.stderr)
        return 1
    loader = unittest.TestLoader()
    suite = loader.discover(str(test_dir), pattern="test_*.py")
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ldi",
        description=(
            "Dry-run Looming Dark control-plane planner. "
            "Validates a task packet and prints worker/run-class routing without "
            "invoking Codex, Cursor, Unity, or paid services."
        ),
        epilog=(
            "One-command execution from the repository root:\n"
            "  python3 scripts/ldi --dry-run tasks/examples/valid-editor-tooling.yaml\n"
            "  python3 scripts/ldi --self-test"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("task", nargs="?", help="Path to a task YAML packet")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=True,
        help="Plan only (default; the only supported mode in this version)",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Unsupported in this version; exits nonzero",
    )
    parser.add_argument("--json", action="store_true", help="Print JSON only")
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="Run bundled valid/invalid routing tests",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    root = repo_root()

    if args.execute:
        print(
            "error: execute is not supported; this version is dry-run only",
            file=sys.stderr,
        )
        return 2

    if args.self_test:
        return run_self_test(root)

    if not args.task:
        parser.print_help()
        return 2

    task_path = Path(args.task)
    if not task_path.is_absolute():
        task_path = (Path.cwd() / task_path).resolve()

    try:
        plan = plan_task(task_path, root=root)
    except PlanError as exc:
        payload = {"ok": False, "error": str(exc), "dry_run": True}
        if args.json:
            sys.stdout.write(format_json(payload))
        else:
            print(f"error: {exc}", file=sys.stderr)
            sys.stdout.write(format_json(payload))
        return 1

    if args.json:
        sys.stdout.write(format_json(plan))
    else:
        print(format_human(plan))
        print()
        print("=== JSON ===")
        sys.stdout.write(format_json(plan))
    return 0


if __name__ == "__main__":
    sys.exit(main())
