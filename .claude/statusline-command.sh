#!/usr/bin/env bash
# Claude Code statusLine.
#
# Renders exactly one line:
#   Opus 5 xhigh · dotfiles · ctx 3% · tok 124k in 118k out 5k · 5h 13% · 7d 4%
#
# Why it is written this defensively — the statusline renderer splits our
# output on newlines. A single line is passed to Ink with wrap="truncate", so
# it can never wrap or disturb the footer. Two or more lines are rendered as a
# stacked column instead, which pushes the prompt around and is what makes
# typed text stop echoing in plan mode and question menus. So: never emit a
# newline (not even a trailing one), never emit an ANSI escape, and never fail
# in a way that leaks text to stdout.
#
# The width cap is enforced in *bytes*, under LC_ALL=C. Bytes are not display
# columns — the "·" separator is 2 bytes wide but 1 column, and a directory
# name may be anything — but in UTF-8 a character never costs fewer bytes than
# it does columns (2-byte accented chars are 1 column, 3-byte CJK and 4-byte
# emoji are 2). So a byte count can only ever over-estimate the width, never
# under-estimate it, which is what makes the cap safe to trust. It errs toward
# truncating slightly early, which is harmless; the failure that matters would
# be truncating too late.

export LC_ALL=C

MAX=100

line=$(jq -r '
  # 0-100 number -> "42%". Anything else -> null (segment is dropped).
  def pct:
    if type == "number"
    then ((if . < 0 then 0 elif . > 100 then 100 else . end) | round | tostring) + "%"
    else null
    end;

  # Token count -> "812", "12k", "1.2M". Anything else -> "0".
  def hum:
    if type == "number" and . >= 0 then
      if   . < 1000    then (floor | tostring)
      elif . < 1000000 then ((. / 1000) | round | tostring) + "k"
      else                  ((. / 100000) | round / 10 | tostring) + "M"
      end
    else "0"
    end;

  def str: if type == "string" then . else "" end;
  def seg($label; $v): if $v == null then empty else $label + " " + $v end;

  (.context_window // {})                     as $c
  | ($c.total_input_tokens  | if type == "number" then . else 0 end) as $in
  | ($c.total_output_tokens | if type == "number" then . else 0 end) as $out
  # .[0:N] slices by codepoint, so these caps bound the line by construction
  # and always leave valid UTF-8.
  | (.model.display_name | str | .[0:14])     as $model
  # .effort is absent entirely on models without effort levels.
  | (.effort.level | str)                     as $effort
  | ((.workspace.current_dir // .cwd | str)
      | split("/") | map(select(. != "")) | last // "" | .[0:14]) as $dir
  | [
      ([$model, $effort] | map(select(. != "")) | join(" ")),
      $dir,
      seg("ctx"; $c.used_percentage | pct),
      "tok " + (($in + $out) | hum)
        + " in " + ($in | hum) + " out " + ($out | hum),
      seg("5h"; .rate_limits.five_hour.used_percentage  | pct),
      seg("7d"; .rate_limits.seven_day.used_percentage | pct)
    ]
  | map(select(. != ""))
  | join(" · ")
' 2>/dev/null)

# Belt and braces: drop anything that could move the cursor or add a line.
# Under LC_ALL=C this is exactly 0x00-0x1F and 0x7F, which covers both stray
# newlines and the ESC that would begin an escape sequence. Bytes >= 0x80 are
# untouched, so the "·" separators and non-ASCII directory names survive.
line=${line//[[:cntrl:]]/}

if [ "${#line}" -gt "$MAX" ]; then
  # The cut is byte-wise, so it can land inside a multi-byte character. The
  # first *dropped* byte tells us: if it is a continuation byte (0x80-0xBF) we
  # severed a character, so walk the trailing continuation bytes off and drop
  # their lead byte too. Otherwise the cut was already on a boundary.
  next=${line:$MAX:1}
  line=${line:0:$MAX}
  case $next in
    [$'\x80'-$'\xbf'])
      while [ -n "$line" ]; do
        last=${line: -1}
        line=${line%?}
        case $last in [$'\x80'-$'\xbf']) ;; *) break ;; esac
      done
      ;;
  esac
fi

printf '%s' "$line"
exit 0
