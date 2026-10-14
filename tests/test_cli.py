"""Offline regression tests for the unified user interface."""
import contextlib
import io
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import configuration
import research
import route_budget

SOURCE = Path(__file__).resolve().parents[1]


class UserInterfaceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        shutil.copytree(SOURCE / "config", self.root / "config")
        (self.root / "projects").mkdir()
        self.project = self.root / "projects" / "example"
        (self.project / "research").mkdir(parents=True)
        (self.project / "literature").mkdir()
        self.write("PROJECT.json", {"schema_version": 1, "id": "example", "title": "示例", "checks": []})
        self.write("research/STATE.json", {"phase": "FALSIFICATION", "decision": "CONTINUE",
                                          "priority_problem": "一个明确的最小研究命题",
                                          "next_task": "针对固定命题先尝试寻找严格反例，再构造最小可检验引理。",
                                          "last_run": None, "research_route": "C"})
        (self.project / "GOAL.md").write_text("# 固定目标\n\n目标不可自动放宽。\n", encoding="utf-8")
        self.write("literature/queries.json", {"queries": ["privacy secure aggregation"]})
        self.patches = [patch.object(research, "ROOT", self.root), patch.object(configuration, "ROOT", self.root)]
        for item in self.patches:
            item.start()

    def tearDown(self):
        for item in reversed(self.patches):
            item.stop()
        self.temp.cleanup()

    def write(self, path, obj):
        configuration.atomic_json(self.project / path, obj)

    def read(self, path):
        return configuration.load_json(self.project / path)

    def cli(self, argv):
        stream = io.StringIO()
        with contextlib.redirect_stdout(stream), contextlib.redirect_stderr(stream):
            result = research.main(argv)
        return result, stream.getvalue()

    def test_project_inference_from_nested_directory(self):
        nested = self.project / "proofs" / "draft"
        nested.mkdir(parents=True)
        with patch.object(Path, "cwd", return_value=nested):
            self.assertEqual(research.resolve_project(), self.project)
        with patch.object(Path, "cwd", return_value=self.root):
            self.assertEqual(self.cli(["status"])[0], 0)
            self.assertEqual(self.cli(["run"])[0], 2)

    def test_ideas_are_versioned_and_never_automatically_run(self):
        with patch.object(research, "run_child") as child:
            self.assertEqual(self.cli(["ideas", "add", "example", "--title", "小缺陷修复",
                                       "--text", "测试小缺陷能否低成本地恢复整数等式。"])[0], 0)
            initial = (self.project / "ideas" / "IDEA-0001" / "v001.md").read_bytes()
            self.assertEqual(self.cli(["ideas", "update", "example", "--id", "IDEA-0001",
                                       "--reason", "增加腐化条件", "--text", "增加客户端和聚合器同时恶意的模型。"])[0], 0)
            child.assert_not_called()
        self.assertEqual((self.project / "ideas" / "IDEA-0001" / "v001.md").read_bytes(), initial)
        self.assertEqual(self.read("ideas/INDEX.json")["ideas"][0]["version"], 2)
        self.assertEqual(self.read("research/STATE.json")["research_route"], "C")

    def test_select_idea_preserves_goal_and_records_explicit_activation(self):
        self.cli(["ideas", "add", "example", "--title", "授权一致性", "--text", "先寻找历史授权状态分叉的最小反例。"])
        original = (self.project / "GOAL.md").read_bytes()
        self.assertEqual(self.cli(["ideas", "select", "example", "--id", "IDEA-0001"])[0], 0)
        state = self.read("research/STATE.json")
        self.assertEqual(state["research_route"], "IDEA/IDEA-0001/v1")
        self.assertEqual(state["selected_idea"], {"id": "IDEA-0001", "version": 1})
        self.assertEqual((self.project / "GOAL.md").read_bytes(), original)
        self.assertTrue((self.project / "research" / "DECISION_LOG.md").exists())

    def test_active_run_lock_blocks_idea_selection_but_allows_stop_signal(self):
        self.cli(["ideas", "add", "example", "--title", "研究", "--text", "先查找最相近的文献。"])
        with research.project_lock(self.project):
            self.assertEqual(self.cli(["ideas", "select", "example", "--id", "IDEA-0001"])[0], 2)
            self.assertEqual(self.cli(["stop", "example"])[0], 0)
        self.assertTrue((self.project / ".control" / "STOP_REQUESTED").exists())
        self.assertEqual(self.cli(["run", "example"])[0], 2)
        self.assertEqual(self.cli(["clear-stop", "example"])[0], 0)

    def test_budget_and_model_updates_preserve_other_configuration(self):
        self.assertEqual(self.cli(["config", "example", "--model", "gpt-6.1-sol", "--effort", "high"])[0], 0)
        self.assertEqual(self.cli(["budget", "example", "--set", "12", "--stagnation", "4"])[0], 0)
        override = configuration.load_json(self.root / "config" / "projects" / "example.json")
        self.assertEqual(override["model_policy"]["routine"]["effort"], "high")
        self.assertEqual(override["route_policy"]["initial_round_budget"], 12)
        self.assertEqual(self.cli(["budget", "example", "--clear"])[0], 0)
        override = configuration.load_json(self.root / "config" / "projects" / "example.json")
        self.assertNotIn("route_policy", override)
        self.assertEqual(override["model_policy"]["routine"]["effort"], "high")

    def test_invalid_model_and_budget_do_not_damage_configuration(self):
        self.cli(["config", "example", "--effort", "high"])
        path = self.root / "config" / "projects" / "example.json"
        before = path.read_bytes()
        self.assertEqual(self.cli(["config", "example", "--model", "bad\nmodel"])[0], 2)
        self.assertEqual(self.cli(["budget", "example", "--set", "-1"])[0], 2)
        self.assertEqual(path.read_bytes(), before)

    def test_watch_does_not_loop_on_success_without_research_state_advance(self):
        with patch.object(research, "run_child", return_value=0) as run:
            self.assertEqual(self.cli(["watch", "example", "--max-rounds", "8", "--pause-seconds", "0"])[0], 3)
            self.assertEqual(run.call_count, 1)

    def test_watch_runs_bounded_rounds_and_preserves_runner_overrides(self):
        counter = 0
        def fake_runner(command):
            nonlocal counter
            counter += 1
            state = self.read("research/STATE.json")
            state["last_run"] = f"run-{counter}"
            self.write("research/STATE.json", state)
            self.assertIn("--no-fetch", command)
            self.assertIn("--route-budget", command)
            return 0
        with patch.object(research, "run_child", side_effect=fake_runner):
            result, _ = self.cli(["watch", "example", "--max-rounds", "2", "--pause-seconds", "0",
                                  "--no-fetch", "--route-budget", "6"])
        self.assertEqual(result, 0)
        self.assertEqual(counter, 2)

    def test_watch_cooperatively_stops_when_request_arrives_before_next_run(self):
        def requested_during_child(command):
            path = self.project / ".control" / "STOP_REQUESTED"
            research.replace_text(path, "stop requested")
            return 0
        with patch.object(research, "run_child", side_effect=requested_during_child):
            self.assertEqual(self.cli(["watch", "example", "--max-rounds", "8"])[0], 0)

    def test_runtime_configuration_is_centralized_and_survives_model_change(self):
        result, output = self.cli(["config", "example", "--max-seconds", "600", "--pause-seconds", "3",
                                   "--max-rounds", "4", "--network", "off", "--web-search", "disabled",
                                   "--pdf-download", "on", "--pdf-limit", "2", "--pdf-max-mb", "12"])
        self.assertEqual(result, 0, output)
        self.cli(["config", "example", "--effort", "high"])
        settings = configuration.settings_for(self.project)
        self.assertEqual(settings["execution"]["max_seconds"], 600)
        self.assertEqual(settings["execution"]["network_access"], False)
        self.assertEqual(settings["literature"]["max_pdf_downloads_per_round"], 2)
        self.assertEqual(settings["model_policy"]["routine"]["effort"], "high")

    def test_status_is_read_only_and_creates_no_route_ledger(self):
        before = set(self.root.rglob("*"))
        self.assertEqual(self.cli(["status", "example"])[0], 0)
        self.assertEqual(set(self.root.rglob("*")), before)

    def test_new_project_escapes_multiline_goal_and_title(self):
        shutil.copytree(SOURCE / "templates", self.root / "templates")
        goalfile = self.root / "目标.txt"
        goalfile.write_text('\ufeff需要证明 "私有权重" 的正确性。\n第二行包含 \\ 符号。', encoding="utf-8")
        title = '带有 "引号" 的项目'
        result, output = self.cli(["new", "second-project", "--goal-file", str(goalfile), "--title", title])
        self.assertEqual(result, 0, output)
        created = self.root / "projects" / "second-project"
        self.assertEqual(configuration.load_json(created / "PROJECT.json")["title"], title)
        self.assertEqual(configuration.load_json(created / "research" / "STATE.json")["decision"], "PAUSE")
        self.assertIn("第二行", (created / "GOAL.md").read_text(encoding="utf-8"))
        self.assertNotIn("{{", (created / "PROJECT.json").read_text(encoding="utf-8"))
        self.assertEqual(self.cli(["new", "second-project", "--goal-file", str(goalfile)])[0], 2)

    def test_manifest_checks_use_current_python_and_keep_spaces_in_arguments(self):
        script = self.project / "scripts" / "verify project.py"
        script.parent.mkdir()
        script.write_text("pass\n", encoding="utf-8")
        self.write("PROJECT.json", {"id": "example", "checks": [["scripts/verify project.py", "a b"]]})
        with patch("runner_core.validate_project", return_value=self.read("research/STATE.json")), \
             patch.object(research, "run_child", return_value=0) as run:
            self.assertEqual(self.cli(["check", "example"])[0], 0)
            command = run.call_args.args[0]
            self.assertEqual(command, [sys.executable, str(script), "a b"])

    def test_pdf_import_deduplicates_and_hashes_uploaded_bytes(self):
        pdf = self.root / "paper.pdf"
        pdf.write_bytes(b"%PDF-1.4\nminimal test fixture\n%%EOF\n")
        self.assertEqual(self.cli(["paper", "ingest", "example", "--file", str(pdf), "--url", "https://eprint.iacr.org/2026/1"])[0], 0)
        self.assertEqual(self.cli(["paper", "ingest", "example", "--file", str(pdf)])[0], 0)
        uploads = self.read("literature/uploads.json")
        self.assertEqual(len(uploads["files"]), 1)
        record = uploads["files"][0]
        self.assertEqual(record["sha256"], research.sha256_file(pdf))
        self.assertEqual((self.project / record["file"]).read_bytes(), pdf.read_bytes())

    def test_explicit_doctor_auth_failures_return_nonzero_without_credential_output(self):
        git_result = subprocess.CompletedProcess([], 0, str(self.root), "")
        auth_failure = subprocess.CompletedProcess([], 1, "private credential test marker", "")
        with patch.object(research.shutil, "which", side_effect=lambda name: "/bin/" + name), \
             patch.object(research.subprocess, "run", side_effect=[auth_failure, git_result]):
            result, output = self.cli(["doctor", "example", "--auth"])
        self.assertEqual(result, 2)
        self.assertNotIn("private credential test marker", output)
        self.assertIn("NOT_LOGGED_IN", output)
        with patch.object(research.shutil, "which", side_effect=lambda name: "/bin/" + name), \
             patch.object(research.subprocess, "run", side_effect=[subprocess.TimeoutExpired("codex", 15), git_result]):
            self.assertEqual(self.cli(["doctor", "example", "--auth"])[0], 2)
        with patch.object(research.shutil, "which", side_effect=lambda name: "/bin/" + name), \
             patch.object(research.subprocess, "run", return_value=git_result) as run:
            result, output = self.cli(["doctor", "example", "--auth", "--offline"])
        self.assertEqual(result, 0)
        self.assertEqual(run.call_count, 1)
        self.assertIn("SKIPPED_OFFLINE", output)


if __name__ == "__main__":
    unittest.main()
