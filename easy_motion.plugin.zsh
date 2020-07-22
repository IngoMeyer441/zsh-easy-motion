# Configuration values
_EASY_MOTION_DIM_DEFAULT="fg=242"
_EASY_MOTION_HIGHLIGHT_DEFAULT="fg=196,bold"
_EASY_MOTION_HIGHLIGHT_2_FIRST_DEFAULT="fg=11,bold"
_EASY_MOTION_HIGHLIGHT_2_SECOND_DEFAULT="fg=3,bold"
_EASY_MOTION_TARGET_KEYS_DEFAULT="asdghklqwertyuiopzxcvbnmfj;"

_EASY_MOTION_ROOT_DIR="${0:h}"
# in a script, we cannot query if zsh is in vi operator pending mode
# -> keep track of it
_EASY_MOTION_VIOPP=0
_EASY_MOTION_TIMESTAMP_CMD="python -c 'import time; print(int(time.time() * 1000))'"

function vi-easy-motion () {
    local -a MOTIONS_WITH_ARGUMENT=( "f" "F" "t" "T" "s" )
    local MAX_VIOPP_TIME_DELTA=500
    local motion
    local motion_argument
    local -a motion_indices
    local target_key
    local saved_buffer
    local saved_predisplay
    local saved_postdisplay
    local -a saved_region_highlight
    local ret

    function _easy-motion-setup-variables {
        : "${EASY_MOTION_DIM:=${_EASY_MOTION_DIM_DEFAULT}}"
        : "${EASY_MOTION_HIGHLIGHT:=${_EASY_MOTION_HIGHLIGHT_DEFAULT}}"
        : "${EASY_MOTION_HIGHLIGHT_2_FIRST:=${_EASY_MOTION_HIGHLIGHT_2_FIRST_DEFAULT}}"
        : "${EASY_MOTION_HIGHLIGHT_2_SECOND:=${_EASY_MOTION_HIGHLIGHT_2_SECOND_DEFAULT}}"
        : "${EASY_MOTION_TARGET_KEYS:=${_EASY_MOTION_TARGET_KEYS_DEFAULT}}"
    }

    function _easy-motion-save-state {
        local current_time
        current_time="$(python -c 'import time; print(int(time.time() * 1000))')"
        saved_buffer="${BUFFER}"
        saved_predisplay="${PREDISPLAY}"
        saved_postdisplay="${POSTDISPLAY}"
        saved_region_highlight=("${region_highlight[@]}")
        # Assume that operator pending mode was already exited if ${MAX_VIOPP_TIME_DELTA} milliseconds are over
        if (( ${_EASY_MOTION_VIOPP} )) && (( ${current_time} - ${_EASY_MOTION_VIOPP_TIMESTAMP} > ${MAX_VIOPP_TIME_DELTA} )); then
            _EASY_MOTION_VIOPP=0
        fi
    }

    function _easy-motion-main {
        local state line
        local region_type region_pos region_key
        local target_index motion
        declare -A region_type_to_highlight

        region_type_to_highlight=( \
            ["s"]="${EASY_MOTION_HIGHLIGHT}" \
            ["p1"]="${EASY_MOTION_HIGHLIGHT_2_FIRST}" \
            ["p2"]="${EASY_MOTION_HIGHLIGHT_2_SECOND}" \
        )

        PREDISPLAY=""
        POSTDISPLAY=""

        state="none"
        # In bash, "command | while ..." would not work because while runs in a subshell and variables cannot be modified.
        # But in zsh, the while loop is NOT executed in its own subshell.
        "${_EASY_MOTION_ROOT_DIR}/easy_motion.py" "${EASY_MOTION_TARGET_KEYS}" "${CURSOR}" "${BUFFER}" </dev/tty 2>/dev/null | \
        while read -r line; do
            # >&2 echo "${line}"
            case "${line}" in
                highlight_start)
                    state="highlight"
                    region_highlight=( "0 $#BUFFER ${EASY_MOTION_DIM}" )
                    BUFFER="${saved_buffer}"
                    continue
                    ;;
                highlight_end)
                    state="none"
                    # Force a redisplay of the command line
                    zle -R
                    continue
                    ;;
                jump)
                    state="jump"
                    continue
                    ;;
                *)
                    ;;
            esac
            case "${state}" in
                highlight)
                    read -r region_type region_pos region_key <<< "${line}"
                    region_highlight+=( "${region_pos} $(( region_pos + 1 )) ${region_type_to_highlight[${region_type}]}" )
                    BUFFER[$((region_pos + 1))]="${region_key}"
                    ;;
                jump)
                    read -r target_index motion <<< "${line}"
                    ;;
            esac
        done || return 2

        if [[ -n "${target_index}" ]]; then
            if (( _EASY_MOTION_VIOPP )); then
                case "${motion}" in
                    e|E|ge|gE|f|t)
                        (( target_index++ ))
                        ;;
                    s)
                        if (( target_index > CURSOR )); then
                            (( target_index++ ))
                        fi
                        ;;
                esac
            fi
            CURSOR="${target_index}"
        fi

        return 0
    }

    function _easy-motion-restore-state {
        BUFFER="${saved_buffer}"
        PREDISPLAY="${saved_predisplay}"
        POSTDISPLAY="${saved_postdisplay}"
        region_highlight=("${saved_region_highlight[@]}")
        _EASY_MOTION_VIOPP=0
    }

    _easy-motion-setup-variables && \
    _easy-motion-save-state && \
    _easy-motion-main && \
    ret="$?"
    _easy-motion-restore-state
    # Force a redisplay of the command line
    zle -R

    return "${ret}"
}

function vi-change-wrapper () {
    _EASY_MOTION_VIOPP=1
    _EASY_MOTION_VIOPP_TIMESTAMP="$(python -c 'import time; print(int(time.time() * 1000))')"
    zle vi-change
}
function vi-delete-wrapper () {
    _EASY_MOTION_VIOPP=1
    _EASY_MOTION_VIOPP_TIMESTAMP="$(python -c 'import time; print(int(time.time() * 1000))')"
    zle vi-delete
}
zle -N vi-change-wrapper
zle -N vi-delete-wrapper
bindkey -M vicmd c vi-change-wrapper
bindkey -M vicmd d vi-delete-wrapper

zle -N vi-easy-motion
