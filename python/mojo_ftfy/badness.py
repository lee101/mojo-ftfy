"""Conservative mojibake detection used to gate encoding repairs."""

from __future__ import annotations

import warnings

from ._lib import badness as _mojo_badness


def badness(text: str) -> int:
    return _mojo_badness(text)


def is_bad(text: str) -> bool:
    return badness(text) > 0


def sequence_weirdness(text: str) -> int:
    warnings.warn(
        "sequence_weirdness is deprecated; use badness instead",
        DeprecationWarning,
        stacklevel=2,
    )
    return badness(text)
