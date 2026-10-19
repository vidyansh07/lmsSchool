"""Who this environment may email at all.

`EMAIL_RECIPIENT_ALLOWLIST` is empty in production: everybody may be emailed.
A staging or demo environment names who may be — entries are either a whole
address (`priya@example.com`) or a domain (`@gmail.com`) — because its
database is full of seeded accounts at real domains (`@grras.com` has real
mail servers), and a working mail service would otherwise write to them every
hour.

Every outgoing message asks this before it is handed to the mail service:
notification mail (`apps.notifications.channels`) and account mail
(`apps.accounts.emails`) alike. A refused one is recorded as not sent with
`NOT_ON_LIST`, so the account page says why.
"""

from __future__ import annotations

from django.conf import settings

NOT_ON_LIST = (
    "Not sent: this environment only emails the addresses on its recipient list, "
    "and this address is not on it."
)


def _entries() -> list[str]:
    raw = getattr(settings, "EMAIL_RECIPIENT_ALLOWLIST", None) or []
    if isinstance(raw, str):
        raw = raw.split(",")
    return [entry.strip().lower() for entry in raw if entry and entry.strip()]


def recipient_allowed(address: str) -> bool:
    entries = _entries()
    if not entries:
        return True
    address = (address or "").strip().lower()
    if not address or "@" not in address:
        return False
    domain = "@" + address.rsplit("@", 1)[1]
    return address in entries or domain in entries
