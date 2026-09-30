"""Console output helpers that cannot fail on legacy Windows encodings."""

from __future__ import annotations

import sys
from typing import Any, TextIO


def safe_print(
    *values: Any,
    sep: str = " ",
    end: str = "\n",
    file: TextIO | None = None,
    flush: bool = False,
) -> None:
    stream = file or sys.stdout
    text = sep.join(str(value) for value in values)
    encoding = getattr(stream, "encoding", None) or "utf-8"
    safe_text = text.encode(encoding, errors="backslashreplace").decode(encoding)
    print(safe_text, end=end, file=stream, flush=flush)
