#!/bin/bash

# Codex passes external `notify` payloads as one JSON argument. The
# request_user_input lifecycle hook passes JSON on stdin with --hook.
# Notification failures are intentionally non-fatal so they never interrupt Codex.

jq_bin="/opt/homebrew/bin/jq"
sqlite_bin="/usr/bin/sqlite3"
rg_bin="/opt/homebrew/bin/rg"

if [[ "${1:-}" == "--hook" ]]; then
  IFS= read -r payload || exit 0
else
  payload="${1:-}"
fi

if [[ -z "${payload:-}" || ! -x "$jq_bin" ]]; then
  exit 0
fi

json_value() {
  printf '%s' "$payload" | "$jq_bin" -r "$1 // empty" 2>/dev/null
}

send_ntfy() {
  local title="$1"
  local tags="$2"
  local message="$3"

  # Test the event filter without contacting ntfy.sh.
  if [[ "${CODEX_NTFY_DRY_RUN:-}" == "1" ]]; then
    printf 'send\t%s\t%s\n' "$title" "$message"
    return 0
  fi

  local topic_file="${HOME}/.codex/ntfy-topic"
  if [[ ! -r "$topic_file" ]]; then
    return 0
  fi

  local topic
  IFS= read -r topic < "$topic_file"
  case "$topic" in
    ""|*[!A-Za-z0-9_-]*) return 0 ;;
  esac

  /usr/bin/curl \
    --fail \
    --silent \
    --show-error \
    --max-time 5 \
    --retry 1 \
    --retry-delay 1 \
    -H "Title: ${title}" \
    -H "Tags: ${tags}" \
    -H "Priority: default" \
    --data-binary "$message" \
    "https://ntfy.sh/${topic}" \
    >/dev/null 2>&1 || true
}

event_type="$(json_value '.type')" || exit 0
hook_event="$(json_value '.hook_event_name')" || exit 0

# request_user_input pauses the turn before the turn-complete event. A
# PreToolUse hook calls this branch at the point Codex needs an answer.
if [[ "$hook_event" == "PreToolUse" ]]; then
  tool_name="$(json_value '.tool_name')" || exit 0
  if [[ "$tool_name" == "request_user_input" ]]; then
    send_ntfy \
      "Codex needs input" \
      "computer,question" \
      "Codex is waiting for your answer."
  fi
  exit 0
fi

if [[ "$event_type" != "agent-turn-complete" ]]; then
  exit 0
fi

thread_id="$(json_value '.["thread-id"]')" || exit 0
turn_id="$(json_value '.["turn-id"]')" || exit 0
last_message="$(json_value '.["last-assistant-message"]')" || exit 0

# Empty completions occur during compaction, interruption, and automatic
# continuation. They are progress boundaries, not finished work.
if [[ -z "$thread_id" || -z "$turn_id" || -z "$last_message" ]]; then
  exit 0
fi
case "$thread_id:$turn_id" in
  *[!A-Za-z0-9_:-]*) exit 0 ;;
esac

# The legacy notify payload does not identify subagents. Cross-check the turn
# against an interactive root thread's indexed rollout: guardian/reviewer and
# delegated subagents, plus headless `codex exec` workers, must not notify.
state_db="${HOME}/.codex/state_5.sqlite"
if [[ ! -r "$state_db" || ! -x "$sqlite_bin" || ! -x "$rg_bin" ]]; then
  exit 0
fi

rollout_path="$($sqlite_bin "$state_db" \
  "SELECT rollout_path FROM threads WHERE id = '$thread_id' AND thread_source = 'user' AND source IN ('cli', 'vscode') LIMIT 1;" \
  2>/dev/null)" || exit 0
if [[ -z "$rollout_path" || ! -r "$rollout_path" ]]; then
  exit 0
fi
if ! "$rg_bin" -Fq "\"type\":\"task_complete\",\"turn_id\":\"$turn_id\"" "$rollout_path" 2>/dev/null; then
  exit 0
fi

# In /goal mode, only terminal or attention-required states should notify.
# An active goal creates several autonomous turn-complete events.
goals_db="${HOME}/.codex/goals_1.sqlite"
if [[ -r "$goals_db" ]]; then
  goal_status="$($sqlite_bin "$goals_db" \
    "SELECT status FROM thread_goals WHERE thread_id = '$thread_id' LIMIT 1;" \
    2>/dev/null)" || goal_status=""
  if [[ "$goal_status" == "active" ]]; then
    exit 0
  fi
fi

# Fallback local macOS notification (disabled while ntfy.sh is active).
# Uncomment both lines if you need to switch back to the local alert:
# /usr/bin/osascript -e 'display notification "Task finished" with title "Codex"' >/dev/null 2>&1 || true
# /usr/bin/afplay /System/Library/Sounds/Glass.aiff >/dev/null 2>&1 &

case "${goal_status:-}" in
  paused|blocked|usage_limited|budget_limited)
    send_ntfy \
      "Codex needs attention" \
      "computer,warning" \
      "Codex stopped before finishing and needs your attention."
    ;;
  *)
    send_ntfy \
      "Codex work complete" \
      "computer,heavy_check_mark" \
      "The main Codex task finished."
    ;;
esac

exit 0
