_EASY_MOTION_ROOT_DIR="${0:h}"

function _easy-motion () {
    local -a MOTIONS_WITH_ARGUMENT=( "f" "F" "t" "T" "s" )
    local -a TARGET_KEYS=( "a" "s" "d" "g" "h" "k" "l" "q" "w" "e" "r" "t" "y" "u" \
        "i" "o" "p" "z" "x" "c" "v" "b" "n" "m" "f" "j" ";" )
    local motion
    local motion_argument
    local -a motion_indices
    local target_key
    local saved_buffer
    local ret

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
            motion_indices=($("${_EASY_MOTION_ROOT_DIR}/motion2indices.py" "${CURSOR}" "${motion}" "${BUFFER}")) || \
                return 3
        else
            motion_indices=($("${_EASY_MOTION_ROOT_DIR}/motion2indices.py" "${CURSOR}" "${motion}" "${motion_argument}" "${BUFFER}")) || \
                return 4
        fi
        return 0
    }

    function _easy-motion-display-targets {
        local i motion_index target_key

        saved_buffer="${BUFFER}"
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
        read -k -s target_key || return 5
        target_index=${TARGET_KEYS[(i)${target_key}]}
        (( ${target_index} <= ${#TARGET_KEYS} )) || return 6
        (( ${target_index} <= ${#motion_indices})) || return 7
        # Move the cursor to the chosen target
        CURSOR="${motion_indices[${target_index}]}"
        zle -R
        return 0
    }

    function _easy-motion-clean-highlight {
        region_highlight=()
        BUFFER="${saved_buffer}"
    }

    _easy-motion-read-motion && \
    _easy-motion-motion-to-indices && \
    _easy-motion-display-targets && \
    _easy-motion-choose-target
    ret="$?"
    _easy-motion-clean-highlight

    return "${ret}"
}

zle -N _easy-motion
