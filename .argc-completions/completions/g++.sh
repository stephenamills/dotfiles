#!/usr/bin/env bash
# Automatic generated, DON'T MODIFY IT.

# @arg words~[`_choice_delegate`]

. "$ARGC_COMPLETIONS_ROOT/utils/_argc_utils.sh"

_choice_delegate() {
    if _argc_util_has_path_prefix; then
        echo "__argc_value=path"
        return
    fi
    if [[ "$ARGC_CWORD" == -* ]]; then
        if [[  "$ARGC_CWORD" == *'='* ]]; then
            prefix="${ARGC_CWORD%%=*}="
            echo "__argc_prefix=$prefix"
            echo "__argc_filter=${ARGC_CWORD#*=}"
            "${argc__args[0]}" --completion="$ARGC_CWORD" | sed "s/$prefix//"
        else
            "${argc__args[0]}" --completion="$ARGC_CWORD" | sed 's/=.*/=\x00/'
        fi
    elif [[ ${#argc__args[@]} -gt 2 ]]; then
        prev="${argc__args[-2]}"
        if [[ "$prev" == -* ]]; then
            "${argc__args[0]}" --completion="$prev $ARGC_CWORD" | sed -e "s/$prev\s\+//" -e 's/=$/=\x00/'
        fi
    fi
}

command eval "$(argc --argc-eval "$0" "$@")"