#!/usr/bin/env python
# -*- coding: utf-8 -*-

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function
from __future__ import unicode_literals

import re
import sys

try:
    from typing import (  # noqa: F401  # pylint: disable=unused-import
        cast,
        AnyStr,
        Callable,
        Dict,
        IO,
        Iterable,
        List,
        Optional,
        Text,
        Tuple,
        Union,
    )
except ImportError:
    cast = lambda t, x: x  # type: ignore  # noqa: E731
    Text = unicode if (sys.version_info.major < 3) else str  # type: ignore

PY2 = sys.version_info.major < 3  # is needed for correct mypy checking

VALID_MOTIONS = ("b", "B", "ge", "gE", "e", "E", "w", "W", "f", "F", "t", "T", "s", "c")
MOTIONS_WITH_ARGUMENT = ("f", "F", "t", "T", "s")
FORWARD_MOTIONS = ("e", "E", "w", "W", "f", "t")
BACKWARD_MOTIONS = ("b", "B", "ge", "gE", "F", "T")
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


class MissingCursorPositionError(Exception):
    pass


class InvalidCursorPositionError(Exception):
    pass


class InvalidMotionError(Exception):
    pass


class MissingMotionError(Exception):
    pass


class MissingMotionArgumentError(Exception):
    pass


class MissingTextError(Exception):
    pass


def parse_arguments():
    # type: () -> Tuple[int, Text, Text, Optional[Text]]
    if PY2:
        argv = [arg.decode("utf-8") for arg in sys.argv]
    else:
        argv = list(sys.argv)
    # Remove program name from argument vector
    argv.pop(0)
    # Extract cursor position
    if not argv:
        raise MissingCursorPositionError("No cursor position given.")
    if not argv[0].isdigit():
        raise InvalidCursorPositionError('The cursor "{}" position is not a number.'.format(argv[0]))
    cursor_position = int(argv.pop(0))
    # Extract motion
    if not argv:
        raise MissingMotionError("No motion given.")
    motion = argv.pop(0)
    if motion not in VALID_MOTIONS:
        raise InvalidMotionError('"{}" is not a valid motion argument.'.format(motion))
    # Extract motion argument (if needed)
    if motion in MOTIONS_WITH_ARGUMENT:
        if not argv:
            raise MissingMotionArgumentError('"{}" needs an argument that is missing.'.format(motion))
        motion_argument = argv.pop(0)  # type: Optional[Text]
    else:
        motion_argument = None
    # Extract text
    if not argv:
        raise MissingTextError("No text given.")
    text = " ".join(argv)
    return cursor_position, text, motion, motion_argument


def motion_to_indices(cursor_position, text, motion, motion_argument):
    # type: (int, Text, Text, Optional[Text]) -> Iterable[int]
    indices_offset = 0
    if motion in FORWARD_MOTIONS:
        text = text[cursor_position + 1 :]
        indices_offset = cursor_position + 1
    elif motion in BACKWARD_MOTIONS:
        text = text[:cursor_position]
    if motion_argument is None:
        regex = re.compile(MOTION_TO_REGEX[motion])
    else:
        regex = re.compile(MOTION_TO_REGEX[motion].format(re.escape(motion_argument)))
    matches = list(regex.finditer(text))
    if motion in BACKWARD_MOTIONS:
        matches = list(reversed(matches))
    indices = [
        match_obj.start(i) + indices_offset
        for match_obj in matches
        for i in range(1, regex.groups + 1)
        if match_obj.start(i) >= 0
    ]
    return indices


def main():
    # type: () -> None
    try:
        cursor_position, text, motion, motion_argument = parse_arguments()
        indices = motion_to_indices(cursor_position, text, motion, motion_argument)
        print(" ".join(Text(index) for index in indices))
    except (
        MissingCursorPositionError,
        InvalidCursorPositionError,
        InvalidMotionError,
        MissingMotionError,
        MissingMotionArgumentError,
        MissingTextError,
    ) as e:
        print(e, file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
