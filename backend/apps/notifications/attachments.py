"""Documents an email can carry, drawn at the moment it is sent.

The outbox stores a reference — `{"kind": "fee_receipt", "id": "<uuid>"}` —
and the app that owns the document registers how to draw it. Notifications
therefore depends on nobody: the fees app teaches it about receipts in its own
`AppConfig.ready`, and a kind nobody registered is reported, not guessed at.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass


@dataclass(frozen=True)
class RenderedAttachment:
    filename: str
    content: bytes
    mimetype: str = "application/pdf"


Renderer = Callable[[str], RenderedAttachment]

_RENDERERS: dict[str, Renderer] = {}


class UnknownAttachment(LookupError):
    """A message names a document kind, or a record, that cannot be drawn."""


def register(kind: str, renderer: Renderer) -> None:
    _RENDERERS[kind] = renderer


def render(reference: dict) -> RenderedAttachment:
    kind = str(reference.get("kind", ""))
    renderer = _RENDERERS.get(kind)
    if renderer is None:
        raise UnknownAttachment(f"No renderer for attachment kind {kind!r}.")
    return renderer(str(reference.get("id", "")))


def reference(kind: str, record_id) -> dict[str, str]:
    """The outbox's form of an attachment — the one to filter on, too."""
    return {"kind": kind, "id": str(record_id)}
