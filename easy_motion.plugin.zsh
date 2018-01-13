_EASY_MOTION_ROOT_DIR="${0:h}"
# in a script, we cannot query if zsh is in vi operator pending mode
# -> keep track of it
_EASY_MOTION_VIOPP=0
_EASY_MOTION_TIMESTAMP_CMD="python -c 'import time; print(int(time.time() * 1000))'"

function vi-easy-motion () {
    local -a MOTIONS_WITH_ARGUMENT=( "f" "F" "t" "T" "s" )
    local -a TARGET_KEYS=( "a" "s" "d" "g" "h" "k" "l" "q" "w" "e" "r" "t" "y" "u" \
        "i" "o" "p" "z" "x" "c" "v" "b" "n" "m" "f" "j" ";" )
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

    function _easy-motion-read-motion {
        local second_motion_character

        read -k -s motion || return 1
        # 'g' -> second character is needed
        if [[ "${motion}" == "g" ]]; then
            read -k -s second_motion_character || return 1
            motion="${motion}${second_motion_character}"
        fi
        # Check if ${motion} needs an additional argument
        if (( ${MOTIONS_WITH_ARGUMENT[(I)${motion}]} )); then
            read -k -s motion_argument || return 2
        fi
        return 0
    }

    function _easy-motion-motion-to-indices {
        # Get the indices for the selected motion + optional argument
        if [[ -z "${motion_argument}" ]]; then
            motion_indices=($("${_EASY_MOTION_ROOT_DIR}/motion2indices.py" "${CURSOR}" "${motion}" "${BUFFER}" 2>/dev/null)) || \
                return 3
        else
            motion_indices=($("${_EASY_MOTION_ROOT_DIR}/motion2indices.py" "${CURSOR}" "${motion}" "${motion_argument}" "${BUFFER}" 2>/dev/null)) || \
                return 4
        fi
        return 0
    }

    function _easy-motion-display-targets {
        local i motion_index target_key

        PREDISPLAY=""
        POSTDISPLAY=""
        region_highlight=( "0 $#BUFFER fg=black,bold" )
        i=1
        while [[ "${i}" -le "${#motion_indices}" && "${i}" -le "${#TARGET_KEYS}" ]]; do
            motion_index="${motion_indices[${i}]}"
            target_key="${TARGET_KEYS[${i}]}"
            region_highlight+=( "${motion_index} $(( ${motion_index} + 1 )) fg=196,bold" )
            BUFFER[${motion_index}+1]="${target_key}"
            (( i++ ))
        done
        # Force a redisplay of the command line
        zle -R
        return 0
    }

    function _easy-motion-choose-target {
        local target_index
        local new_cursor
        read -k -s target_key || return 5
        target_index=${TARGET_KEYS[(i)${target_key}]}
        (( ${target_index} <= ${#TARGET_KEYS} )) || return 6
        (( ${target_index} <= ${#motion_indices})) || return 7
        # Move the cursor to the chosen target
        new_cursor="${motion_indices[${target_index}]}"
        if (( ${_EASY_MOTION_VIOPP} )); then
            case $motion in
                e|E|ge|gE|f|t)
                    (( new_cursor++ ))
                    ;;
                s)
                    if (( ${new_cursor} > ${CURSOR} )); then
                        (( new_cursor++ ))
                    fi
                    ;;
            esac
        fi
        CURSOR="${new_cursor}"
        zle -R
        return 0
    }

    function _easy-motion-restore-state {
        BUFFER="${saved_buffer}"
        PREDISPLAY="${saved_predisplay}"
        POSTDISPLAY="${saved_postdisplay}"
        region_highlight=("${saved_region_highlight[@]}")
        _EASY_MOTION_VIOPP=0
    }

    _easy-motion-save-state && \
    _easy-motion-read-motion && \
    _easy-motion-motion-to-indices && \
    _easy-motion-display-targets && \
    _easy-motion-choose-target
    ret="$?"
    _easy-motion-restore-state

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
