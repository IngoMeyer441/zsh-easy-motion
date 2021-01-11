#!/usr/bin/env python
# -*- coding: utf-8 -*-

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function
from __future__ import unicode_literals

import os
import re
import sys
import termios

PY2 = sys.version_info.major < 3  # is needed for correct mypy checking

if PY2:
    from itertools import izip_longest as zip_longest
else:
    from itertools import zip_longest

try:
    from typing import (  # noqa: F401  # pylint: disable=unused-import
        cast,
        Any,
        AnyStr,
        Callable,
        Dict,
        Generator,
        IO,
        Iterable,
        Iterator,
        List,
        Optional,
        Tuple,
        Union,
    )
except ImportError:
    cast = lambda t, x: x  # type: ignore  # noqa: E731

if PY2:
    str = unicode

VALID_MOTIONS = frozenset(("b", "B", "ge", "gE", "e", "E", "w", "W", "j", "J", "k", "K", "f", "F", "t", "T", "s", "c"))
MOTIONS_WITH_ARGUMENT = frozenset(("f", "F", "t", "T", "s"))
FORWARD_MOTIONS = frozenset(("e", "E", "w", "W", "j", "J", "f", "t", "s", "c"))
BACKWARD_MOTIONS = frozenset(("b", "B", "ge", "gE", "k", "K", "F", "T", "s", "c"))
LINEWISE_MOTIONS = frozenset(("j", "J", "k", "K"))
VIOPP_INCREMENT_CURSOR_MOTIONS = frozenset(("e", "E", "ge", "gE", "f", "t"))
VIOPP_INCREMENT_CURSOR_ON_FORWARD_MOTIONS = frozenset(("s"))
MOTION_TO_REGEX = {
    "b": r"\b(\w)",
    "B": r"(?:^|\s)(\S)",
    "ge": r"(\w)\b",
    "gE": r"(\S)(?:\s|$)",
    "e": r"(\w)\b",
    "E": r"(\S)(?:\s|$)",
    "w": r"\b(\w)",
    "W": r"\s(\S)",
    "j": r"^(?:\s*)(\S)",
    "J": r"(\S)(?:\s*)$",
    "k": r"^(?:\s*)(\S)",
    "K": r"(\S)(?:\s*)$",
    "f": r"({})",
    "F": r"({})",
    "t": r"(.){}",
    "T": r"{}(.)",
    "s": r"({})",
    "c": r"(?:_(\w))|(?:[a-z]([A-Z]))",
}


class MissingTargetKeysError(Exception):
    pass


class MissingCursorPositionError(Exception):
    pass


class InvalidCursorPositionError(Exception):
    pass


class MissingVioppFlagError(Exception):
    pass


class InvalidVioppFlagError(Exception):
    pass


class MissingTextError(Exception):
    pass


class InvalidMotionError(Exception):
    pass


class InvalidTargetError(Exception):
    pass


class ReadState(object):
    MOTION = 0
    MOTION_ARGUMENT = 1
    TARGET = 2
    HIGHLIGHT = 3


class JumpTarget(object):
    DIRECT = 0
    GROUP = 1
    PREVIEW = 2


def str2bool(bool_text):
    # type: (str) -> bool
    if bool_text.lower() in ("true", "on", "yes", "1"):
        return True
    elif bool_text.lower() in ("false", "off", "no", "0"):
        return False
    raise ValueError


def parse_arguments():
    # type: () -> Tuple[int, bool, str, str]
    if PY2:
        argv = [arg.decode("utf-8") for arg in sys.argv]
    else:
        argv = list(sys.argv)
    # Remove program name from argument vector
    argv.pop(0)
    # Extract target keys
    if not argv:
        raise MissingTargetKeysError("No target keys given.")
    target_keys = argv.pop(0)
    if len(target_keys) < 2:
        raise MissingTargetKeysError("At least two target keys are needed.")
    # Extract cursor position
    if not argv:
        raise MissingCursorPositionError("No cursor position given.")
    if not argv[0].isdigit():
        raise InvalidCursorPositionError('The cursor position "{}" is not a number.'.format(argv[0]))
    cursor_position = int(argv.pop(0))
    # Extract viopp flag
    if not argv:
        raise MissingVioppFlagError("No viopp flag given.")
    try:
        is_in_viopp = str2bool(argv.pop(0))
    except ValueError:
        raise InvalidVioppFlagError('The viopp flag "{}" is not a valid boolean flag.'.format(argv[0]))
    # Extract text
    if not argv:
        raise MissingTextError("No text given.")
    text = " ".join(argv)
    return cursor_position, is_in_viopp, target_keys, text


def find_first_line_end(cursor_position, text):
    # type: (int, str) -> int
    first_line_end = re.match(r".*($)", text[cursor_position:], flags=re.MULTILINE)
    assert first_line_end is not None
    return first_line_end.end(1)


def find_latest_line_start(cursor_position, text):
    # type: (int, str) -> int
    latest_line_start = re.match(r"(?:.*)(^)", text[: cursor_position + 1], flags=re.MULTILINE | re.DOTALL)
    assert latest_line_start is not None
    return latest_line_start.start(1)


def adjust_text(cursor_position, text, is_forward_motion, motion):
    # type: (int, str, bool, str) -> Tuple[str, int]
    indices_offset = 0
    if is_forward_motion:
        if motion in LINEWISE_MOTIONS:
            first_line_end_index = find_first_line_end(cursor_position, text)
            text = text[cursor_position + first_line_end_index :]
            indices_offset = cursor_position + first_line_end_index
        else:
            # Take one character more at the start to exclude wrong positives for word beginnings
            # Pad one character at the end to be compatible with the handling of word endings (see below)
            text = text[cursor_position:] + " "
            indices_offset = cursor_position
    else:
        if motion in LINEWISE_MOTIONS:
            latest_line_start_index = find_latest_line_start(cursor_position, text)
            text = text[:latest_line_start_index]
        else:
            # Take one character more at the end to exclude wrong positives for word endings
            # Pad one character at the start to be compatible with the handling of word beginnings (see above)
            text = " " + text[: cursor_position + 1]
            indices_offset = -1
    return text, indices_offset


def motion_to_indices(cursor_position, text, motion, motion_argument):
    # type: (int, str, str, Optional[str]) -> Iterable[int]
    indices_offset = 0
    if motion in FORWARD_MOTIONS and motion in BACKWARD_MOTIONS:
        # Split the motion into the forward and backward motion and handle these recursively
        forward_motion_indices = motion_to_indices(cursor_position, text, motion + ">", motion_argument)
        backward_motion_indices = motion_to_indices(cursor_position, text, motion + "<", motion_argument)
        # Create a generator which yields the indices round-robin
        indices = (
            index
            for index_pair in zip_longest(forward_motion_indices, backward_motion_indices)
            for index in index_pair
            if index is not None
        )
    else:
        is_forward_motion = motion in FORWARD_MOTIONS or motion.endswith(">")
        if motion.endswith(">") or motion.endswith("<"):
            motion = motion[:-1]
        text, indices_offset = adjust_text(cursor_position, text, is_forward_motion, motion)
        if motion_argument is None:
            regex = re.compile(MOTION_TO_REGEX[motion], flags=re.MULTILINE)
        else:
            regex = re.compile(MOTION_TO_REGEX[motion].format(re.escape(motion_argument)), flags=re.MULTILINE)
        matches = regex.finditer(text)
        if not is_forward_motion:
            matches = reversed(list(matches))
        is_linewise_motion = motion in LINEWISE_MOTIONS
        indices = (
            match_obj.start(i) + indices_offset
            for match_obj in matches
            for i in range(1, regex.groups + 1)
            if match_obj.start(i) >= 0 and (is_linewise_motion or (0 < match_obj.start(i) < len(text) - 1))
        )
    return indices


def group_indices(indices, group_length):
    # type: (Iterable[int], int) -> Union[List[Any], int]

    def group(indices, group_length):
        # type: (Iterable[int], int) -> Union[List[Any], int]
        def find_required_slot_sizes(num_indices, group_length):
            # type: (int, int) -> List[int]
            if num_indices <= group_length:
                slot_sizes = num_indices * [1]
            else:
                slot_sizes = group_length * [1]
                next_increase_slot = group_length - 1
                while sum(slot_sizes) < num_indices:
                    slot_sizes[next_increase_slot] *= group_length
                    next_increase_slot = (next_increase_slot - 1 + group_length) % group_length
                previous_increase_slot = (next_increase_slot + 1) % group_length
                # Always fill rear slots first
                slot_sizes[previous_increase_slot] -= sum(slot_sizes) - num_indices
            return slot_sizes

        indices_as_tuple = tuple(indices)
        num_indices = len(indices_as_tuple)
        if num_indices == 1:
            return indices_as_tuple[0]
        slot_sizes = find_required_slot_sizes(num_indices, group_length)
        slot_start_indices = [0]
        for slot_size in slot_sizes[:-1]:
            slot_start_indices.append(slot_start_indices[-1] + slot_size)
        grouped_indices = [
            group(indices_as_tuple[slot_start_index : slot_start_index + slot_size], group_length)
            for slot_start_index, slot_size in zip(slot_start_indices, slot_sizes)
        ]
        return grouped_indices

    grouped_indices = group(indices, group_length)
    return grouped_indices


def generate_jump_targets(grouped_indices, target_keys):
    # type: (Iterable[Any], str) -> Generator[Tuple[int, int, str], None, None]
    def find_leaves(group_or_index):
        # type: (Union[Iterable[Any], int]) -> Iterator[int]
        if isinstance(group_or_index, int):
            yield group_or_index
        else:
            for sub_group_or_index in group_or_index:
                for leave in find_leaves(sub_group_or_index):
                    yield leave

    for target_key, group_or_index in zip(target_keys, grouped_indices):
        if isinstance(group_or_index, int):
            yield (JumpTarget.DIRECT, group_or_index, target_key)
        else:
            for preview_key, sub_group_or_index in zip(target_keys, group_or_index):
                for leave in find_leaves(sub_group_or_index):
                    yield (JumpTarget.GROUP, leave, target_key)
                    yield (JumpTarget.PREVIEW, leave + 1, preview_key)


def print_highlight_regions(grouped_indices, target_keys):
    # type: (Iterable[Any], str) -> None
    target_type_to_code = {
        JumpTarget.DIRECT: "s",
        JumpTarget.GROUP: "p1",
        JumpTarget.PREVIEW: "p2",
    }
    jump_targets = sorted(generate_jump_targets(grouped_indices, target_keys), key=lambda x: x[1])
    print("highlight_start")
    sys.stdout.flush()
    for target_type, text_pos, target_key in jump_targets:
        print("{} {:d} {}".format(target_type_to_code[target_type], text_pos, target_key))
        sys.stdout.flush()
    print("highlight_end")
    sys.stdout.flush()


def adjust_jump_target(cursor_position, found_index, is_in_viopp, text, motion):
    # type: (int, int, bool, str, str) -> Tuple[int, Optional[int], Optional[str]]
    def extend_to_line_border(lower_index, upper_index):
        # type: (int, int) -> Tuple[int, int]
        latest_line_start = re.match(r"(?:.*)(^)", text[: lower_index + 1], flags=re.MULTILINE | re.DOTALL)
        assert latest_line_start is not None
        lower_index = latest_line_start.start(1) - 1
        first_line_end = re.match(r".*($)", text[upper_index:], flags=re.MULTILINE)
        assert first_line_end is not None
        upper_index += first_line_end.end(1)
        return (lower_index, upper_index)

    mark = None
    extra_motion = None
    if is_in_viopp:
        if motion in VIOPP_INCREMENT_CURSOR_MOTIONS or (
            motion in VIOPP_INCREMENT_CURSOR_ON_FORWARD_MOTIONS and found_index > cursor_position
        ):
            found_index += 1
        elif motion in LINEWISE_MOTIONS:
            if found_index > cursor_position:
                mark, found_index = extend_to_line_border(cursor_position, found_index)
            else:
                found_index, mark = extend_to_line_border(found_index, cursor_position)
            extra_motion = "W"

    return (found_index, mark, extra_motion)


def print_jump_target(found_index, mark=None, extra_motion=None):
    # type: (int, Optional[int], Optional[str]) -> None
    print("jump")
    if mark is None:
        print("{:d}".format(found_index))
    elif extra_motion is None:
        print("{:d} {:d}".format(found_index, mark))
    else:
        print("{:d} {:d} {}".format(found_index, mark, extra_motion))
    sys.stdout.flush()


def handle_user_input(cursor_position, is_in_viopp, target_keys, text):
    # type: (int, bool, str, str) -> None
    fd = sys.stdin.fileno()

    def setup_terminal():
        # type: () -> List[Union[int, List[bytes]]]
        old_term_settings = termios.tcgetattr(fd)
        new_term_settings = termios.tcgetattr(fd)
        new_term_settings[3] = (
            cast(int, new_term_settings[3]) & ~termios.ICANON & ~termios.ECHO
        )  # unbuffered and no echo
        termios.tcsetattr(fd, termios.TCSADRAIN, new_term_settings)
        return old_term_settings

    def reset_terminal(old_term_settings):
        # type: (List[Union[int, List[bytes]]]) -> None
        termios.tcsetattr(fd, termios.TCSADRAIN, old_term_settings)

    old_term_settings = setup_terminal()

    read_state = ReadState.MOTION
    motion = None
    motion_argument = None
    target = None
    grouped_indices = None
    try:
        while True:
            if read_state != ReadState.HIGHLIGHT:
                next_key = os.read(fd, 80)[:1].decode("ascii")  # blocks until any amount of bytes is available
            if read_state == ReadState.MOTION:
                if motion is None:
                    motion = next_key
                else:
                    motion += next_key
                if motion != "g":  # `g` always needs a second key press
                    if motion not in VALID_MOTIONS:
                        raise InvalidMotionError('The key "{}" is no valid motion.'.format(motion))
                    if motion in MOTIONS_WITH_ARGUMENT:
                        read_state = ReadState.MOTION_ARGUMENT
                    else:
                        read_state = ReadState.HIGHLIGHT
            elif read_state == ReadState.MOTION_ARGUMENT:
                motion_argument = next_key
                read_state = ReadState.HIGHLIGHT
            elif read_state == ReadState.TARGET:
                target = next_key
                if target not in target_keys:
                    raise InvalidTargetError('The key "{}" is no valid target.'.format(target))
                read_state = ReadState.HIGHLIGHT
            elif read_state == ReadState.HIGHLIGHT:
                assert motion is not None
                if grouped_indices is None:
                    indices = motion_to_indices(cursor_position, text, motion, motion_argument)
                    grouped_indices = group_indices(indices, len(target_keys))
                else:
                    try:
                        # pylint: disable=unsubscriptable-object
                        grouped_indices = grouped_indices[target_keys.index(target)]
                    except IndexError:
                        raise InvalidTargetError('The key "{}" is no valid target.'.format(target))
                if not isinstance(grouped_indices, int):
                    if not grouped_indices:  # if no targets found
                        break
                    print_highlight_regions(grouped_indices, target_keys)
                    read_state = ReadState.TARGET
                else:
                    # The user selected a leave target, we can break now
                    found_index, mark, extra_motion = adjust_jump_target(
                        cursor_position, grouped_indices, is_in_viopp, text, motion
                    )
                    print_jump_target(found_index, mark, extra_motion)
                    break
    finally:
        reset_terminal(old_term_settings)


def main():
    # type: () -> None
    try:
        cursor_position, is_in_viopp, target_keys, text = parse_arguments()
        handle_user_input(cursor_position, is_in_viopp, target_keys, text)
    except (
        MissingTargetKeysError,
        MissingCursorPositionError,
        InvalidCursorPositionError,
        MissingVioppFlagError,
        InvalidVioppFlagError,
        MissingTextError,
        InvalidMotionError,
        InvalidTargetError,
    ) as e:
        print(e, file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
