"""Stage 9 of the showcase: announcements in every state, weeks of discussion,
templates and deliveries across channels and states, forms and rules — and a
second run that creates nothing.

Runs the command up to and including ``comms`` on the empty test database,
twice, inside ``django_capture_on_commit_callbacks`` so the announcement
fan-out mails, the delivery dispatch task and the stage's own parking hook
all fire the way they do after a real commit. There are no SITP rows here,
so every imported-account path is proved to be a clean no-op.

One test runs the command twice and checks everything, rather than one test
per promise: the four stages in front build a hundred accounts, a catalogue
and fourteen batches, and a run per test would put the file well over its
time budget.
"""

from __future__ import annotations

import os
import re
from datetime import timedelta
from io import StringIO
from unittest import mock

import pytest
from django.core.management import call_command
from django.utils import timezone

from apps.accounts.models import User
from apps.announcements.models import Announcement, AnnouncementStatus, Audience
from apps.automation.models import AutomationRule, AutomationRuleStatus, AutomationRun
from apps.batches.models import Batch
from apps.common.showcase.context import MARKER
from apps.common.showcase.stages.s09_comms import (
    _BATCH_NAMES,
    CUSTOM_TEMPLATES,
    FORMS,
    RULES,
    SEEDED_EMAIL_CONTENT,
    SEND_TEMPLATE_KEY,
    THREADS,
    WHATSAPP_TEMPLATE_KEY,
)
from apps.communication.models import (
    Delivery,
    DeliveryState,
    MessageChannel,
    MessageTemplate,
    TemplateStatus,
)
from apps.discussions.models import Reply, Thread
from apps.forms.models import (
    FormDefinition,
    FormDefinitionStatus,
    FormField,
    FormFieldType,
    FormVersionStatus,
)
from apps.notifications.models import Notification

SEED_PASSWORD = "Showcase-Demo-Passw0rd!"
STAGES = "organisation,people,courses,batches,comms"

#: The labels this stage counts. The second run must show created 0 for each.
LABELS = (
    "announcement",
    "thread",
    "reply",
    "notification_read",
    "template_version",
    "message_template",
    "delivery",
    "form_definition",
    "form_version",
    "automation_rule",
)

ROW_RE = re.compile(r"^\s+(\S+)\s+(\d+)\s+(\d+)$", re.MULTILINE)


def run(django_capture_on_commit_callbacks) -> str:
    out = StringIO()
    with (
        mock.patch.dict(os.environ, {"DEMO_USER_PASSWORD": SEED_PASSWORD}),
        django_capture_on_commit_callbacks(execute=True),
    ):
        call_command("seed_showcase", "--only", STAGES, stdout=out, stderr=out)
    return out.getvalue()


def rows(output: str) -> dict[str, tuple[int, int]]:
    """The 'Rows by model' table as ``label -> (created, found)``."""
    table = output.split("Rows by model (this run)", 1)[1].split("Sign in as", 1)[0]
    return {label: (int(c), int(f)) for label, c, f in ROW_RE.findall(table)}


def counts() -> dict[str, int]:
    return {
        "announcements": Announcement.all_objects.count(),
        "threads": Thread.objects.count(),
        "replies": Reply.objects.count(),
        "notifications": Notification.objects.count(),
        "notifications_read": Notification.objects.filter(read_at__isnull=False).count(),
        "templates": MessageTemplate.all_objects.count(),
        "template_versions": sum(t.versions.count() for t in MessageTemplate.all_objects.all()),
        "deliveries": Delivery.objects.count(),
        **{
            f"deliveries_{state}": Delivery.objects.filter(state=state).count()
            for state in DeliveryState.values
        },
        "forms": FormDefinition.all_objects.count(),
        "form_fields": FormField.objects.count(),
        "rules": AutomationRule.all_objects.count(),
        "runs": AutomationRun.objects.count(),
    }


def showcase_batch(key: str) -> Batch:
    return Batch.objects.get(name=_BATCH_NAMES[key])


@pytest.mark.django_db
def test_comms_stage_builds_every_state_and_is_idempotent(django_capture_on_commit_callbacks):
    first = run(django_capture_on_commit_callbacks)
    after_first = counts()
    second = run(django_capture_on_commit_callbacks)

    # --- Second run: nothing created, nothing changed -----------------------
    table = rows(second)
    for label in LABELS:
        assert table[label][0] == 0, f"second run created {label}: {table[label]}"
        assert table[label][1] > 0, f"second run found no {label}"
    assert counts() == after_first
    for label in LABELS:
        assert rows(first)[label][0] > 0, f"first run created no {label}"
    assert "manual send to GRS-B" in first and "deliveries)" in first
    assert re.search(r"manual send to GRS-B-\d+: found", second)
    assert "announcement 'Welcome to the new Grras portal': created (published)" in first
    assert "announcement 'Welcome to the new Grras portal': found (published)" in second

    now = timezone.now()
    owner = User.objects.get(email="owner@grras.com")
    headline_student = User.objects.get(email="student@grras.com")
    headline = showcase_batch("a2")

    # --- Announcements: every audience, every status, one 'everyone' ---------
    notices = Announcement.all_objects.filter(body__startswith=MARKER)
    assert notices.count() == 9
    assert {a.audience for a in notices} == set(Audience.values)
    assert {a.status for a in notices} == set(AnnouncementStatus.values)
    everyone = notices.get(audience=Audience.EVERYONE)
    assert everyone.status == AnnouncementStatus.PUBLISHED
    assert everyone.is_pinned is True
    assert everyone.published_at < now - timedelta(days=20)
    assert everyone.created_at == everyone.published_at
    told = Notification.objects.filter(resource_type="announcement", resource_id=str(everyone.pk))
    assert told.count() == User.objects.filter(is_active=True).count()
    assert set(told.values_list("created_at", flat=True)) == {everyone.published_at}
    assert set(told.values_list("recipient__is_active", flat=True)) == {True}

    scheduled = notices.get(status=AnnouncementStatus.SCHEDULED)
    assert scheduled.audience == Audience.TRAINERS
    assert scheduled.publish_at > now
    assert not Notification.objects.filter(resource_id=str(scheduled.pk)).exists()
    cancelled = notices.get(status=AnnouncementStatus.CANCELLED)
    assert cancelled.audience == Audience.BRANCH and cancelled.branch.code == "MAIN"
    draft = notices.get(status=AnnouncementStatus.DRAFT)
    assert draft.audience == Audience.SELECTED
    assert draft.recipients.count() == 3
    archived = notices.get(status=AnnouncementStatus.ARCHIVED)
    assert archived.batch == showcase_batch("c1")
    assert Notification.objects.filter(resource_id=str(archived.pk)).exists()
    role_notice = notices.get(audience=Audience.ROLE)
    assert role_notice.role.slug == "placement-coordinator"
    assert Notification.objects.filter(
        resource_id=str(role_notice.pk), recipient__email="placement@grras.com"
    ).exists()
    batch_notice = notices.get(audience=Audience.BATCH, status=AnnouncementStatus.PUBLISHED)
    assert batch_notice.batch == headline
    assert batch_notice.expires_at > now
    assert Notification.objects.filter(
        resource_id=str(batch_notice.pk), recipient=headline_student
    ).exists()
    assert notices.get(audience=Audience.BRANCH, status="published").branch.code == "PUNE"
    assert notices.get(audience=Audience.COURSE).course.slug == "rhcsa"

    # --- Discussions: answered, unanswered, pinned, closed, hidden ------------
    threads = Thread.objects.filter(body__startswith=MARKER)
    assert threads.count() == len(THREADS) == 10
    assert {t.batch.name for t in threads} == {_BATCH_NAMES[k] for k in ("a2", "a3", "a1")}
    assert threads.filter(batch=headline, author=headline_student).exists()
    assert threads.filter(is_pinned=True).count() == 1
    closed = threads.get(is_closed=True)
    assert closed.closed_by == closed.batch.trainer.user
    assert closed.closed_at is not None and closed.closed_at < now - timedelta(days=20)
    assert threads.filter(has_trainer_reply=True).count() == 7
    assert threads.filter(reply_count=0).count() == 3
    for thread in threads:
        assert thread.reply_count == thread.replies.count()
        assert thread.author in {
            row.student.user for row in thread.batch.enrollments.select_related("student__user")
        }
        if thread.reply_count:
            assert thread.last_reply_at == max(r.created_at for r in thread.replies.all())
            assert thread.last_reply_at > thread.created_at
    assert min(t.created_at for t in threads) < now - timedelta(days=25)
    assert max(t.created_at for t in threads) > now - timedelta(days=2)
    trainer_replies = Reply.objects.filter(is_trainer_response=True)
    assert trainer_replies.count() == 7
    for row in trainer_replies:
        assert row.author == row.thread.batch.trainer.user
    hidden = Reply.objects.get(is_hidden=True)
    assert hidden.hidden_reason.startswith(MARKER)
    assert hidden.hidden_by == hidden.thread.batch.trainer.user
    assert hidden.is_trainer_response is False
    # The trainer was told about each question, back when it was asked.
    for thread in threads:
        asked = Notification.objects.filter(
            resource_type="thread", resource_id=str(thread.pk), title__startswith="New question"
        )
        assert asked.count() == 1 and asked.get().created_at == thread.created_at

    # --- Notifications: both states on the headline accounts ------------------
    for email in ("owner@grras.com", "student@grras.com", "trainer@grras.com"):
        mine = Notification.objects.for_user(User.objects.get(email=email))
        # The newest is always left unread, even for the owner, who on this
        # database has only the 'everyone' notice (stages 5-8 did not run).
        assert mine.unread().exists(), email
        assert mine.order_by("-created_at", "-pk").first().read_at is None, email
        if email != "owner@grras.com":
            assert mine.count() > 1, email
            assert mine.filter(read_at__isnull=False).exists(), email
    # A read on the bell survives the re-run: the second run marked nothing.
    assert table["notification_read"] == (0, after_first["notifications_read"])

    # --- Templates: seeded ones re-versioned, custom ones per channel ---------
    for key, (subject, _text, variables) in SEEDED_EMAIL_CONTENT.items():
        template = MessageTemplate.objects.get(key=key)
        assert template.status == TemplateStatus.PUBLISHED
        assert template.versions.count() == 2
        assert template.current_version.number == 2
        assert template.current_version.subject == subject
        assert template.current_version.variables == variables
        assert template.current_version.approved_by == owner
        assert template.versions.get(number=1).is_published, "v1 stays on the record"
    in_app = MessageTemplate.objects.get(key="in_app.batch_notice")
    assert (in_app.channel, in_app.status) == (MessageChannel.IN_APP, TemplateStatus.PUBLISHED)
    assert in_app.kind == "batch.updated"
    welcome = MessageTemplate.objects.get(key="email.batch_welcome")
    assert welcome.status == TemplateStatus.APPROVED
    assert welcome.current_version is None
    assert welcome.versions.get().approved_at is not None
    whatsapp = MessageTemplate.objects.get(key=WHATSAPP_TEMPLATE_KEY)
    assert (whatsapp.channel, whatsapp.status) == (MessageChannel.WHATSAPP, TemplateStatus.DRAFT)
    assert whatsapp.versions.get().provider_template_id == "grras_class_reminder_v1"
    assert whatsapp.versions.get().approved_at is None
    assert len(CUSTOM_TEMPLATES) == 3

    # --- Deliveries: every state, through the real dispatch where possible ---
    assert set(Delivery.objects.values_list("state", flat=True)) == set(DeliveryState.values)
    send_version = MessageTemplate.objects.get(key=SEND_TEMPLATE_KEY).current_version
    emails = Delivery.objects.filter(channel=MessageChannel.EMAIL)
    cohort = {
        row.student.user for row in headline.enrollments.filter(status__in=["active", "completed"])
    }
    assert emails.count() == len(cohort)
    assert {d.recipient for d in emails} == cohort
    for delivery in emails:
        assert delivery.template_version == send_version
        assert delivery.variables["batch"]["name"] == headline.name
        assert delivery.requested_by == owner
    assert emails.filter(state=DeliveryState.CANCELLED).count() == 1
    queued = emails.get(state=DeliveryState.QUEUED)
    assert (queued.attempts, queued.email_message_id, queued.error) == (0, None, "")
    sent = emails.filter(state=DeliveryState.SENT)
    assert sent.count() >= 1
    for delivery in sent:
        assert delivery.attempts == 1 and delivery.email_message_id is not None
    assert emails.filter(state=DeliveryState.PROCESSING).count() == 1
    assert emails.filter(state=DeliveryState.DELIVERED).count() == 1
    failed = Delivery.objects.filter(state=DeliveryState.FAILED)
    assert failed.count() == 2
    for delivery in failed:
        assert delivery.channel == MessageChannel.WHATSAPP
        assert delivery.recipient.whatsapp_opt_in is True
        assert delivery.address == delivery.recipient.phone
        assert "not configured" in delivery.error
        assert delivery.attempts == 1

    # --- Forms: per entity, every field type, a draft on top, one archived ----
    published_types: set[str] = set()
    for spec in FORMS:
        definition = FormDefinition.objects.get(slug=spec.slug)
        assert definition.entity == spec.entity
        assert definition.created_by == owner
        v1 = definition.versions.get(number=1)
        assert v1.status == FormVersionStatus.PUBLISHED
        assert v1.published_by == owner
        assert v1.fields.count() == len(spec.fields)
        published_types |= set(v1.fields.values_list("type", flat=True))
        if spec.extra:
            v2 = definition.versions.get(number=2)
            assert v2.status == FormVersionStatus.DRAFT
            assert v2.cloned_from == v1
            assert v2.fields.count() == len(spec.fields) + len(spec.extra)
        else:
            assert definition.versions.count() == 1
        expected = FormDefinitionStatus.ARCHIVED if spec.archived else FormDefinitionStatus.ACTIVE
        assert definition.status == expected
    assert published_types == set(FormFieldType.values)
    assert {spec.entity for spec in FORMS} == {"activity", "student", "registration", "review"}
    # The seeded catalogue is left exactly as the migration made it.
    assert FormDefinition.objects.get(slug="mock-interview").versions.count() == 1

    # --- Automation: seeded active, one paused, one draft ---------------------
    paused = AutomationRule.objects.get(name=RULES[0].name)
    assert paused.status == AutomationRuleStatus.PAUSED
    assert paused.created_by == owner
    assert paused.description.startswith(MARKER)
    assert paused.actions[0]["type"] == "create_activity"
    drafted = AutomationRule.objects.get(name=RULES[1].name)
    assert drafted.status == AutomationRuleStatus.DRAFT
    assert drafted.actions[0]["params"]["template"] == "email.project_overdue"
    assert AutomationRule.objects.filter(status=AutomationRuleStatus.ACTIVE).count() == 9
    # The 9 catalogue rules, plus the example drafts (4 enquiry rules from
    # `automation.0005`, 1 class-report rule from `automation.0007`); the
    # showcase leaves every one of them as it found it.
    unauthored = AutomationRule.objects.filter(created_by__isnull=True)
    assert unauthored.filter(status=AutomationRuleStatus.ACTIVE).count() == 9
    assert unauthored.filter(status=AutomationRuleStatus.DRAFT).count() == 5
    assert "runs on record" in first

    # --- Nothing this stage does touches an account -------------------------
    assert SEED_PASSWORD not in first + second
