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

    def test_actual_execution_proof_task_plans_codex_high(self) -> None:
        plan = ldi.plan_task(
            ROOT / "tasks/examples/valid-actual-task-execution-proof.yaml", root=ROOT
        )
        self.assertEqual(plan["task_id"], "LDI-EX-0008")
        self.assertEqual(plan["worker"], "codex")
        self.assertEqual(plan["run_class"], "high")

    def test_cursor_actual_execution_proof_task_plans_cursor_low(self) -> None:
        plan = ldi.plan_task(
            ROOT / "tasks/examples/valid-cursor-actual-task-execution-proof.yaml", root=ROOT
        )
        self.assertEqual(plan["task_id"], "LDI-EX-0009")
        self.assertEqual(plan["worker"], "cursor")
        self.assertEqual(plan["run_class"], "low")

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
        self.assertEqual(payload["workers"]["cursor"]["executable"], "agent")


class WorkerAdapterTests(unittest.TestCase):
    def test_safe_command_construction_uses_argument_array(self) -> None:
        adapter = ldi.CodexAdapter()
        task = {"id": "LDI-EX-CMD", "status": "approved", "objective": "x"}
        with mock.patch("shutil.which", return_value="/tmp/fake codex"):
            command = adapter.build_command(
                task,
                ROOT / "tasks/examples/valid-live-dispatch-proof.yaml",
                ROOT,
            )
        self.assertEqual(command, ["/tmp/fake codex", "--version"])

    def test_actual_command_construction_uses_stdin_and_schema(self) -> None:
        adapter = ldi.CodexAdapter()
        task = {
            "id": "LDI-EX-CMD",
            "status": "approved",
            "objective": "x",
            "proof_task": {"objective": "prove it"},
        }
        with mock.patch("shutil.which", return_value="/tmp/fake codex"):
            command = adapter.build_command(
                task,
                ROOT / "tasks/examples/valid-actual-task-execution-proof.yaml",
                ROOT,
                instruction_path=Path("/tmp/instruction.json"),
                response_schema_path=Path("/tmp/schema.json"),
            )
        self.assertEqual(command[0], "/tmp/fake codex")
        self.assertIn("exec", command)
        self.assertIn("--output-schema", command)
        self.assertEqual(command[-1], "-")
        self.assertNotIn("LDI-EX-CMD", command)

    def test_cursor_command_construction_uses_agent_prompt_mode(self) -> None:
        adapter = ldi.CursorAdapter()
        task = {
            "id": "LDI-EX-CURSOR",
            "status": "approved",
            "objective": "x",
            "proof_task": {"objective": "prove it"},
        }
        with mock.patch("shutil.which", return_value="/tmp/agent"):
            command = adapter.build_command(
                task,
                ROOT / "tasks/examples/valid-actual-task-execution-proof.yaml",
                ROOT,
                instruction_path=Path("/tmp/instruction.json"),
                response_schema_path=Path("/tmp/schema.json"),
            )
        self.assertEqual(command[0:4], ["/tmp/agent", "-p", "--output-format", "json"])
        self.assertIn("--trust", command)
        self.assertIn("--workspace", command)
        self.assertIn("/tmp/instruction.json", command[-1])
        self.assertNotIn("LDI-EX-CURSOR", command)

    def test_worker_instruction_contains_required_context(self) -> None:
        task_path = ROOT / "tasks/examples/valid-actual-task-execution-proof.yaml"
        task = ldi.load_yaml_file(task_path)
        instruction = ldi.build_worker_instruction(task, task_path, ROOT)
        self.assertEqual(instruction["task"]["id"], "LDI-EX-0008")
        self.assertIn("objective", instruction["task"])
        self.assertEqual(instruction["context_policy"], "compact_file_references")
        self.assertIn("AGENTS.md", instruction["authoritative_repo_rule_paths"])
        self.assertIn("CONSTRUCTION.md", instruction["authoritative_repo_rule_paths"])
        self.assertNotIn("authoritative_repo_rules", instruction)
        self.assertIn("allowed_paths", instruction)
        self.assertIn("forbidden_paths", instruction)
        self.assertEqual(
            instruction["proof_task"]["required_output_file"],
            "tasks/examples/worker-execution-proof/LDI-EX-0008.json",
        )

    def test_compact_context_does_not_embed_full_authoritative_docs(self) -> None:
        task_path = ROOT / "tasks/examples/valid-actual-task-execution-proof.yaml"
        task = ldi.load_yaml_file(task_path)
        instruction_text = json.dumps(ldi.build_worker_instruction(task, task_path, ROOT))
        agents_text = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
        construction_text = (ROOT / "CONSTRUCTION.md").read_text(encoding="utf-8")
        self.assertNotIn(agents_text[:200], instruction_text)
        self.assertNotIn(construction_text[:200], instruction_text)

    def test_compact_context_materially_reduces_instruction_size(self) -> None:
        task_path = ROOT / "tasks/examples/valid-actual-task-execution-proof.yaml"
        task = ldi.load_yaml_file(task_path)
        compact = ldi.build_worker_instruction(task, task_path, ROOT)
        legacy = ldi.build_legacy_embedded_worker_instruction(task, task_path, ROOT)
        compact_size = len(json.dumps(compact, sort_keys=True))
        legacy_size = len(json.dumps(legacy, sort_keys=True))
        self.assertLess(compact_size, legacy_size * 0.6)

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
            worker_calls = [
                call for call in run.call_args_list if call.args[0] != ["git", "status", "--porcelain"]
            ]
            self.assertEqual(len(worker_calls), 1)
            self.assertEqual(worker_calls[0].args[0], ["/tmp/codex", "--version"])
            self.assertIsNone(worker_calls[0].kwargs["input"])
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

            def fake_run(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
                if args and args[0] == ["git", "status", "--porcelain"]:
                    return subprocess.CompletedProcess(args=args[0], returncode=0, stdout="", stderr="")
                raise exc

            with mock.patch("shutil.which", return_value="/tmp/codex"):
                with mock.patch("subprocess.run", side_effect=fake_run):
                    report = ldi.execute_task(task_path, root=root, timeout_seconds=1)
            self.assertEqual(report["status"], "timeout")
            self.assertTrue((root / report["report_path"]).is_file())

    def test_actual_execution_captures_response_and_validates_output(self) -> None:
        completed = subprocess.CompletedProcess(
            args=["/tmp/codex", "exec", "-"],
            returncode=0,
            stdout=json.dumps(
                {
                    "task_id": "LDI-EX-0008",
                    "status": "completed",
                    "files_changed": [
                        "tasks/examples/worker-execution-proof/LDI-EX-0008.json"
                    ],
                    "checks_performed": ["proof written"],
                    "warnings": [],
                    "unresolved": [],
                    "summary": "done",
                }
            ),
            stderr="",
        )
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for folder in ("control-plane", "tasks/examples"):
                (root / folder).mkdir(parents=True, exist_ok=True)
            (root / "AGENTS.md").write_text("agents\n", encoding="utf-8")
            (root / "CONSTRUCTION.md").write_text("construction\n", encoding="utf-8")
            (root / "control-plane" / "ROUTING.yaml").write_text(
                (ROOT / "control-plane" / "ROUTING.yaml").read_text(encoding="utf-8"),
                encoding="utf-8",
            )
            (root / "control-plane" / "ARCHITECTURE.md").write_text("arch\n", encoding="utf-8")
            (root / "control-plane" / "README.md").write_text("readme\n", encoding="utf-8")
            (root / "control-plane" / "ldi.py").write_text("ldi\n", encoding="utf-8")
            proof_dir = root / "tasks/examples/worker-execution-proof"
            proof_dir.mkdir()
            proof_path = proof_dir / "LDI-EX-0008.json"
            task_path = root / "tasks/examples/task.yaml"
            objective = "Prove actual local worker task execution."
            task_path.write_text(
                "id: LDI-EX-0008\nstatus: approved\n"
                f"objective: {objective}\ntask_class: cross_system\n"
                "worker:\n  preferred: codex\n  run_class: HIGH\n"
                "inputs:\n  specs: []\n"
                "ownership:\n  allowed_paths:\n    - tasks/examples/worker-execution-proof/**\n"
                "  forbidden_paths:\n    - assets/**\n"
                "budget:\n  paid_credits_allowed: false\n  max_estimated_cost_usd: 0\n  max_generation_attempts: 0\n"
                "proof_task:\n  objective: Write proof.\n",
                encoding="utf-8",
            )

            def fake_run(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
                if args and args[0] == ["git", "status", "--porcelain"]:
                    return subprocess.CompletedProcess(args=args[0], returncode=0, stdout="", stderr="")
                proof_path.write_text(
                    json.dumps(
                        {
                            "task_id": "LDI-EX-0008",
                            "objective": objective,
                            "followed_repository_restrictions": True,
                            "permitted_directory": "tasks/examples/worker-execution-proof",
                            "worker_result": "completed",
                        }
                    ),
                    encoding="utf-8",
                )
                return completed

            with mock.patch("shutil.which", return_value="/tmp/codex"):
                with mock.patch("subprocess.run", side_effect=fake_run) as run:
                    report = ldi.execute_task(task_path, root=root)
            worker_call = [
                call for call in run.call_args_list if call.args[0] != ["git", "status", "--porcelain"]
            ][0]
            self.assertIn("control_plane_instruction_version", worker_call.kwargs["input"])
            self.assertNotIn("LDI-EX-0008", worker_call.args[0])
            self.assertEqual(report["worker_invocation_status"], "completed")
            self.assertEqual(report["task_acceptance_status"], "accepted")
            self.assertEqual(report["status"], "completed")
            self.assertEqual(report["worker_response"]["task_id"], "LDI-EX-0008")
            self.assertTrue(report["validation_results"][0]["accepted"])

    def test_partial_worker_response_with_valid_proof_is_not_accepted(self) -> None:
        completed = subprocess.CompletedProcess(
            args=["/tmp/codex", "exec", "-"],
            returncode=0,
            stdout=json.dumps(
                {
                    "task_id": "LDI-EX-0008",
                    "status": "partial",
                    "files_changed": [
                        "tasks/examples/worker-execution-proof/LDI-EX-0008.json"
                    ],
                    "checks_performed": ["proof written"],
                    "warnings": [],
                    "unresolved": ["worker reported a blocker"],
                    "summary": "proof exists but task is partial",
                }
            ),
            stderr="",
        )
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for folder in ("control-plane", "tasks/examples"):
                (root / folder).mkdir(parents=True, exist_ok=True)
            (root / "AGENTS.md").write_text("agents\n", encoding="utf-8")
            (root / "CONSTRUCTION.md").write_text("construction\n", encoding="utf-8")
            (root / "control-plane" / "ROUTING.yaml").write_text(
                (ROOT / "control-plane" / "ROUTING.yaml").read_text(encoding="utf-8"),
                encoding="utf-8",
            )
            for rel_path in ("ARCHITECTURE.md", "README.md", "ldi.py"):
                (root / "control-plane" / rel_path).write_text(rel_path, encoding="utf-8")
            proof_dir = root / "tasks/examples/worker-execution-proof"
            proof_dir.mkdir()
            proof_path = proof_dir / "LDI-EX-0008.json"
            task_path = root / "tasks/examples/task.yaml"
            objective = "Prove actual local worker task execution."
            task_path.write_text(
                "id: LDI-EX-0008\nstatus: approved\n"
                f"objective: {objective}\ntask_class: cross_system\n"
                "worker:\n  preferred: codex\n  run_class: HIGH\n"
                "inputs:\n  specs: []\n"
                "ownership:\n  allowed_paths:\n    - tasks/examples/worker-execution-proof/**\n"
                "  forbidden_paths:\n    - assets/**\n"
                "budget:\n  paid_credits_allowed: false\n  max_estimated_cost_usd: 0\n  max_generation_attempts: 0\n"
                "proof_task:\n  objective: Write proof.\n",
                encoding="utf-8",
            )

            def fake_run(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
                if args and args[0] == ["git", "status", "--porcelain"]:
                    return subprocess.CompletedProcess(args=args[0], returncode=0, stdout="", stderr="")
                proof_path.write_text(
                    json.dumps(
                        {
                            "task_id": "LDI-EX-0008",
                            "objective": objective,
                            "followed_repository_restrictions": True,
                            "permitted_directory": "tasks/examples/worker-execution-proof",
                            "worker_result": "completed",
                        }
                    ),
                    encoding="utf-8",
                )
                return completed

            with mock.patch("shutil.which", return_value="/tmp/codex"):
                with mock.patch("subprocess.run", side_effect=fake_run):
                    report = ldi.execute_task(task_path, root=root)
            self.assertTrue(report["validation_results"][0]["accepted"])
            self.assertEqual(report["worker_invocation_status"], "completed")
            self.assertEqual(report["task_acceptance_status"], "rejected")
            self.assertEqual(report["status"], "failed")
            self.assertIn("worker response was not completed", report["unresolved"][0])

    def test_cursor_auth_failure_reports_single_concrete_blocker(self) -> None:
        blocker = ldi.classify_worker_failure(
            "cursor",
            "Error: Authentication required. Please run 'agent login' first.",
        )
        self.assertEqual(
            blocker,
            "Cursor agent authentication required: run 'agent login' or set CURSOR_API_KEY",
        )

    def test_cursor_envelope_with_prose_normalizes_to_completion_object(self) -> None:
        # Exact Cursor Agent shape from reports/LDI-EX-0009-20260909T182948Z.json
        inner_completion = {
            "task_id": "LDI-EX-0009",
            "status": "completed",
            "files_changed": [
                "tasks/examples/worker-execution-proof/LDI-EX-0009.json"
            ],
            "checks_performed": [
                "Read AGENTS.md and CONSTRUCTION.md locally before editing.",
                "Created tasks/examples/worker-execution-proof/LDI-EX-0009.json with the required deterministic proof fields.",
                "Confirmed edits stayed within the permitted proof directory and did not touch Unity, design, asset, package, or project-settings paths.",
            ],
            "warnings": [],
            "unresolved": [],
            "summary": (
                "Created the deterministic proof artifact for LDI-EX-0009 with the "
                "required task id, objective, permitted directory, restriction "
                "confirmation, and completed worker result."
            ),
        }
        prose_prefixed_result = (
            "I'll read the instruction file and the project docs it depends on, "
            "then execute exactly what's requested.Creating the required proof "
            "artifact, then returning only the structured completion JSON.Writing "
            "the proof artifact, then returning only the completion JSON."
            + json.dumps(inner_completion)
        )
        stdout = json.dumps(
            {
                "type": "result",
                "subtype": "success",
                "is_error": False,
                "duration_ms": 29836,
                "duration_api_ms": 29836,
                "result": prose_prefixed_result,
                "session_id": "9c94096c-55b6-4a96-83dd-54fc760bdaa2",
                "request_id": "f66dc3ff-c3bf-4aa0-91bf-3fd31985d094",
                "usage": {
                    "inputTokens": 44597,
                    "outputTokens": 1497,
                    "cacheReadTokens": 123520,
                    "cacheWriteTokens": 0,
                },
            }
        )
        parsed = ldi.parse_worker_response(stdout)
        self.assertEqual(parsed["status"], "completed")
        self.assertEqual(parsed["unresolved"], [])
        self.assertEqual(parsed["warnings"], [])
        self.assertEqual(parsed["task_id"], "LDI-EX-0009")
        self.assertTrue(ldi.worker_response_is_successful(parsed))

    def test_codex_completion_object_is_unchanged_by_cursor_normalization(self) -> None:
        completion = {
            "task_id": "LDI-EX-0008",
            "status": "completed",
            "files_changed": [],
            "checks_performed": [],
            "warnings": [],
            "unresolved": [],
            "summary": "done",
        }
        parsed = ldi.parse_worker_response(json.dumps(completion))
        self.assertEqual(parsed, completion)

    def test_cursor_envelope_acceptance_with_valid_proof(self) -> None:
        objective = (
            "Prove that Cursor can complete an actual local worker task through "
            "the control-plane execute path."
        )
        inner_completion = {
            "task_id": "LDI-EX-0009",
            "status": "completed",
            "files_changed": [
                "tasks/examples/worker-execution-proof/LDI-EX-0009.json"
            ],
            "checks_performed": ["proof written"],
            "warnings": [],
            "unresolved": [],
            "summary": "done",
        }
        prose_prefixed_result = (
            "I'll read the instruction file and the project docs it depends on, "
            "then execute exactly what's requested.Creating the required proof "
            "artifact, then returning only the structured completion JSON.Writing "
            "the proof artifact, then returning only the completion JSON."
            + json.dumps(inner_completion)
        )
        completed = subprocess.CompletedProcess(
            args=["/tmp/agent", "-p", "--output-format", "json"],
            returncode=0,
            stdout=json.dumps(
                {
                    "type": "result",
                    "subtype": "success",
                    "is_error": False,
                    "duration_ms": 29836,
                    "duration_api_ms": 29836,
                    "result": prose_prefixed_result,
                    "session_id": "9c94096c-55b6-4a96-83dd-54fc760bdaa2",
                    "request_id": "f66dc3ff-c3bf-4aa0-91bf-3fd31985d094",
                    "usage": {
                        "inputTokens": 44597,
                        "outputTokens": 1497,
                        "cacheReadTokens": 123520,
                        "cacheWriteTokens": 0,
                    },
                }
            )
            + "\n",
            stderr="",
        )
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for folder in ("control-plane", "tasks/examples"):
                (root / folder).mkdir(parents=True, exist_ok=True)
            (root / "AGENTS.md").write_text("agents\n", encoding="utf-8")
            (root / "CONSTRUCTION.md").write_text("construction\n", encoding="utf-8")
            (root / "control-plane" / "ROUTING.yaml").write_text(
                (ROOT / "control-plane" / "ROUTING.yaml").read_text(encoding="utf-8"),
                encoding="utf-8",
            )
            for rel_path in ("ARCHITECTURE.md", "README.md", "ldi.py"):
                (root / "control-plane" / rel_path).write_text(rel_path, encoding="utf-8")
            proof_dir = root / "tasks/examples/worker-execution-proof"
            proof_dir.mkdir()
            proof_path = proof_dir / "LDI-EX-0009.json"
            task_path = root / "tasks/examples/task.yaml"
            task_path.write_text(
                "id: LDI-EX-0009\nstatus: approved\n"
                f"objective: {objective}\ntask_class: tooling\n"
                "worker:\n  preferred: cursor\n  run_class: LOW\n"
                "inputs:\n  specs: []\n"
                "ownership:\n  allowed_paths:\n    - tasks/examples/worker-execution-proof/**\n"
                "  forbidden_paths:\n    - assets/**\n"
                "budget:\n  paid_credits_allowed: false\n  max_estimated_cost_usd: 0\n  max_generation_attempts: 0\n"
                "proof_task:\n  objective: Write proof.\n",
                encoding="utf-8",
            )

            def fake_run(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
                if args and args[0] == ["git", "status", "--porcelain"]:
                    return subprocess.CompletedProcess(args=args[0], returncode=0, stdout="", stderr="")
                proof_path.write_text(
                    json.dumps(
                        {
                            "task_id": "LDI-EX-0009",
                            "objective": objective,
                            "followed_repository_restrictions": True,
                            "permitted_directory": "tasks/examples/worker-execution-proof",
                            "worker_result": "completed",
                        }
                    ),
                    encoding="utf-8",
                )
                return completed

            with mock.patch("shutil.which", return_value="/tmp/agent"):
                with mock.patch("subprocess.run", side_effect=fake_run):
                    report = ldi.execute_task(task_path, root=root)
            self.assertEqual(report["worker_response"]["status"], "completed")
            self.assertEqual(report["worker_response"]["unresolved"], [])
            self.assertTrue(report["validation_results"][0]["accepted"])
            self.assertEqual(report["task_acceptance_status"], "accepted")
            self.assertEqual(report["status"], "completed")


class ContextBudgetTests(unittest.TestCase):
    def test_low_context_budget_metadata_is_present_and_bounded(self) -> None:
        task_path = ROOT / "tasks/examples/valid-cursor-actual-task-execution-proof.yaml"
        task = ldi.load_yaml_file(task_path)
        instruction = ldi.build_worker_instruction(task, task_path, ROOT)
        budget = instruction["context_budget"]
        self.assertEqual(budget["run_class"], "low")
        self.assertEqual(budget["max_task_specific_context_files"], 5)
        self.assertLessEqual(len(budget["selected_task_specific_context_paths"]), 5)
        self.assertIn("compact context", budget["guidance"].lower())
        self.assertNotIn("authoritative_repo_rules", instruction)

    def test_medium_context_budget_metadata_is_present_and_bounded(self) -> None:
        task_path = ROOT / "tasks/examples/valid-editor-tooling.yaml"
        task = ldi.load_yaml_file(task_path)
        # Locked run_class is absent; routing for tooling is medium.
        instruction = ldi.build_worker_instruction(task, task_path, ROOT, run_class="medium")
        budget = instruction["context_budget"]
        self.assertEqual(budget["run_class"], "medium")
        self.assertEqual(budget["max_task_specific_context_files"], 10)
        self.assertLessEqual(len(budget["selected_task_specific_context_paths"]), 10)

    def test_named_fewer_context_files_preserves_narrower_scope(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "control-plane").mkdir()
            (root / "control-plane" / "ROUTING.yaml").write_text(
                (ROOT / "control-plane" / "ROUTING.yaml").read_text(encoding="utf-8"),
                encoding="utf-8",
            )
            task_path = root / "task.yaml"
            task_path.write_text(
                "id: LDI-EX-BUDGET\nstatus: approved\n"
                "objective: Budget scope check.\n"
                "task_class: tooling\n"
                "worker:\n  preferred: cursor\n  run_class: LOW\n"
                "inputs:\n  specs:\n    - control-plane/README.md\n    - control-plane/ARCHITECTURE.md\n",
                encoding="utf-8",
            )
            task = ldi.load_yaml_file(task_path)
            instruction = ldi.build_worker_instruction(task, task_path, root)
            budget = instruction["context_budget"]
            self.assertEqual(budget["max_task_specific_context_files"], 2)
            self.assertEqual(
                budget["selected_task_specific_context_paths"],
                ["control-plane/README.md", "control-plane/ARCHITECTURE.md"],
            )

    def test_high_run_class_omits_context_budget(self) -> None:
        task_path = ROOT / "tasks/examples/valid-actual-task-execution-proof.yaml"
        task = ldi.load_yaml_file(task_path)
        instruction = ldi.build_worker_instruction(task, task_path, ROOT)
        self.assertNotIn("context_budget", instruction)


class CursorPermissionConfigTests(unittest.TestCase):
    def _load_permissions(self) -> dict[str, list[str]]:
        path = ROOT / ldi.CURSOR_CLI_PERMISSIONS_PATH
        self.assertTrue(path.is_file(), f"missing {ldi.CURSOR_CLI_PERMISSIONS_PATH}")
        payload = json.loads(path.read_text(encoding="utf-8"))
        permissions = payload.get("permissions")
        self.assertIsInstance(permissions, dict)
        allow = permissions.get("allow")
        deny = permissions.get("deny")
        self.assertIsInstance(allow, list)
        self.assertIsInstance(deny, list)
        return {"allow": allow, "deny": deny}

    def test_cursor_permissions_allow_readonly_inspection_commands(self) -> None:
        allow = self._load_permissions()["allow"]
        required = {
            "Shell(git:status*)",
            "Shell(git:diff*)",
            "Shell(git:log*)",
            "Shell(git:show*)",
            "Shell(git:rev-parse*)",
            "Shell(git:merge-base*)",
            "Shell(git:rev-list*)",
            "Shell(git:branch*)",
            "Shell(git:stash list*)",
            "Shell(ls)",
            "Shell(cat)",
            "Shell(head)",
            "Shell(tail)",
            "Shell(test)",
            "Shell(grep)",
        }
        self.assertTrue(required.issubset(set(allow)))

    def test_cursor_permissions_deny_install_and_destructive_commands(self) -> None:
        deny = self._load_permissions()["deny"]
        required_substrings = [
            "Shell(brew:install",
            "Shell(pip",
            "Shell(pip3",
            "Shell(npm:install",
            "Shell(yarn:install",
            "Shell(pnpm:install",
            "Shell(curl",
            "Shell(rm",
            "Shell(sudo",
            "Shell(chmod",
            "Shell(git:clean",
            "Shell(git:reset --hard",
            "Shell(git:push --force",
        ]
        for needle in required_substrings:
            self.assertTrue(
                any(str(item).startswith(needle) or needle in str(item) for item in deny),
                f"missing deny coverage for {needle}",
            )

    def test_cursor_permissions_have_no_broad_shell_allowances(self) -> None:
        allow = self._load_permissions()["allow"]
        forbidden = {
            "Shell(git)",
            "Shell(gh)",
            "Shell(python3)",
            "Shell(*)",
            "Shell(**)",
        }
        self.assertTrue(forbidden.isdisjoint(set(allow)))
        for item in allow:
            self.assertFalse(str(item) in {"Shell(git)", "Shell(gh)", "Shell(python3)"})
            self.assertFalse(str(item).startswith("Shell(*)"))


if __name__ == "__main__":
    unittest.main()
