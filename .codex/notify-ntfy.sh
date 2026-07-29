#!/bin/bash

# Codex passes one JSON payload argument to external notification programs.
# Notification failures are intentionally non-fatal so they never interrupt Codex.

payload="${1:-}"
if [[ -z "$payload" ]]; then
  exit 0
fi

event_type="$(printf '%s' "$payload" | /opt/homebrew/bin/jq -r '.type // empty' 2>/dev/null)" || exit 0
if [[ "$event_type" != "agent-turn-complete" ]]; then
  exit 0
fi

# Fallback local macOS notification (disabled while ntfy.sh is active).
# Uncomment both lines if you need to switch back to the local alert:
# /usr/bin/osascript -e 'display notification "Task finished" with title "Codex"' >/dev/null 2>&1 || true
# /usr/bin/afplay /System/Library/Sounds/Glass.aiff >/dev/null 2>&1 &

topic_file="${HOME}/.codex/ntfy-topic"
if [[ ! -r "$topic_file" ]]; then
  exit 0
fi

IFS= read -r topic < "$topic_file"
case "$topic" in
  ""|*[!A-Za-z0-9_-]*) exit 0 ;;
esac

/usr/bin/curl \
  --fail \
  --silent \
  --show-error \
  --max-time 10 \
  --retry 2 \
  --retry-delay 1 \
  -H "Title: Codex task complete" \
  -H "Tags: computer,heavy_check_mark" \
  -H "Priority: default" \
  --data-binary "A Codex CLI turn finished." \
  "https://ntfy.sh/${topic}" \
  >/dev/null 2>&1 || true

exit 0
