"""Tests for the Looming Dark control-plane dry-run CLI."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "control-plane"))

import ldi  # noqa: E402


class PlanTaskTests(unittest.TestCase):
    def test_valid_editor_tooling_routes_cursor_medium(self) -> None:
        plan = ldi.plan_task(ROOT / "tasks/examples/valid-editor-tooling.yaml", root=ROOT)
        self.assertTrue(plan["ok"])
        self.assertTrue(plan["dry_run"])
        self.assertEqual(plan["task_id"], "LDI-EX-0001")
        self.assertEqual(plan["worker"], "cursor")
        self.assertEqual(plan["run_class"], "medium")
        self.assertFalse(plan["worker_locked"])
        self.assertFalse(plan["run_class_locked"])
        self.assertFalse(plan["exclusive_ownership_required"])
        self.assertEqual(plan["conflict_matches"], [])
        self.assertIn("dry-run", plan["next_action"])

    def test_valid_architecture_routes_codex_high(self) -> None:
        plan = ldi.plan_task(ROOT / "tasks/examples/valid-architecture.yaml", root=ROOT)
        self.assertEqual(plan["worker"], "codex")
        self.assertEqual(plan["run_class"], "high")

    def test_locked_worker_and_run_class_are_preserved(self) -> None:
        plan = ldi.plan_task(ROOT / "tasks/examples/valid-locked-worker.yaml", root=ROOT)
        self.assertEqual(plan["worker"], "cursor")
        self.assertEqual(plan["run_class"], "low")
        self.assertTrue(plan["worker_locked"])
        self.assertTrue(plan["run_class_locked"])

    def test_unity_paths_require_exclusive_ownership(self) -> None:
        plan = ldi.plan_task(ROOT / "tasks/examples/valid-unity-conflict.yaml", root=ROOT)
        self.assertTrue(plan["exclusive_ownership_required"])
        patterns = {item["pattern"] for item in plan["conflict_matches"]}
        self.assertIn("*.unity", patterns)
        self.assertIn("*.prefab", patterns)

    def test_approved_cli_task_packet_plans(self) -> None:
        plan = ldi.plan_task(
            ROOT / "tasks/approved/LDI-INFRA-0002-control-plane-cli.yaml",
            root=ROOT,
        )
        self.assertEqual(plan["task_id"], "LDI-INFRA-0002")
        self.assertEqual(plan["worker"], "cursor")
        self.assertEqual(plan["run_class"], "medium")
        self.assertTrue(plan["worker_locked"])
        self.assertTrue(plan["run_class_locked"])
        self.assertFalse(plan["exclusive_ownership_required"])

    def test_template_nested_worker_lock(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "nested.yaml"
            path.write_text(
                "\n".join(
                    [
                        "id: LDI-EX-NESTED",
                        "status: approved",
                        "objective: Nested worker lock from the task template.",
                        "task_class: docs",
                        "worker:",
                        "  preferred: cursor",
                        "  run_class: MEDIUM",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            plan = ldi.plan_task(path, root=ROOT)
            self.assertEqual(plan["worker"], "cursor")
            self.assertEqual(plan["run_class"], "medium")
            self.assertTrue(plan["worker_locked"])
            self.assertTrue(plan["run_class_locked"])

    def test_missing_id_fails(self) -> None:
        with self.assertRaises(ldi.PlanError) as ctx:
            ldi.plan_task(ROOT / "tasks/examples/invalid-missing-id.yaml", root=ROOT)
        self.assertIn("missing required fields: id", str(ctx.exception))

    def test_unknown_locked_worker_fails(self) -> None:
        with self.assertRaises(ldi.PlanError) as ctx:
            ldi.plan_task(ROOT / "tasks/examples/invalid-unknown-worker.yaml", root=ROOT)
        self.assertIn("invalid locked worker", str(ctx.exception))

    def test_unknown_task_class_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bad-class.yaml"
            path.write_text(
                "id: LDI-EX-BAD-CLASS\nstatus: approved\n"
                "objective: Unknown class.\ntask_class: not_a_real_class\n",
                encoding="utf-8",
            )
            with self.assertRaises(ldi.PlanError) as ctx:
                ldi.plan_task(path, root=ROOT)
            self.assertIn("no routing rule matches task_class", str(ctx.exception))

    def test_human_and_json_contain_required_fields(self) -> None:
        plan = ldi.plan_task(ROOT / "tasks/examples/valid-editor-tooling.yaml", root=ROOT)
        human = ldi.format_human(plan)
        for token in ("task_id:", "worker:", "run_class:", "exclusive_ownership_required:", "next_action:"):
            self.assertIn(token, human)
        payload = ldi.format_json(plan)
        for token in (
            '"task_id"',
            '"worker"',
            '"run_class"',
            '"exclusive_ownership_required"',
            '"next_action"',
        ):
            self.assertIn(token, payload)


class CliTests(unittest.TestCase):
    def _run(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "ldi"), *args],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )

    def test_cli_valid_example_exit_zero(self) -> None:
        result = self._run("--dry-run", "tasks/examples/valid-editor-tooling.yaml")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("task_id: LDI-EX-0001", result.stdout)
        self.assertIn("worker: cursor", result.stdout)
        self.assertIn("run_class: medium", result.stdout)
        self.assertIn("=== JSON ===", result.stdout)

    def test_cli_invalid_example_exit_nonzero(self) -> None:
        result = self._run("--dry-run", "tasks/examples/invalid-missing-id.yaml")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("missing required fields: id", result.stderr)
        self.assertIn('"ok": false', result.stdout)

    def test_cli_execute_rejected(self) -> None:
        result = self._run("--execute", "tasks/examples/valid-editor-tooling.yaml")
        self.assertEqual(result.returncode, 2)
        self.assertIn("dry-run only", result.stderr)

    def test_cli_json_flag(self) -> None:
        result = self._run("--json", "--dry-run", "tasks/examples/valid-editor-tooling.yaml")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(result.stdout.lstrip().startswith("{"))
        self.assertIn('"worker": "cursor"', result.stdout)

    def test_dry_run_does_not_write_files(self) -> None:
        before = []
        for folder in ("control-plane", "scripts", "tasks", "tests"):
            path = ROOT / folder
            if path.exists():
                for item in path.rglob("*"):
                    if item.is_file():
                        before.append((item, item.stat().st_mtime_ns, item.read_bytes()))
        result = self._run("--dry-run", "tasks/examples/valid-editor-tooling.yaml")
        self.assertEqual(result.returncode, 0, result.stderr)
        after = []
        for folder in ("control-plane", "scripts", "tasks", "tests"):
            path = ROOT / folder
            if path.exists():
                for item in path.rglob("*"):
                    if item.is_file():
                        after.append((item, item.stat().st_mtime_ns, item.read_bytes()))
        self.assertEqual(before, after)
        self.assertIsNone(os.environ.get("LDI_EXECUTE"))


if __name__ == "__main__":
    unittest.main()
