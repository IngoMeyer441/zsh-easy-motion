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
        IO,
        Iterable,
        Iterator,
        List,
        Optional,
        Text,
        Tuple,
        Union,
    )
except ImportError:
    cast = lambda t, x: x  # type: ignore  # noqa: E731
    Text = unicode if (sys.version_info.major < 3) else str  # type: ignore

VALID_MOTIONS = frozenset(("b", "B", "ge", "gE", "e", "E", "w", "W", "f", "F", "t", "T", "s", "c"))
MOTIONS_WITH_ARGUMENT = frozenset(("f", "F", "t", "T", "s"))
FORWARD_MOTIONS = frozenset(("e", "E", "w", "W", "f", "t", "s", "c"))
BACKWARD_MOTIONS = frozenset(("b", "B", "ge", "gE", "F", "T", "s", "c"))
MOTION_TO_REGEX = {
    "b": r"\b(\w)",
    "B": r"(?:^|\s)(\S)",
    "ge": r"(\w)\b",
    "gE": r"(\S)(?:\s|$)",
    "e": r"(\w)\b",
    "E": r"(\S)(?:\s|$)",
    "w": r"\b(\w)",
    "W": r"\s(\S)",
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


def parse_arguments():
    # type: () -> Tuple[int, Text, Text]
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
    # Extract cursor position
    if not argv:
        raise MissingCursorPositionError("No cursor position given.")
    if not argv[0].isdigit():
        raise InvalidCursorPositionError('The cursor position "{}" is not a number.'.format(argv[0]))
    cursor_position = int(argv.pop(0))
    # Extract text
    if not argv:
        raise MissingTextError("No text given.")
    text = " ".join(argv)
    return cursor_position, target_keys, text


def motion_to_indices(cursor_position, text, motion, motion_argument):
    # type: (int, Text, Text, Optional[Text]) -> Iterable[int]
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
        if is_forward_motion:
            text = text[cursor_position + 1 :]
            indices_offset = cursor_position + 1
        else:
            text = text[:cursor_position]
        if motion_argument is None:
            regex = re.compile(MOTION_TO_REGEX[motion])
        else:
            regex = re.compile(MOTION_TO_REGEX[motion].format(re.escape(motion_argument)))
        matches = regex.finditer(text)
        if not is_forward_motion:
            matches = reversed(list(matches))
        indices = (
            match_obj.start(i) + indices_offset
            for match_obj in matches
            for i in range(1, regex.groups + 1)
            if match_obj.start(i) >= 0
        )
    return indices


def group_indices(indices, group_length):
    # type: (Iterable[int], int) -> List[Any]

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
    if isinstance(grouped_indices, int):
        return [grouped_indices]
    else:
        return grouped_indices


def print_highlight_regions(grouped_indices, target_keys):
    # type: (Iterable[Any], Text) -> None
    def find_leaves(group_or_index):
        # type: (Union[Iterable[Any], int]) -> Iterator[int]
        if isinstance(group_or_index, int):
            yield group_or_index
        else:
            for sub_group_or_index in group_or_index:
                for leave in find_leaves(sub_group_or_index):
                    yield leave

    print("highlight_start")
    sys.stdout.flush()
    for target_key, group_or_index in zip(target_keys, grouped_indices):
        if isinstance(group_or_index, int):
            print("s {:d} {}".format(group_or_index, target_key))
            sys.stdout.flush()
        else:
            for preview_key, sub_group_or_index in zip(target_keys, group_or_index):
                for leave in find_leaves(sub_group_or_index):
                    print("p1 {:d} {}".format(leave, target_key))
                    print("p2 {:d} {}".format(leave + 1, preview_key))
                    sys.stdout.flush()
    print("highlight_end")
    sys.stdout.flush()


def print_jump_target(found_index, motion):
    # type: (int, Text) -> None
    print("jump")
    print("{:d} {}".format(found_index, motion))
    sys.stdout.flush()


def handle_user_input(cursor_position, target_keys, text):
    # type: (int, Text, Text) -> None
    fd = sys.stdin.fileno()

    def setup_terminal():
        # type: () -> List[Union[int, List[bytes]]]
        old_term_settings = termios.tcgetattr(fd)
        new_term_settings = termios.tcgetattr(fd)
        new_term_settings[3] = (
            cast(int, new_term_settings[3]) & ~termios.ICANON & ~termios.ECHO
        )  # unbuffered and no echo
        termios.tcsetattr(fd, termios.TCSAFLUSH, new_term_settings)
        return old_term_settings

    def reset_terminal(old_term_settings):
        # type: (List[Union[int, List[bytes]]]) -> None
        termios.tcsetattr(fd, termios.TCSAFLUSH, old_term_settings)

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
                motion = next_key
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
                    print_highlight_regions(grouped_indices, target_keys)
                    read_state = ReadState.TARGET
                else:
                    # The user selected a leave target, we can break now
                    print_jump_target(grouped_indices, motion)
                    break
    finally:
        reset_terminal(old_term_settings)


def main():
    # type: () -> None
    try:
        cursor_position, target_keys, text = parse_arguments()
        handle_user_input(cursor_position, target_keys, text)
    except (
        MissingTargetKeysError,
        MissingCursorPositionError,
        InvalidCursorPositionError,
        MissingTextError,
        InvalidMotionError,
        InvalidTargetError,
    ) as e:
        print(e, file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
