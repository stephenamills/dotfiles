#!/usr/bin/env python3
"""Stop hook: copy the newest Codex plan to the clipboard as soon as it appears.

Codex has no ExitPlanMode tool, and the Stop payload's `last_assistant_message`
is useless here: in Plan mode, finalize_turn_item() runs the assistant text
through strip_proposed_plan_blocks() before last_agent_message is derived from
it, so a plan-only message arrives as null and a plan with a preamble arrives as
the preamble alone.

The plan does reach disk. Codex parses the block into a Plan turn item and
records it in the session rollout as
  {"type":"event_msg","payload":{"type":"item_completed","turn_id":...,
   "item":{"type":"Plan","text":"<markdown>"}}}
with the tags already stripped. The Stop payload carries both `transcript_path`
(the rollout) and `turn_id`, and core awaits live_thread.persist() before running
this hook, so the record is on disk. Matching on turn_id means a turn that only
discusses a plan cannot clobber the clipboard.

Companion to ~/.claude/copy-plan-to-clipboard.sh, which does this for Claude Code.

Do not gate on permission_mode: hook_permission_mode() only ever reports
"default" or "bypassPermissions", never "plan".
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def plan_text_for_turn(transcript_path, turn_id) -> str | None:
    """Return the Plan item recorded for this turn, if there is one."""
    if not isinstance(transcript_path, str) or not transcript_path:
        return None
    if not isinstance(turn_id, str) or not turn_id:
        return None

    plan = None
    try:
        with Path(transcript_path).open("r", encoding="utf-8", errors="replace") as file:
            for line in file:
                # Rollouts run to megabytes and are almost entirely irrelevant
                # here; skip the JSON parse unless the line could be the one.
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
                if payload.get("turn_id") != turn_id:
                    continue

                item = payload.get("item")
                if not isinstance(item, dict) or item.get("type") != "Plan":
                    continue

                text = item.get("text")
                if isinstance(text, str) and text.strip():
                    # Keep scanning: if the turn revised its plan, the last wins.
                    plan = text.strip()
    except (OSError, UnicodeError):
        return None

    return plan


def main() -> int:
    # Hook payloads arrive on a pipe. Reading an inherited tty would block
    # forever and swallow keystrokes -- the failure the Claude hook hit in 3fa6aa5.
    if sys.stdin.isatty():
        return 0

    try:
        event = json.load(sys.stdin)
    except (ValueError, UnicodeError):
        return 0
    if not isinstance(event, dict):
        return 0
    if event.get("hook_event_name") != "Stop":
        return 0

    plan = plan_text_for_turn(event.get("transcript_path"), event.get("turn_id"))
    if plan is None:
        return 0

    try:
        subprocess.run(
            ["/usr/bin/pbcopy"],
            input=f"{plan}\n",
            text=True,
            timeout=5,
            check=True,
        )
    except (OSError, subprocess.SubprocessError):
        return 0

    # Confirm in-session, since a silent hook is indistinguishable from a broken
    # one. `continue` stays true -- this hook must never halt the turn.
    json.dump(
        {"continue": True, "systemMessage": "Plan copied to clipboard"},
        sys.stdout,
        ensure_ascii=False,
    )
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
