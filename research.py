#!/usr/bin/env python3
"""Portable user interface for the unified cryptography research workspace.

Use from the controller root with a project ID, or from a project directory
without one. All subprocess arguments are lists; no shell interpolation.
"""
from __future__ import annotations

import argparse
import contextlib
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from urllib.parse import urlparse

from configuration import ROOT, atomic_json, deep_merge, load_json, project_id, settings_for, validate_settings
from route_budget import file_lock, policy_for, project_key, validate_policy

STOP_DECISIONS = {"PAUSE", "STOP", "NEEDS_REVIEW", "NEEDS_INPUT"}
IDEA_ID = re.compile(r"^IDEA-[0-9]{4,}$")
PROJECT_ID = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
ROUTE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:/-]{0,79}$")
EFFORTS = ("low", "medium", "high", "xhigh", "max", "ultra")


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def print_json(obj):
    print(json.dumps(obj, ensure_ascii=False, indent=2))


def projects():
    base = ROOT / "projects"
    return sorted((p for p in base.iterdir() if p.is_dir() and (p / "PROJECT.json").is_file()),
                  key=lambda p: p.name) if base.is_dir() else []


def resolve_project(value=None):
    if value:
        candidate = ROOT / "projects" / value
        if not candidate.is_dir():
            supplied = Path(value).expanduser()
            candidate = supplied.resolve()
    else:
        cwd = Path.cwd().resolve()
        candidate = next((p for p in (cwd, *cwd.parents)
                          if (p / "PROJECT.json").is_file()), None)
        if candidate is None:
            raise ValueError("请指定项目，例如 research.cmd status secagg-research；在项目目录中可省略项目名。")
    candidate = candidate.resolve()
    candidate.relative_to((ROOT / "projects").resolve())
    ident = project_id(candidate)
    if candidate != (ROOT / "projects" / ident).resolve():
        raise ValueError("项目必须位于 projects/<PROJECT.json 中的 id>。")
    return candidate


def project_lock(project):
    return file_lock(ROOT / "locks" / ("route-" + project_key(project) + ".lock"))


def read_state(project):
    state = load_json(project / "research" / "STATE.json", {})
    if not isinstance(state, dict):
        raise ValueError("STATE.json 必须是 JSON 对象。")
    return state


def replace_text(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=".write-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as out:
            out.write(text)
            if not text.endswith("\n"):
                out.write("\n")
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def append_decision(project, title, text):
    path = project / "research" / "DECISION_LOG.md"
    previous = path.read_text(encoding="utf-8-sig") if path.exists() else "# 研究决策记录\n"
    replace_text(path, previous.rstrip() + f"\n\n## {now()} — {title}\n\n{text}\n")


def runner_command(project, args, *, rounds=None, mode=None):
    cmd = [sys.executable, str(ROOT / "runner.py"), "--project", str(project)]
    if mode:
        cmd.append(mode)
    else:
        cmd.extend(["--rounds", str(rounds if rounds is not None else args.rounds)])
    for field in ("model", "effort", "max_seconds", "route_budget", "stagnation_rounds",
                  "extension_round_budget", "max_extensions"):
        value = getattr(args, field, None)
        if value is not None:
            cmd.extend(["--" + field.replace("_", "-"), str(value)])
    for field in ("dry_run", "no_fetch", "offline", "audit", "route_sync"):
        if getattr(args, field, False):
            cmd.append("--" + field.replace("_", "-"))
    return cmd


def run_child(cmd, cwd=ROOT, timeout=None):
    return subprocess.run(cmd, cwd=cwd, timeout=timeout, check=False).returncode


def command_list(args):
    for project in projects():
        manifest = load_json(project / "PROJECT.json", {})
        state = read_state(project)
        print(f"{project_id(project)}\t{manifest.get('title', project.name)}\t"
              f"{state.get('phase', '?')} / {state.get('decision', '?')}")
    return 0


def command_doctor(args):
    selected = [resolve_project(args.project)] if args.project else projects()
    git = shutil.which("git")
    codex = shutil.which("codex")
    findings = {"python": {"path": sys.executable, "version": sys.version.split()[0],
                            "supported": sys.version_info >= (3, 10)},
                "git": git, "codex": codex, "controller": str(ROOT),
                "project_ids": [project_id(p) for p in selected],
                "pdf_parser": "PyMuPDF" if importlib.util.find_spec("pymupdf") or importlib.util.find_spec("fitz") else "optional: not installed",
                "offline": args.offline}
    if os.environ.get("CRYPTO_CONTROLLER_HOME"):
        findings["legacy_home"] = "旧 CRYPTO_CONTROLLER_HOME 不参与本框架的目录定位。"
    auth_failed = False
    if args.auth and not args.offline and codex:
        try:
            result = subprocess.run([codex, "login", "status"], capture_output=True,
                                    text=True, encoding="utf-8", errors="replace", timeout=15)
            findings["auth"] = {"exit_code": result.returncode,
                                "status": "LOGGED_IN" if result.returncode == 0 else "NOT_LOGGED_IN"}
            auth_failed = result.returncode != 0
        except (OSError, subprocess.TimeoutExpired) as exc:
            findings["auth"] = {"error": type(exc).__name__}
            auth_failed = True
    elif args.auth:
        findings["auth"] = "SKIPPED_OFFLINE" if args.offline else "CODEX_NOT_FOUND"
    if git:
        result = subprocess.run([git, "-C", str(ROOT), "rev-parse", "--show-toplevel"],
                                capture_output=True, text=True, timeout=10)
        findings["git_root"] = result.stdout.strip() if result.returncode == 0 else "NOT_INITIALIZED"
    print_json(findings)
    return 0 if findings["python"]["supported"] and git and (codex or args.offline) and not auth_failed else 2


def command_check(args):
    import runner_core
    selected = projects() if args.project == "all" else [resolve_project(args.project)]
    failed = False
    for project in selected:
        print("CHECK:", project_id(project), flush=True)
        try:
            runner_core.validate_project(project)
            settings_for(project)
            policy_for(ROOT, project)
            import supervision
            supervision.policy_for(ROOT, project)
            manifest = load_json(project / "PROJECT.json", {})
            checks = manifest.get("checks", [])
            if not isinstance(checks, list):
                raise ValueError("PROJECT.json checks 必须是数组。")
            project_failed = False
            for spec in checks:
                if isinstance(spec,dict) and spec.get('kind') == 'SYSTEM_TEST':
                    from theory_gate import require_system_ready
                    require_system_ready(project)
                argv = spec.get("argv") if isinstance(spec, dict) else spec
                if not isinstance(argv, list) or not argv or not all(isinstance(v, str) for v in argv):
                    raise ValueError("每个项目检查必须提供非空 argv 字符串数组。")
                # Project checks are Python scripts, always using the same interpreter.
                if argv[0] in {"python", "python3", "{python}", "{{PYTHON}}"}:
                    argv = argv[1:]
                if not argv or not argv[0].endswith(".py"):
                    raise ValueError("项目检查的首个参数必须是项目内 Python 脚本。")
                script = (project / argv[0]).resolve()
                script.relative_to(project)
                if not script.is_file():
                    raise ValueError(f"项目检查脚本不存在：{argv[0]}")
                timeout = spec.get("timeout_seconds", 120) if isinstance(spec, dict) else 120
                if type(timeout) is not int or not 1 <= timeout <= 600:
                    raise ValueError("项目检查 timeout_seconds 必须在 1 至 600 秒内。")
                if run_child([sys.executable, str(script), *argv[1:]], project, timeout):
                    failed = True
                    project_failed = True
            print("CHECK_FAILED:" if project_failed else "CHECK_OK:", project_id(project), flush=True)
        except (RuntimeError, ValueError, OSError, subprocess.TimeoutExpired) as exc:
            print("CHECK_FAILED:", project_id(project), str(exc), file=sys.stderr)
            failed = True
    return 2 if failed else 0


def command_status(args):
    import supervision
    selected = [resolve_project(args.project)] if args.project else projects()
    for project in selected:
        state = read_state(project)
        policy, origins, _ = policy_for(ROOT, project)
        ledger_path = ROOT / "state" / "routes" / (project_key(project) + ".json")
        ledger = load_json(ledger_path, {})
        epochs = ledger.get("epochs", [])
        latest = load_json(ROOT / "logs" / project_id(project) / "latest-status.json", {})
        print_json({"project": project_id(project), "state": state,
                    "stop_requested": (project / ".control" / "STOP_REQUESTED").exists(),
                    "route_policy": policy, "policy_sources": origins,
                    "route_epoch": epochs[-1] if epochs else None, "last_execution": latest,
                    "supervision": supervision.status(ROOT, project, ledger)})
    return 0


def command_run(args):
    project = resolve_project(args.project)
    if (project / ".control" / "STOP_REQUESTED").exists() and not args.dry_run:
        raise ValueError("项目已请求停止；执行 clear-stop 后再启动。")
    return run_child(runner_command(project, args))


def command_watch(args):
    project = resolve_project(args.project)
    execution = settings_for(project).get("execution", {})
    limit = None if args.forever else (args.max_rounds if args.max_rounds is not None else execution.get("max_rounds", 8))
    pause = args.pause_seconds if args.pause_seconds is not None else execution.get("pause_seconds", 10)
    if limit is not None and (type(limit) is not int or not 1 <= limit <= 500):
        raise ValueError("--max-rounds 必须在 1 至 500 之间；持续执行需显式使用 --forever。")
    if not isinstance(pause, (int, float)) or not 0 <= pause <= 60:
        raise ValueError("--pause-seconds 必须在 0 至 60 之间。")
    completed = 0
    while limit is None or completed < limit:
        if (project / ".control" / "STOP_REQUESTED").exists():
            print("WATCH_STOP: STOP_REQUESTED")
            return 0
        before = read_state(project)
        if before.get("decision") in STOP_DECISIONS or before.get("phase") == "DONE":
            print("WATCH_STOP:", before.get("decision"), before.get("phase"))
            return 0
        code = run_child(runner_command(project, args, rounds=1))
        if code:
            print("WATCH_STOP: execution_failed", code)
            return code
        after = read_state(project)
        if not after.get("last_run") or after.get("last_run") == before.get("last_run"):
            if (project / ".control" / "STOP_REQUESTED").exists():
                print("WATCH_STOP: STOP_REQUESTED")
                return 0
            if after.get("decision") in STOP_DECISIONS or after.get("phase") == "DONE":
                print("WATCH_STOP:", after.get("decision"), after.get("phase"))
                return 0
            print("WATCH_STOP: no_fresh_last_run")
            return 3
        completed += 1
        print("WATCH_COMPLETED:", completed, flush=True)
        if after.get("decision") in STOP_DECISIONS or after.get("phase") == "DONE":
            print("WATCH_STOP:", after.get("decision"), after.get("phase"))
            return 0
        if limit is None or completed < limit:
            # Short waits preserve immediate Ctrl+C and prompt stop handling.
            until = time.monotonic() + pause
            while time.monotonic() < until:
                if (project / ".control" / "STOP_REQUESTED").exists():
                    print("WATCH_STOP: STOP_REQUESTED")
                    return 0
                time.sleep(min(0.25, max(0, until - time.monotonic())))
    print("WATCH_STOP: invocation_budget_reached", completed)
    return 0


def command_stop(args):
    project = resolve_project(args.project)
    path = project / ".control" / "STOP_REQUESTED"
    # Stop is a cooperative signal and must remain usable while runner owns lock.
    if args.command == "stop":
        replace_text(path, now())
        print("STOP_REQUESTED:", project_id(project), "当前轮完成后停止。")
    else:
        with project_lock(project):
            path.unlink(missing_ok=True)
        print("STOP_CLEARED:", project_id(project))
    return 0


def override_path(project):
    return ROOT / "config" / "projects" / (project_id(project) + ".json")


def command_budget(args):
    project = resolve_project(args.project)
    updates = {"initial_round_budget": args.set, "stagnation_rounds": args.stagnation,
               "extension_round_budget": args.extension, "max_extensions": args.max_extensions}
    updates = {k: v for k, v in updates.items() if v is not None}
    if args.clear and updates:
        raise ValueError("--clear 与预算更新参数不能同时使用。")
    if args.clear or updates:
        with project_lock(project):
            path = override_path(project)
            obj = load_json(path, {})
            if args.clear:
                obj.pop("route_policy", None)
            else:
                obj["route_policy"] = validate_policy({**obj.get("route_policy", {}), **updates}, partial=True)
            settings_for(project)  # Validate existing configuration before replacing it.
            atomic_json(path, obj)
    policy, origins, _ = policy_for(ROOT, project)
    print_json({"project": project_id(project), "route_policy": policy, "sources": origins})
    return 0


def command_config(args):
    project = resolve_project(args.project)
    model_updates = {}
    for tier in ("routine", "critical"):
        names = ("model", "effort") if tier == "routine" else ("critical_model", "critical_effort")
        entry = {key: getattr(args, name) for key, name in zip(("model", "effort"), names)
                 if getattr(args, name) is not None}
        if entry:
            model_updates[tier] = entry
    updates = {"model_policy": model_updates} if model_updates else {}
    execution = {key: getattr(args, key) for key in ("max_seconds", "pause_seconds", "max_rounds", "web_search")
                 if getattr(args, key, None) is not None}
    if args.network is not None:
        execution["network_access"] = args.network == "on"
    if execution:
        updates["execution"] = execution
    literature = {}
    if args.pdf_download is not None:
        literature["automatic_pdf_download"] = args.pdf_download == "on"
    if args.pdf_limit is not None:
        literature["max_pdf_downloads_per_round"] = args.pdf_limit
    if args.pdf_max_mb is not None:
        literature["max_pdf_mb"] = args.pdf_max_mb
    if literature:
        updates["literature"] = literature
    if updates:
        with project_lock(project):
            path = override_path(project)
            obj = load_json(path, {})
            validate_settings(deep_merge(settings_for(project), updates))
            atomic_json(path, deep_merge(obj, updates))
    print_json({"project": project_id(project), "settings": settings_for(project)})
    return 0


def command_supervision(args):
    """Controller-only supervisor operations; preview/status never call a model."""
    import supervision
    action = args.supervision_command
    if args.project == "all" and action not in {"status", "history", "configure"}:
        raise ValueError("监督 run/show/rollback 必须指定一个项目；all 仅支持 status/history/configure。")
    selected = projects() if args.project == "all" or (action in {"status", "history"} and not args.project) else [resolve_project(args.project)]
    updates = {}
    if action == "configure":
        fields = ("interval", "max_reviews", "max_attempts_per_review", "max_seconds",
                  "max_total_seconds", "model", "effort")
        updates = {key: getattr(args, key) for key in fields if getattr(args, key) is not None}
        for field in ("model", "effort"):
            if updates.get(field) == "inherit":
                updates[field] = ""
        if args.enabled is not None:
            updates["enabled"] = args.enabled == "on"
    failed = False
    for project in selected:
        if action in {"history", "show"}:
            result = (supervision.history(ROOT, project) if action == "history"
                      else supervision.show_review(ROOT, project, args.id))
            print_json({"project": project_id(project), **result})
            continue
        if action == "status" or (action == "run" and args.dry_run):
            print_json({"project": project_id(project), **supervision.status(ROOT, project)})
            continue
        # maybe_supervise owns the core execution lock; operator writes take it here.
        with project_lock(project):
            if action == "run":
                import runner_core
                from route_budget import load_ledger, total_budget
                state = runner_core.validate_project(project)
                route_policy, _, _ = policy_for(ROOT, project)
                _, ledger, epoch = load_ledger(ROOT, project, state)
                budget_reason = "budget_exhausted" if epoch["effective_rounds"] >= total_budget(epoch, route_policy) else None
                result = supervision.maybe_supervise(ROOT, project, ledger,
                    budget_reason=budget_reason, force=args.force)
                failed = failed or not result.get("proceed", True)
            else:
                with file_lock(ROOT / "locks" / (project_key(project) + ".lock")):
                    if action == "configure":
                        result = supervision.configure(ROOT, project, updates)
                    else:
                        result = supervision.rollback(ROOT, project, args.id)
            print_json({"project": project_id(project), **result})
    return 2 if failed else 0


def command_fetch(args):
    return run_child(runner_command(resolve_project(args.project), args, mode="--fetch-only"))


def command_review(args):
    project = resolve_project(args.project)
    if args.prepare:
        return run_child(runner_command(project, args, mode="--prepare-pro"))
    args.audit = True
    args.rounds = 1
    return run_child(runner_command(project, args))


def idea_index(project):
    data = load_json(project / "ideas" / "INDEX.json", {"schema_version": 1, "ideas": [], "events": []})
    if not isinstance(data, dict) or not isinstance(data.get("ideas"), list):
        raise ValueError("ideas/INDEX.json 格式错误。")
    data.setdefault("events", [])
    return data


def text_input(args):
    content = Path(args.file).expanduser().read_text(encoding="utf-8-sig") if args.file else args.text
    if not isinstance(content, str) or not content.strip():
        raise ValueError("请用 --text 或 --file 提供非空研究想法。")
    return content.strip()


def get_idea(index, ident):
    if not IDEA_ID.fullmatch(ident or ""):
        raise ValueError("想法编号应为 IDEA-0001 形式。")
    item = next((i for i in index["ideas"] if i.get("id") == ident), None)
    if not item:
        raise ValueError(f"研究想法不存在：{ident}")
    return item


def idea_body(project, item):
    path = (project / item["revisions"][-1]["file"]).resolve()
    path.relative_to(project / "ideas")
    return path.read_text(encoding="utf-8-sig")


def command_ideas(args):
    project = resolve_project(args.project)
    if args.idea_command in {"list", "show"}:
        index = idea_index(project)
        if args.idea_command == "list":
            for item in index["ideas"]:
                print(f"{item['id']}\tv{item['version']}\t{item['title']}\t{item.get('route') or 'auto'}")
        else:
            item = get_idea(index, args.id)
            print_json({key: value for key, value in item.items() if key != "revisions"})
            print(idea_body(project, item))
        return 0
    with project_lock(project):
        index = idea_index(project)
        if args.idea_command == "add":
            content = text_input(args)
            next_num = max([int(item["id"].split("-")[1]) for item in index["ideas"]] or [0]) + 1
            item = {"id": f"IDEA-{next_num:04d}", "title": args.title.strip(), "version": 1,
                    "created": now(), "updated": now(), "route": args.route,
                    "revisions": []}
            if not item["title"]:
                raise ValueError("--title 不能为空。")
            if args.route and not ROUTE_ID.fullmatch(args.route):
                raise ValueError("研究路线编号包含无效字符。")
            index["ideas"].append(item)
            reason = "用户新增研究想法"
        else:
            item = get_idea(index, args.id)
            if args.idea_command in {"attach", "detach"}:
                state = read_state(project)
                pins = state.get("supporting_ideas", [])
                if not isinstance(pins, list): raise ValueError("supporting_ideas 必须是数组。")
                pins = [pin for pin in pins if pin.get("id") != item["id"]]
                if args.idea_command == "attach":
                    idea_body(project, item)  # Validate the pinned source file before writing state.
                    pins.append({"id": item["id"], "version": item["version"]})
                state["supporting_ideas"] = pins
                atomic_json(project / "research/STATE.json", state)
                index["events"].append({"type": args.idea_command.upper(), "id": item["id"],
                                        "version": item["version"], "at": now()})
                atomic_json(project / "ideas/INDEX.json", index)
                append_decision(project, "补充想法" if args.idea_command == "attach" else "移除补充想法",
                    f"用户{args.idea_command} {item['id']} 第 {item['version']} 版。当前路线、阶段和主任务保持原值。")
                print("IDEA_ATTACHED:" if args.idea_command == "attach" else "IDEA_DETACHED:", item["id"])
                return 0
            if args.idea_command == "select":
                content = idea_body(project, item)
                route = args.route or item.get("route") or f"IDEA/{item['id']}/v{item['version']}"
                if not ROUTE_ID.fullmatch(route):
                    raise ValueError("研究路线编号包含无效字符。")
                state = read_state(project)
                before_route = state.get("research_route")
                state.update({"research_route": route, "phase": "FALSIFICATION", "decision": "CONTINUE",
                              "priority_problem": item["title"],
                              "next_task": f"研究已选想法 {item['id']} 第 {item['version']} 版：{item['title']}。\n"
                                           f"先核查最相近成果和反例，再给出一个可独立检验的最小命题；保持 GOAL.md 的目标和约束。\n{content}",
                              "selected_idea": {"id": item["id"], "version": item["version"]}})
                atomic_json(project / "research" / "STATE.json", state)
                event = {"type": "SELECT", "id": item["id"], "version": item["version"],
                         "from_route": before_route, "route": route, "at": now()}
                index["events"].append(event)
                index["active_idea"] = {"id": item["id"], "version": item["version"]}
                atomic_json(project / "ideas" / "INDEX.json", index)
                append_decision(project, f"选择研究想法 {item['id']}",
                                f"用户通过统一接口选择第 {item['version']} 版：{item['title']}。\n"
                                f"路线：{route}。目标约束保留。后续需单独调用 run 或 watch 执行。")
                print("IDEA_SELECTED:", item["id"], "ROUTE:", route)
                return 0
            content = text_input(args)
            reason = args.reason.strip()
            if not reason:
                raise ValueError("更新想法必须提供非空 --reason。")
            item["version"] += 1
            item["updated"] = now()
            if args.title:
                item["title"] = args.title.strip()
        rel = Path("ideas") / item["id"] / f"v{item['version']:03d}.md"
        path = project / rel
        if path.exists():
            raise ValueError("想法版本文件已存在；拒绝覆盖。")
        replace_text(path, content)
        item["revisions"].append({"version": item["version"], "file": rel.as_posix(),
                                  "reason": reason, "at": now(),
                                  "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
        index["events"].append({"type": args.idea_command.upper(), "id": item["id"],
                                "version": item["version"], "reason": reason, "at": now()})
        atomic_json(project / "ideas" / "INDEX.json", index)
        print("IDEA_SAVED:", item["id"], "VERSION:", item["version"], "未自动启动研究。")
    return 0


def command_paper(args):
    project = resolve_project(args.project)
    source = Path(args.file).expanduser().resolve()
    if not source.is_file() or source.suffix.lower() != ".pdf":
        raise ValueError("paper ingest 需要现有 PDF 文件。")
    with source.open("rb") as handle:
        if b"%PDF-" not in handle.read(1024):
            raise ValueError("文件缺少 PDF 文件头。")
    if args.url and urlparse(args.url).scheme not in {"http", "https"}:
        raise ValueError("--url 需要 HTTP 或 HTTPS 原文地址。")
    digest = sha256_file(source)
    with project_lock(project):
        registry = load_json(project / "literature" / "uploads.json", {"schema_version": 1, "files": []})
        existing = next((x for x in registry["files"] if x["sha256"] == digest), None)
        if existing:
            print("PAPER_ALREADY_IMPORTED:", existing["file"])
            return 0
        destination = project / "literature" / "pdfs" / source.name
        if destination.exists() and destination.resolve() != source:
            destination = destination.with_name(destination.stem + "-" + digest[:12] + ".pdf")
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.resolve() != source:
            shutil.copy2(source, destination)
        record = {"file": destination.relative_to(project).as_posix(), "original_name": source.name,
                  "sha256": digest, "size_bytes": source.stat().st_size, "imported_at": now(),
                  "source_url": args.url, "title": args.title or source.stem}
        registry["files"].append(record)
        atomic_json(project / "literature" / "uploads.json", registry)
        print_json(record)
    return 0


def sha256_file(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def command_new(args):
    if not PROJECT_ID.fullmatch(args.id):
        raise ValueError("项目名包含小写字母、数字、下划线和连字符，以字母或数字开头，最多 64 个字符。")
    destination = ROOT / "projects" / args.id
    if destination.exists():
        raise ValueError(f"项目已存在：{args.id}")
    if not args.goal_file and not args.idea_file:
        raise ValueError('请提供 --goal-file 或 --idea-file；也可以同时提供。')
    source = args.goal_file or args.idea_file
    goal = Path(source).expanduser().read_text(encoding="utf-8-sig").strip()
    idea = Path(args.idea_file).expanduser().read_text(encoding='utf-8-sig').strip() if args.idea_file else None
    if args.idea_file and not idea: raise ValueError('想法文件不能为空。')
    if not goal:
        raise ValueError("目标文件不能为空。")
    template = ROOT / "templates" / "project"
    if not (template / "PROJECT.json").is_file():
        raise ValueError("缺少 templates/project 项目模板。")
    title = args.title or args.id
    substitutions = {"{{PROJECT_ID}}": args.id, "{{PROJECT_TITLE}}": title,
                     "{{PROFILE}}": args.profile, "{{GOAL}}": goal}
    def substitute(value):
        if isinstance(value, str):
            for key, replacement in substitutions.items():
                value = value.replace(key, replacement)
            return value
        if isinstance(value, list):
            return [substitute(v) for v in value]
        if isinstance(value, dict):
            return {k: substitute(v) for k, v in value.items()}
        return value
    with file_lock(ROOT / "locks" / "project-registry.lock"):
        if destination.exists():
            raise ValueError(f"项目已存在：{args.id}")
        try:
            shutil.copytree(template, destination, ignore=shutil.ignore_patterns("__pycache__", ".git", "*.pyc"))
            for file in destination.rglob("*"):
                if file.is_file() and file.suffix in {".json", ".md", ".txt", ".py", ".cmd", ".ps1"}:
                    if file.suffix == ".json":
                        atomic_json(file, substitute(load_json(file, {})))
                    else:
                        replace_text(file, substitute(file.read_text(encoding="utf-8-sig")))
            replace_text(destination / "GOAL.md", f"# {title}\n\n{goal}\n")
            manifest = load_json(destination / "PROJECT.json", {})
            manifest.update({"id": args.id, "title": title,
                             "profiles": [args.profile]})
            atomic_json(destination / "PROJECT.json", manifest)
            profile = load_json(destination / "RESEARCH_PROFILE.json", {})
            profile["profiles"] = [args.profile]
            atomic_json(destination / "RESEARCH_PROFILE.json", profile)
            state = read_state(destination)
            state.update({"phase": "INTAKE", "decision": "PAUSE", "last_run": None,
                          'initialization_required': True, 'initialization_status': 'NOT_RUN',
                          "priority_problem": f"明确 {title} 的最小研究命题和最相近基线。",
                          "next_task": "阅读 GOAL.md 及上传材料，固定研究对象、威胁模型、不可放宽条件、最相近基线和一个可证伪的核心命题。"})
            if idea:
                rel = 'ideas/IDEA-0001/v001.md'; replace_text(destination / rel, idea)
                pin = {'id': 'IDEA-0001', 'version': 1}
                item = {'id': pin['id'], 'title': title, 'version': 1, 'route': 'INITIAL/INTAKE',
                    'created': now(), 'updated': now(), 'revisions': [{'version': 1, 'file': rel,
                    'reason': '新建时导入原始研究想法', 'at': now(),
                    'sha256': hashlib.sha256((destination / rel).read_bytes()).hexdigest()}]}
                atomic_json(destination / 'ideas/INDEX.json', {'schema_version': 1, 'ideas': [item],
                    'active_idea': pin, 'events': [{'type': 'INITIAL_IDEA', **pin, 'at': now()}]})
                state['selected_idea'] = pin
            atomic_json(destination / "research" / "STATE.json", state)
        except Exception:
            shutil.rmtree(destination, ignore_errors=True)
            raise
    print("PROJECT_CREATED:", args.id)
    print('原始目标/想法已保存。运行 research.cmd initialize ' + args.id + '，按 idea 生成初始化研究文档；也可先 prompt --initialize 预览。')
    return 0


def command_initialize(args):
    import runner_core
    from engine.discovery_scheduler import active
    project = resolve_project(args.project)
    if active(project): raise ValueError('请先关闭当前研究尝试，再重新初始化研究文档。')
    state = runner_core.validate_project(project)
    if (project / 'research/INITIALIZATION.json').exists() and not args.refresh:
        raise ValueError('初始化记录已存在；明确使用 --refresh 更新派生文档。原始材料保持原样。')
    state.update(phase='INTAKE', decision='CONTINUE', initialization_required=True,
                 initialization_status='NOT_RUN',
                 next_task='依据已固定的用户想法与原始材料，执行 initialize_from_idea.md，补齐派生文档并明确所有未确认事项。')
    if args.dry_run:
        tier, model, effort = runner_core.plan_route(project, state, model=args.model, effort=args.effort)
        print('INITIALIZATION_PREVIEW:', model, effort)
        print(runner_core.build_prompt(project, state, 'PREVIEW_ONLY', tier))
        return 0
    if (project / '.control/STOP_REQUESTED').exists(): raise ValueError('先 clear-stop，再执行 initialize。')
    with project_lock(project): atomic_json(project / 'research/STATE.json', state)
    args.rounds = 1
    return run_child(runner_command(project, args))


def command_ready(args):
    project = resolve_project(args.project)
    import runner_core
    with project_lock(project):
        state = runner_core.validate_project(project)
        queries = load_json(project / "literature" / "queries.json", {})
        groups = queries.get("groups", queries.get("queries", [])) if isinstance(queries, dict) else queries
        if not groups:
            raise ValueError("请先填写 literature/queries.json 的检索组。")
        if args.phase:
            from theory_gate import SYSTEM_PHASES, require_system_ready
            if args.phase in SYSTEM_PHASES: require_system_ready(project)
            state['phase']=args.phase
        if args.task:
            if len(args.task.strip()) < 12:
                raise ValueError("--task 请提供明确研究任务，至少 12 个字符。")
            state["next_task"] = args.task.strip()
        state.update({"decision": "CONTINUE", "phase": state.get("phase")})
        atomic_json(project / "research" / "STATE.json", state)
        append_decision(project, "用户启用项目", "用户通过 ready 启用现有目标和下一轮任务，尚未执行模型调用。")
    print("PROJECT_READY:", project_id(project))
    return 0


def command_refocus(args):
    """Operator-directed recovery; retain scientific history and consumed budget."""
    import runner_core
    from engine.discovery_scheduler import active
    from research_focus import make_focus
    from route_budget import load_ledger, save_ledger, total_budget
    project = resolve_project(args.project)
    if len(args.task.strip()) < 24 or len(args.reason.strip()) < 12:
        raise ValueError('refocus 需要具体任务（至少 24 字符）及恢复原因（至少 12 字符）。')
    if args.problem is not None and len(args.problem.strip()) < 12:
        raise ValueError('--problem 需明确核心问题，至少 12 个字符。')
    if not 0 <= args.extra_rounds <= 100:
        raise ValueError('--extra-rounds 必须在 0 至 100 之间。')
    with project_lock(project):
        if active(project):
            raise ValueError('存在固定命题的研究尝试；先通过 attempt close 保留检查点并关闭该尝试。')
        state = runner_core.validate_project(project)
        if state.get('initialization_required'):
            raise ValueError('请先完成项目初始化，再固定主线研究任务。')
        policy, _, _ = policy_for(ROOT, project)
        path, ledger, epoch = load_ledger(ROOT, project, state)
        if epoch['last_processed_run'] != state.get('last_run'):
            raise ValueError('last_run 与预算账本不一致；先审查并显式 route-sync。')
        budget = total_budget(epoch, policy) + args.extra_rounds
        if budget <= epoch['effective_rounds']:
            raise ValueError('没有剩余研究预算；用 --extra-rounds 明确追加，已用轮次保持不变。')
        previous = copy.deepcopy(state)
        old_focus = copy.deepcopy(epoch['focus'])
        problem = args.problem.strip() if args.problem else old_focus['core_problem']
        state.update(phase=args.phase, decision='CONTINUE', priority_problem=problem,
                     next_task=args.task.strip())
        epoch.update(focus=make_focus(project, state, problem), review_pending=False,
                     review_reason=None, support_rounds=0, stagnation=0)
        epoch['operator_added_rounds'] = epoch.get('operator_added_rounds', 0) + args.extra_rounds
        ledger['events'].append({'type': 'OPERATOR_REFOCUS', 'at': now(),
            'reason': args.reason.strip(), 'previous_focus': old_focus, 'focus': epoch['focus'],
            'previous_decision': previous['decision'], 'previous_task': previous['next_task'],
            'next_task': state['next_task'], 'extra_rounds': args.extra_rounds,
            'effective_rounds': epoch['effective_rounds'], 'budget': budget})
        transaction = runner_core.ProjectTransaction(project).capture()
        path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='refocus-', dir=path.parent) as temp:
            backup = Path(temp) / 'ledger.json'
            if path.is_file():
                shutil.copy2(path, backup)
            try:
                atomic_json(project / 'research/STATE.json', state)
                append_decision(project, '用户将任务重新聚焦核心问题',
                    args.reason.strip() + '\n\n核心问题：' + problem + '\n\n下一任务：' + state['next_task']
                    + f'\n\n追加研究轮数：{args.extra_rounds}；已用轮数：{epoch["effective_rounds"]}。')
                save_ledger(path, ledger)
                transaction.accept()
            except BaseException:
                transaction.rollback('OPERATOR_REFOCUS_FAILED')
                if backup.is_file():
                    os.replace(backup, path)
                else:
                    path.unlink(missing_ok=True)
                raise
    print('PROJECT_REFOCUSED:', project_id(project))
    print('ROUTE_USED:', epoch['effective_rounds'], 'BUDGET:', budget)
    print('No model call made; proof/review statuses and existing evidence were preserved.')
    if (project / '.control/STOP_REQUESTED').exists():
        print('STOP_REQUESTED remains set; use clear-stop explicitly before running.')
    return 0


def command_theory(args):
    from theory_gate import check_readiness, APPROVAL_PATH
    from research_quality import scientific_files, hash_file
    project=resolve_project(args.project)
    if args.theory_command == 'status':
        try:
            approval=check_readiness(project)
            print_json({'theory_ready':True,'claim_id':approval['claim_id'],'reviewer':approval['reviewer']})
        except (OSError,ValueError,KeyError) as exc:
            print_json({'theory_ready':False,'reason':str(exc),'next_action':'完成贡献、原文比较和正确性审查后，由用户执行 theory approve。'})
        return 0
    with project_lock(project):
        if args.theory_command == 'revoke':
            record=load_json(project/APPROVAL_PATH,{})
            record.update({'schema_version':1,'decision':'REVOKED','revoked_at':now(),'revoke_reason':args.reason})
            atomic_json(project/APPROVAL_PATH,record)
            append_decision(project,'撤回系统实现许可',args.reason)
            return 0
        paths={'contribution':args.contribution,'correctness':args.correctness,'novelty':args.novelty}
        if args.security: paths['security']=args.security
        files=scientific_files(project,list(paths.values()))
        by_path={rel:path for rel,path in files}
        if APPROVAL_PATH in by_path: raise ValueError('不能用许可文件证明自身。')
        state=read_state(project)
        from engine.claim_graph import require_theory_claim
        discovery_claim = require_theory_claim(project, args.claim)
        record={'schema_version':1,'decision':'APPROVED','claim_id':args.claim,
            'reviewer':args.reviewer,'reason':args.reason,'approved_at':now(),
            'goal_sha256':hash_file(project/'GOAL.md'),'research_route':state.get('research_route'),
            'idea_pins':{'selected_idea':state.get('selected_idea'),'supporting_ideas':state.get('supporting_ideas',[])},
            'inputs':{p.relative_to(project).as_posix():hash_file(p) for p in (project/'inputs').rglob('*') if p.is_file()},
            'constraint_files':{name:hash_file(project/name) for name in ('AGENTS.md','RESEARCH_PROFILE.json','research/THREAT_MODEL.md','research/SECURITY_MODEL.md','research/SECURITY_DEFINITIONS.md') if (project/name).is_file()},
            'evidence':{key:{'file':rel,'sha256':hash_file(by_path[rel])} for key,rel in paths.items()},
            'remaining_critical_obligations':[],
            'scope':'SYSTEM_IMPLEMENTATION_AND_TEST_FOR_APPROVED_CLAIM_ONLY'}
        if discovery_claim:
            record['discovery_claim_sha256'] = discovery_claim['spec_sha256']
        atomic_json(project/APPROVAL_PATH,record)
        check_readiness(project)
        append_decision(project,'用户确认理论审查完成',f"主张 {args.claim}；审查者 {args.reviewer}。{args.reason}。许可绑定证据摘要；当前阶段不自动变化。")
        print('THEORY_APPROVED:',args.claim,'；需要系统开发时再使用 ready --phase IMPLEMENTATION 或 SYSTEM_TEST。')
    return 0


def command_prompt(args):
    import runner_core
    from route_budget import load_ledger, selected_route, needs_review, generate_directive
    project = resolve_project(args.project)
    state = runner_core.validate_project(project)
    policy, _, _ = policy_for(ROOT, project)
    _, _, epoch = load_ledger(ROOT, project, state)
    reason = needs_review(epoch, policy)
    route_review = bool(reason)
    audit = args.audit and not route_review
    state = copy.deepcopy(state)
    if args.initialize:
        state.update(phase='INTAKE', initialization_required=True)
    state['next_task'] = generate_directive(selected_route(state), epoch, policy, bool(reason), reason, state['next_task'])
    tier, _, _ = runner_core.plan_route(project, state, audit=audit or route_review)
    content = runner_core.build_prompt(project, state, 'PREVIEW_ONLY', tier,
                                      audit=audit, route_review=route_review)
    if args.output:
        destination = Path(args.output).expanduser().resolve()
        if destination.exists(): raise ValueError('提示词输出文件已存在，请使用新文件名。')
        replace_text(destination, content)
        print('PROMPT_SAVED:', destination)
    else:
        print(content)
    return 0


def add_project(parser, *, optional=True):
    parser.add_argument("project", nargs="?" if optional else None, help="项目 ID；在项目目录中可省略")


def common_run_options(parser, *, run=True):
    if run:
        parser.add_argument("--rounds", type=int, default=1)
    parser.add_argument("--model")
    parser.add_argument("--effort", choices=EFFORTS)
    parser.add_argument("--max-seconds", type=int)
    parser.add_argument("--no-fetch", action="store_true")
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--route-budget", type=int)
    parser.add_argument("--stagnation-rounds", type=int)
    parser.add_argument("--extension-round-budget", type=int)
    parser.add_argument("--max-extensions", type=int)


def parser():
    p = argparse.ArgumentParser(description="统一密码学自动研究框架：在根目录指定项目，在项目目录省略项目名。")
    version = (Path(__file__).resolve().parent / "VERSION").read_text(encoding="utf-8-sig").strip()
    p.add_argument("--version", action="version", version="CryptoResearchController " + version)
    sub = p.add_subparsers(dest="command", required=True)
    def command(name, function, help_text):
        c = sub.add_parser(name, help=help_text)
        c.set_defaults(function=function)
        return c
    command("list", command_list, "列出研究项目")
    c = command("doctor", command_doctor, "检查 Python、Git、Codex 环境")
    add_project(c); c.add_argument("--offline", action="store_true"); c.add_argument("--auth", action="store_true")
    c = command("check", command_check, "本地检查项目结构与证据；不调用模型")
    add_project(c)
    c = command("status", command_status, "只读查看状态、预算和最近执行")
    add_project(c)
    c = command("run", command_run, "执行有限轮研究")
    add_project(c); common_run_options(c)
    c.add_argument("--dry-run", action="store_true"); c.add_argument("--audit", action="store_true")
    c.add_argument("--route-sync", action="store_true", help="审查外部状态修改后，显式接纳 last_run 漂移")
    c = command("watch", command_watch, "自动连续研究，默认最多 8 轮")
    add_project(c); common_run_options(c, run=False)
    limit = c.add_mutually_exclusive_group(); limit.add_argument("--max-rounds", type=int); limit.add_argument("--forever", action="store_true")
    c.add_argument("--pause-seconds", type=float)
    for name in ("stop", "clear-stop"):
        add_project(command(name, command_stop, "请求轮间停止" if name == "stop" else "清除停止请求"))
    c = command("budget", command_budget, "查看或保存项目路线预算")
    add_project(c); c.add_argument("--set", type=int); c.add_argument("--stagnation", type=int)
    c.add_argument("--extension", type=int); c.add_argument("--max-extensions", type=int); c.add_argument("--clear", action="store_true")
    c = command("config", command_config, "查看或保存项目模型参数")
    add_project(c)
    for name in ("model", "critical-model"):
        c.add_argument("--" + name)
    for name in ("effort", "critical-effort"):
        c.add_argument("--" + name, choices=EFFORTS)
    c.add_argument("--max-seconds", type=int); c.add_argument("--pause-seconds", type=int)
    c.add_argument("--max-rounds", type=int)
    c.add_argument("--network", choices=("on", "off"))
    c.add_argument("--web-search", choices=("live", "cached", "disabled"))
    c.add_argument("--pdf-download", choices=("on", "off"))
    c.add_argument("--pdf-limit", type=int); c.add_argument("--pdf-max-mb", type=int)
    c = command("supervision", command_supervision, "配置、查看、执行或回滚独立科研监督")
    supervision_sub = c.add_subparsers(dest="supervision_command", required=True)
    for action in ("status", "history", "show", "configure", "run", "rollback"):
        supervisor = supervision_sub.add_parser(action)
        add_project(supervisor)
        if action == "configure":
            supervisor.add_argument("--enabled", choices=("on", "off"))
            for field in ("interval", "max-reviews", "max-attempts-per-review", "max-seconds", "max-total-seconds"):
                supervisor.add_argument("--" + field, type=int)
            supervisor.add_argument("--model", help="独立监督模型；inherit 沿用 critical 模型")
            supervisor.add_argument("--effort", choices=("inherit", *EFFORTS))
        elif action == "run":
            supervisor.add_argument("--dry-run", action="store_true", help="只读显示状态，不执行监督模型")
            supervisor.add_argument("--force", action="store_true", help="显式触发当前快照监督，仍遵守独立预算和幂等约束")
        elif action == "rollback":
            supervisor.add_argument("--id", required=True, help="最新已应用监督记录的 review_id")
        elif action == "show":
            supervisor.add_argument("--id", help="监督记录的 review_id；默认查看最近记录")
    c = command("fetch", command_fetch, "更新文献与本地 PDF 提取")
    add_project(c); c.add_argument("--offline", action="store_true")
    c = command("review", command_review, "独立审查；--prepare 生成审查材料")
    add_project(c); common_run_options(c, run=False); c.add_argument("--prepare", action="store_true")
    c = command("ideas", command_ideas, "保存、更新、查看和选择研究想法")
    idea_sub = c.add_subparsers(dest="idea_command", required=True)
    for name in ("list", "show", "add", "update", "select", "attach", "detach"):
        i = idea_sub.add_parser(name); add_project(i)
        if name in {"show", "update", "select", "attach", "detach"}:
            i.add_argument("--id", required=True)
        if name in {"add", "update"}:
            i.add_argument("--title", required=name == "add")
            source = i.add_mutually_exclusive_group(required=True)
            source.add_argument("--text"); source.add_argument("--file")
        if name == "update":
            i.add_argument("--reason", required=True)
        if name in {"add", "select"}:
            i.add_argument("--route")
    c = command("paper", command_paper, "导入论文 PDF 并记录来源与摘要")
    paper_sub = c.add_subparsers(dest="paper_command", required=True)
    i = paper_sub.add_parser("ingest"); add_project(i)
    i.add_argument("--file", required=True); i.add_argument("--url"); i.add_argument("--title")
    c = command("new", command_new, "从固定模板创建新研究项目")
    c.add_argument("id"); c.add_argument("--goal-file"); c.add_argument('--idea-file'); c.add_argument("--title")
    c.add_argument("--profile", choices=("generic", "mpc_secagg", "ntru_lattice"), default="generic")
    c = command('initialize', command_initialize, '按 idea 补齐初始化研究文档；--dry-run 只预览')
    add_project(c); common_run_options(c, run=False); c.add_argument('--dry-run', action='store_true'); c.add_argument('--refresh', action='store_true')
    c = command("theory", command_theory, "理论审查状态和用户批准的系统实现门禁")
    gate_sub=c.add_subparsers(dest='theory_command',required=True)
    for action in ('status','approve','revoke'):
        gate=gate_sub.add_parser(action);add_project(gate)
        if action == 'approve':
            for field in ('claim','contribution','correctness','novelty','reviewer','reason'):
                gate.add_argument('--'+field,required=True)
            gate.add_argument('--security')
        elif action == 'revoke':gate.add_argument('--reason',required=True)
    c = command("prompt", command_prompt, "预览最终提示词，不调用模型、不修改研究状态")
    add_project(c); c.add_argument("--audit", action="store_true"); c.add_argument("--output"); c.add_argument('--initialize', action='store_true')
    c = command("ready", command_ready, "填写材料后显式启用项目")
    add_project(c); c.add_argument("--task", help="启用时明确下一轮任务"); c.add_argument("--phase", choices=("LITERATURE","NOVELTY","FALSIFICATION","CONSTRUCTION","CORRECTNESS","PROOF","SECURITY","COST","IMPLEMENTATION","SYSTEM_TEST","EXPERIMENT","WRITING","REVIEW"))
    c = command('refocus', command_refocus, '显式恢复核心任务，保留证据、审查状态与已用预算')
    add_project(c)
    c.add_argument('--problem', help='核心研究问题；默认沿用控制器已固定的主线')
    c.add_argument('--task', required=True)
    c.add_argument('--reason', required=True)
    c.add_argument('--extra-rounds', type=int, default=0, help='显式追加轮数，不清零已用预算')
    c.add_argument('--phase', default='FALSIFICATION',
                   choices=('FALSIFICATION', 'CONSTRUCTION', 'CORRECTNESS', 'SECURITY', 'COST', 'PROOF', 'NOVELTY', 'LITERATURE'))
    from engine.cli import add_commands
    add_commands(sub, add_project, common_run_options)
    return p


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        return args.function(args)
    except KeyboardInterrupt:
        print("INTERRUPTED: 可在另一个窗口使用 stop 请求当前轮完成后停止。", file=sys.stderr)
        return 130
    except (RuntimeError, ValueError, OSError, KeyError, subprocess.TimeoutExpired) as exc:
        print("ERROR:", str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
