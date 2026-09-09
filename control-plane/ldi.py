#!/usr/bin/env python3
"""Looming Dark control-plane CLI.

Reads a task packet, validates required fields, applies ROUTING.yaml, and
prints a deterministic execution plan. Live execution is explicitly gated and
uses local worker adapters without invoking paid generation services.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from fnmatch import fnmatch
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError as exc:  # pragma: no cover - PyYAML is expected in the runtime
    yaml = None

REQUIRED_FIELDS = ("id", "status", "objective")
NON_LOCK_OWNERS = frozenset({"shared", "unassigned", "any", "none", "null"})
BROAD_PATHS = frozenset({"*", "**", "**/*", ".", "./", "/", "/**"})
NEXT_ACTION = (
    "dry-run only; do not invoke Cursor, Codex, Unity, Meshy, Tripo, or paid services"
)
WORKER_NAMES = ("cursor", "codex", "claude")
DEFAULT_TIMEOUT_SECONDS = 20
PROOF_ROOT = "tasks/examples/worker-execution-proof"
AUTHORITATIVE_RULE_PATHS = ("AGENTS.md", "CONSTRUCTION.md")


class PlanError(Exception):
    """Invalid task input or unusable routing configuration."""


class ExecuteError(Exception):
    """Execution was rejected or failed before a report could be written."""


def repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def load_yaml_file(path: Path) -> Any:
    if not path.is_file():
        raise PlanError(f"file not found: {path}")
    try:
        text = path.read_text(encoding="utf-8")
        data = safe_load_yaml(text)
    except OSError as exc:
        raise PlanError(f"cannot read {path}: {exc}") from exc
    return data


def safe_load_yaml(text: str) -> Any:
    if yaml is not None:
        try:
            return yaml.safe_load(text)
        except yaml.YAMLError as exc:
            raise PlanError(f"invalid YAML: {exc}") from exc
    return parse_simple_yaml(text)


def parse_simple_yaml(text: str) -> Any:
    """Parse the small YAML subset used by Looming Dark task packets."""

    lines = text.splitlines()

    def strip_comment(raw: str) -> str:
        in_quote: str | None = None
        for idx, ch in enumerate(raw):
            if ch in {"'", '"'}:
                in_quote = None if in_quote == ch else ch
            if ch == "#" and in_quote is None:
                return raw[:idx]
        return raw

    def parse_scalar(raw: str) -> Any:
        value = raw.strip()
        if value in {"", "null", "Null", "NULL", "~"}:
            return None
        if value in {"true", "True", "TRUE"}:
            return True
        if value in {"false", "False", "FALSE"}:
            return False
        if value.startswith("[") and value.endswith("]"):
            inner = value[1:-1].strip()
            if not inner:
                return []
            return [parse_scalar(part.strip()) for part in inner.split(",")]
        if (value.startswith('"') and value.endswith('"')) or (
            value.startswith("'") and value.endswith("'")
        ):
            return value[1:-1]
        try:
            return int(value)
        except ValueError:
            pass
        try:
            return float(value)
        except ValueError:
            return value

    def next_content(start: int) -> tuple[int, int, str] | None:
        for idx in range(start, len(lines)):
            raw = strip_comment(lines[idx]).rstrip()
            if not raw.strip():
                continue
            return idx, len(raw) - len(raw.lstrip(" ")), raw.strip()
        return None

    def parse_block(start: int, indent: int) -> tuple[Any, int]:
        marker = next_content(start)
        if marker is None:
            return {}, start
        _, marker_indent, marker_text = marker
        if marker_indent < indent:
            return {}, start
        is_list = marker_text.startswith("- ")
        container: Any = [] if is_list else {}
        i = start
        while i < len(lines):
            raw = strip_comment(lines[i]).rstrip()
            if not raw.strip():
                i += 1
                continue
            current_indent = len(raw) - len(raw.lstrip(" "))
            if current_indent < indent:
                break
            if current_indent > indent:
                i += 1
                continue
            text = raw.strip()
            if isinstance(container, list):
                if not text.startswith("- "):
                    break
                item_text = text[2:].strip()
                if not item_text:
                    value, i = parse_block(i + 1, indent + 2)
                    container.append(value)
                    continue
                if ":" in item_text and not item_text.startswith(("'", '"')):
                    key, rest = item_text.split(":", 1)
                    item: dict[str, Any] = {}
                    if rest.strip():
                        item[key.strip()] = parse_scalar(rest)
                        i += 1
                    else:
                        value, i = parse_block(i + 1, indent + 4)
                        item[key.strip()] = value
                    while i < len(lines):
                        nxt = next_content(i)
                        if nxt is None or nxt[1] < indent + 2 or nxt[2].startswith("- "):
                            break
                        raw2 = strip_comment(lines[i]).rstrip()
                        sub_indent = len(raw2) - len(raw2.lstrip(" "))
                        if sub_indent != indent + 2:
                            i += 1
                            continue
                        key2, rest2 = raw2.strip().split(":", 1)
                        if rest2.strip():
                            item[key2.strip()] = parse_scalar(rest2)
                            i += 1
                        else:
                            value2, i = parse_block(i + 1, indent + 4)
                            item[key2.strip()] = value2
                    container.append(item)
                    continue
                container.append(parse_scalar(item_text))
                i += 1
                continue
            if ":" not in text:
                i += 1
                continue
            key, rest = text.split(":", 1)
            key = key.strip()
            rest = rest.strip()
            if rest in {">-", ">"}:
                parts: list[str] = []
                i += 1
                while i < len(lines):
                    raw2 = lines[i].rstrip()
                    if not raw2.strip():
                        i += 1
                        continue
                    sub_indent = len(raw2) - len(raw2.lstrip(" "))
                    if sub_indent <= indent:
                        break
                    parts.append(raw2.strip())
                    i += 1
                container[key] = " ".join(parts)
            elif rest:
                container[key] = parse_scalar(rest)
                i += 1
            else:
                value, i = parse_block(i + 1, indent + 2)
                container[key] = value
        return container, i

    parsed, _ = parse_block(0, 0)
    return parsed


def utc_now() -> str:
    return _dt.datetime.now(tz=_dt.UTC).isoformat(timespec="seconds")


def sanitize_output(text: str, limit: int = 4000) -> str:
    cleaned = text.replace("\x00", "")
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[:limit] + "\n[truncated]"


def task_status(task: dict[str, Any]) -> str:
    return str(task.get("status", "")).strip().lower()


def validate_approved_for_execute(task: dict[str, Any]) -> None:
    if task_status(task) != "approved":
        raise ExecuteError("live dispatch requires task status: approved")
    budget = task.get("budget")
    if isinstance(budget, dict):
        paid = bool(budget.get("paid_credits_allowed"))
        max_cost = budget.get("max_estimated_cost_usd", 0)
        attempts = budget.get("max_generation_attempts", 0)
        if paid or max_cost not in (0, 0.0, "0", "0.0", None) or attempts not in (0, "0", None):
            raise ExecuteError("live dispatch cannot infer permission to spend paid credits")


class WorkerAdapter:
    """Local CLI adapter boundary for future MCP/API-backed workers."""

    name = ""
    executable = ""

    def discover(self) -> dict[str, Any]:
        path = shutil.which(self.executable)
        return {
            "worker": self.name,
            "adapter": self.__class__.__name__,
            "executable": self.executable,
            "path": path,
            "available": path is not None,
        }

    def build_command(
        self,
        task: dict[str, Any],
        task_path: Path,
        root: Path,
        instruction_path: Path | None = None,
        response_schema_path: Path | None = None,
    ) -> list[str]:
        raise NotImplementedError

    def build_stdin(self, instruction: dict[str, Any] | None) -> str | None:
        if instruction is None:
            return None
        return json.dumps(instruction, indent=2, sort_keys=True)


class VersionProbeAdapter(WorkerAdapter):
    """Repository-safe adapter with an actual-task path when authorized."""

    def build_command(
        self,
        task: dict[str, Any],
        task_path: Path,
        root: Path,
        instruction_path: Path | None = None,
        response_schema_path: Path | None = None,
    ) -> list[str]:
        discovered = self.discover()
        if not discovered["path"]:
            raise ExecuteError(f"worker '{self.name}' is unavailable")
        if should_execute_real_task(task):
            if self.name == "claude":
                raise ExecuteError("Claude remains review-first and cannot receive write ownership")
            if instruction_path is None or response_schema_path is None:
                raise ExecuteError("actual task execution requires instruction and schema paths")
            return [
                str(discovered["path"]),
                "--cd",
                str(root),
                "--sandbox",
                "workspace-write",
                "-a",
                "never",
                "exec",
                "--output-schema",
                str(response_schema_path),
                "-",
            ]
        return [str(discovered["path"]), "--version"]


class CursorAdapter(VersionProbeAdapter):
    name = "cursor"
    executable = "agent"

    def build_stdin(self, instruction: dict[str, Any] | None) -> str | None:
        return None

    def build_command(
        self,
        task: dict[str, Any],
        task_path: Path,
        root: Path,
        instruction_path: Path | None = None,
        response_schema_path: Path | None = None,
    ) -> list[str]:
        discovered = self.discover()
        if not discovered["path"]:
            raise ExecuteError("Cursor agent CLI is unavailable: executable 'agent' was not found on PATH")
        if should_execute_real_task(task):
            if instruction_path is None:
                raise ExecuteError("actual task execution requires an instruction path")
            prompt = (
                "Read the JSON task instruction file at "
                f"{instruction_path} and execute it exactly. Return only the "
                "structured completion JSON requested by that instruction."
            )
            return [
                str(discovered["path"]),
                "-p",
                "--output-format",
                "json",
                "--trust",
                "--workspace",
                str(root),
                prompt,
            ]
        return [str(discovered["path"]), "--version"]


class CodexAdapter(VersionProbeAdapter):
    name = "codex"
    executable = "codex"


class ClaudeAdapter(VersionProbeAdapter):
    name = "claude"
    executable = "claude"


def worker_adapters() -> dict[str, WorkerAdapter]:
    return {
        "cursor": CursorAdapter(),
        "codex": CodexAdapter(),
        "claude": ClaudeAdapter(),
    }


def discover_workers() -> dict[str, Any]:
    return {
        "ok": True,
        "workers": {
            name: adapter.discover() for name, adapter in worker_adapters().items()
        },
    }


def should_execute_real_task(task: dict[str, Any]) -> bool:
    return isinstance(task.get("proof_task"), dict)


def collect_authoritative_context_paths(task: dict[str, Any]) -> list[str]:
    paths = list(AUTHORITATIVE_RULE_PATHS)
    inputs = task.get("inputs")
    specs = inputs.get("specs") if isinstance(inputs, dict) else []
    for rel_path in _as_path_list(specs):
        if rel_path not in paths:
            paths.append(rel_path)
    return paths


def build_completion_requirements(task: dict[str, Any]) -> dict[str, Any]:
    completion = task.get("completion_report")
    if isinstance(completion, dict):
        return completion
    return {
        "files_changed": [],
        "checks_performed": [],
        "warnings": [],
        "unresolved": [],
        "follow_up_tasks": [],
    }


def build_legacy_embedded_worker_instruction(task: dict[str, Any], task_path: Path, root: Path) -> dict[str, Any]:
    instruction = build_worker_instruction(task, task_path, root)
    embedded: dict[str, str] = {}
    for rel_path in collect_authoritative_context_paths(task):
        path = root / rel_path
        if path.is_file():
            embedded[rel_path] = path.read_text(encoding="utf-8")
    instruction["authoritative_repo_rules"] = embedded
    instruction.pop("authoritative_repo_rule_paths", None)
    return instruction


def build_worker_instruction(task: dict[str, Any], task_path: Path, root: Path) -> dict[str, Any]:
    task_id = _as_nonempty_str(task.get("id"))
    objective = _as_nonempty_str(task.get("objective"))
    if task_id is None or objective is None:
        raise ExecuteError("cannot build worker instruction without task id and objective")
    ownership = task.get("ownership") if isinstance(task.get("ownership"), dict) else {}
    proof_task = task.get("proof_task") if isinstance(task.get("proof_task"), dict) else {}
    proof_file = f"{PROOF_ROOT}/{task_id}.json"
    instruction = {
        "control_plane_instruction_version": 1,
        "task": {
            "id": task_id,
            "path": str(task_path.resolve().relative_to(root.resolve())).replace("\\", "/"),
            "objective": objective,
            "acceptance": task.get("acceptance") or [],
        },
        "context_policy": "compact_file_references",
        "invariant_rules": [
            "The repository is authoritative over chat history or model memory.",
            "Read each authoritative_repo_rule_paths entry locally before editing.",
            "Obey the task packet ownership, allowed paths, forbidden paths, budget, and acceptance criteria.",
            "Do not install packages or invoke paid/external asset services unless the approved task explicitly authorizes it.",
            "Do not touch Unity, design, asset, package, or project-settings paths unless explicitly allowed.",
        ],
        "authoritative_repo_rule_paths": collect_authoritative_context_paths(task),
        "allowed_paths": _as_path_list(ownership.get("allowed_paths")),
        "forbidden_paths": _as_path_list(ownership.get("forbidden_paths")),
        "completion_report_requirements": build_completion_requirements(task),
        "proof_task": {
            "objective": proof_task.get("objective"),
            "permitted_effect": proof_task.get("permitted_effect") or [],
            "forbidden_effect": proof_task.get("forbidden_effect") or [],
            "required_output_file": proof_file,
            "required_output_json": {
                "task_id": task_id,
                "objective": objective,
                "followed_repository_restrictions": True,
                "permitted_directory": PROOF_ROOT,
                "worker_result": "completed",
            },
        },
        "hard_restrictions": [
            "Read the repository files listed in authoritative_repo_rule_paths before editing.",
            "Modify only the required proof output file under tasks/examples/worker-execution-proof/.",
            "Do not modify Unity, design, asset, package, or project settings paths.",
            "Do not install packages.",
            "Do not invoke paid services or external asset services.",
            "Return a structured JSON completion result matching the provided schema.",
        ],
    }
    return instruction


def worker_response_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "task_id": {"type": "string"},
            "status": {"type": "string"},
            "files_changed": {"type": "array", "items": {"type": "string"}},
            "checks_performed": {"type": "array", "items": {"type": "string"}},
            "warnings": {"type": "array", "items": {"type": "string"}},
            "unresolved": {"type": "array", "items": {"type": "string"}},
            "summary": {"type": "string"},
        },
        "required": [
            "task_id",
            "status",
            "files_changed",
            "checks_performed",
            "warnings",
            "unresolved",
            "summary",
        ],
    }


def git_changed_files(root: Path) -> list[str]:
    result = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return []
    files: list[str] = []
    for line in result.stdout.splitlines():
        if not line:
            continue
        files.append(line[3:].strip())
    return sorted(files)


def validate_proof_output(root: Path, instruction: dict[str, Any] | None) -> dict[str, Any]:
    if instruction is None:
        return {"kind": "version_probe", "accepted": True, "checks": []}
    required = instruction["proof_task"]["required_output_json"]
    rel_path = instruction["proof_task"]["required_output_file"]
    path = root / rel_path
    checks: list[str] = []
    if not path.is_file():
        return {"kind": "actual_task", "accepted": False, "checks": [f"missing {rel_path}"]}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {"kind": "actual_task", "accepted": False, "checks": [f"invalid proof JSON: {exc}"]}
    accepted = True
    for key, expected in required.items():
        actual = data.get(key)
        ok = actual == expected
        checks.append(f"{key}: {'ok' if ok else 'mismatch'}")
        accepted = accepted and ok
    return {
        "kind": "actual_task",
        "accepted": accepted,
        "proof_path": rel_path,
        "checks": checks,
    }


def worker_response_is_successful(response: dict[str, Any] | None) -> bool:
    if not isinstance(response, dict):
        return False
    status = str(response.get("status", "")).strip().lower()
    unresolved = response.get("unresolved")
    has_unresolved = bool(unresolved) if isinstance(unresolved, list) else unresolved not in (None, "")
    return status in {"completed", "success", "successful"} and not has_unresolved


def classify_worker_failure(worker: str, stderr: str) -> str:
    lowered = stderr.lower()
    if worker == "cursor" and (
        "authentication required" in lowered
        or "agent login" in lowered
        or "cursor_api_key" in lowered
    ):
        return "Cursor agent authentication required: run 'agent login' or set CURSOR_API_KEY"
    return "recommended failover route: inspect report and re-route explicitly"


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


def execute_task(
    task_path: Path,
    root: Path | None = None,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    root = root or repo_root()
    task = validate_required_fields(load_yaml_file(task_path))
    validate_approved_for_execute(task)
    plan = plan_task(task_path, root=root)
    worker = str(plan["worker"]).lower()
    adapter = worker_adapters().get(worker)
    if adapter is None:
        raise ExecuteError(f"no adapter configured for worker '{worker}'")

    start = utc_now()
    start_monotonic = time.monotonic()
    discovery = adapter.discover()
    instruction = build_worker_instruction(task, task_path, root) if should_execute_real_task(task) else None
    before_files = git_changed_files(root)
    with tempfile.TemporaryDirectory(prefix="ldi-worker-") as tmp:
        tmpdir = Path(tmp)
        instruction_path = tmpdir / "instruction.json"
        schema_path = tmpdir / "response-schema.json"
        if instruction is not None:
            instruction_path.write_text(format_json(instruction), encoding="utf-8")
            schema_path.write_text(format_json(worker_response_schema()), encoding="utf-8")
        command = adapter.build_command(
            task,
            task_path,
            root,
            instruction_path=instruction_path if instruction is not None else None,
            response_schema_path=schema_path if instruction is not None else None,
        )
        stdin_text = adapter.build_stdin(instruction)
        command_hash = hashlib.sha256("\0".join(command).encode("utf-8")).hexdigest()

        report: dict[str, Any] = {
            "schema_version": 2,
            "task_id": plan["task_id"],
            "task_path": plan["task_path"],
            "worker": worker,
            "run_class": plan["run_class"],
            "adapter": adapter.__class__.__name__,
            "command_identity": {
                "executable": command[0],
                "argv": command,
                "sha256": command_hash,
            },
            "discovery": discovery,
            "started_at": start,
            "ended_at": None,
            "duration_seconds": None,
            "status": "running",
            "worker_invocation_status": "running",
            "task_acceptance_status": "not_evaluated",
            "exit_status": None,
            "stdout_summary": "",
            "stderr_summary": "",
            "task_result": None,
            "worker_response": None,
            "files_changed": [],
            "validation_results": [],
            "warnings": [],
            "unresolved": [],
        }

        try:
            result = subprocess.run(
                command,
                cwd=root,
                input=stdin_text,
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
                check=False,
            )
            report["exit_status"] = result.returncode
            report["stdout_summary"] = sanitize_output(result.stdout)
            report["stderr_summary"] = sanitize_output(result.stderr)
            if result.stderr.strip():
                report["warnings"].append("worker wrote to stderr; see stderr_summary")
            if result.returncode == 0:
                report["worker_invocation_status"] = "completed"
                report["task_result"] = "local worker CLI invocation completed through adapter"
                if instruction is None:
                    report["status"] = "completed"
                    report["task_acceptance_status"] = "accepted"
                else:
                    report["worker_response"] = parse_worker_response(result.stdout)
                    validation = validate_proof_output(root, instruction)
                    report["validation_results"].append(validation)
                    response_ok = worker_response_is_successful(report["worker_response"])
                    accepted = bool(validation.get("accepted")) and response_ok
                    report["task_acceptance_status"] = "accepted" if accepted else "rejected"
                    report["status"] = "completed" if accepted else "failed"
                    if not accepted:
                        if not validation.get("accepted"):
                            report["unresolved"].append("proof output validation failed")
                        if not response_ok:
                            report["unresolved"].append(
                                "worker response was not completed/successful or has unresolved blockers"
                            )
            else:
                report["status"] = "failed"
                report["worker_invocation_status"] = "failed"
                report["task_acceptance_status"] = "not_evaluated"
                report["task_result"] = "worker exited nonzero; no automatic retry attempted"
                report["unresolved"].append(classify_worker_failure(worker, result.stderr))
        except subprocess.TimeoutExpired as exc:
            report["status"] = "timeout"
            report["worker_invocation_status"] = "timeout"
            report["task_acceptance_status"] = "not_evaluated"
            report["exit_status"] = None
            report["stdout_summary"] = sanitize_output(exc.stdout or "")
            report["stderr_summary"] = sanitize_output(exc.stderr or "")
            report["task_result"] = f"worker timed out after {timeout_seconds} seconds"
            report["unresolved"].append("recommended failover route: inspect timeout and re-route explicitly")
        finally:
            after_files = git_changed_files(root)
            report["files_changed"] = sorted(set(after_files) - set(before_files))
            report["ended_at"] = utc_now()
            report["duration_seconds"] = round(time.monotonic() - start_monotonic, 3)
            write_execution_report(report, root=root)

    return report


def extract_json_object(text: str) -> dict[str, Any] | None:
    """Parse a JSON object from text that may include leading/trailing prose."""

    stripped = text.strip()
    if not stripped:
        return None
    try:
        parsed = json.loads(stripped)
    except json.JSONDecodeError:
        parsed = None
    else:
        if isinstance(parsed, dict):
            return parsed

    decoder = json.JSONDecoder()
    for index, char in enumerate(stripped):
        if char != "{":
            continue
        try:
            obj, _ = decoder.raw_decode(stripped[index:])
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict):
            return obj
    return None


def is_cursor_result_envelope(payload: dict[str, Any]) -> bool:
    return (
        payload.get("type") == "result"
        and payload.get("subtype") == "success"
        and payload.get("is_error") is False
        and isinstance(payload.get("result"), str)
    )


def normalize_cursor_worker_response(payload: dict[str, Any]) -> dict[str, Any]:
    """Return the inner completion object from a Cursor Agent result envelope.

    Codex and other workers that already emit the completion object are unchanged.
    """

    if not is_cursor_result_envelope(payload):
        return payload
    inner = extract_json_object(payload["result"])
    return inner if isinstance(inner, dict) else payload


def parse_worker_response(stdout: str) -> dict[str, Any] | None:
    stripped = stdout.strip()
    if not stripped:
        return None
    for candidate in (stripped, stripped.splitlines()[-1]):
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return normalize_cursor_worker_response(parsed)
    return None


def write_execution_report(report: dict[str, Any], root: Path) -> Path:
    reports_dir = root / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    safe_task_id = "".join(
        ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in str(report["task_id"])
    )
    timestamp = _dt.datetime.now(tz=_dt.UTC).strftime("%Y%m%dT%H%M%SZ")
    path = reports_dir / f"{safe_task_id}-{timestamp}.json"
    path.write_text(format_json(report), encoding="utf-8")
    report["report_path"] = str(path.relative_to(root)).replace("\\", "/")
    path.write_text(format_json(report), encoding="utf-8")
    return path


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


def format_worker_discovery(payload: dict[str, Any]) -> str:
    lines = ["Looming Dark worker discovery", "-----------------------------"]
    for name in WORKER_NAMES:
        info = payload["workers"].get(name, {})
        status = "available" if info.get("available") else "unavailable"
        path = info.get("path") or "(not found)"
        lines.append(f"{name}: {status} - {path}")
    return "\n".join(lines)


def format_execution_human(report: dict[str, Any]) -> str:
    lines = [
        "Looming Dark live dispatch report",
        "---------------------------------",
        f"task_id: {report['task_id']}",
        f"worker: {report['worker']}",
        f"run_class: {report['run_class']}",
        f"adapter: {report['adapter']}",
        f"status: {report['status']}",
        f"exit_status: {report['exit_status']}",
        f"report_path: {report.get('report_path', '(not written)')}",
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
            "Looming Dark control-plane planner and explicitly gated local "
            "worker dispatcher."
        ),
        epilog=(
            "One-command execution from the repository root:\n"
            "  python3 scripts/ldi --dry-run tasks/examples/valid-editor-tooling.yaml\n"
            "  python3 scripts/ldi --self-test\n"
            "  python3 scripts/ldi --workers"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("task", nargs="?", help="Path to a task YAML packet")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=True,
        help="Plan only (default)",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Execute an approved task through a local worker adapter",
    )
    parser.add_argument("--json", action="store_true", help="Print JSON only")
    parser.add_argument("--workers", action="store_true", help="Discover local worker CLIs")
    parser.add_argument(
        "--timeout",
        type=int,
        default=DEFAULT_TIMEOUT_SECONDS,
        help=f"Worker timeout in seconds for --execute (default: {DEFAULT_TIMEOUT_SECONDS})",
    )
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

    if args.self_test:
        return run_self_test(root)

    if args.workers:
        payload = discover_workers()
        if args.json:
            sys.stdout.write(format_json(payload))
        else:
            print(format_worker_discovery(payload))
            print()
            print("=== JSON ===")
            sys.stdout.write(format_json(payload))
        return 0

    if not args.task:
        parser.print_help()
        return 2

    task_path = Path(args.task)
    if not task_path.is_absolute():
        task_path = (Path.cwd() / task_path).resolve()

    try:
        if args.execute:
            report = execute_task(task_path, root=root, timeout_seconds=args.timeout)
            if args.json:
                sys.stdout.write(format_json(report))
            else:
                print(format_execution_human(report))
                print()
                print("=== JSON ===")
                sys.stdout.write(format_json(report))
            return 0 if report["status"] == "completed" else 1
        plan = plan_task(task_path, root=root)
    except (PlanError, ExecuteError) as exc:
        payload = {"ok": False, "error": str(exc), "dry_run": not args.execute}
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
