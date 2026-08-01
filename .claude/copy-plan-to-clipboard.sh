#!/usr/bin/env bash
# PreToolUse hook for ExitPlanMode: copies the plan to the clipboard the moment Claude
# presents it — before the approval prompt — so the plan can be pasted elsewhere without
# accepting or rejecting it first.
#
# Companion to the cplan function in .zshrc, which reaches older plans. This only ever
# provides the newest one.

payload=$(cat)

# The runtime supplies the plan inline, despite ExitPlanMode declaring no such parameter
plan=$(printf '%s' "$payload" | jq -r '.tool_input.plan // empty')

# Fall back to the plan file the payload names, in case that ever stops being true
if [ -z "$plan" ]; then
	file=$(printf '%s' "$payload" | jq -r '.tool_input.planFilePath // empty')
	if [ -n "$file" ] && [ -f "$file" ]; then
		plan=$(<"$file")
	fi
fi

# Exit quietly rather than blanking the clipboard when neither source has anything
[ -n "$plan" ] || exit 0

printf '%s\n' "$plan" | pbcopy

# Confirm in the session, since a silent hook is indistinguishable from a broken one
echo '{"systemMessage":"Plan copied to clipboard"}'
