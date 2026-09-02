"""Streaming CSV export — §8.5.

    "Do not load massive exports completely into application memory."

So an export is a generator handed to Django's ``StreamingHttpResponse``, and
nothing anywhere holds the whole result set. The report producers already
iterate with ``.iterator()``; this writes each row as it arrives and yields the
bytes.

Two things worth stating:

**Formula injection.** A cell beginning ``=``, ``+``, ``-`` or ``@`` is executed
by Excel when the file is opened. A student called ``=cmd|…`` — or a note
somebody typed — would run on the machine of whoever opened the export. Every
value is prefixed accordingly. This is the mirror image of the import-side check
in §4.6: there we refuse formulas coming in, here we neutralise them going out.

**Permissions.** An export is a report, so it runs on the same scoped queryset
and carries the same access rules. There is no "export everything" path that
skips them.
"""

from __future__ import annotations

import csv
from collections.abc import Iterable, Iterator
from typing import Any

#: Excel treats a leading one of these as the start of a formula.
_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


class _Echo:
    """A file-like object that returns what it is given.

    ``csv.writer`` needs something with ``write``; this hands the formatted line
    straight back so it can be yielded rather than buffered.
    """

    def write(self, value: str) -> str:
        return value


def sanitise(value: Any) -> str:
    """Render one cell safely for a spreadsheet."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "yes" if value else "no"
    text = str(value)
    if text.startswith(_FORMULA_PREFIXES):
        # A leading apostrophe is what Excel reads as "this is text".
        return "'" + text
    return text


def stream_csv(columns: Iterable[dict[str, str]], rows: Iterable[dict[str, Any]]) -> Iterator[str]:
    """Yield a CSV a line at a time.

    The header comes from the report's own column definitions, so a column added
    to a report appears in its export without touching this function.
    """
    writer = csv.writer(_Echo())
    keys = [column["key"] for column in columns]

    yield writer.writerow([column["label"] for column in columns])
    for row in rows:
        yield writer.writerow([sanitise(row.get(key)) for key in keys])


def filename_for(key: str) -> str:
    """A safe download name, built here rather than from anything user-supplied."""
    import re

    from django.utils import timezone

    stem = re.sub(r"[^a-z0-9_-]+", "-", key.lower()).strip("-") or "report"
    return f"{stem}-{timezone.localdate().isoformat()}.csv"
