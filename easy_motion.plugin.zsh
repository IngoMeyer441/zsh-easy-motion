# Configuration values
_EASY_MOTION_DIM_DEFAULT="fg=242"
_EASY_MOTION_HIGHLIGHT_DEFAULT="fg=196,bold"
_EASY_MOTION_HIGHLIGHT_2_FIRST_DEFAULT="fg=11,bold"
_EASY_MOTION_HIGHLIGHT_2_SECOND_DEFAULT="fg=3,bold"
_EASY_MOTION_TARGET_KEYS_DEFAULT="asdghklqwertyuiopzxcvbnmfj;"

_EASY_MOTION_ROOT_DIR="${0:h}"

function vi-easy-motion () {
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
        saved_buffer="${BUFFER}"
        saved_predisplay="${PREDISPLAY}"
        saved_postdisplay="${POSTDISPLAY}"
        saved_region_highlight=("${region_highlight[@]}")
    }

    function _easy-motion-main {
        local is_in_viopp state line
        local region_type region_pos region_key
        local target_index mark
        declare -A region_type_to_highlight

        region_type_to_highlight=( \
            ["s"]="${EASY_MOTION_HIGHLIGHT}" \
            ["p1"]="${EASY_MOTION_HIGHLIGHT_2_FIRST}" \
            ["p2"]="${EASY_MOTION_HIGHLIGHT_2_SECOND}" \
        )

        PREDISPLAY=""
        POSTDISPLAY=""

        is_in_viopp="$(( MARK < 0 ))"
        state="none"
        # In bash, "command | while ..." would not work because while runs in a subshell and variables cannot be modified.
        # But in zsh, the while loop is NOT executed in its own subshell.
        "${_EASY_MOTION_ROOT_DIR}/easy_motion.py" "${EASY_MOTION_TARGET_KEYS}" "${CURSOR}" "${is_in_viopp}" "${BUFFER}" </dev/tty 2>/dev/null | \
        while read -r line; do
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
                    read -r target_index mark <<< "${line}"
                    if [[ -n "${target_index}" ]]; then
                        CURSOR="${target_index}"
                    fi
                    if [[ -n "${mark}" ]]; then
                        MARK="${mark}"
                    fi
                    state="none"
                    ;;
            esac
        done || return 2

        return 0
    }

    function _easy-motion-restore-state {
        BUFFER="${saved_buffer}"
        PREDISPLAY="${saved_predisplay}"
        POSTDISPLAY="${saved_postdisplay}"
        region_highlight=("${saved_region_highlight[@]}")
    }

    _easy-motion-setup-variables && \
    _easy-motion-save-state && \
    _easy-motion-main && \
    ret="$?"
    _easy-motion-restore-state

    return "${ret}"
}

zle -N vi-easy-motion
