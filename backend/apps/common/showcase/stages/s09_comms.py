"""Stage 9 — everything that talks to people: announcements, threads, mail, rules.

Creates, through the services and idempotently:

* **Announcements** (``apps.announcements.services``): one per audience kind.
  The *everyone* notice is published once and kept short, because
  ``publish`` writes one ``Notification`` per active account — on staging
  that is every imported SITP address too. A course notice, a batch notice
  on the headline student's cohort (with an expiry), a *role* notice to the
  placement coordinators (stage 2's custom role, or the system role of that
  kind when the custom one is missing), a *branch* notice for Pune — all
  published and backdated across the last three weeks, with the fan-out
  notifications backdated to match. Then the other states: the trainers'
  notice is **scheduled** for a future ``publish_at``, a certificates notice
  on the completed cohort is published and **archived**, a guest-lecture
  notice is scheduled and **cancelled**, and a *selected-people* notice is
  left in **draft**. The everyone notice is **pinned**.
  Idempotent by ``(title, body starts with the marker)`` through
  ``Announcement.all_objects``, so a notice a later stage bins is found in
  the bin rather than made again.

* **Discussions** (``apps.discussions.services``): ten threads by students
  on the headline student's active batch and two other active cohorts —
  most answered by the batch's own trainer (``reply`` derives
  ``is_trainer_response`` from the batch's trainer), three unanswered, one
  **pinned**, one **closed**, one reply **hidden** with a reason. Every
  thread, reply and the notifications they raised are backdated so the
  board reads as weeks of conversation. Idempotent by ``(batch, title)``.

* **Notifications**: every other notification of the six headline accounts
  (owner, MAIN admin/manager/counsellor, headline trainer and student) is
  marked read through ``mark_read``, the newest always left unread, so both
  states show on the bell.

* **Communication** (``apps.communication.services``): the seven
  migration-seeded email templates get a second, real version —
  ``create_draft_version`` → ``update_draft_version`` → ``approve_version``
  → ``publish_version`` — with a variable allowlist; found when the
  published version already carries this content. Three custom templates:
  an **in-app** one (kind must be a ``NotificationKind``) published, an
  **email** one left *approved*, a **WhatsApp** one left *draft* with a
  provider template id. Then ``manual_send`` of one published email
  template to the headline cohort with the exact recomputed
  ``confirm_count`` — ``Delivery`` rows, one per student — and the delivery
  states: **cancelled** through ``cancel_delivery`` while still queued;
  **failed** by sending the WhatsApp draft through ``create_deliveries`` +
  ``dispatch_delivery`` to two opted-in students, which the Null provider
  refuses with its own reason (the retry affordance needs exactly that);
  **sent** by the real dispatch task at commit. See
  :func:`_park_deliveries` for the two transient states and *delivered*.

* **Forms** (``apps.forms.services``): a custom form per entity —
  placement readiness (activity), onboarding (student), registration
  source, trainer quarterly review — each with v1 published and a newer v2
  **draft** cloned from it; between them every ``FormFieldType`` appears on
  a published version. A fifth, legacy feedback form is published and then
  **archived** — the one write here with no service (see
  :func:`_ensure_form`). Idempotent by slug through ``all_objects``.

* **Automation** (``apps.automation.services``): the nine seeded rules stay
  active. One custom rule is created active by the superadmin (the author
  must hold every action's permission) and **paused** with a reason; a
  second, using ``send_email`` with a seeded template key, is left in
  **draft**. ``AutomationRun`` rows are never written here — the dispatches
  stages 6-8 triggered wrote them; this stage only counts and reports them.

Leaves in ``ctx``: nothing new.

Why some delivery states are written without a service
-------------------------------------------------------
A ``Delivery`` is *queued* only between ``create_deliveries`` and the
dispatch task, and *processing* only inside that task. Under eager Celery
(test and local settings, and the staging clone this runs on) the task fires
in the stage's own ``on_commit`` and moves every row to *sent* before anyone
can look. *Delivered* has exactly one producer, the WhatsApp webhook, which
needs a provider message id no Null-provider send ever gets. So three rows
of the manual send are parked in those states by a queryset ``update()``
registered on commit *after* the dispatch hooks, i.e. after the real send
already happened. On a deployment with a live worker the queued and
processing rows would be picked up and sent again; that is harmless — the
task re-reads state and a second send of a demo notice is the worst case.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from time import perf_counter
from typing import Any

from django.db import transaction
from django.db.models import Count
from django.utils import timezone

from apps.accounts.models import User, UserRole
from apps.announcements.models import Announcement, Audience
from apps.announcements.services import (
    archive,
    cancel_scheduled,
    create_announcement,
    publish,
    schedule,
)
from apps.authorization.models import Role
from apps.automation.models import (
    AutomationRule,
    AutomationRuleStatus,
    AutomationRun,
    AutomationTrigger,
)
from apps.automation.services import create_rule, pause_rule
from apps.batches.models import Batch
from apps.communication.models import (
    Delivery,
    DeliveryState,
    MessageChannel,
    MessageTemplate,
    TemplateVersion,
)
from apps.communication.providers import NullWhatsAppProvider, get_provider
from apps.communication.services import (
    approve_version,
    cancel_delivery,
    create_deliveries,
    create_template,
    dispatch_delivery,
    manual_send,
    resolve_recipients,
    update_draft_version,
)
from apps.communication.services import create_draft_version as create_template_draft
from apps.communication.services import publish_version as publish_template_version
from apps.discussions.models import Reply, Thread
from apps.discussions.services import create_thread, hide_reply, set_closed, set_pinned
from apps.discussions.services import reply as reply_to
from apps.forms.models import (
    FormDefinition,
    FormDefinitionStatus,
    FormEntity,
    FormFieldType,
    FormVersion,
    FormVersionStatus,
)
from apps.forms.services import create_definition, set_fields
from apps.forms.services import create_draft_version as create_form_draft
from apps.forms.services import publish_version as publish_form_version
from apps.notifications.models import Notification, NotificationKind
from apps.notifications.services import mark_read

from ..context import MARKER, Context, batch_key
from ..roster import MAIN, PUNE
from .s04_batches import SPECS

#: Stage 4's batches by spec key → name, so this stage names cohorts the way
#: that stage did and finds them through the same ``batch_key``.
_BATCH_NAMES: dict[str, str] = {spec.key: spec.name for spec in SPECS}

#: The headline student's active cohort (stage 4: ``headline=True``, active).
HEADLINE_BATCH = "a2"
#: The completed cohort the archived certificates notice went to.
COMPLETED_BATCH = "c1"

#: The published email template the manual send uses.
SEND_TEMPLATE_KEY = "email.result_published"
#: The WhatsApp draft the failed sends go through.
WHATSAPP_TEMPLATE_KEY = "whatsapp.class_reminder"


def run(ctx: Context) -> None:
    if ctx.superadmin is None:
        raise RuntimeError("No superadmin yet: run the organisation stage first.")
    owner = ctx.superadmin

    _timed(ctx, "templates", lambda: _ensure_templates(ctx, owner))
    _timed(ctx, "announcements", lambda: _ensure_announcements(ctx))
    _timed(ctx, "discussions", lambda: _ensure_discussions(ctx))
    _timed(ctx, "deliveries", lambda: _ensure_deliveries(ctx, owner))
    _timed(ctx, "forms", lambda: _ensure_forms(ctx, owner))
    _timed(ctx, "automation", lambda: _ensure_automation(ctx, owner))
    # Last, so the notifications this stage raised are among those read.
    _timed(ctx, "notifications", lambda: _ensure_reads(ctx))


def _timed(ctx: Context, what: str, step: Callable[[], Any]) -> None:
    started = perf_counter()
    step()
    ctx.out(f"comms/{what}: {perf_counter() - started:.1f}s")


def _batch(ctx: Context, key: str) -> Batch | None:
    return ctx.showcase_batches.get(batch_key(_BATCH_NAMES[key]))


def _backdate_many(queryset, **fields: Any) -> int:
    """:meth:`Context.backdate` for a set of rows — the same queryset
    ``update()``, no ``save()`` hooks, no ``auto_now`` — for the fan-out
    notifications a publish writes by the hundred, where one update per row
    would be the slowest thing in the stage."""
    return queryset.update(**fields)


# ---------------------------------------------------------------------------
# Announcements
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AnnouncementSpec:
    key: str
    title: str
    body: str
    audience: str
    #: ``batch:a2``, ``course:rhcsa``, ``branch:PUNE``, ``role`` or ``""``.
    target: str
    #: Roster local part of the author.
    actor: str
    #: published, scheduled, draft, archived, cancelled.
    outcome: str
    days_ago: int = 0
    hour: int = 10
    minute: int = 0
    pinned: bool = False
    expires_in_days: int | None = None
    #: For the selected audience: how many of the headline cohort to name.
    selected: int = 0


ANNOUNCEMENTS: tuple[AnnouncementSpec, ...] = (
    AnnouncementSpec(
        "portal", "Welcome to the new Grras portal",
        "Timetables, attendance, results and fees are now in one place. Sign in with "
        "your registered email; the helpdesk is on extension 204.",
        Audience.EVERYONE, "", "owner", "published", days_ago=21, hour=10, pinned=True,
    ),
    AnnouncementSpec(
        "rhcsa-exam", "RHCSA exam slots for October",
        "Red Hat exam slots on 14, 21 and 28 October are open. Tell your trainer which "
        "date you want by Friday; each sitting takes twelve candidates.",
        Audience.COURSE, "course:rhcsa", "admin", "published", days_ago=12, hour=11, minute=30,
    ),
    AnnouncementSpec(
        "lab-move", "Lab 1 moves to the second floor from Monday",
        "The DevOps cohort meets in the new Lab 1 (second floor, next to the library) "
        "from Monday. Same time, better machines; bring your lab notebook.",
        Audience.BATCH, f"batch:{HEADLINE_BATCH}", "admin", "published",
        days_ago=5, hour=9, minute=15, expires_in_days=21,
    ),
    AnnouncementSpec(
        "placement-shortlists", "Placement drive: shortlists due Friday",
        "Send the shortlist for the 18 October drive to placements@grras.com by Friday "
        "evening — name, cohort, mock-interview score and resume link.",
        Audience.ROLE, "role", "owner", "published", days_ago=8, hour=16,
    ),
    AnnouncementSpec(
        "pune-parking", "Pune centre: two-wheeler parking moves to the basement",
        "From Thursday, two-wheelers park in the basement; the front lot is reserved for "
        "visitors. Collect a parking sticker from reception.",
        Audience.BRANCH, f"branch:{PUNE}", "admin.pune", "published", days_ago=2, hour=8,
        minute=45,
    ),
    AnnouncementSpec(
        "trainer-meet", "Trainer meeting this Saturday at 10:00",
        "Monthly trainer meeting in the conference room: October timetable, lab upgrades "
        "and the placement calendar. Bring your batch progress sheets.",
        Audience.TRAINERS, "", "admin", "scheduled",
    ),
    AnnouncementSpec(
        "stipend-forms", "Internship stipend forms",
        "Your internship stipend form is ready for signature at the accounts desk. "
        "Bring a cancelled cheque or a bank passbook copy.",
        Audience.SELECTED, "", "admin", "draft", selected=3,
    ),
    AnnouncementSpec(
        "certs-ready", "RHCSA certificates ready for collection",
        "Certificates for the evening RHCSA cohort are at reception. Collect them on any "
        "weekday between 10:00 and 18:00 with a photo ID.",
        Audience.BATCH, f"batch:{COMPLETED_BATCH}", "admin", "archived", days_ago=40, hour=12,
    ),
    AnnouncementSpec(
        "guest-lecture", "Guest lecture on Kubernetes security postponed",
        "The guest lecture planned for this week is postponed; a new date follows once "
        "the speaker confirms.",
        Audience.BRANCH, f"branch:{MAIN}", "admin", "cancelled",
    ),
)  # fmt: skip


def _ensure_announcements(ctx: Context) -> None:
    for spec in ANNOUNCEMENTS:
        target = _announcement_target(ctx, spec)
        if target is None:
            ctx.out(f"announcement '{spec.title}': skipped (no {spec.target or 'recipients'})")
            continue
        existing = Announcement.all_objects.filter(
            title=spec.title, body__startswith=MARKER
        ).first()
        if existing is not None:
            ctx.found_existing("announcement")
            ctx.out(f"announcement '{spec.title}': found ({existing.status})")
            continue

        actor = ctx.users.get(spec.actor) or ctx.superadmin
        recipients = target.pop("recipients", None)
        expires_at = (
            ctx.at(ctx.days_ahead(spec.expires_in_days), 23, 59) if spec.expires_in_days else None
        )
        row = create_announcement(
            actor=actor,
            recipients=recipients,
            title=spec.title,
            body=ctx.note(spec.body),
            audience=spec.audience,
            is_pinned=spec.pinned,
            expires_at=expires_at,
            **target,
        )
        _settle_announcement(ctx, row, actor, spec)
        ctx.created("announcement")
        ctx.out(f"announcement '{spec.title}': created ({row.status})")


def _announcement_target(ctx: Context, spec: AnnouncementSpec) -> dict[str, Any] | None:
    """The target fields for the audience, or ``None`` when the database has
    no row to point at (a course the courses stage did not make, a cohort
    with nobody on it)."""
    kind, _, name = spec.target.partition(":")
    if kind == "batch":
        batch = _batch(ctx, name)
        return None if batch is None else {"batch": batch}
    if kind == "course":
        course = ctx.courses.get(name)
        return None if course is None else {"course": course}
    if kind == "branch":
        return {"branch": ctx.branch(name)}
    if kind == "role":
        role = ctx.roles.get("placement-coordinator") or (
            Role.objects.filter(is_system=True, kind=UserRole.COUNSELLOR).order_by("slug").first()
        )
        return None if role is None else {"role": role}
    if spec.audience == Audience.SELECTED:
        batch = _batch(ctx, HEADLINE_BATCH)
        people = _students_of(ctx, batch)[: spec.selected] if batch is not None else []
        return None if not people else {"recipients": people}
    return {}


def _settle_announcement(
    ctx: Context, row: Announcement, actor: User, spec: AnnouncementSpec
) -> None:
    """Walk the new draft to the state the spec names, then backdate it.

    Backdating comes after the last service call on the row, and the fan-out
    notifications a publish wrote are moved to the same moment: a notice
    published three weeks ago whose bell rang this morning is a giveaway.
    """
    when = ctx.at(ctx.days_ago(spec.days_ago), spec.hour, spec.minute)
    if spec.outcome in ("published", "archived"):
        publish(announcement=row, actor=actor)
        if spec.outcome == "archived":
            archive(announcement=row, actor=actor)
        told = _backdate_many(
            Notification.objects.filter(resource_type="announcement", resource_id=str(row.pk)),
            created_at=when,
            updated_at=when,
        )
        ctx.out(f"announcement '{spec.title}': told {told}")
        ctx.backdate(row, created_at=when, updated_at=when, published_at=when)
        return
    if spec.outcome in ("scheduled", "cancelled"):
        schedule(announcement=row, actor=actor, publish_at=ctx.at(ctx.days_ahead(3), 9, 0))
        if spec.outcome == "cancelled":
            cancel_scheduled(announcement=row, actor=actor)
    # A draft, a scheduled or a cancelled notice was written yesterday.
    when = ctx.at(ctx.days_ago(1), 15, 20)
    ctx.backdate(row, created_at=when, updated_at=when)


# ---------------------------------------------------------------------------
# Discussions
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ReplySpec:
    #: ``trainer`` or a student index into the batch's author list.
    who: str | int
    body: str
    hours_later: int
    hidden_reason: str = ""


@dataclass(frozen=True)
class ThreadSpec:
    batch: str
    title: str
    body: str
    #: Index into the batch's author list (the headline student is 0 on a2).
    author: int
    days_ago: int
    hour: int
    minute: int = 0
    replies: tuple[ReplySpec, ...] = ()
    pinned: bool = False
    closed: bool = False


THREADS: tuple[ThreadSpec, ...] = (
    # --- The headline cohort: DevOps, taught by the headline trainer ----------
    ThreadSpec(
        HEADLINE_BATCH, "Docker build keeps failing at the pip install step",
        "My Dockerfile from Tuesday's lab dies on `pip install -r requirements.txt` with "
        "'No space left on device', but `df -h` on the host shows 40G free. Same "
        "Dockerfile works on my classmate's laptop.",
        0, 20, 19, 40,
        replies=(
            ReplySpec("trainer",
                      "That is the wheel cache filling the build container's /tmp, not the "
                      "host. Pin the base image to python:3.12-slim and add --no-cache-dir "
                      "to the pip line; we will cover multi-stage builds on Thursday.", 14),
            ReplySpec(0, "That fixed it — image is 180 MB smaller too. Thank you!", 16),
        ),
    ),
    ThreadSpec(
        HEADLINE_BATCH, "Lab setup checklist for the Kubernetes week",
        "Can we have one list of everything to install before Monday? kubectl, minikube, "
        "helm, and which versions — half the class had a different minikube last time.",
        1, 16, 8, 30,
        replies=(
            ReplySpec("trainer",
                      "Pinned. Install kubectl 1.31, minikube 1.34 with the docker driver, "
                      "helm 3.16, and k9s if you like a TUI. Run `minikube start` once at "
                      "home so the image pull happens on your own wifi, not the lab's.", 2),
        ),
        pinned=True,
    ),
    ThreadSpec(
        HEADLINE_BATCH, "Anyone else getting a 403 from the private registry?",
        "`docker push registry.lab.grras.local/aarav/api:1.0` returns 403 since this "
        "morning. `docker login` says succeeded. Was the token rotated?",
        2, 3, 10, 5,
    ),
    ThreadSpec(
        HEADLINE_BATCH, "Ansible vault password prompt in the CI job",
        "The playbook works locally but the Jenkins job hangs at 'Vault password:'. How "
        "do people handle the vault in CI without committing the password?",
        3, 9, 21, 10,
        replies=(
            ReplySpec(4, "Use --vault-password-file pointing at a file the CI injects as a "
                         "secret, and keep that path out of git.", 3),
            ReplySpec("trainer",
                      "Exactly that. In Jenkins bind the credential to a file with "
                      "withCredentials, pass it as --vault-password-file, and never echo "
                      "it. We will do exactly this in Friday's pipeline lab.", 20),
        ),
    ),
    # --- Python full stack, weekends -----------------------------------------
    ThreadSpec(
        "a3", "Django migrations conflict after the merge",
        "After merging my branch there are two 0007 migrations in the accounts app and "
        "`migrate` refuses to run. Do I delete one?",
        0, 26, 11, 15,
        replies=(
            ReplySpec("trainer",
                      "Never delete one that a teammate already applied. Run `makemigrations "
                      "--merge`, review the merge migration it writes, and commit that. "
                      "Closing this since it is resolved; the merge recipe is in week 6 notes.",
                      5),
        ),
        closed=True,
    ),
    ThreadSpec(
        "a3", "Is the weekend class on during Diwali?",
        "The calendar shows Diwali on the Sunday. Are we meeting on the Saturday only, "
        "or is the whole weekend off?",
        1, 6, 18, 25,
    ),
    ThreadSpec(
        "a3", "Best way to structure DRF serializers for nested writes",
        "For the order-with-items API, should I write nested create() on the serializer "
        "or handle it in the view? The docs seem to discourage nested writes.",
        2, 13, 20, 50,
        replies=(
            ReplySpec(3, "I put it in the serializer's create() and it got messy fast. Curious "
                         "what the recommended way is.", 1),
            ReplySpec("trainer",
                      "Neither: put the write in a service function (`create_order(...)`) "
                      "and call it from the serializer's create(). The serializer validates, "
                      "the service writes, the view stays thin. That is the pattern in the "
                      "week 9 project skeleton.", 26),
        ),
    ),
    # --- AWS, evenings ----------------------------------------------------------
    ThreadSpec(
        "a1", "IAM policy for the S3 lab keeps denying ListBucket",
        "My policy allows s3:* on arn:aws:s3:::grras-lab-aarav/* but `aws s3 ls` on the "
        "bucket says AccessDenied on ListBucket. GetObject works.",
        0, 10, 20, 15,
        replies=(
            ReplySpec("trainer",
                      "ListBucket is a bucket-level action, so it needs the bucket ARN "
                      "without /*. Add a second statement for arn:aws:s3:::grras-lab-aarav "
                      "itself. This trips up half of every SAA exam, so remember it.", 9),
            ReplySpec(1, "If anyone wants the full SAA question bank, DM me for the paid dump "
                         "link, 500 rupees.", 12,
                      hidden_reason="Advertised paid exam dumps; against the batch rules."),
        ),
    ),
    ThreadSpec(
        "a1", "Free-tier billing alert went off after the EC2 lab",
        "Got a $0.42 billing alert email overnight. I stopped the instance but did not "
        "terminate it — is the EBS volume what is costing?",
        2, 1, 7, 45,
    ),
    ThreadSpec(
        "a1", "Notes from Tuesday's VPC peering session",
        "Sharing my notes from the peering lab: route tables both sides, no overlapping "
        "CIDRs, security groups can reference the peer's SG id. Corrections welcome.",
        1, 18, 22, 5,
        replies=(
            ReplySpec("trainer",
                      "Good notes. One addition: peering is not transitive — A↔B and B↔C "
                      "does not give A↔C; that is what Transit Gateway is for.", 3),
        ),
    ),
)  # fmt: skip


def _students_of(ctx: Context, batch: Batch) -> list[User]:
    """The live students of a cohort, in a fixed order: the headline student
    first when they are on it, then by email. Live enrolments only, so a
    cancelled or transferred student never authors a thread."""
    users = {row.student.user.pk: row.student.user for row in ctx.live_enrolments(batch)}
    ordered = sorted(users.values(), key=lambda user: user.email)
    headline = ctx.students[MAIN][0] if ctx.students.get(MAIN) else None
    if headline is not None and headline.user_id in users:
        ordered.remove(users[headline.user_id])
        ordered.insert(0, users[headline.user_id])
    return ordered


def _ensure_discussions(ctx: Context) -> None:
    authors: dict[str, list[User]] = {}
    for spec in THREADS:
        batch = _batch(ctx, spec.batch)
        if batch is None or batch.trainer_id is None:
            ctx.out(f"thread '{spec.title}': skipped (no batch or no trainer)")
            continue
        if spec.batch not in authors:
            authors[spec.batch] = _students_of(ctx, batch)
        students = authors[spec.batch]
        if not students:
            ctx.out(f"thread '{spec.title}': skipped (nobody on {batch.code})")
            continue

        existing = Thread.objects.filter(batch=batch, title=spec.title).first()
        if existing is not None:
            ctx.found_existing("thread")
            ctx.found_existing("reply", existing.reply_count)
            ctx.out(f"thread '{spec.title}': found")
            continue
        _create_thread(ctx, batch, students, spec)
        ctx.created("thread")
        ctx.out(f"thread '{spec.title}': created ({len(spec.replies)} replies)")


def _create_thread(ctx: Context, batch: Batch, students: list[User], spec: ThreadSpec) -> None:
    trainer = batch.trainer.user
    author = students[spec.author % len(students)]
    thread = create_thread(batch=batch, actor=author, title=spec.title, body=ctx.note(spec.body))
    opened = ctx.at(ctx.days_ago(spec.days_ago), spec.hour, spec.minute)

    rows: list[tuple[Reply, datetime, ReplySpec]] = []
    for reply_spec in spec.replies:
        actor = trainer if reply_spec.who == "trainer" else students[reply_spec.who % len(students)]
        row = reply_to(thread=thread, actor=actor, body=ctx.note(reply_spec.body))
        rows.append((row, opened + timedelta(hours=reply_spec.hours_later), reply_spec))
        ctx.created("reply")

    # Moderation, by the trainer, after the replies: a closed thread refuses them.
    for row, _, reply_spec in rows:
        if reply_spec.hidden_reason:
            hide_reply(row=row, actor=trainer, reason=ctx.note(reply_spec.hidden_reason))
    if spec.pinned:
        set_pinned(thread=thread, actor=trainer, pinned=True)
    if spec.closed:
        set_closed(thread=thread, actor=trainer, closed=True)

    # Backdating, after the last service call on each row.
    last = opened
    for row, at, _ in rows:
        ctx.backdate(row, created_at=at, updated_at=at)
        last = max(last, at)
    fields: dict[str, Any] = {"created_at": opened, "updated_at": last}
    if rows:
        fields["last_reply_at"] = last
    if spec.closed:
        fields["closed_at"] = last + timedelta(hours=1)
        fields["updated_at"] = fields["closed_at"]
    ctx.backdate(thread, **fields)

    raised = Notification.objects.filter(resource_type="thread", resource_id=str(thread.pk))
    _backdate_many(
        raised.filter(title__startswith="New question"), created_at=opened, updated_at=opened
    )
    _backdate_many(raised.filter(title__startswith="Reply on"), created_at=last, updated_at=last)


# ---------------------------------------------------------------------------
# Notifications: read and unread on the headline accounts
# ---------------------------------------------------------------------------


def _headline_users(ctx: Context) -> list[User]:
    candidates: list[User | None] = [
        ctx.superadmin,
        ctx.admins.get(MAIN),
        ctx.managers.get(MAIN),
        ctx.counsellors.get(MAIN),
        ctx.trainers[MAIN][0].user if ctx.trainers.get(MAIN) else None,
        ctx.students[MAIN][0].user if ctx.students.get(MAIN) else None,
    ]
    seen: set = set()
    users: list[User] = []
    for user in candidates:
        if user is not None and user.pk not in seen:
            seen.add(user.pk)
            users.append(user)
    return users


def _ensure_reads(ctx: Context) -> None:
    """Every other notification, oldest first, read — through ``mark_read``,
    which is a no-op on one already read, so a second run changes nothing
    and a real read on the bell is never undone.

    The newest is always left unread, whatever its parity: the bell must
    still show a count, and an account with a single notification — the
    owner on a database where only the *everyone* notice has reached him
    yet — would otherwise be read through with nothing left to show.
    """
    for user in _headline_users(ctx):
        rows = list(Notification.objects.for_user(user).order_by("created_at", "pk"))
        changed = kept = 0
        for index, notification in enumerate(rows):
            if index % 2 or index == len(rows) - 1:
                continue
            if notification.read_at is None:
                mark_read(notification=notification)
                changed += 1
            else:
                kept += 1
        ctx.created("notification_read", changed)
        ctx.found_existing("notification_read", kept)
        ctx.out(f"notifications for {user.email}: {changed} marked read, {kept} already read")


# ---------------------------------------------------------------------------
# Communication templates
# ---------------------------------------------------------------------------

#: Real content for the seven migration-seeded email templates:
#: key → (subject, text body, variable allowlist).
SEEDED_EMAIL_CONTENT: dict[str, tuple[str, str, list[str]]] = {
    "email.activity_assigned": (
        "New activity: {{activity.title}}",
        "Hello {{recipient.first_name}},\n\n"
        "{{activity.title}} has been assigned to you and is due on {{activity.due_at}}. "
        "Open My work on the portal to see the details and mark it done.\n\n"
        "Grras Solutions",
        ["recipient.first_name", "recipient.name", "activity.title", "activity.due_at"],
    ),
    "email.activity_completed": (
        "Completed: {{activity.title}} for {{student.name}}",
        "Hello {{recipient.first_name}},\n\n"
        "{{activity.title}} for {{student.name}} was completed and is ready for your "
        "review on the portal.\n\n"
        "Grras Solutions",
        ["recipient.first_name", "recipient.name", "activity.title", "student.name"],
    ),
    "email.attendance_warning": (
        "Your attendance is at {{attendance.percent}}%",
        "Hello {{recipient.first_name}},\n\n"
        "Your attendance has dropped to {{attendance.percent}}%, below the 75% the course "
        "requires for completion. Please speak to your trainer or counsellor this week so "
        "we can plan how to catch up.\n\n"
        "Grras Solutions",
        ["recipient.first_name", "recipient.name", "attendance.percent"],
    ),
    "email.result_published": (
        "Your result for {{batch.name}} is out",
        "Hello {{recipient.first_name}},\n\n"
        "A new result for {{batch.name}} is on your dashboard. Open Results on the portal "
        "to see your marks and your trainer's remarks.\n\n"
        "Grras Solutions",
        ["recipient.first_name", "recipient.name", "batch.name"],
    ),
    "email.activity_overdue": (
        "Overdue: {{activity.title}}",
        "Hello {{recipient.first_name}},\n\n"
        "{{activity.title}} was due on {{activity.due_at}} and is now overdue. Please "
        "complete it, or tell your counsellor if something is in the way.\n\n"
        "Grras Solutions",
        ["recipient.first_name", "recipient.name", "activity.title", "activity.due_at"],
    ),
    "email.risk_level_changed": (
        "{{student.name}} is now at {{risk.level}} risk",
        "Hello {{recipient.first_name}},\n\n"
        "{{student.name}}'s risk level changed from {{risk.previous_level}} to "
        "{{risk.level}}. Open their record on the portal to see which rules triggered and "
        "plan a follow-up.\n\n"
        "Grras Solutions",
        [
            "recipient.first_name",
            "recipient.name",
            "student.name",
            "risk.level",
            "risk.previous_level",
        ],
    ),
    "email.project_overdue": (
        "Project overdue: {{project.title}}",
        "Hello {{recipient.first_name}},\n\n"
        "{{project.title}} is {{project.days_overdue}} day(s) past its deadline. Submit it "
        "on the portal as soon as you can; late submissions are still graded.\n\n"
        "Grras Solutions",
        ["recipient.first_name", "recipient.name", "project.title", "project.days_overdue"],
    ),
}


@dataclass(frozen=True)
class TemplateSpec:
    key: str
    name: str
    channel: str
    kind: str
    #: draft, approved or published — where the version is left.
    target: str
    subject: str
    body_text: str
    variables: list[str] = field(default_factory=list)
    provider_template_id: str = ""


CUSTOM_TEMPLATES: tuple[TemplateSpec, ...] = (
    TemplateSpec(
        "in_app.batch_notice", "Batch notice (in-app)", MessageChannel.IN_APP,
        NotificationKind.BATCH_UPDATED, "published",
        "A note from your trainer on {{batch.name}}",
        "{{notice}}",
        ["batch.name", "notice", "recipient.first_name"],
    ),
    TemplateSpec(
        "email.batch_welcome", "Batch welcome", MessageChannel.EMAIL, "batch.welcome", "approved",
        "Welcome to {{batch.name}}",
        "Hello {{recipient.first_name}},\n\n"
        "Welcome to {{batch.name}}. Your first class is on {{batch.start_date}}; the "
        "timetable, lab location and your trainer's details are on the portal.\n\n"
        "Grras Solutions",
        ["recipient.first_name", "recipient.name", "batch.name", "batch.start_date"],
    ),
    TemplateSpec(
        WHATSAPP_TEMPLATE_KEY, "Class reminder (WhatsApp)", MessageChannel.WHATSAPP,
        "class.reminder", "draft",
        "",
        "Hi {{recipient.first_name}}, your {{batch.name}} class starts at {{session.time}} "
        "today in {{session.location}}. Reply STOP to opt out.",
        ["recipient.first_name", "batch.name", "session.time", "session.location"],
        provider_template_id="grras_class_reminder_v1",
    ),
)  # fmt: skip


def _html(text: str) -> str:
    """The same paragraph wrapping the seed migration used."""
    return "<p>" + text.replace("\n\n", "</p><p>").replace("\n", "<br>") + "</p>"


def _ensure_templates(ctx: Context, owner: User) -> None:
    for key, (subject, text, variables) in SEEDED_EMAIL_CONTENT.items():
        _ensure_seeded_template(ctx, owner, key, subject, text, variables)
    for spec in CUSTOM_TEMPLATES:
        _ensure_custom_template(ctx, owner, spec)


def _content_is(version: TemplateVersion | None, subject, text, variables, provider_id) -> bool:
    return (
        version is not None
        and version.subject == subject
        and version.body_text == text
        and version.body_html == _html(text)
        and list(version.variables or []) == list(variables)
        and version.provider_template_id == provider_id
    )


def _ensure_seeded_template(
    ctx: Context, owner: User, key: str, subject: str, text: str, variables: list[str]
) -> None:
    """A real version on a seeded template: found when the published version
    already carries this content, otherwise a new draft (or the draft that
    is already there — a database migrated with an older seed may hold the
    template with its first version still unpublished) is filled, approved
    and published."""
    template = (
        MessageTemplate.objects.filter(key=key, channel=MessageChannel.EMAIL)
        .select_related("current_version")
        .first()
    )
    if template is None:
        ctx.out(f"template {key}: not on this database, skipped")
        return
    if _content_is(template.current_version, subject, text, variables, ""):
        ctx.found_existing("template_version")
        ctx.out(f"template {key}: found (v{template.current_version.number} published)")
        return
    version = (
        TemplateVersion.objects.filter(template=template, published_at__isnull=True)
        .order_by("-number")
        .first()
    )
    if version is None:
        version = create_template_draft(actor=owner, template=template)
    update_draft_version(
        actor=owner,
        version=version,
        subject=subject,
        body_text=text,
        body_html=_html(text),
        variables=list(variables),
    )
    approve_version(actor=owner, version=version)
    publish_template_version(actor=owner, version=version)
    ctx.created("template_version")
    ctx.out(f"template {key}: created (v{version.number} published)")


def _ensure_custom_template(ctx: Context, owner: User, spec: TemplateSpec) -> None:
    """A custom template walked to ``spec.target``. Looked up through
    ``all_objects`` so a binned one is found, not remade under the same key."""
    template = MessageTemplate.all_objects.filter(key=spec.key).first()
    if template is None:
        template = create_template(
            actor=owner, key=spec.key, name=spec.name, channel=spec.channel, kind=spec.kind
        )
        ctx.created("message_template")
        ctx.out(f"template {spec.key}: created")
    else:
        ctx.found_existing("message_template")
        ctx.out(f"template {spec.key}: found ({template.status})")

    version = TemplateVersion.objects.filter(template=template).order_by("-number").first()
    if template.deleted_at is not None or version is None:
        return
    if not version.is_published:
        # A no-op when unchanged, so an approval already given survives.
        update_draft_version(
            actor=owner,
            version=version,
            subject=spec.subject,
            body_text=spec.body_text,
            body_html=_html(spec.body_text) if spec.channel != MessageChannel.WHATSAPP else "",
            variables=list(spec.variables),
            provider_template_id=spec.provider_template_id,
        )
    if spec.target in ("approved", "published") and version.approved_at is None:
        approve_version(actor=owner, version=version)
    if spec.target == "published" and not version.is_published:
        publish_template_version(actor=owner, version=version)


# ---------------------------------------------------------------------------
# Deliveries
# ---------------------------------------------------------------------------


def _ensure_deliveries(ctx: Context, owner: User) -> None:
    batch = _batch(ctx, HEADLINE_BATCH)
    template = (
        MessageTemplate.objects.filter(key=SEND_TEMPLATE_KEY, channel=MessageChannel.EMAIL)
        .select_related("current_version")
        .first()
    )
    if batch is None or template is None or template.current_version is None:
        ctx.out("deliveries: no headline batch or no published template, skipped")
    else:
        _ensure_manual_send(ctx, owner, batch, template.current_version)
    _ensure_failed_deliveries(ctx, owner)
    ctx.out("deliveries by state: " + _state_summary())


def _ensure_manual_send(ctx: Context, owner: User, batch: Batch, version: TemplateVersion) -> None:
    """One send to the headline cohort, with the recipient count recomputed
    the way the composer does it, so ``confirm_count`` is exactly right."""
    spec = {"batch": str(batch.pk)}
    recipients = resolve_recipients(actor=owner, channel=MessageChannel.EMAIL, spec=spec)
    if not recipients:
        ctx.out(f"manual send to {batch.code}: nobody eligible, skipped")
        return
    existing = Delivery.objects.filter(
        channel=MessageChannel.EMAIL, template_version=version, recipient__in=recipients
    )
    found = existing.count()
    if found:
        ctx.found_existing("delivery", found)
        ctx.out(f"manual send to {batch.code}: found ({found} deliveries)")
        return

    result = manual_send(
        actor=owner,
        channel=MessageChannel.EMAIL,
        template_key=SEND_TEMPLATE_KEY,
        recipients_spec=spec,
        variables={"batch": {"name": batch.name, "code": batch.code}},
        confirm_count=len(recipients),
    )
    ctx.created("delivery", result["count"])
    ctx.out(f"manual send to {batch.code}: created ({result['count']} deliveries)")

    rows = sorted(Delivery.objects.filter(pk__in=result["delivery_ids"]), key=lambda d: d.address)
    if rows:
        # Still queued inside this transaction: the one moment a cancel is legal.
        cancel_delivery(actor=owner, delivery=rows[0])
    parked = dict(
        zip(
            [row.pk for row in rows[1:4]],
            (DeliveryState.QUEUED, DeliveryState.PROCESSING, DeliveryState.DELIVERED),
            strict=False,
        )
    )
    if parked:
        # After the dispatch hooks `create_deliveries` registered — see the
        # module docstring for why these three states need this.
        transaction.on_commit(lambda: _park_deliveries(parked))


def _park_deliveries(parked: dict[Any, str]) -> None:
    """Set three states no service can leave a row in, by queryset update,
    once the real dispatch has run. A queued row has not been attempted, so
    its attempt count and outbox link go too."""
    now = timezone.now()
    for pk, state in parked.items():
        fields: dict[str, Any] = {"state": state, "updated_at": now}
        if state == DeliveryState.QUEUED:
            fields.update(attempts=0, error="", email_message=None)
        Delivery.objects.filter(pk=pk).update(**fields)


def _ensure_failed_deliveries(ctx: Context, owner: User) -> None:
    """Two WhatsApp sends to opted-in students, dispatched synchronously
    through the same function the task calls, so the Null provider's own
    refusal is the error on the row. A configured provider would really
    send, so then the rows are left queued for the worker instead."""
    version = (
        TemplateVersion.objects.filter(
            template__key=WHATSAPP_TEMPLATE_KEY, template__channel=MessageChannel.WHATSAPP
        )
        .order_by("-number")
        .first()
    )
    opted = sorted(
        (u for u in ctx.users.values() if u.is_active and u.whatsapp_opt_in and u.phone),
        key=lambda u: u.email,
    )[:2]
    if version is None or not opted:
        ctx.out("whatsapp deliveries: no template or no opted-in students, skipped")
        return
    todo = [
        u
        for u in opted
        if not Delivery.objects.filter(template_version=version, recipient=u).exists()
    ]
    if len(todo) < len(opted):
        ctx.found_existing("delivery", len(opted) - len(todo))
    if not todo:
        ctx.out(f"whatsapp deliveries: found ({len(opted)})")
        return
    rows = create_deliveries(
        channel=MessageChannel.WHATSAPP,
        template_version=version,
        recipients=todo,
        requested_by=owner,
    )
    ctx.created("delivery", len(rows))
    if isinstance(get_provider(), NullWhatsAppProvider):
        for row in rows:
            dispatch_delivery(row)
        ctx.out(f"whatsapp deliveries: created ({len(rows)}, failed by the Null provider)")
    else:
        ctx.out(f"whatsapp deliveries: created ({len(rows)}, left queued for the worker)")


def _state_summary() -> str:
    counts = dict.fromkeys(DeliveryState.values, 0)
    for row in Delivery.objects.values("state").annotate(n=Count("pk")).order_by():
        counts[row["state"]] = row["n"]
    return ", ".join(f"{state} {n}" for state, n in counts.items())


# ---------------------------------------------------------------------------
# Forms
# ---------------------------------------------------------------------------


def _opt(*values: str) -> list[dict[str, str]]:
    return [{"value": v, "label": v.replace("_", " ").capitalize()} for v in values]


@dataclass(frozen=True)
class FormSpec:
    slug: str
    name: str
    entity: str
    fields: tuple[dict[str, Any], ...]
    #: Added on the v2 draft. Empty means no v2.
    extra: tuple[dict[str, Any], ...] = ()
    archived: bool = False


FORMS: tuple[FormSpec, ...] = (
    FormSpec(
        "placement-readiness", "Placement readiness check", FormEntity.ACTIVITY,
        (
            {"key": "readiness_score", "label": "Readiness score (0-10)",
             "type": FormFieldType.NUMBER, "required": True,
             "validation": {"min": 0, "max": 10}, "performance_key": "readiness",
             "visible_to_student": True},
            {"key": "communication", "label": "Communication", "type": FormFieldType.SELECT,
             "required": True, "options": _opt("weak", "fair", "strong")},
            {"key": "technical_topics", "label": "Topics assessed",
             "type": FormFieldType.MULTISELECT,
             "options": _opt("linux", "networking", "cloud", "python", "sql", "devops")},
            {"key": "resume_url", "label": "Resume link", "type": FormFieldType.URL},
            {"key": "portfolio_file", "label": "Portfolio (PDF)", "type": FormFieldType.FILE,
             "validation": {"max_mb": 10}},
            {"key": "ready_for_drive", "label": "Ready for the next drive",
             "type": FormFieldType.BOOLEAN, "required": True, "visible_to_student": True},
            {"key": "target_role", "label": "Target role", "type": FormFieldType.TEXT,
             "validation": {"max_length": 80}},
            {"key": "interview_date", "label": "Mock interview date", "type": FormFieldType.DATE},
            {"key": "notes", "label": "Panel notes", "type": FormFieldType.RICHTEXT,
             "help": "Visible to staff only."},
        ),
        extra=(
            {"key": "mentor", "label": "Assigned mentor", "type": FormFieldType.RELATION,
             "options": {"model": "trainer"}},
        ),
    ),
    FormSpec(
        "student-onboarding", "Student onboarding survey", FormEntity.STUDENT,
        (
            {"key": "preferred_name", "label": "Preferred name", "type": FormFieldType.TEXT,
             "visible_to_student": True},
            {"key": "guardian_phone", "label": "Guardian phone", "type": FormFieldType.PHONE,
             "required": True},
            {"key": "guardian_email", "label": "Guardian email", "type": FormFieldType.EMAIL},
            {"key": "laptop_available", "label": "Own laptop?", "type": FormFieldType.RADIO,
             "required": True, "options": _opt("yes", "no", "shared")},
            {"key": "interests", "label": "Interests", "type": FormFieldType.CHECKBOX,
             "options": _opt("cloud", "security", "data", "web", "networking")},
            {"key": "joined_on", "label": "Orientation attended at",
             "type": FormFieldType.DATETIME},
            {"key": "photo", "label": "ID photo", "type": FormFieldType.IMAGE,
             "validation": {"max_mb": 5}},
            {"key": "home_heading", "label": "Where you live", "type": FormFieldType.HEADING,
             "help": "Used to suggest the nearest centre."},
            {"key": "home_state", "label": "Home state", "type": FormFieldType.SELECT,
             "options": _opt("rajasthan", "maharashtra", "other")},
            {"key": "home_city", "label": "Home city", "type": FormFieldType.DEPENDENT_SELECT,
             "options": {"parent": "home_state", "choices": {
                 "rajasthan": _opt("jaipur", "kota", "ajmer"),
                 "maharashtra": _opt("pune", "mumbai"),
                 "other": _opt("other"),
             }}},
            {"key": "preferred_slot", "label": "Preferred class time", "type": FormFieldType.TIME,
             "validation": {"min": "07:00", "max": "21:00"}},
            {"key": "code_of_conduct", "label": "I agree to the institute's code of conduct",
             "type": FormFieldType.CONSENT, "required": True},
        ),
        extra=(
            {"key": "about_me", "label": "About me", "type": FormFieldType.TEXTAREA,
             "visible_to_student": True},
        ),
    ),
    FormSpec(
        "registration-source", "Registration source", FormEntity.REGISTRATION,
        (
            {"key": "heard_from", "label": "How did you hear about us?",
             "type": FormFieldType.SELECT, "required": True,
             "options": _opt("friend", "google", "instagram", "college", "walk_in", "other")},
            {"key": "referral_code", "label": "Referral code", "type": FormFieldType.TEXT},
            {"key": "expected_budget", "label": "Budget (INR)", "type": FormFieldType.DECIMAL,
             "validation": {"min": 0}},
            {"key": "consent_marketing", "label": "OK to send course updates",
             "type": FormFieldType.BOOLEAN},
            {"key": "counselling_rating", "label": "How was the counselling?",
             "type": FormFieldType.RATING, "validation": {"max": 5}},
            {"key": "utm_source", "label": "UTM source", "type": FormFieldType.HIDDEN,
             "validation": {"default": "walk-in"}},
        ),
        extra=(
            {"key": "comments", "label": "Anything else?", "type": FormFieldType.TEXTAREA},
        ),
    ),
    FormSpec(
        "trainer-quarterly-review", "Trainer quarterly review", FormEntity.REVIEW,
        (
            {"key": "reviewed_batch", "label": "Batch reviewed", "type": FormFieldType.RELATION,
             "required": True, "options": {"model": "batch"}},
            {"key": "delivery_rating", "label": "Delivery rating (1-5)",
             "type": FormFieldType.NUMBER, "required": True,
             "validation": {"min": 1, "max": 5}, "performance_key": "delivery"},
            {"key": "strengths", "label": "Strengths", "type": FormFieldType.TEXTAREA},
            {"key": "review_date", "label": "Review date", "type": FormFieldType.DATE,
             "required": True},
        ),
        extra=(
            {"key": "goals", "label": "Goals for next quarter", "type": FormFieldType.RICHTEXT},
        ),
    ),
    FormSpec(
        "legacy-feedback-form", "Legacy feedback form (2024)", FormEntity.ACTIVITY,
        (
            {"key": "rating", "label": "Rating (1-5)", "type": FormFieldType.NUMBER,
             "validation": {"min": 1, "max": 5}},
            {"key": "comments", "label": "Comments", "type": FormFieldType.TEXTAREA},
        ),
        archived=True,
    ),
)  # fmt: skip


def _ensure_forms(ctx: Context, owner: User) -> None:
    for spec in FORMS:
        _ensure_form(ctx, owner, spec)


def _ensure_form(ctx: Context, owner: User, spec: FormSpec) -> None:
    definition = FormDefinition.all_objects.filter(slug=spec.slug).first()
    if definition is None:
        definition = create_definition(
            actor=owner, slug=spec.slug, name=spec.name, entity=spec.entity
        )
        ctx.created("form_definition")
        ctx.out(f"form {spec.slug}: created")
    else:
        ctx.found_existing("form_definition")
        ctx.out(f"form {spec.slug}: found ({definition.status})")
        if definition.deleted_at is not None:
            return

    v1 = FormVersion.objects.filter(definition=definition, number=1).first()
    if v1 is not None and v1.status == FormVersionStatus.DRAFT:
        set_fields(actor=owner, version=v1, fields=[dict(f) for f in spec.fields])
        publish_form_version(actor=owner, version=v1)
        ctx.created("form_version")
    elif v1 is not None:
        ctx.found_existing("form_version")

    if spec.extra:
        v2 = FormVersion.objects.filter(definition=definition, number=2).first()
        if v2 is None:
            v2 = create_form_draft(actor=owner, definition=definition, cloned_from=v1)
            set_fields(
                actor=owner, version=v2, fields=[dict(f) for f in (*spec.fields, *spec.extra)]
            )
            ctx.created("form_version")
        else:
            ctx.found_existing("form_version")

    if spec.archived and definition.status != FormDefinitionStatus.ARCHIVED:
        # No service archives a definition (`apps.forms.services` only
        # archives a *version* when the next one is published), so this is
        # the one plain write in the stage; a later service for it should
        # replace this line.
        FormDefinition.objects.filter(pk=definition.pk).update(
            status=FormDefinitionStatus.ARCHIVED, updated_at=timezone.now()
        )
        ctx.out(f"form {spec.slug}: archived (no service exists; plain update)")


# ---------------------------------------------------------------------------
# Automation
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RuleSpec:
    name: str
    description: str
    trigger: str
    conditions: tuple[dict[str, Any], ...]
    actions: tuple[dict[str, Any], ...]
    status: str
    pause_reason: str = ""


RULES: tuple[RuleSpec, ...] = (
    RuleSpec(
        "Doubt session after a failed weekly test",
        "Books a doubt session with the batch trainer and tells the student when a "
        "weekly test comes in under 40%.",
        AutomationTrigger.ASSESSMENT_FAILED,
        ({"path": "assessment.percent", "op": "lt", "value": 40},),
        (
            {
                "type": "create_activity",
                "params": {"type": "doubt-session", "assign_to": "batch_trainer", "due_in_days": 5},
            },
            {
                "type": "send_notification",
                "params": {
                    "to": "student",
                    "kind": NotificationKind.RESULT_PUBLISHED,
                    "title": "Let's go over that test, {{student.name}}",
                    "body": "Your trainer will book a doubt session this week.",
                },
            },
        ),
        AutomationRuleStatus.ACTIVE,
        pause_reason="Paused for the exam fortnight; trainers are booked solid.",
    ),
    RuleSpec(
        "Email the student when a project is three days overdue",
        "Sends the project-overdue email template once a project is three or more days late.",
        AutomationTrigger.PROJECT_OVERDUE,
        ({"path": "project.days_overdue", "op": "gte", "value": 3},),
        ({"type": "send_email", "params": {"template": "email.project_overdue", "to": "student"}},),
        AutomationRuleStatus.DRAFT,
    ),
)


def _ensure_automation(ctx: Context, owner: User) -> None:
    for spec in RULES:
        existing = AutomationRule.all_objects.filter(name=spec.name).first()
        if existing is not None:
            ctx.found_existing("automation_rule")
            ctx.out(f"rule '{spec.name}': found ({existing.status})")
            continue
        rule = create_rule(
            actor=owner,
            name=spec.name,
            description=ctx.note(spec.description),
            trigger=spec.trigger,
            conditions=[dict(c) for c in spec.conditions],
            actions=[dict(a) for a in spec.actions],
            status=spec.status,
        )
        if spec.pause_reason:
            pause_rule(rule=rule, actor=owner, reason=ctx.note(spec.pause_reason))
        ctx.created("automation_rule")
        ctx.out(f"rule '{spec.name}': created ({rule.status})")

    total = AutomationRun.objects.count()
    recent = AutomationRun.objects.filter(
        created_at__gte=timezone.now() - timedelta(days=7)
    ).count()
    active = AutomationRule.objects.filter(status=AutomationRuleStatus.ACTIVE).count()
    ctx.out(
        f"automation: {active} active rules; {total} runs on record, {recent} in the last "
        "7 days (written by earlier stages' dispatches, never here)"
    )
