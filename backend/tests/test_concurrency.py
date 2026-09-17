"""Concurrency regression sweep (ERP Phase 24, §54/§78, IMPLEMENTATION_PLAN
row 24).

Every check-then-act pattern in the programme claims, in its own module's
comments, that a lock or constraint makes it race-safe. A single-threaded
test can call the same function twice in a row and prove the *logic* is
correct, but it can never prove the *lock* is real — two sequential calls on
one connection never actually contend for anything. This file is the one
place that proves it with genuine concurrent access: real `threading.Thread`
workers, each on its own database connection (`connection.close()` in a
``finally`` hands the pooled connection back rather than corrupting the next
test), synchronised with a `threading.Barrier` so both sides are inside the
race window at the same instant, against
``@pytest.mark.django_db(transaction=True)`` — the ORM's default test
wrapper runs everything in one outer transaction per test, which would
serialise the two "concurrent" calls through Python's own GIL and the same
connection's own transaction, proving nothing.

Coverage, one function per check-then-act pattern found across Phases 1-23:

* OTP verify (Phase 4) — already has its own real-thread test in
  ``test_otp.py``; re-collected here by reference (not duplicated) so this
  file is a genuine "every pattern in one place" sweep rather than one with
  an unexplained gap in it.
* Forms: ``publish_version``'s "at most one PUBLISHED version" invariant
  (Phase 8) — had no concurrent test anywhere before this file.
* Automation: the dispatch idempotency guard already has a real-thread test
  in ``test_automation.py`` (confirmed passing, not duplicated); the
  *rate guard* — a separate check-then-act on the same `dispatch()` — did
  not, and is added here.
* Performance: ``recompute_risk``'s first-ever computation for an enrolment
  (Phase 13) — a `OneToOneField` create with no existing row to lock.
* Communication: ``manual_send``'s server-recomputed `confirm_count`
  (Phase 19) — two concurrent, independently valid sends must not corrupt
  or cross-contaminate each other's count.

Each assertion is on the database's final state, not just on "no exception
was raised" — a race that silently produces two winners where there should
be one leaves no exception behind at all.
"""

from __future__ import annotations

import threading

import pytest
from django.db import connection

from tests.test_otp import (
    test_two_simultaneous_verifies_only_one_succeeds as _otp_verify_race_reference,
)

# Re-exported under a `test_` name of its own so this file's collection is a
# genuine one-stop list of every real-concurrency test in the suite — the
# function itself, and its assertions, live in `test_otp.py`; nothing here
# duplicates them.
test_otp_verify_is_never_double_consumed_under_real_concurrency = _otp_verify_race_reference


# ---------------------------------------------------------------------------
# Forms: publish_version — "at most one PUBLISHED version per definition"
# ---------------------------------------------------------------------------


@pytest.mark.django_db(transaction=True)
def test_two_concurrent_publishes_of_different_drafts_never_leave_two_published_versions():
    """`apps.forms.services.publish_version` takes `select_for_update()`
    across every version row of the definition before checking "what's
    currently published" — its own docstring names the exact race this
    guards: two concurrent `publish_version` calls for two different draft
    versions of the same definition must not both read "nothing published
    yet" and both write PUBLISHED. Nothing before this test ever called it
    from more than one thread."""
    from apps.accounts.models import User, UserRole
    from apps.forms import services
    from apps.forms.models import FormDefinition, FormField, FormVersion, FormVersionStatus

    actor = User.objects.create_user(
        email="form-publisher@example.test",
        password="correct-horse-battery-staple",
        first_name="Pat",
        last_name="Publisher",
        role=UserRole.ADMIN,
        is_staff=True,
    )
    definition = FormDefinition.objects.create(slug="concurrency-form", name="Concurrency form")
    v1 = FormVersion.objects.create(definition=definition, number=1, status=FormVersionStatus.DRAFT)
    FormField.objects.create(
        version=v1, key="a", label="A", type="text", order=0, options=[], validation={}
    )
    v2 = FormVersion.objects.create(definition=definition, number=2, status=FormVersionStatus.DRAFT)
    FormField.objects.create(
        version=v2, key="b", label="B", type="text", order=0, options=[], validation={}
    )

    results: list[str] = []
    errors: list[Exception] = []
    barrier = threading.Barrier(2)

    def publish(version) -> None:
        try:
            barrier.wait(timeout=5)
            services.publish_version(actor=actor, version=version)
            results.append("published")
        except Exception as exc:
            errors.append(exc)
        finally:
            connection.close()

    threads = [
        threading.Thread(target=publish, args=(v1,)),
        threading.Thread(target=publish, args=(v2,)),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)

    # Both writes have distinct schemas (different field keys, so different
    # hashes), so both are legitimate publishes serialised one after the
    # other by the lock — neither should have been refused as "unchanged".
    # Which one lands second (and so ends up the winner) depends on real
    # thread scheduling, not on anything this test controls — the invariant
    # under test is "exactly one", never which specific version it is.
    assert not errors, errors
    assert results == ["published", "published"]

    v1.refresh_from_db()
    v2.refresh_from_db()
    statuses = {v1.status, v2.status}
    assert statuses == {FormVersionStatus.PUBLISHED, FormVersionStatus.ARCHIVED}
    assert (
        FormVersion.objects.filter(
            definition=definition, status=FormVersionStatus.PUBLISHED
        ).count()
        == 1
    )


# ---------------------------------------------------------------------------
# Automation: the dispatch rate guard — "at most N runs per (rule, object)"
# ---------------------------------------------------------------------------


@pytest.mark.django_db(transaction=True)
def test_two_concurrent_dispatches_at_the_daily_limit_never_both_run(enrollment, admin_user):
    """The rate guard's own comment in `apps.automation.services.dispatch`
    names this exact race: `SELECT ... FOR UPDATE` on the rule row
    serialises two dispatches racing for the same `(rule, object)` pair so
    the second one counts the first one's just-committed run instead of a
    stale, pre-commit count that would let both through. The daily limit is
    lowered to 1 so a single successful run already exhausts it; the second,
    genuinely concurrent dispatch of a second distinct occurrence of the
    same object must be skipped, not run. `test_automation.py`'s own
    `TestRateGuard` test proves the guard's arithmetic sequentially; this is
    the real-thread version `AGENT_PLAYBOOK.md` calls for, which a
    sequential test cannot reach."""
    from datetime import timedelta

    from django.utils import timezone

    from apps.automation.models import (
        AutomationRule,
        AutomationRuleStatus,
        AutomationRun,
        AutomationRunStatus,
        AutomationTrigger,
    )
    from apps.automation.services import create_rule, dispatch
    from apps.policies.services import update_policy
    from apps.work.models import Activity, ActivityStatus, ActivityType

    update_policy(
        actor=admin_user,
        category="automation",
        key="max_runs_per_object_per_day",
        value=1,
        branch=None,
        reason="concurrency test",
    )
    AutomationRule.objects.update(status=AutomationRuleStatus.PAUSED)
    rule = create_rule(
        actor=admin_user,
        name="Concurrency rate-guard rule",
        trigger=AutomationTrigger.ACTIVITY_COMPLETED,
        actions=[],
        status=AutomationRuleStatus.ACTIVE,
    )

    activity_type = ActivityType.objects.create(
        slug="concurrency-rate-guard-type",
        name="Concurrency type",
        category="mentoring",
        allowed_creator_roles=["admin", "superadmin"],
        allowed_assignee_roles=["trainer"],
        visible_to_student=True,
        requires_review=False,
    )
    activity = Activity.objects.create(
        student=enrollment.student,
        enrollment=enrollment,
        batch=enrollment.batch,
        branch=enrollment.batch.branch,
        activity_type=activity_type,
        title="Concurrency activity",
        status=ActivityStatus.COMPLETED,
        completed_at=timezone.now(),
        created_by=admin_user,
    )

    # Two distinct *occurrences* of the same object (`_occurrence_for` keys
    # `ACTIVITY_COMPLETED` off `target.completed_at`) — genuinely different
    # in-memory `completed_at` values, one per thread, so the idempotency
    # guard's own `occurrence_key` uniqueness constraint is not what stops
    # the second dispatch here; only the rate guard's `select_for_update`
    # can be. Neither copy needs saving: `dispatch` reads attributes off the
    # object it is handed, never re-queries it.
    activity_occurrence_one = Activity.objects.get(pk=activity.pk)
    activity_occurrence_one.completed_at = timezone.now()
    activity_occurrence_two = Activity.objects.get(pk=activity.pk)
    activity_occurrence_two.completed_at = timezone.now() + timedelta(minutes=1)

    errors: list[Exception] = []
    barrier = threading.Barrier(2)

    def attempt(occurrence) -> None:
        try:
            barrier.wait(timeout=5)
            dispatch(AutomationTrigger.ACTIVITY_COMPLETED, occurrence)
        except Exception as exc:
            errors.append(exc)
        finally:
            connection.close()

    threads = [
        threading.Thread(target=attempt, args=(activity_occurrence_one,)),
        threading.Thread(target=attempt, args=(activity_occurrence_two,)),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)

    assert not errors, errors
    runs = list(AutomationRun.objects.filter(rule=rule, object_id=activity.pk))
    assert len(runs) == 2
    statuses = sorted(run.status for run in runs)
    assert statuses == [AutomationRunStatus.RAN, AutomationRunStatus.SKIPPED]


# ---------------------------------------------------------------------------
# Performance: recompute_risk — a brand-new enrolment's very first verdict
# ---------------------------------------------------------------------------


@pytest.mark.django_db(transaction=True)
def test_two_simultaneous_first_time_risk_recomputes_leave_exactly_one_risk_state(enrollment):
    """`recompute_risk`'s own docstring names two independent callers that
    can reach the same enrolment at once: the debounced Celery task and the
    synchronous `student_360` fallback for "an enrolment's very first read".
    Its `select_for_update()` locks a `RiskState` row that already exists —
    for a brand-new enrolment there is none yet, so the lock acquires
    nothing and both callers can read `existing=None` before either has
    written. `RiskState.enrollment` is a `OneToOneField` (the model's own
    docstring: "the one live verdict for an enrolment"), so two concurrent
    `.create()` calls for the same enrolment can only leave one row behind —
    this proves that holds under real concurrency, not just by inspection of
    the unique constraint."""
    from apps.performance import services
    from apps.performance.models import RiskState

    errors: list[Exception] = []
    barrier = threading.Barrier(2)

    def attempt() -> None:
        try:
            barrier.wait(timeout=5)
            services.recompute_risk(enrollment=enrollment)
        except Exception as exc:
            errors.append(exc)
        finally:
            connection.close()

    threads = [threading.Thread(target=attempt) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)

    assert not errors, errors
    assert RiskState.objects.filter(enrollment=enrollment).count() == 1


# ---------------------------------------------------------------------------
# Communication: manual_send — the server-recomputed confirm_count
# ---------------------------------------------------------------------------


@pytest.mark.django_db(transaction=True)
def test_two_concurrent_manual_sends_each_get_their_own_correct_count(
    admin_user, student_profile, other_student_profile
):
    """`manual_send` recomputes the recipient count fresh, in-process, on
    every call (`services.py`'s own docstring: "never trust the client's
    number as a ceiling either") rather than reading it from any cache or
    shared counter. Two independently valid sends — one to each of two real
    students — running at the same instant must not cross-contaminate: each
    must see and record exactly its own recipient's count, and the union of
    deliveries created must be exactly the two recipients, never a merged,
    doubled or dropped set."""
    from apps.communication import services
    from apps.communication.models import Delivery, MessageChannel

    template = services.create_template(
        actor=admin_user,
        key="concurrency.manual.send",
        name="Concurrency manual send",
        channel=MessageChannel.EMAIL,
        kind="activity.assigned",
    )
    version = template.versions.get(number=1)
    version = services.update_draft_version(
        actor=admin_user,
        version=version,
        subject="Hello {{recipient.name}}",
        body_text="Hi {{recipient.name}}",
        variables=["recipient.name"],
    )
    version = services.approve_version(actor=admin_user, version=version)
    services.publish_version(actor=admin_user, version=version)

    results: list[dict] = []
    errors: list[Exception] = []
    barrier = threading.Barrier(2)

    def send(student_id: str) -> None:
        try:
            barrier.wait(timeout=5)
            result = services.manual_send(
                actor=admin_user,
                channel=MessageChannel.EMAIL,
                template_key="concurrency.manual.send",
                recipients_spec={"students": [str(student_id)]},
                variables={},
                confirm_count=1,
            )
            results.append(result)
        except Exception as exc:
            errors.append(exc)
        finally:
            connection.close()

    threads = [
        threading.Thread(target=send, args=(student_profile.pk,)),
        threading.Thread(target=send, args=(other_student_profile.pk,)),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)

    assert not errors, errors
    assert len(results) == 2
    assert all(result["count"] == 1 for result in results)

    all_delivery_ids = {did for result in results for did in result["delivery_ids"]}
    assert len(all_delivery_ids) == 2  # no lost or shared row between the two sends
    assert Delivery.objects.filter(pk__in=all_delivery_ids).count() == 2
