#!/usr/bin/env python3
"""ntfy push notifications for Codex, driven entirely by lifecycle hooks.

Replaces notify-ntfy.sh. Notifies on exactly three moments:

  1. A question needs answering  -- PreToolUse on `request_user_input`.
  2. A plan is ready to review   -- Stop, when the turn recorded a Plan item.
  3. Work is finished            -- Stop, on any other completed root turn.

Why hooks rather than the legacy top-level `notify` command: that payload cannot
tell a real turn from a subagent's, which is why the old script needed a
state_5.sqlite lookup plus a ripgrep over the rollout to filter. The Stop hook is
dispatched separately from SubagentStop and internal subagents return early, so
subagent turns simply never arrive here.

The old script also missed every plan turn. It bailed when the legacy payload's
last-assistant-message was empty, and in Plan mode Codex strips the
<proposed_plan> block out of that text before it is built -- so a plan-only
message left it null and the notification never fired. Case 2 reads the Plan item
Codex records in the rollout instead, the same source copy-plan-to-clipboard.py
uses.

Never gate on permission_mode: hook_permission_mode() only ever reports
"default" or "bypassPermissions", never "plan".

Set CODEX_NTFY_DRY_RUN=1 to print what would be sent instead of contacting
ntfy.sh.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

TOPIC_FILE = Path.home() / ".codex" / "ntfy-topic"
GOALS_DB = Path.home() / ".codex" / "goals_1.sqlite"

# Sessions that represent a person waiting at a terminal. `exec` is excluded so
# the batch skills' nested `codex exec` workers stay silent; subagent sessions
# record a table here rather than a string and are excluded by the isinstance
# check in interactive_session().
INTERACTIVE_SOURCES = {"cli", "vscode"}

# A goal drives many autonomous turns; only its terminal states are worth a push.
GOAL_QUIET_STATUS = "active"


def send(title: str, tags: str, message: str, priority: str = "default") -> None:
    """Post to ntfy. Never raises: a failed notification must not disturb Codex."""
    if os.environ.get("CODEX_NTFY_DRY_RUN") == "1":
        print(f"send\t{title}\t{tags}\t{message}")
        return

    try:
        topic = TOPIC_FILE.read_text(encoding="utf-8").strip()
    except (OSError, UnicodeError):
        return
    # The topic is the whole secret; refuse anything that could reshape the URL.
    if not topic or not re.fullmatch(r"[A-Za-z0-9_-]+", topic):
        return

    try:
        subprocess.run(
            [
                "/usr/bin/curl", "--fail", "--silent", "--show-error",
                "--max-time", "5", "--retry", "1", "--retry-delay", "1",
                "-H", f"Title: {title}",
                "-H", f"Tags: {tags}",
                "-H", f"Priority: {priority}",
                "--data-binary", message,
                f"https://ntfy.sh/{topic}",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return


def read_rollout(transcript_path) -> tuple[str | None, dict | None]:
    """Return (session source, newest Plan item) from the rollout, in one pass.

    The rollout is the only thing that has to be read: its first record carries
    the session source, and the plan Codex parsed out of the assistant message is
    recorded further down as an item_completed / Plan entry.
    """
    if not isinstance(transcript_path, str) or not transcript_path:
        return None, None

    source = None
    plans: dict[str, str] = {}
    try:
        with Path(transcript_path).open("r", encoding="utf-8", errors="replace") as file:
            for index, line in enumerate(file):
                if index == 0:
                    try:
                        record = json.loads(line)
                    except ValueError:
                        continue
                    if record.get("type") == "session_meta":
                        source = (record.get("payload") or {}).get("source")
                    continue

                # Rollouts run to megabytes; skip the parse unless it could match.
                if '"item_completed"' not in line or '"Plan"' not in line:
                    continue
                try:
                    record = json.loads(line)
                except ValueError:
                    continue
                payload = record.get("payload")
                if not isinstance(payload, dict):
                    continue
                if payload.get("type") != "item_completed":
                    continue
                item = payload.get("item")
                if not isinstance(item, dict) or item.get("type") != "Plan":
                    continue
                text = item.get("text")
                if isinstance(text, str) and text.strip():
                    # Later plans in the same turn replace earlier ones.
                    plans[payload.get("turn_id")] = text.strip()
    except (OSError, UnicodeError):
        return None, None

    return source, plans


def interactive_session(source) -> bool:
    """True for a session a person is sitting in front of.

    Subagent sources deserialize to a dict, never a string, so the isinstance
    check alone excludes them; `exec` is excluded by name.
    """
    return isinstance(source, str) and source in INTERACTIVE_SOURCES


def goal_is_active(session_id) -> bool:
    """True while a /goal run is mid-flight, so its own turns stay quiet.

    Any failure reports False: a missed suppression is better than silence,
    which is the failure mode being fixed here.
    """
    if not isinstance(session_id, str) or not session_id or not GOALS_DB.exists():
        return False
    try:
        import sqlite3

        uri = f"file:{GOALS_DB}?mode=ro"
        with sqlite3.connect(uri, uri=True, timeout=1.0) as connection:
            row = connection.execute(
                "SELECT status FROM thread_goals WHERE thread_id = ? LIMIT 1;",
                (session_id,),
            ).fetchone()
    except Exception:
        return False
    return bool(row) and row[0] == GOAL_QUIET_STATUS


def first_line(text, limit: int = 120) -> str:
    """A one-line gist for the notification body."""
    if not isinstance(text, str):
        return ""
    for raw in text.splitlines():
        line = raw.strip().lstrip("#").strip()
        if line:
            return line if len(line) <= limit else line[: limit - 1] + "…"
    return ""


def handle_pre_tool_use(event) -> None:
    if event.get("tool_name") != "request_user_input":
        return
    send(
        "Codex needs input",
        "computer,question",
        "Codex is waiting for your answer.",
        priority="high",
    )


def handle_stop(event) -> None:
    # A blocking Stop hook re-runs the turn and fires Stop again; only the
    # genuine finish should notify.
    if event.get("stop_hook_active") is True:
        return

    source, plans = read_rollout(event.get("transcript_path"))
    if not interactive_session(source):
        return

    plan = (plans or {}).get(event.get("turn_id"))
    if plan:
        gist = first_line(plan)
        send(
            "Codex plan ready",
            "computer,memo",
            f"A plan is ready for your review: {gist}" if gist
            else "A plan is ready for your review.",
            priority="high",
        )
        return

    if goal_is_active(event.get("session_id")):
        return

    gist = first_line(event.get("last_assistant_message"))
    send(
        "Codex work complete",
        "computer,heavy_check_mark",
        f"Codex finished: {gist}" if gist else "Codex finished the task.",
    )


def main() -> int:
    # Hook payloads arrive on a pipe. Reading an inherited tty would block
    # forever and swallow keystrokes typed behind the hook.
    if sys.stdin.isatty():
        return 0

    try:
        event = json.load(sys.stdin)
    except (ValueError, UnicodeError):
        return 0
    if not isinstance(event, dict):
        return 0

    name = event.get("hook_event_name")
    if name == "PreToolUse":
        handle_pre_tool_use(event)
    elif name == "Stop":
        handle_stop(event)
    # SubagentStop and everything else are deliberately ignored.

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
