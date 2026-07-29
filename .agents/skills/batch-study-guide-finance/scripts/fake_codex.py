#!/usr/bin/env python3
"""Deterministic fake Codex executable for supervisor acceptance tests."""

from __future__ import annotations

import fcntl
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


def multi_agent_v2_config() -> str:
    return next(
        (
            argument
            for argument in sys.argv
            if argument.startswith("features.multi_agent_v2={")
        ),
        "",
    )


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
        "```mermaid\n"
        "flowchart LR\n"
        '  material[\"Course material\"] --> concepts[\"Key concepts\"]\n'
        '  concepts --> practice[\"Guided practice\"]\n'
        '  practice --> mastery[\"Demonstrated mastery\"]\n'
        "```\n\n"
        "## Review Questions\n\n"
        "1. What is the central concept? Use the direct explanation above.\n\n"
        f"{MARKER}\n"
    )


def course_map_candidate(prompt: str) -> str:
    links = re.findall(r"(?m)^- ([^:\n]+): (.+)$", prompt)
    ordered_links = "\n".join(
        f"{index}. [{Path(source).stem}](<{destination}>) — integrated chapter {index}."
        for index, (source, destination) in enumerate(links, 1)
    )
    whole_course = "UNIT_ID: course-map-whole-course" in prompt
    headings = (
        (
            "Course Thesis and Learning Outcomes",
            "Ordered Topic Path",
            "Whole-Course Architecture and Dependencies",
            "Topic-by-Topic Learning and Mastery",
            "Integrated Cross-Topic Derivation",
            "Whole-Course Quantitative Framework and Worked Examples",
            "End-to-End Operating Workflow and Decision Gates",
            "Cross-Topic Synthesis",
            "Whole-Course Misconceptions and Failure Modes",
            "Cumulative Whole-Course Application",
            "Whole-Course Mastery Checklist",
            "Whole-Course Retrieval Questions and Answers",
            "Whole-Course Spaced Review Plan",
        )
        if whole_course
        else (
            "Section Thesis and Learning Outcomes",
            "Ordered Chapter Path",
            "Architecture and Dependencies",
            "Chapter-by-Chapter Learning and Mastery",
            "Integrated Conceptual Derivation",
            "Quantitative Framework and Worked Examples",
            "Operating Workflow and Decision Gates",
            "Cross-Chapter Synthesis",
            "Misconceptions and Failure Modes",
            "Cumulative Application",
            "Mastery Checklist",
            "Retrieval Questions and Answers",
            "Spaced Review Plan",
        )
    )
    ordered_heading = "Ordered Topic Path" if whole_course else "Ordered Chapter Path"
    architecture_heading = (
        "Whole-Course Architecture and Dependencies"
        if whole_course
        else "Architecture and Dependencies"
    )
    workflow_heading = (
        "End-to-End Operating Workflow and Decision Gates"
        if whole_course
        else "Operating Workflow and Decision Gates"
    )
    sections: list[str] = [
        "# Complete Course Map" if whole_course else "# Topic Course Map",
        "",
    ]
    for heading in headings:
        sections.extend([f"## {heading}", ""])
        if heading == ordered_heading:
            sections.extend([ordered_links, ""])
        elif heading == architecture_heading:
            sections.extend(
                [
                    "```mermaid",
                    "flowchart LR",
                    '  A["Foundation"] --> B["Integration"]',
                    '  B --> C["Application"]',
                    "```",
                    "",
                ]
            )
        elif heading == workflow_heading:
            sections.extend(
                [
                    "```mermaid",
                    "flowchart TD",
                    '  I["Inputs"] --> D{"Checks pass?"}',
                    '  D -->|Yes| O["Decision"]',
                    '  D -->|No| R["Review"]',
                    '  R --> I',
                    "```",
                    "",
                ]
            )
        else:
            sections.extend(
                [
                    "The topic is taught with explicit dependencies, practical application, "
                    "observable mastery evidence, and corrective feedback.",
                    "",
                ]
            )
    sections.extend([MARKER, ""])
    return "\n".join(sections)


def prohibited_d2_candidate() -> str:
    return (
        "# Lesson Study Guide\n\n"
        "## Overview\n\nA complete-looking candidate with a prohibited legacy diagram.\n\n"
        "```d2\n"
        "concept -> mastery\n"
        "```\n\n"
        f"{MARKER}\n"
    )


def invalid_mermaid_candidate() -> str:
    return (
        "# Lesson Study Guide\n\n## Overview\n\nA complete candidate with invalid Mermaid syntax.\n\n"
        "```mermaid\n"
        "flowchart LR\n"
        "  A -->\n"
        "```\n\n"
        f"{MARKER}\n"
    )


def invalid_raw_mermaid() -> str:
    return (
        "flowchart LR\n"
        "  A -->\n"
    )


def repaired_mermaid() -> str:
    return (
        "flowchart LR\n"
        '  question[\"How is mastery built?\"] --> concept[\"Repaired concept\"]\n'
        '  concept --> practice[\"Guided practice\"]\n'
        '  practice --> mastery[\"Demonstrated mastery\"]\n'
        '  mastery -. \"feedback\" .-> practice\n'
    )


def targeted_repair(prompt: str) -> str:
    parts: list[str] = []
    for kind, key in re.findall(r"<<<STUDY-GUIDE-(MERMAID|SECTION):(.+?)>>>", prompt):
        parts.append(f"<<<STUDY-GUIDE-{kind}:{key}>>>")
        if kind == "MERMAID":
            parts.extend(
                [
                    "flowchart LR",
                    '  question["What must be mastered?"] --> concept["Core concept"]',
                    '  concept --> practice["Guided practice"]',
                    '  practice --> mastery["Demonstrated mastery"]',
                    '  mastery -. "review" .-> concept',
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


def dispatch_manifest(dispatcher_prompt: str) -> list[dict[str, object]]:
    required_instructions = (
        "`agents.spawn_agent` exactly once",
        "`fork_turns` to `\"none\"`",
        "`agents.wait_agent`",
        "`agents.list_agents`",
    )
    missing = [item for item in required_instructions if item not in dispatcher_prompt]
    if missing or "spawn_agents_on_csv" in dispatcher_prompt:
        raise RuntimeError(
            "dispatcher prompt does not use the required V2 protocol: "
            + ", ".join(missing or ["legacy CSV dispatcher"])
        )
    match = re.search(
        r"BEGIN WAVE MANIFEST\n(.*?)\nEND WAVE MANIFEST",
        dispatcher_prompt,
        flags=re.DOTALL,
    )
    if not match:
        raise RuntimeError("dispatcher prompt lacks a V2 wave manifest")
    value = json.loads(match.group(1))
    if not isinstance(value, list) or not all(isinstance(row, dict) for row in value):
        raise RuntimeError("V2 wave manifest must be an array of task objects")
    required = {
        "task_name", "unit_id", "stage", "attempt", "input_path", "artifact_path",
        "read_budget_bytes",
    }
    for row in value:
        if set(row) != required:
            raise RuntimeError(f"V2 wave manifest has unexpected fields: {sorted(row)}")
    return value


def main() -> int:
    if "--version" in sys.argv and "exec" not in sys.argv:
        print(os.environ.get("FAKE_CODEX_VERSION", "codex-cli fake-1.0"))
        return 0
    dispatcher_prompt = sys.stdin.read()
    total, _ = state_call("dispatcher")
    scenario = os.environ.get("FAKE_CODEX_SCENARIO", "success")
    emit({"type": "thread.started", "thread_id": f"fake-dispatcher-{total}"})
    emit({"type": "item.started", "item": {"type": "function_call", "name": "agents.spawn_agent"}})
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
        message = "agents.spawn_agent tool unavailable: unknown tool"
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

    input_rows = dispatch_manifest(dispatcher_prompt)
    v2_config = multi_agent_v2_config()
    state_path = Path(os.environ["FAKE_CODEX_STATE"])
    with state_path.open("r", encoding="utf-8") as handle:
        state = json.load(handle)
    state.setdefault("waves", []).append(
        {
            "size": len(input_rows),
            "unit_ids": [row["unit_id"] for row in input_rows],
            "task_names": [row["task_name"] for row in input_rows],
            "v2_enabled": argument_value("--enable") == "multi_agent_v2",
            "v2_thread_limit": (
                f"max_concurrent_threads_per_session={len(input_rows) + 1}" in v2_config
            ),
            "v2_spawn_metadata_visible": "hide_spawn_agent_metadata=false" in v2_config,
            "v2_agents_namespace": 'tool_namespace="agents"' in v2_config,
            "v2_no_model_overrides": "expose_spawn_agent_model_overrides=false" in v2_config,
            "v2_direct_tool_access": "non_code_mode_only=false" in v2_config,
            "legacy_fanout_absent": "features.enable_fanout=true" not in sys.argv,
            "legacy_agent_limits_absent": not any(
                argument.startswith("agents.max_") or argument.startswith("agents.job_max_runtime")
                for argument in sys.argv
            ),
            "user_config_enabled": "--ignore-user-config" not in sys.argv,
            "legacy_sandbox_absent": "--sandbox" not in sys.argv,
            "nested_sandbox_disabled": 'default_permissions=":danger-full-access"' in sys.argv,
        }
    )
    state_path.write_text(json.dumps(state), encoding="utf-8")

    quota_after = int(os.environ.get("FAKE_CODEX_QUOTA_AFTER", "0"))
    dispatcher_error: str | None = None
    for row in input_rows:
        stage = str(row["stage"])
        worker_number, stage_call_number = state_call(stage, row=row)
        artifact = Path(str(row["artifact_path"]))
        input_prompt = Path(str(row["input_path"])).read_text(encoding="utf-8")
        if quota_after and worker_number > quota_after:
            dispatcher_error = "account usage limit reached"
        elif scenario == "worker_quota":
            dispatcher_error = "account usage limit reached"
        elif scenario == "transient" and stage == "generation" and stage_call_number == 1:
            dispatcher_error = "Service unavailable; Retry-After: 1"
        elif scenario == "missing_candidate" and stage_call_number == 1:
            pass
        elif scenario == "malformed_artifact" and stage_call_number == 1:
            artifact.symlink_to(Path(str(row["input_path"])))
        else:
            if scenario == "truncated" and stage_call_number == 1:
                rendered = "# Short\n\nThis is incomplete.\n"
            elif scenario == "invalid_d2" and stage_call_number == 1:
                rendered = (
                    repaired_mermaid()
                    if stage == "diagram_repair"
                    else prohibited_d2_candidate()
                )
            elif scenario == "mermaid_retry":
                if stage == "generation":
                    rendered = invalid_mermaid_candidate()
                elif stage == "diagram_repair" and stage_call_number == 1:
                    rendered = invalid_raw_mermaid()
                else:
                    rendered = repaired_mermaid()
            elif stage == "section_repair":
                rendered = targeted_repair(input_prompt)
            elif stage in {"diagram_repair", "source_attribution_repair"}:
                rendered = (
                    repaired_mermaid()
                    if stage == "diagram_repair"
                    else "Teaching is direct and precise.\n"
                )
            else:
                rendered = (
                    course_map_candidate(input_prompt)
                    if "UNIT_KIND: course_map" in input_prompt
                    else candidate()
                )
            artifact.write_text(rendered, encoding="utf-8")
    if dispatcher_error:
        print(dispatcher_error, file=sys.stderr, flush=True)
        emit({"type": "turn.failed", "error": dispatcher_error})
        return 1
    complete()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
