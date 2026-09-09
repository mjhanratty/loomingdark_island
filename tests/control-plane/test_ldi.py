"""Tests for the Looming Dark control-plane dry-run CLI."""

from __future__ import annotations

import os
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

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

    def test_architecture_review_routes_claude_high(self) -> None:
        plan = ldi.plan_task(
            ROOT / "tasks/examples/valid-architecture-review.yaml", root=ROOT
        )
        self.assertEqual(plan["task_id"], "LDI-EX-0005")
        self.assertEqual(plan["task_class"], "architecture_review")
        self.assertEqual(plan["worker"], "claude")
        self.assertEqual(plan["run_class"], "high")
        self.assertFalse(plan["worker_locked"])
        self.assertFalse(plan["run_class_locked"])

    def test_locked_worker_and_run_class_are_preserved(self) -> None:
        plan = ldi.plan_task(ROOT / "tasks/examples/valid-locked-worker.yaml", root=ROOT)
        self.assertEqual(plan["worker"], "cursor")
        self.assertEqual(plan["run_class"], "low")
        self.assertTrue(plan["worker_locked"])
        self.assertTrue(plan["run_class_locked"])

    def test_locked_claude_worker_is_preserved(self) -> None:
        plan = ldi.plan_task(ROOT / "tasks/examples/valid-locked-claude.yaml", root=ROOT)
        self.assertEqual(plan["task_id"], "LDI-EX-0006")
        self.assertEqual(plan["worker"], "claude")
        self.assertEqual(plan["run_class"], "high")
        self.assertTrue(plan["worker_locked"])
        self.assertTrue(plan["run_class_locked"])
        self.assertEqual(plan["task_class"], "docs")

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

    def test_live_dispatch_proof_task_plans_codex_high(self) -> None:
        plan = ldi.plan_task(ROOT / "tasks/examples/valid-live-dispatch-proof.yaml", root=ROOT)
        self.assertEqual(plan["task_id"], "LDI-EX-0007")
        self.assertEqual(plan["worker"], "codex")
        self.assertEqual(plan["run_class"], "high")
        self.assertTrue(plan["worker_locked"])
        self.assertTrue(plan["run_class_locked"])

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

    def test_cli_execute_draft_rejected(self) -> None:
        with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as tmp:
            tmp.write(
                "id: LDI-EX-DRAFT\nstatus: draft\n"
                "objective: Draft task must not execute.\n"
                "task_class: docs\n"
            )
            tmp_path = tmp.name
        try:
            result = self._run("--execute", tmp_path)
        finally:
            Path(tmp_path).unlink(missing_ok=True)
        self.assertEqual(result.returncode, 1)
        self.assertIn("requires task status: approved", result.stderr)

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

    def test_workers_reports_unavailable_without_failing(self) -> None:
        result = self._run("--json", "--workers")
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertTrue(payload["ok"])
        self.assertEqual(set(payload["workers"]), {"cursor", "codex", "claude"})
        for info in payload["workers"].values():
            self.assertIn("available", info)


class WorkerAdapterTests(unittest.TestCase):
    def test_safe_command_construction_uses_argument_array(self) -> None:
        adapter = ldi.CodexAdapter()
        task = {"id": "LDI-EX-CMD", "status": "approved", "objective": "x"}
        with mock.patch("shutil.which", return_value="/tmp/fake codex"):
            command = adapter.build_command(task, ROOT / "tasks/examples/valid-live-dispatch-proof.yaml")
        self.assertEqual(command, ["/tmp/fake codex", "--version"])

    def test_unavailable_worker_discovery(self) -> None:
        with mock.patch("shutil.which", return_value=None):
            payload = ldi.discover_workers()
        self.assertFalse(payload["workers"]["cursor"]["available"])
        self.assertFalse(payload["workers"]["codex"]["available"])
        self.assertFalse(payload["workers"]["claude"]["available"])

    def test_execute_rejects_unapproved_task(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "draft.yaml"
            path.write_text(
                "id: LDI-EX-DRAFT\nstatus: draft\n"
                "objective: Draft task must not execute.\n"
                "task_class: cross_system\n"
                "worker:\n  preferred: codex\n  run_class: HIGH\n",
                encoding="utf-8",
            )
            with self.assertRaises(ldi.ExecuteError):
                ldi.execute_task(path, root=ROOT)

    def test_execute_handles_nonzero_and_writes_report(self) -> None:
        completed = subprocess.CompletedProcess(
            args=["/tmp/codex", "--version"],
            returncode=7,
            stdout="",
            stderr="bad exit",
        )
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "control-plane").mkdir()
            (root / "control-plane" / "ROUTING.yaml").write_text(
                (ROOT / "control-plane" / "ROUTING.yaml").read_text(encoding="utf-8"),
                encoding="utf-8",
            )
            task_path = root / "task.yaml"
            task_path.write_text(
                "id: LDI-EX-NONZERO\nstatus: approved\n"
                "objective: Nonzero proof.\ntask_class: cross_system\n"
                "worker:\n  preferred: codex\n  run_class: HIGH\n"
                "budget:\n  paid_credits_allowed: false\n  max_estimated_cost_usd: 0\n  max_generation_attempts: 0\n",
                encoding="utf-8",
            )
            with mock.patch("shutil.which", return_value="/tmp/codex"):
                with mock.patch("subprocess.run", return_value=completed) as run:
                    report = ldi.execute_task(task_path, root=root)
            run.assert_called_once()
            self.assertEqual(run.call_args.args[0], ["/tmp/codex", "--version"])
            self.assertEqual(report["status"], "failed")
            self.assertEqual(report["exit_status"], 7)
            self.assertTrue((root / report["report_path"]).is_file())

    def test_execute_handles_timeout_and_writes_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "control-plane").mkdir()
            (root / "control-plane" / "ROUTING.yaml").write_text(
                (ROOT / "control-plane" / "ROUTING.yaml").read_text(encoding="utf-8"),
                encoding="utf-8",
            )
            task_path = root / "task.yaml"
            task_path.write_text(
                "id: LDI-EX-TIMEOUT\nstatus: approved\n"
                "objective: Timeout proof.\ntask_class: cross_system\n"
                "worker:\n  preferred: codex\n  run_class: HIGH\n"
                "budget:\n  paid_credits_allowed: false\n  max_estimated_cost_usd: 0\n  max_generation_attempts: 0\n",
                encoding="utf-8",
            )
            exc = subprocess.TimeoutExpired(["/tmp/codex", "--version"], timeout=1)
            with mock.patch("shutil.which", return_value="/tmp/codex"):
                with mock.patch("subprocess.run", side_effect=exc):
                    report = ldi.execute_task(task_path, root=root, timeout_seconds=1)
            self.assertEqual(report["status"], "timeout")
            self.assertTrue((root / report["report_path"]).is_file())


if __name__ == "__main__":
    unittest.main()
