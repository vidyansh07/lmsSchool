"""Who hears about what, and how.

One question, asked in one place: given something that happened, which people
should be told and down which channel. Every caller asks
`channels_for(event, recipient)` rather than reading the rules itself, so the
day a channel is added there is one function to change and not nine call
sites.

The rules are the institute's policy. A person's own preference
(`NotificationPreference`) is a separate, narrower thing and is still applied
by the delivery code underneath: policy decides whether the institute sends
at all, preference decides whether this person wants that category by email.
Policy can never *add* a message somebody has opted out of.
"""

from __future__ import annotations

from .models import MessageChannelKind, MessageRecipient, MessageRule

#: The channels a rule can name, in the order the settings screen draws them.
CHANNELS: tuple[str, ...] = (
    MessageChannelKind.SMS,
    MessageChannelKind.EMAIL,
    MessageChannelKind.PUSH,
)

RECIPIENTS: tuple[str, ...] = (
    MessageRecipient.STUDENT,
    MessageRecipient.GUARDIAN,
    MessageRecipient.OWNER,
)


def channels_for(event: str, recipient: str) -> set[str]:
    """The channels this event should reach this recipient on.

    An empty set is the normal answer for most cells, and means *do not
    send*. A missing row means off, so a new event is silent until somebody
    turns it on — which is the right way round: a product that starts texting
    parents the day it is deployed has made a decision nobody took.
    """
    return set(
        MessageRule.objects.enabled()
        .filter(event=event, recipient=recipient)
        .values_list("channel", flat=True)
    )


def matrix() -> dict[str, dict[str, set[str]]]:
    """Every rule, as `{event: {recipient: {channel, …}}}`.

    One query for the whole screen. Reading it cell by cell would be
    one query per event per recipient to draw a table, which is the shape of
    mistake that only shows up once the table has rows in it.
    """
    found: dict[str, dict[str, set[str]]] = {}
    for rule in MessageRule.objects.enabled():
        found.setdefault(rule.event, {}).setdefault(rule.recipient, set()).add(rule.channel)
    return found


def set_cell(*, event: str, recipient: str, channel: str, enabled: bool) -> MessageRule:
    """Turn one cell on or off.

    `update_or_create`, so a cell that was never seeded can be switched on
    without the screen having to know whether a row exists — which is a
    question about our storage, not about the institute's policy.
    """
    rule, _created = MessageRule.objects.update_or_create(
        event=event,
        recipient=recipient,
        channel=channel,
        defaults={"is_enabled": enabled},
    )
    return rule


def audience_for(event: str, *, student) -> list[tuple[str, object, set[str]]]:
    """Who to tell about something that happened to one student, and how.

    Returns `(recipient_kind, person, channels)` for each audience the matrix
    turns on and that actually exists — a student with no guardian recorded
    produces no guardian row rather than a silent failure later, and a
    student with no owner produces no owner row.

    The *person* for a guardian is the first guardian (`is_primary`), because
    that is what "first guardian of the student" means on the settings
    screen. Sending to all of them is a cell the screen can turn on later;
    what it must not do is quietly mean "all" while saying "first".
    """
    from apps.notifications.models import MessageRecipient

    found: list[tuple[str, object, set[str]]] = []

    channels = channels_for(event, MessageRecipient.STUDENT)
    if channels and getattr(student, "user_id", None):
        found.append((MessageRecipient.STUDENT, student.user, channels))

    channels = channels_for(event, MessageRecipient.GUARDIAN)
    if channels:
        guardian = student.guardians.filter(is_primary=True).first()
        if guardian is not None:
            found.append((MessageRecipient.GUARDIAN, guardian, channels))

    channels = channels_for(event, MessageRecipient.OWNER)
    if channels and getattr(student, "owner_id", None):
        found.append((MessageRecipient.OWNER, student.owner, channels))

    return found


def deliver_for_event(
    event: str,
    *,
    student,
    kind: str,
    title: str,
    body: str = "",
    link_path: str = "",
    resource_type: str = "",
    resource_id: object = "",
) -> dict[str, int]:
    """Tell everybody the matrix says to tell, down the channels it names.

    Returns a count per channel of what was actually sent, which is how the
    one honest gap in this is reported rather than hidden:

    * **push** is the in-app notification, written for anybody with an
      account. A guardian has no account, so a guardian cell on this channel
      sends nothing — recorded in the count as zero rather than pretended.
    * **email** rides the same notification, which mails it unless the person
      has opted that category out. Their own preference still wins: policy
      decides whether the institute sends at all, never whether somebody who
      opted out gets one anyway.
    * **sms** has **no provider wired yet**. The rule is stored and counted,
      and nothing is sent. Returning the count rather than swallowing it is
      what stops this becoming a feature everybody believes is working.

    Never raises. A notification that fails must not roll back the payment
    that caused it.
    """
    from apps.notifications.models import MessageRecipient

    from . import services

    sent = {MessageChannelKind.SMS: 0, MessageChannelKind.EMAIL: 0, MessageChannelKind.PUSH: 0}
    for recipient_kind, person, channels in audience_for(event, student=student):
        wants_push = MessageChannelKind.PUSH in channels
        wants_email = MessageChannelKind.EMAIL in channels
        if MessageChannelKind.SMS in channels:
            sent[MessageChannelKind.SMS] += 1

        if recipient_kind == MessageRecipient.GUARDIAN:
            # A guardian is a name, a number and an address — not an account.
            # Nothing in-app can reach them, and the email path goes through
            # a user's own preferences, which they do not have. Counted, not
            # faked.
            continue

        if not (wants_push or wants_email):
            continue
        written = services.notify(
            recipient=person,
            kind=kind,
            title=title,
            body=body,
            link_path=link_path,
            resource_type=resource_type,
            resource_id=resource_id,
            send_email=wants_email,
        )
        if written is not None:
            if wants_push:
                sent[MessageChannelKind.PUSH] += 1
            if wants_email:
                sent[MessageChannelKind.EMAIL] += 1
    return sent
