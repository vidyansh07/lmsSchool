"""Fee triggers for automation: a payment recorded, an instalment due soon,
an instalment overdue.

What is pinned:

- a recorded payment reaches a `FEE_PAYMENT_RECORDED` rule with the payment,
  the fee as it now stands and the student, and `payment.is_first` tells the
  registration payment apart;
- the morning sweep offers each unpaid instalment due within the week as
  `FEE_INSTALMENT_DUE` with `days_until`, and each late one as
  `FEE_INSTALMENT_OVERDUE` with `days_overdue`; a paid one is never offered;
- a rule reminding "3 days before" runs once that day, not again on a second
  sweep the same morning;
- seeding with `suppressed()` fires nothing.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.utils import timezone

from apps.automation import services as automation
from apps.automation.evaluator import context_for
from apps.automation.models import AutomationRun, AutomationRunStatus, AutomationTrigger
from apps.fees import mail, services, tasks
from apps.fees.models import FeeInstallment
from apps.notifications.models import Notification


def _plan(enrollment, actor, *, start=None, count=3, amount="5000"):
    start = start or timezone.localdate()
    return services.set_fee_plan(
        enrollment=enrollment,
        actor=actor,
        agreed_amount=str(int(amount) * count),
        installments=[
            {"amount": amount, "due_on": start + timedelta(days=30 * index)}
            for index in range(count)
        ],
    )


def _remind(admin_user, *, trigger, conditions):
    return automation.create_rule(
        actor=admin_user,
        name=f"Fee rule {trigger}",
        trigger=trigger,
        conditions=conditions,
        actions=[
            {
                "type": "send_notification",
                "params": {
                    "to": "student",
                    "kind": "fee.reminder",
                    "title": "Fee reminder",
                },
            }
        ],
        status="active",
    )


@pytest.mark.django_db
def test_a_payment_reaches_its_rule_with_the_fee_and_the_student(
    admin_user, counsellor_user, enrollment
):
    plan = _plan(enrollment, counsellor_user)
    rule = automation.create_rule(
        actor=admin_user,
        name="Welcome the first payment",
        trigger="FEE_PAYMENT_RECORDED",
        conditions=[{"path": "payment.is_first", "op": "eq", "value": True}],
        actions=[
            {
                "type": "send_notification",
                "params": {
                    "to": "student",
                    "kind": "fee.payment",
                    "title": "Thanks for {{payment.receipt_number}}",
                },
            }
        ],
        status="active",
    )
    first = services.record_payment(plan=plan, actor=counsellor_user, amount="5000")
    context = context_for(AutomationTrigger.FEE_PAYMENT_RECORDED, first)
    assert context["payment"]["is_first"] is True
    assert context["fee"]["balance"] == 10000.0
    assert context["student"]["id"] == str(enrollment.student_id)

    automation.dispatch(AutomationTrigger.FEE_PAYMENT_RECORDED, first)
    assert AutomationRun.objects.get(rule=rule).status == AutomationRunStatus.RAN
    assert Notification.objects.filter(
        recipient=enrollment.student.user, title=f"Thanks for {first.receipt_number}"
    ).exists()

    second = services.record_payment(plan=plan, actor=counsellor_user, amount="2000")
    assert (
        context_for(AutomationTrigger.FEE_PAYMENT_RECORDED, second)["payment"]["is_first"] is False
    )
    automation.dispatch(AutomationTrigger.FEE_PAYMENT_RECORDED, second)
    assert AutomationRun.objects.filter(rule=rule).count() == 1


@pytest.mark.django_db
def test_the_payment_signal_enqueues_after_commit(
    counsellor_user, enrollment, django_capture_on_commit_callbacks, monkeypatch
):
    from apps.automation import tasks as automation_tasks

    seen: list[str] = []
    monkeypatch.setattr(
        automation_tasks.dispatch_fee_payment_recorded, "delay", lambda pk: seen.append(pk)
    )
    plan = _plan(enrollment, counsellor_user)
    with django_capture_on_commit_callbacks(execute=True):
        payment = services.record_payment(plan=plan, actor=counsellor_user, amount="5000")
    assert seen == [str(payment.pk)]

    seen.clear()
    with mail.suppressed(), django_capture_on_commit_callbacks(execute=True):
        services.record_payment(plan=plan, actor=counsellor_user, amount="1000")
    assert seen == []


@pytest.mark.django_db
def test_the_sweep_offers_due_and_late_instalments_once_each(
    counsellor_user, enrollment, monkeypatch
):
    from apps.fees.signals import instalment_due, instalment_overdue

    today = timezone.localdate()
    # First instalment 10 days late, second due in 3 days... built by hand so
    # both fall inside the windows.
    plan = services.set_fee_plan(
        enrollment=enrollment,
        actor=counsellor_user,
        agreed_amount="15000",
        installments=[
            {"amount": "5000", "due_on": today - timedelta(days=10)},
            {"amount": "5000", "due_on": today + timedelta(days=3)},
            {"amount": "5000", "due_on": today + timedelta(days=40)},
        ],
    )
    due: list[tuple[int, int]] = []
    late: list[tuple[int, int]] = []

    def on_due(sender, *, installment, days, **kwargs):
        due.append((installment.sequence, days))

    def on_late(sender, *, installment, days, **kwargs):
        late.append((installment.sequence, days))

    instalment_due.connect(on_due, dispatch_uid="test.on_due")
    instalment_overdue.connect(on_late, dispatch_uid="test.on_late")
    try:
        assert tasks.sweep(today=today) == {"due": 1, "overdue": 1}
        assert due == [(2, 3)] and late == [(1, 10)]

        # Paying the late one off takes it out of the next morning's sweep.
        due.clear()
        late.clear()
        services.record_payment(plan=plan, actor=counsellor_user, amount="5000")
        assert tasks.sweep(today=today) == {"due": 1, "overdue": 0}
        assert late == []
    finally:
        instalment_due.disconnect(dispatch_uid="test.on_due")
        instalment_overdue.disconnect(dispatch_uid="test.on_late")


@pytest.mark.django_db
def test_a_three_days_before_reminder_runs_once_that_day(admin_user, counsellor_user, enrollment):
    today = timezone.localdate()
    services.set_fee_plan(
        enrollment=enrollment,
        actor=counsellor_user,
        agreed_amount="10000",
        installments=[
            {"amount": "5000", "due_on": today + timedelta(days=3)},
            {"amount": "5000", "due_on": today + timedelta(days=33)},
        ],
    )
    rule = _remind(
        admin_user,
        trigger="FEE_INSTALMENT_DUE",
        conditions=[{"path": "instalment.days_until", "op": "eq", "value": 3}],
    )
    installment = FeeInstallment.objects.get(plan__enrollment=enrollment, sequence=1)
    context = context_for(AutomationTrigger.FEE_INSTALMENT_DUE, installment, days_until=3)
    assert context["instalment"]["count"] == 2
    assert context["instalment"]["balance"] == 5000.0

    automation.dispatch(AutomationTrigger.FEE_INSTALMENT_DUE, installment, days_until=3)
    automation.dispatch(AutomationTrigger.FEE_INSTALMENT_DUE, installment, days_until=3)
    assert AutomationRun.objects.filter(rule=rule).count() == 1
    assert (
        Notification.objects.filter(recipient=enrollment.student.user, kind="fee.reminder").count()
        == 1
    )

    # Another day's countdown does not match "3 days before".
    automation.dispatch(AutomationTrigger.FEE_INSTALMENT_DUE, installment, days_until=2)
    assert AutomationRun.objects.filter(rule=rule).count() == 1


@pytest.mark.django_db
def test_an_overdue_rule_reads_how_late_it_is(admin_user, counsellor_user, enrollment):
    today = timezone.localdate()
    services.set_fee_plan(
        enrollment=enrollment,
        actor=counsellor_user,
        agreed_amount="5000",
        installments=[{"amount": "5000", "due_on": today - timedelta(days=7)}],
    )
    rule = _remind(
        admin_user,
        trigger="FEE_INSTALMENT_OVERDUE",
        conditions=[{"path": "instalment.days_overdue", "op": "gte", "value": 7}],
    )
    installment = FeeInstallment.objects.get(plan__enrollment=enrollment)
    automation.dispatch(AutomationTrigger.FEE_INSTALMENT_OVERDUE, installment, days_overdue=7)
    assert AutomationRun.objects.get(rule=rule).status == AutomationRunStatus.RAN


@pytest.mark.django_db
def test_a_rule_may_only_read_its_triggers_paths(admin_user):
    from apps.common.exceptions import ApplicationError

    with pytest.raises(ApplicationError):
        automation.create_rule(
            actor=admin_user,
            name="Wrong path",
            trigger="FEE_PAYMENT_RECORDED",
            conditions=[{"path": "instalment.days_until", "op": "eq", "value": 3}],
            actions=[],
            status="draft",
        )


@pytest.mark.django_db
def test_the_example_fee_rules_are_drafts_an_admin_can_switch_on():
    from apps.automation.models import AutomationRule
    from apps.automation.services import _validate_rule_shape

    rules = AutomationRule.objects.filter(trigger__startswith="FEE_INSTALMENT_")
    assert {rule.status for rule in rules} == {"draft"}
    assert rules.count() == 2
    for rule in rules:
        _validate_rule_shape(rule.trigger, rule.conditions, rule.actions)
