#!/usr/bin/env bash
# Automatic generated, DON'T MODIFY IT.

# @arg words~[`_choice_delegate`]

. "$ARGC_COMPLETIONS_ROOT/utils/_argc_utils.sh"

_choice_delegate() {
    output="$(GO_FLAGS_COMPLETION=1 "${argc__args[@]}")"
    if [[ -z "$output" ]]; then
        _argc_util_comp_path
        return
    fi
    echo "$output" | sed 's|\([=/:]\)$|\1\x00|'
}

command eval "$(argc --argc-eval "$0" "$@")"