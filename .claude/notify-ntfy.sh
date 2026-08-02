#!/bin/bash

# Claude Code hook notifier for ntfy.sh.
#
# Every path is deliberately non-fatal: a notification failure must never
# interrupt or block a Claude Code session.  Hook payloads arrive as JSON on
# stdin, and curl is detached so even the synchronous PermissionRequest hook
# returns to Claude immediately.

JQ=/opt/homebrew/bin/jq
CURL=/usr/bin/curl
DATE=/bin/date

# Never read from the terminal.  Hook payloads arrive on a pipe; if Claude ever
# hands this script an inherited tty instead (which happens for hooks it does
# not wait on), an unbounded read would block forever AND swallow every
# keystroke typed into the prompt behind it — the "ghost text" failure where
# typing into a question or plan-approval box shows nothing.  Bail instead, and
# bound the read even on a real pipe so a stalled writer cannot hang the hook.
[ -t 0 ] && exit 0
payload=""
IFS= read -r -d '' -t 2 payload
[ -n "$payload" ] || exit 0

event=$(
  printf '%s' "$payload" | "$JQ" -r '.hook_event_name // empty' 2>/dev/null
) || exit 0
[ -n "$event" ] || exit 0

# Read the topic.  This is the same topic Codex publishes to; the "Claude · <dir>"
# title prefix is what distinguishes the two senders on the phone.  A missing or
# malformed topic file silently disables notifications.
topic_file="${HOME}/.claude/ntfy-topic"
read_topic() {
  [ -r "$topic_file" ] || return 1
  IFS= read -r topic < "$topic_file" || true
  case "$topic" in
    ""|*[!A-Za-z0-9_-]*) return 1 ;;
  esac
  return 0
}

# Keep a safe, short directory label in every title.
directory_name() {
  local cwd=$1 dir
  cwd=${cwd%/}
  dir=${cwd##*/}
  [ -n "$dir" ] || dir="root"
  printf '%s' "$dir"
}

# Send in the background with all three standard streams redirected.  The
# caller never waits for network I/O, and curl failures are intentionally
# ignored.
send_ntfy() {
  local title=$1 tags=$2 priority=$3 body=$4
  "$CURL" \
    --fail \
    --silent \
    --show-error \
    --max-time 10 \
    --retry 2 \
    --retry-delay 1 \
    -H "Title: $title" \
    -H "Tags: $tags" \
    -H "Priority: $priority" \
    --data-binary "$body" \
    "https://ntfy.sh/${topic}" \
    </dev/null >/dev/null 2>&1 &
  return 0
}

# The plan is supplied inline by current Claude versions.  Keep the file
# fallback for versions that only provide planFilePath, matching the clipboard
# hook's dual-source behavior.  Remove heading markers and cap the body.
plan_summary() {
  local plan file summary
  plan=$(printf '%s' "$payload" | "$JQ" -r '.tool_input.plan // empty' 2>/dev/null) || plan=""
  if [ -z "$plan" ]; then
    file=$(printf '%s' "$payload" | "$JQ" -r '.tool_input.planFilePath // empty' 2>/dev/null) || file=""
    if [ -n "$file" ] && [ -f "$file" ]; then
      plan=$(/bin/cat "$file" 2>/dev/null) || plan=""
    fi
  fi
  [ -n "$plan" ] || return 0

  summary=$(printf '%s\n' "$plan" | /usr/bin/awk '{ sub(/^#+[[:space:]]*/, ""); print }') || summary=""
  printf '%s' "${summary:0:400}"
}

question_summary() {
  printf '%s' "$payload" | "$JQ" -r '
    (.tool_input.questions // [])
    | map(
        if ((.header // "") != "" and (.question // "") != "")
        then (.header + ": " + .question)
        else (.question // .header // "")
        end
      )
    | map(select(length > 0))
    | join("\n")
  ' 2>/dev/null
}

case "$event" in
  PermissionRequest)
    tool_name=$(printf '%s' "$payload" | "$JQ" -r '.tool_name // empty' 2>/dev/null) || exit 0
    [ "$tool_name" = "ExitPlanMode" ] || exit 0

    # Write the stamp before topic lookup or body extraction.  Notification
    # hooks can use it to suppress a second ping for the same plan dialog.
    session_id=$(printf '%s' "$payload" | "$JQ" -r '.session_id // empty' 2>/dev/null) || session_id=""
    stamp_path=""
    case "$session_id" in
      ""|*[!A-Za-z0-9_-]*) ;;
      *) stamp_path="${TMPDIR:-/tmp}/claude-ntfy-plan-${session_id}" ;;
    esac
    if [ -n "$stamp_path" ]; then
      printf '%s\n' "$($DATE +%s 2>/dev/null)" > "$stamp_path" 2>/dev/null || true
    fi

    read_topic || exit 0
    cwd=$(printf '%s' "$payload" | "$JQ" -r '.cwd // empty' 2>/dev/null) || cwd=""
    dir=$(directory_name "$cwd")
    body=$(plan_summary)
    [ -n "$body" ] || body="A Claude Code plan is ready for approval."
    send_ntfy "Claude · ${dir} — Plan ready" "clipboard" "high" "$body"
    exit 0
    ;;

  PreToolUse)
    tool_name=$(printf '%s' "$payload" | "$JQ" -r '.tool_name // empty' 2>/dev/null) || exit 0
    [ "$tool_name" = "AskUserQuestion" ] || exit 0
    read_topic || exit 0
    cwd=$(printf '%s' "$payload" | "$JQ" -r '.cwd // empty' 2>/dev/null) || cwd=""
    dir=$(directory_name "$cwd")
    body=$(question_summary)
    [ -n "$body" ] || body="Claude is waiting for your answer."
    send_ntfy "Claude · ${dir} — Question" "question" "high" "$body"
    exit 0
    ;;

  Notification)
    notification_type=$(printf '%s' "$payload" | "$JQ" -r '.notification_type // empty' 2>/dev/null) || exit 0
    [ "$notification_type" = "permission_prompt" ] || exit 0

    # ExitPlanMode may also produce a permission_prompt notification.  Filter
    # its wording first so ordering does not matter.
    is_plan_prompt=$(printf '%s' "$payload" | "$JQ" -r '
      ((.message // "") | test("exitplanmode|plan[[:space:]-]*(approval|ready)|approve[^\\n]*plan|plan[^\\n]*approve"; "i"))
    ' 2>/dev/null) || is_plan_prompt="false"
    [ "$is_plan_prompt" = "true" ] && exit 0

    # Secondary ordering guard: PermissionRequest writes this stamp before it
    # sends its own notification.  A fresh stamp means this is the same plan
    # dialog, not a separate approval request.
    session_id=$(printf '%s' "$payload" | "$JQ" -r '.session_id // empty' 2>/dev/null) || session_id=""
    case "$session_id" in
      ""|*[!A-Za-z0-9_-]*) ;;
      *)
        stamp_path="${TMPDIR:-/tmp}/claude-ntfy-plan-${session_id}"
        if [ -r "$stamp_path" ]; then
          stamp_epoch=$(/bin/cat "$stamp_path" 2>/dev/null) || stamp_epoch=""
          case "$stamp_epoch" in
            ""|*[!0-9]*) ;;
            *)
              now=$($DATE +%s 2>/dev/null) || now=""
              case "$now" in
                ""|*[!0-9]*) ;;
                *)
                  age=$((now - stamp_epoch))
                  [ "$age" -ge 0 ] && [ "$age" -lt 15 ] && exit 0
                  ;;
              esac
              ;;
          esac
        fi
        ;;
    esac

    read_topic || exit 0
    cwd=$(printf '%s' "$payload" | "$JQ" -r '.cwd // empty' 2>/dev/null) || cwd=""
    dir=$(directory_name "$cwd")
    body=$(printf '%s' "$payload" | "$JQ" -r '.message // empty' 2>/dev/null) || body=""
    [ -n "$body" ] || body="Claude needs your approval."
    send_ntfy "Claude · ${dir} — Needs approval" "question" "high" "$body"
    exit 0
    ;;

  Stop)
    read_topic || exit 0
    cwd=$(printf '%s' "$payload" | "$JQ" -r '.cwd // empty' 2>/dev/null) || cwd=""
    dir=$(directory_name "$cwd")
    body=$(printf '%s' "$payload" | "$JQ" -r '.last_assistant_message // empty' 2>/dev/null) || body=""
    [ -n "$body" ] || body="A Claude Code turn finished."
    body=${body:0:150}
    send_ntfy "Claude · ${dir} — Turn complete" "white_check_mark" "default" "$body"
    exit 0
    ;;
esac

exit 0
