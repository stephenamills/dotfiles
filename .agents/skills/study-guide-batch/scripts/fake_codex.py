#!/usr/bin/env python3
"""Deterministic fake Codex executable for supervisor acceptance tests."""

from __future__ import annotations

import fcntl
import csv
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path


MARKER = "<!-- STUDY-GUIDE-COMPLETE -->"


def state_call(stage: str, *, row: dict[str, str] | None = None) -> tuple[int, int]:
    path = Path(os.environ.get("FAKE_CODEX_STATE", "/tmp/fake-codex-state.json"))
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        handle.seek(0)
        try:
            state = json.load(handle)
        except (json.JSONDecodeError, ValueError):
            state = {"total": 0, "stages": {}, "workers_total": 0}
        stages = state.setdefault("stages", {})
        if row is None:
            state["total"] = int(state.get("total", 0)) + 1
            state.setdefault("calls", []).append(
                {
                    "stage": stage,
                    "argv": sys.argv[1:],
                    "cwd": str(Path.cwd()),
                    "inherited_markers": sorted(
                        key
                        for key in (
                            "CODEX_THREAD_ID",
                            "CODEX_CI",
                            "CODEX_SANDBOX",
                            "CODEX_SANDBOX_NETWORK_DISABLED",
                            "CODEX_APPROVAL_POLICY",
                            "CODEX_PERMISSION_PROFILE",
                            "CI",
                        )
                        if key in os.environ
                    ),
                }
            )
        else:
            state["workers_total"] = int(state.get("workers_total", 0)) + 1
            stages[stage] = int(stages.get(stage, 0)) + 1
            state.setdefault("worker_calls", []).append(dict(row))
        handle.seek(0)
        handle.truncate()
        json.dump(state, handle)
        handle.flush()
        os.fsync(handle.fileno())
        sequence = state.get("workers_total", 0) if row is not None else state.get("total", 0)
        return int(sequence), int(stages.get(stage, 0))


def argument_value(name: str) -> str | None:
    try:
        return sys.argv[sys.argv.index(name) + 1]
    except (ValueError, IndexError):
        return None


def emit(event: dict[str, object]) -> None:
    print(json.dumps(event), flush=True)


def complete() -> None:
    tokens = int(os.environ.get("FAKE_CODEX_TOKENS", "30"))
    emit(
        {
            "type": "turn.completed",
            "usage": {
                "input_tokens": max(1, tokens // 3),
                "cached_input_tokens": 2,
                "output_tokens": max(1, tokens - max(1, tokens // 3)),
                "total_tokens": tokens,
            },
        }
    )


def candidate() -> str:
    words = " ".join(
        f"concept{index} is explained accurately and clearly"
        for index in range(1, 90)
    )
    return (
        "# Lesson Study Guide\n\n"
        "## Overview\n\n"
        f"{words}.\n\n"
        "## Key Concepts\n\n"
        f"{words}.\n\n"
        "```d2\n"
        "material: Course material\n"
        "concepts: Key concepts\n"
        "practice: Guided practice\n"
        "mastery: Demonstrated mastery\n"
        "material -> concepts -> practice -> mastery\n"
        "```\n\n"
        "## Review Questions\n\n"
        "1. What is the central concept? Use the direct explanation above.\n\n"
        f"{MARKER}\n"
    )


def invalid_d2_candidate() -> str:
    return (
        "# Lesson Study Guide\n\n"
        "## Overview\n\nA complete-looking candidate with invalid diagram syntax.\n\n"
        "```d2\n"
        "concept: {\n"
        "  shape: Not a real D2 shape\n"
        "}\n"
        "```\n\n"
        f"{MARKER}\n"
    )


def invalid_layout_candidate() -> str:
    return (
        "# Lesson Study Guide\n\n## Overview\n\nA complete candidate with a tall diagram.\n\n"
        "```d2\n"
        "a: \"Stage A\"\nb: \"Stage B\"\nc: \"Stage C\"\nd: \"Stage D\"\n"
        "e: \"Stage E\"\nf: \"Stage F\"\ng: \"Stage G\"\nh: \"Stage H\"\n"
        "a -> b -> c -> d -> e -> f -> g -> h\n"
        "```\n\n"
        f"{MARKER}\n"
    )


def too_wide_d2() -> str:
    return (
        "direction: right\n"
        "a: \"Stage A\"\nb: \"Stage B\"\nc: \"Stage C\"\nd: \"Stage D\"\n"
        "e: \"Stage E\"\nf: \"Stage F\"\ng: \"Stage G\"\nh: \"Stage H\"\n"
        "a -> b -> c -> d -> e -> f -> g -> h\n"
    )


def repaired_d2() -> str:
    return (
        "concept: Repaired concept\n"
        "practice: Guided practice\n"
        "mastery: Demonstrated mastery\n"
        "concept -> practice -> mastery\n"
    )


def targeted_repair(prompt: str) -> str:
    parts: list[str] = []
    for kind, key in re.findall(r"<<<STUDY-GUIDE-(D2|SECTION):(.+?)>>>", prompt):
        parts.append(f"<<<STUDY-GUIDE-{kind}:{key}>>>")
        if kind == "D2":
            parts.extend(
                [
                    "direction: right",
                    "concept: \"Core concept\"",
                    "practice: \"Guided practice\"",
                    "mastery: \"Demonstrated mastery\"",
                    "concept -> practice -> mastery",
                ]
            )
        else:
            parts.extend(
                [
                    f"## {key}",
                    "",
                    "The targeted section was regenerated without changing the rest of the guide.",
                ]
            )
        parts.append(f"<<<END-STUDY-GUIDE-{kind}:{key}>>>")
    return "\n".join(parts) + "\n"


def prompt_path(dispatcher_prompt: str, label: str) -> Path:
    match = re.search(rf"(?m)^- {re.escape(label)}: (.+)$", dispatcher_prompt)
    if not match:
        raise RuntimeError(f"dispatcher prompt lacks {label}")
    return Path(match.group(1).strip())


def main() -> int:
    if "--version" in sys.argv and "exec" not in sys.argv:
        print(os.environ.get("FAKE_CODEX_VERSION", "codex-cli fake-1.0"))
        return 0
    dispatcher_prompt = sys.stdin.read()
    total, _ = state_call("dispatcher")
    scenario = os.environ.get("FAKE_CODEX_SCENARIO", "success")
    emit({"type": "thread.started", "thread_id": f"fake-dispatcher-{total}"})
    emit(
        {
            "type": "item.started",
            "item": {"type": "mcp_tool_call", "name": "spawn_agents_on_csv"},
        }
    )
    delay = float(os.environ.get("FAKE_CODEX_DELAY", "0"))
    if delay:
        time.sleep(delay)

    if scenario == "auth":
        print("Authentication failed: not logged in", file=sys.stderr, flush=True)
        emit({"type": "turn.failed", "error": "authentication failed"})
        return 1
    if scenario == "quota_json_only":
        message = "You've hit your usage limit. Try again later."
        emit({"type": "error", "message": message})
        emit({"type": "turn.failed", "error": {"message": message}})
        return 1
    if scenario == "environment":
        print(
            "Error: failed to initialize in-process app-server client: Operation not permitted",
            file=sys.stderr,
            flush=True,
        )
        emit({"type": "turn.failed", "error": "operation not permitted"})
        return 1
    if scenario == "capability_unavailable":
        message = "spawn_agents_on_csv tool unavailable: unknown tool"
        print(message, file=sys.stderr, flush=True)
        emit({"type": "turn.failed", "error": message})
        return 1
    if scenario == "malformed_jsonl" and total == 1:
        print("{not-json", flush=True)
        time.sleep(0.2)
        return 0
    if scenario == "timeout":
        heartbeat = os.environ.get("FAKE_CODEX_DESCENDANT_HEARTBEAT")
        if heartbeat:
            code = (
                "import pathlib,sys,time\n"
                "path=pathlib.Path(sys.argv[1])\n"
                "while True:\n"
                " path.write_text(str(time.time()), encoding='utf-8')\n"
                " time.sleep(0.05)\n"
            )
            child = subprocess.Popen([sys.executable, "-c", code, heartbeat])
        else:
            child = subprocess.Popen(["sleep", "60"])
        pid_path = os.environ.get("FAKE_CODEX_DESCENDANT_PID")
        if pid_path:
            Path(pid_path).write_text(str(child.pid), encoding="utf-8")
        time.sleep(60)
        return 0
    if scenario == "mcp":
        emit({"type": "item.started", "item": {"type": "mcp_tool_call", "name": "forbidden"}})
        time.sleep(0.2)
        return 0
    if scenario == "web":
        emit({"type": "item.started", "item": {"type": "web_search", "query": "forbidden"}})
        time.sleep(0.2)
        return 0

    csv_path = prompt_path(dispatcher_prompt, "csv_path")
    output_csv_path = prompt_path(dispatcher_prompt, "output_csv_path")
    with csv_path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = list(reader.fieldnames or [])
        input_rows = list(reader)
    state_path = Path(os.environ["FAKE_CODEX_STATE"])
    with state_path.open("r", encoding="utf-8") as handle:
        state = json.load(handle)
    state.setdefault("waves", []).append(
        {
            "size": len(input_rows),
            "unit_ids": [row["unit_id"] for row in input_rows],
            "multi_agent_enabled": "features.multi_agent=true" in sys.argv,
            "fanout_enabled": "features.enable_fanout=true" in sys.argv,
            "v2_spawn_metadata_visible": (
                "features.multi_agent_v2.hide_spawn_agent_metadata=false" in sys.argv
            ),
            "v2_agents_namespace": (
                'features.multi_agent_v2.tool_namespace="agents"' in sys.argv
            ),
            "max_depth_two": "agents.max_depth=2" in sys.argv,
            "user_config_enabled": "--ignore-user-config" not in sys.argv,
            "legacy_sandbox_absent": "--sandbox" not in sys.argv,
            "nested_sandbox_disabled": 'default_permissions=":danger-full-access"' in sys.argv,
        }
    )
    state_path.write_text(json.dumps(state), encoding="utf-8")

    output_rows: list[dict[str, str]] = []
    quota_after = int(os.environ.get("FAKE_CODEX_QUOTA_AFTER", "0"))
    for row in input_rows:
        stage = row["stage"]
        worker_number, stage_call_number = state_call(stage, row=row)
        artifact = Path(row["artifact_path"])
        input_prompt = Path(row["input_path"]).read_text(encoding="utf-8")
        status = "completed"
        last_error = ""
        result: dict[str, str] = {
            "unit_id": row["unit_id"],
            "stage": stage,
            "artifact": str(artifact),
        }
        if quota_after and worker_number > quota_after:
            status = "failed"
            last_error = "account usage limit reached"
        elif scenario == "worker_quota":
            status = "failed"
            last_error = "account usage limit reached"
        elif scenario == "transient" and stage == "generation" and stage_call_number == 1:
            status = "failed"
            last_error = "Service unavailable; Retry-After: 1"
        elif scenario == "missing_report" and stage_call_number == 1:
            status = "failed"
            last_error = "worker exited without calling report_agent_job_result exactly once"
        elif scenario == "missing_candidate" and stage_call_number == 1:
            pass
        else:
            if scenario == "truncated" and stage_call_number == 1:
                rendered = "# Short\n\nThis is incomplete.\n"
            elif scenario == "invalid_d2" and stage_call_number == 1:
                rendered = repaired_d2() if stage == "diagram_repair" else invalid_d2_candidate()
            elif scenario == "layout_retry":
                if stage == "generation":
                    rendered = invalid_layout_candidate()
                elif stage == "diagram_repair" and stage_call_number == 1:
                    rendered = too_wide_d2()
                else:
                    rendered = repaired_d2()
            elif stage == "section_repair":
                rendered = targeted_repair(input_prompt)
            elif stage in {"diagram_repair", "source_attribution_repair"}:
                rendered = repaired_d2() if stage == "diagram_repair" else "Teaching is direct and precise.\n"
            else:
                rendered = candidate()
            artifact.write_text(rendered, encoding="utf-8")
        if scenario == "malformed_result" and stage_call_number == 1:
            result["unit_id"] = "wrong-unit"
        output_rows.append(
            {
                **row,
                "job_id": f"fake-job-{total}-{worker_number}",
                "item_id": row["unit_id"],
                "status": status,
                "last_error": last_error,
                "result_json": json.dumps(result),
            }
        )
    output_csv_path.parent.mkdir(parents=True, exist_ok=True)
    with output_csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[*fieldnames, "job_id", "item_id", "status", "last_error", "result_json"],
        )
        writer.writeheader()
        writer.writerows(output_rows)
    complete()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
