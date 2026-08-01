#!/usr/bin/env bash
# Claude Code statusLine — compact, width-aware, single-subprocess.
#
# Renders:  model (effort) · dir · ctx N% · 5h N% · 7d N%
#
# Width is the whole point of this script's design. Claude Code does not pass
# the terminal width in its JSON payload, so a status line that renders wider
# than the terminal wraps to a second line and corrupts the footer layout —
# most visibly, typed text in question prompts stops echoing. Every segment
# below is budgeted against the detected width and dropped (or truncated)
# rather than allowed to wrap.
#
# Cost matters too: this runs on a 300ms debounce, so it makes exactly one
# subprocess call (jq) plus an optional `tput`. Rounding happens inside jq and
# the directory basename comes from parameter expansion.

input=$(cat)

# ---- catppuccin mocha palette (truecolor) ----
mauve='38;2;203;166;247'
blue='38;2;137;180;250'
green='38;2;166;227;161'
peach='38;2;250;179;135'
red='38;2;243;139;168'
subtext='38;2;166;173;200'

# One jq call, one value per line. Line-based rather than @tsv on purpose:
# tab is IFS whitespace, so consecutive tabs would collapse and an empty field
# would shift every later value into the wrong variable.
{
  read -r model
  read -r effort
  read -r cwd
  read -r ctx
  read -r five
  read -r weekly
} <<EOF
$(printf '%s' "$input" | jq -r '
  def pct: if type == "number" then (round | tostring) else "" end;
  (.model.display_name // ""),
  (.effort.level // ""),
  (.workspace.current_dir // .cwd // ""),
  (.context_window.remaining_percentage | pct),
  (.rate_limits.five_hour.used_percentage | pct),
  (.rate_limits.seven_day.used_percentage | pct)
' 2>/dev/null)
EOF

dir=${cwd##*/}

# ---- assemble segments as parallel plain/colored arrays ----
# Width is measured on the plain text; the ANSI escapes never enter the count.
plains=()
colors=()

add() {
  # add <color> <text>
  local color=$1 text=$2 buf
  [ -n "$text" ] || return 0
  printf -v buf '\033[%sm%s\033[0m' "$color" "$text"
  plains+=("$text")
  colors+=("$buf")
}

if [ -n "$effort" ]; then
  add "$mauve" "${model:+$model ($effort)}"
else
  add "$mauve" "$model"
fi
add "$blue" "$dir"
add "$green" "${ctx:+ctx ${ctx}%}"
add "$peach" "${five:+5h ${five}%}"
add "$red" "${weekly:+7d ${weekly}%}"

# ---- width budget ----
# COLUMNS first (cheap, and set by most shells), then tput against the
# controlling terminal, then a conservative 80. Anything non-numeric or
# absurdly small is treated as "unknown".
sane() { case $1 in '' | *[!0-9]*) return 1 ;; esac; [ "$1" -ge 20 ]; }

cols=${COLUMNS:-}
if ! sane "$cols"; then
  cols=$(tput cols 2>/dev/null </dev/tty)
  sane "$cols" || cols=80
fi
budget=$((cols - 4))

# Drop segments from the right until the line fits. Separator " · " is three
# display columns wide (the middle dot is one column, two bytes).
n=${#plains[@]}
while [ "$n" -gt 1 ]; do
  w=0
  i=0
  while [ "$i" -lt "$n" ]; do
    w=$((w + ${#plains[i]}))
    [ "$i" -gt 0 ] && w=$((w + 3))
    i=$((i + 1))
  done
  [ "$w" -le "$budget" ] && break
  n=$((n - 1))
done

# A single segment that still overruns gets hard-truncated rather than wrapped.
if [ "$n" -eq 1 ] && [ "${#plains[0]}" -gt "$budget" ]; then
  printf '\033[%sm%s\033[0m' "$mauve" "${plains[0]:0:$budget}"
  exit 0
fi

out=''
i=0
while [ "$i" -lt "$n" ]; do
  if [ "$i" -gt 0 ]; then
    printf -v s '\033[%sm · \033[0m' "$subtext"
    out+=$s
  fi
  out+=${colors[i]}
  i=$((i + 1))
done

printf '%s' "$out"
