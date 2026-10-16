"""Offline CLI coverage for controller-owned supervision and its separate policy."""
import contextlib
import hashlib
import io
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

import configuration
import research
import route_budget
import supervision


SOURCE = Path(__file__).resolve().parents[1]


class SupervisionInterfaceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        shutil.copytree(SOURCE / "config", self.root / "config")
        self.project = self.make_project("example")
        self.patches = [patch.object(research, "ROOT", self.root),
                        patch.object(configuration, "ROOT", self.root)]
        for item in self.patches:
            item.start()

    def tearDown(self):
        for item in reversed(self.patches):
            item.stop()
        self.temp.cleanup()

    def make_project(self, name):
        project = self.root / "projects" / name
        configuration.atomic_json(project / "PROJECT.json", {"schema_version": 1, "id": name, "checks": []})
        configuration.atomic_json(project / "research/STATE.json", {
            "schema_version": 1, "phase": "FALSIFICATION", "decision": "CONTINUE",
            "priority_problem": "一个固定的核心问题", "next_task": "先对固定安全定义寻找最小反例。",
            "research_route": "C", "last_run": None})
        for rel, content in {"GOAL.md": "# 冻结目标\n安全模型不能放宽。\n",
                             "AGENTS.md": "# 原始长期指南\n",
                             "prompts/continue.md": "原始研究任务。\n"}.items():
            path = project / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
        return project

    def cli(self, argv):
        output = io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
            code = research.main(argv)
        return code, output.getvalue()

    def project_bytes(self, project):
        return {path.relative_to(project).as_posix(): path.read_bytes()
                for path in project.rglob("*") if path.is_file()}

    def test_status_and_dry_run_are_read_only_without_model_calls(self):
        before = {str(path): path.read_bytes() for path in self.root.rglob("*") if path.is_file()}
        with patch.object(supervision, "maybe_supervise") as run:
            self.assertEqual(self.cli(["supervision", "status", "all"])[0], 0)
            self.assertEqual(self.cli(["supervision", "run", "example", "--dry-run", "--force"])[0], 0)
            run.assert_not_called()
        after = {str(path): path.read_bytes() for path in self.root.rglob("*") if path.is_file()}
        self.assertEqual(before, after)
        self.assertFalse((self.root / "state").exists())
        self.assertFalse((self.root / "locks").exists())

    def test_history_and_show_are_read_only_without_locks_or_model_calls(self):
        before = {str(path): path.read_bytes() for path in self.root.rglob("*") if path.is_file()}
        with patch.object(supervision, "maybe_supervise") as run:
            code, output = self.cli(["supervision", "history", "all"])
            self.assertEqual(code, 0, output)
            self.assertEqual(json.loads(output)["records"], [])
            code, output = self.cli(["supervision", "show", "example"])
            self.assertEqual(code, 0, output)
            self.assertEqual(json.loads(output)["status"], "no_reviews")
            run.assert_not_called()
        after = {str(path): path.read_bytes() for path in self.root.rglob("*") if path.is_file()}
        self.assertEqual(before, after)
        self.assertFalse((self.root / "state").exists())
        self.assertFalse((self.root / "locks").exists())

    def test_show_routes_explicit_review_and_rejects_all(self):
        review_id = "review-" + "a" * 24
        with patch.object(supervision, "show_review", return_value={"review_id": review_id}) as show:
            code, output = self.cli(["supervision", "show", "example", "--id", review_id])
            self.assertEqual(code, 0, output)
            self.assertEqual(json.loads(output)["review_id"], review_id)
            show.assert_called_once_with(self.root, self.project, review_id)
            self.assertEqual(self.cli(["supervision", "show", "all"])[0], 2)
            show.assert_called_once()

    def test_history_and_show_read_a_real_applied_and_rolled_back_archive(self):
        evidence = self.project / "proofs/core.md"
        evidence.parent.mkdir()
        evidence.write_text("The core malicious-security obligation remains unresolved.\n", encoding="utf-8")
        supervision.configure(self.root, self.project, {"enabled": True})
        state = configuration.load_json(self.project / "research/STATE.json")
        route_path, ledger, _ = route_budget.load_ledger(self.root, self.project, state)
        route_budget.save_ledger(route_path, ledger)

        def propose(controller, project, review_dir, prompt, policy):
            request = configuration.load_json(review_dir / "input.json")
            objective = "Search for a minimal malicious trace against the frozen security goal."
            return {"schema_version": 2, "review_id": request["review_id"],
                    "goal_sha256": request["goal_sha256"], "snapshot_sha256": request["snapshot_sha256"],
                    "verdict": {"decision": "REFOCUS", "core_goal_changed": False,
                                "main_obligation": "GOAL", "evidence_verified": False,
                                "reason": "The core security obligation remains unresolved and needs a decisive counterexample search.",
                                "next_action": objective, "requires_human_approval": False},
                    "next_task": {"anchor_id": request["focus"]["anchor_id"], "target_obligation": "GOAL",
                                  "objective": objective, "steps": ["State the exact frozen adversary and search one finite trace."],
                                  "falsification": "One admissible malicious execution violating the fixed goal falsifies the candidate.",
                                  "expected_evidence": ["An exact adversarial trace or a bounded negative-search record."]},
                    "evidence": [{"path": "proofs/core.md", "sha256": hashlib.sha256(evidence.read_bytes()).hexdigest(),
                                  "reason": "This accepted record names the unresolved core security obligation."}],
                    "agents_guidance": "", "method_change_reason": ""}

        # Synthetic legacy archive fixture only; real live/apply is retired.
        with patch.object(supervision, "_require_legacy_backend"), \
             patch.object(supervision, "_execute", side_effect=propose) as execute:
            result = supervision.maybe_supervise(self.root, self.project, ledger, force=True)
            execute.assert_called_once()
        self.assertEqual(result["status"], "applied", result)
        review_id = result["review_id"]
        before = {str(path): path.read_bytes() for path in self.root.rglob("*") if path.is_file()}
        with patch.object(supervision, "_execute") as execute:
            code, output = self.cli(["supervision", "history", "example"])
            history = json.loads(output)
            self.assertEqual(code, 0, output)
            self.assertEqual(history["active_review"], review_id)
            self.assertEqual(history["records"][0]["status"], "applied")
            code, output = self.cli(["supervision", "show", "example"])
            shown = json.loads(output)
            self.assertEqual(code, 0, output)
            self.assertEqual(shown["verdict"]["decision"], "REFOCUS")
            self.assertFalse(shown["verdict"]["evidence_verified"])
            self.assertEqual(shown["evidence_map"]["references"][0]["path"], "proofs/core.md")
            for name in ("verdict.json", "guide.patch", "evidence_map.json", "manifest.json", "guidance.md"):
                path = Path(shown["artifacts"][name])
                self.assertTrue(path.is_absolute())
                self.assertTrue(path.is_file())
            execute.assert_not_called()
        self.assertEqual(before, {str(path): path.read_bytes() for path in self.root.rglob("*") if path.is_file()})
        self.assertEqual(self.cli(["supervision", "rollback", "example", "--id", review_id])[0], 0)
        code, output = self.cli(["supervision", "show", "example", "--id", review_id])
        self.assertEqual(code, 0, output)
        self.assertEqual(json.loads(output)["status"], "rolled_back")

    def test_version_reports_release_without_project_or_model(self):
        output = io.StringIO()
        with patch.object(supervision, "maybe_supervise") as run, contextlib.redirect_stdout(output):
            with self.assertRaises(SystemExit) as result:
                research.main(["--version"])
            self.assertEqual(result.exception.code, 0)
            run.assert_not_called()
        self.assertEqual(output.getvalue().strip(), "CryptoResearchController " +
                         (SOURCE / "VERSION").read_text(encoding="utf-8-sig").strip())
        self.assertFalse((self.root / "state").exists())

    def test_enable_all_preserves_projects_and_other_configuration(self):
        second = self.make_project("second")
        config_path = self.root / "config/projects/example.json"
        configuration.atomic_json(config_path, {"model_policy": {"routine": {"model": "custom-model", "effort": "high"}},
                                              "route_policy": {"initial_round_budget": 17}})
        before = {p.name: self.project_bytes(p) for p in (self.project, second)}
        with patch.object(supervision, "maybe_supervise") as run:
            code, output = self.cli(["supervision", "configure", "all", "--enabled", "on", "--interval", "3"])
            self.assertEqual(code, 0, output)
            run.assert_not_called()
        config = configuration.load_json(config_path)
        self.assertEqual(config["model_policy"]["routine"]["model"], "custom-model")
        self.assertEqual(config["route_policy"]["initial_round_budget"], 17)
        for project in (self.project, second):
            self.assertEqual(before[project.name], self.project_bytes(project))
            self.assertTrue(supervision.policy_for(self.root, project)["enabled"])
        self.assertEqual(configuration.settings_for(self.project)["supervision_policy"]["interval"], 3)

    def test_policy_errors_leave_existing_config_unchanged(self):
        self.assertEqual(self.cli(["supervision", "configure", "example", "--enabled", "off"])[0], 0)
        path = self.root / "config/projects/example.json"
        before = path.read_bytes()
        self.assertEqual(self.cli(["supervision", "configure", "example", "--interval", "0"])[0], 2)
        self.assertEqual(path.read_bytes(), before)
        obj = configuration.load_json(path)
        obj["supervision_policy"]["unexpected"] = True
        configuration.atomic_json(path, obj)
        with self.assertRaises(ValueError):
            configuration.settings_for(self.project)

    def test_model_inheritance_is_explicit_and_separate_from_research_model(self):
        code, output = self.cli(["supervision", "configure", "example", "--model", "review-model", "--effort", "high"])
        self.assertEqual(code, 0, output)
        self.assertEqual(supervision.policy_for(self.root, self.project)["model"], "review-model")
        self.assertEqual(self.cli(["supervision", "configure", "example", "--model", "inherit", "--effort", "inherit"])[0], 0)
        policy = supervision.policy_for(self.root, self.project)
        self.assertEqual((policy["model"], policy["effort"]), ("", ""))
        self.assertNotEqual(configuration.settings_for(self.project)["model_policy"]["critical"]["model"], "review-model")

    def test_manual_run_holds_route_lock_and_delegates_core_lock_without_saving_budget(self):
        state = configuration.load_json(self.project / "research/STATE.json")
        ledger = {"epochs": [{"effective_rounds": 3}], "events": []}
        def check_run(controller, project, actual_ledger, **kwargs):
            self.assertIs(actual_ledger, ledger)
            self.assertEqual(kwargs, {"budget_reason": "budget_exhausted", "force": True})
            with self.assertRaises(RuntimeError):
                with route_budget.file_lock(self.root / "locks/route-example.lock"):
                    pass
            with route_budget.file_lock(self.root / "locks/example.lock"):
                pass  # Real maybe_supervise acquires this lock itself.
            return {"status": "FAILED", "proceed": False}
        with patch("runner_core.validate_project", return_value=state), \
             patch.object(route_budget, "load_ledger", return_value=(Path("unused"), ledger, ledger["epochs"][-1])), \
             patch.object(route_budget, "total_budget", return_value=3), \
             patch.object(route_budget, "save_ledger") as save, \
             patch.object(supervision, "maybe_supervise", side_effect=check_run):
            code, output = self.cli(["supervision", "run", "example", "--force"])
        self.assertEqual(code, 2, output)
        save.assert_not_called()

    def test_run_and_rollback_reject_all_before_calls(self):
        with patch.object(supervision, "maybe_supervise") as run, patch.object(supervision, "rollback") as rollback:
            self.assertEqual(self.cli(["supervision", "run", "all"])[0], 2)
            self.assertEqual(self.cli(["supervision", "rollback", "all", "--id", "review-1"])[0], 2)
            run.assert_not_called()
            rollback.assert_not_called()

    def test_rollback_passes_selected_review_without_modifying_state(self):
        before = self.project_bytes(self.project)
        def check_rollback(*args):
            for name in ("route-example.lock", "example.lock"):
                with self.assertRaises(RuntimeError):
                    with route_budget.file_lock(self.root / "locks" / name):
                        pass
            return {"status": "ROLLED_BACK"}
        with patch.object(supervision, "rollback", side_effect=check_rollback) as rollback:
            self.assertEqual(self.cli(["supervision", "rollback", "example", "--id", "review-1"])[0], 0)
            rollback.assert_called_once_with(self.root, self.project, "review-1")
        self.assertEqual(before, self.project_bytes(self.project))

    def test_new_template_contains_controlled_regions(self):
        for relative in ("AGENTS.md", "prompts/continue.md"):
            text = (SOURCE / "templates/project" / relative).read_text(encoding="utf-8-sig")
            self.assertEqual(text.count("<!-- SUPERVISION:BEGIN -->"), 1)
            self.assertEqual(text.count("<!-- SUPERVISION:END -->"), 1)


if __name__ == "__main__":
    unittest.main()
