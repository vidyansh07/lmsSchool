"""The fee mails a student is sent: a receipt for every payment, and a
statement when their fee is agreed or changed.

Both are written to the outbox inside the transaction that made the change and
handed to the worker only once it commits, so a payment that rolls back never
mails a receipt for money that was not recorded. The PDF is not stored: the
outbox row names the payment or the plan, and the document is drawn when the
message is sent (`apps.notifications.attachments`).

The wording is the institution's to change. A published communication
template with key `fee.receipt` or `fee.statement` (email channel) replaces
the built-in subject and text; the variables it may use are listed in
`RECEIPT_VARIABLES` and `STATEMENT_VARIABLES`.

Sending is automatic unless an administrator turns it off
(`fee_receipt_email_enabled`, `fee_statement_email_enabled`, and the
institution-wide `notification_email_enabled`). A counsellor can always send
one again by hand while mail is on at all.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import timedelta
from functools import partial
from typing import Any

from django.db import transaction
from django.utils import timezone

from apps.common.exceptions import ApplicationError
from apps.notifications.attachments import RenderedAttachment, reference, register
from apps.notifications.models import EmailMessage, EmailStatus

from .models import FeePayment, FeePlan

logger = logging.getLogger("grras.fees")

RECEIPT_KIND = "fee_receipt"
STATEMENT_KIND = "fee_statement"
RECEIPT_TEMPLATE_KEY = "fee.receipt"
STATEMENT_TEMPLATE_KEY = "fee.statement"

_COMMON_VARIABLES = (
    "student.name",
    "student.first_name",
    "student.student_id",
    "course.title",
    "batch.name",
    "batch.code",
    "enrollment.code",
    "fee.agreed",
    "fee.discount",
    "fee.discount_percent",
    "fee.payable",
    "fee.paid",
    "fee.balance",
    "fee.next_due_amount",
    "fee.next_due_on",
    "institution.name",
)
RECEIPT_VARIABLES = (
    *_COMMON_VARIABLES,
    "payment.receipt_number",
    "payment.amount",
    "payment.paid_on",
    "payment.method",
)
STATEMENT_VARIABLES = _COMMON_VARIABLES

#: A statement still waiting in the outbox is not queued twice: it is drawn when
#: it is sent, so the one already waiting will show the latest figures anyway.
#: This is what keeps "set the fee, then reshape the schedule" one mail, not two.
_STATEMENT_COALESCE = timedelta(minutes=10)


#: Set while seeding demo data or importing history: those ledgers are written
#: through the same services, and nobody should be mailed a receipt for a
#: payment made months ago in another system.
_SUPPRESSED: ContextVar[bool] = ContextVar("fee_mail_suppressed", default=False)


@contextmanager
def suppressed() -> Iterator[None]:
    """No automatic fee mail inside this block."""
    token = _SUPPRESSED.set(True)
    try:
        yield
    finally:
        _SUPPRESSED.reset(token)


def _rupees(value) -> str:
    return f"₹{value:,.2f}"


def _settings():
    from apps.configuration.settings_resolver import effective_settings

    return effective_settings()


def _support_line(resolved) -> str:
    return " · ".join(part for part in (resolved.support_email, resolved.support_phone) if part)


def _plan_for_documents(plan_id: str) -> FeePlan:
    return FeePlan.objects.select_related(
        "enrollment__student__user", "enrollment__course", "enrollment__batch"
    ).get(pk=plan_id)


def _variables(plan: FeePlan, payment: FeePayment | None = None) -> dict[str, Any]:
    enrollment = plan.enrollment
    user = enrollment.student.user
    variables: dict[str, Any] = {
        "student": {
            "name": user.full_name or user.email,
            "first_name": user.first_name or user.full_name or "",
            "student_id": enrollment.student.student_id,
        },
        "course": {"title": enrollment.course.title},
        "batch": {"name": enrollment.batch.name, "code": enrollment.batch.code},
        "enrollment": {"code": enrollment.code},
        "fee": {
            "agreed": _rupees(plan.agreed_amount),
            "discount": _rupees(plan.discount_amount),
            "discount_percent": (
                f"{plan.discount_percent.normalize():f}%"
                if plan.discount_percent is not None
                else ""
            ),
            "payable": _rupees(plan.payable),
            "paid": _rupees(plan.paid),
            "balance": _rupees(plan.balance),
            "next_due_amount": _rupees(plan.next_due_amount) if plan.next_due_amount else "",
            "next_due_on": f"{plan.next_due_on:%d %B %Y}" if plan.next_due_on else "",
        },
        "institution": {"name": _settings().institution_name},
    }
    if payment is not None:
        variables["payment"] = {
            "receipt_number": payment.receipt_number,
            "amount": _rupees(payment.amount),
            "paid_on": f"{payment.paid_on:%d %B %Y}",
            "method": payment.get_method_display(),
        }
    return variables


def _sign_off() -> str:
    resolved = _settings()
    lines = ["", "—", resolved.institution_name]
    support = _support_line(resolved)
    if support:
        lines.append(f"Questions about your fee? {support}")
    return "\n".join(lines)


def _compose(key: str, variables: dict[str, Any], subject: str, body: str) -> tuple[str, str]:
    """The institution's published template if there is one, else the default."""
    from apps.communication.rendering import render_template
    from apps.communication.services import resolve_published_template

    version = resolve_published_template(key=key, channel="email")
    if version is not None:
        rendered = render_template(version, variables)
        subject = rendered["subject"] or subject
        body = rendered["text"] or body
    return subject[:255], body


def _receipt_text(plan: FeePlan, payment: FeePayment) -> tuple[str, str]:
    v = _variables(plan, payment)
    subject = f"Receipt {payment.receipt_number}: {v['payment']['amount']} received"
    lines = [
        f"Dear {v['student']['first_name'] or v['student']['name']},",
        "",
        f"Thank you. We have received {v['payment']['amount']} on {v['payment']['paid_on']} "
        f"by {v['payment']['method'].lower()} towards {v['course']['title']} "
        f"({v['batch']['name']}).",
        "",
        f"Receipt number: {payment.receipt_number}",
        f"Fee payable: {v['fee']['payable']}",
        f"Received so far: {v['fee']['paid']}",
        f"Balance: {v['fee']['balance']}",
    ]
    if plan.next_due_on and plan.balance > 0:
        lines.append(f"Next payment: {v['fee']['next_due_amount']} by {v['fee']['next_due_on']}")
    lines += ["", "Your receipt is attached as a PDF.", _sign_off()]
    return _compose(RECEIPT_TEMPLATE_KEY, v, subject, "\n".join(lines))


def _statement_text(plan: FeePlan) -> tuple[str, str]:
    v = _variables(plan)
    subject = f"Your fee for {v['course']['title']}"
    discount = ""
    if plan.discount_amount > 0:
        how = f" ({v['fee']['discount_percent']})" if v["fee"]["discount_percent"] else ""
        discount = f"Discount: {v['fee']['discount']}{how}"
    lines = [
        f"Dear {v['student']['first_name'] or v['student']['name']},",
        "",
        f"Here is your fee for {v['course']['title']} ({v['batch']['name']}), "
        f"enrolment {v['enrollment']['code']}.",
        "",
        f"Course fee: {v['fee']['agreed']}",
        *([discount] if discount else []),
        f"Payable: {v['fee']['payable']}",
    ]
    if plan.next_due_on and plan.balance > 0:
        lines.append(f"Next payment: {v['fee']['next_due_amount']} by {v['fee']['next_due_on']}")
    lines += [
        "",
        "The attached statement lists the instalment schedule and every payment received.",
        _sign_off(),
    ]
    return _compose(STATEMENT_TEMPLATE_KEY, v, subject, "\n".join(lines))


def _queue(message: EmailMessage) -> None:
    from apps.notifications.channels import enqueue_email

    transaction.on_commit(partial(enqueue_email, message))


def _address(plan: FeePlan) -> str:
    user = plan.enrollment.student.user
    return user.email if user.email and user.is_active else ""


# ---------------------------------------------------------------------------
# Public: queue a mail
# ---------------------------------------------------------------------------


def email_receipt(payment: FeePayment, *, automatic: bool = True) -> EmailMessage | None:
    """Queue the receipt for one payment. Automatic sends respect the
    institution's switches and quietly do nothing without an address; a send
    asked for by hand says why it cannot go."""
    if automatic and _SUPPRESSED.get():
        return None
    resolved = _settings()
    plan = _plan_for_documents(payment.plan_id)
    to = _address(plan)
    if automatic:
        if not (resolved.notification_email_enabled and resolved.fee_receipt_email_enabled):
            return None
        if not to:
            return None
    else:
        _refuse_unless_sendable(resolved, to)
    subject, body = _receipt_text(plan, payment)
    message = EmailMessage.objects.create(
        to_email=to,
        subject=subject,
        body=body,
        template=RECEIPT_KIND,
        attachments=[reference(RECEIPT_KIND, payment.pk)],
    )
    _queue(message)
    return message


def email_statement(plan: FeePlan, *, automatic: bool = True) -> EmailMessage | None:
    """Queue a fee statement. An automatic one already waiting in the outbox
    for this plan is reused rather than doubled."""
    if automatic and _SUPPRESSED.get():
        return None
    resolved = _settings()
    plan = _plan_for_documents(plan.pk)
    to = _address(plan)
    if automatic:
        if not (resolved.notification_email_enabled and resolved.fee_statement_email_enabled):
            return None
        if not to:
            return None
        waiting = (
            EmailMessage.objects.filter(
                template=STATEMENT_KIND,
                status=EmailStatus.PENDING,
                attempts=0,
                created_at__gte=timezone.now() - _STATEMENT_COALESCE,
                attachments__contains=[reference(STATEMENT_KIND, plan.pk)],
            )
            .order_by("-created_at")
            .first()
        )
        if waiting is not None:
            return waiting
    else:
        _refuse_unless_sendable(resolved, to)
    subject, body = _statement_text(plan)
    message = EmailMessage.objects.create(
        to_email=to,
        subject=subject,
        body=body,
        template=STATEMENT_KIND,
        attachments=[reference(STATEMENT_KIND, plan.pk)],
    )
    _queue(message)
    return message


def _refuse_unless_sendable(resolved, to: str) -> None:
    if not resolved.notification_email_enabled:
        raise ApplicationError(
            {"non_field_errors": ["Email is turned off in the institution settings."]}
        )
    if not to:
        raise ApplicationError(
            {"non_field_errors": ["This student has no active email address to send to."]}
        )


def queue_safely(callback, *args, **kwargs) -> None:
    """Run a mail step without letting a mail problem undo the money.

    Called from inside the ledger's transactions. Anything the mail step
    raises is logged and swallowed: a receipt that could not be queued is a
    support task, a payment that failed to record because of it is a lost
    payment.
    """
    try:
        with transaction.atomic():
            callback(*args, **kwargs)
    except Exception:
        logger.exception(
            "Could not queue a fee mail", extra={"context": {"step": callback.__name__}}
        )


def emails_for_plan(plan: FeePlan):
    """Every fee mail about this plan, newest first: its statements and the
    receipts for its payments."""
    payment_ids = [str(pk) for pk in plan.payments.values_list("pk", flat=True)]
    references = [reference(STATEMENT_KIND, plan.pk)] + [
        reference(RECEIPT_KIND, pk) for pk in payment_ids
    ]
    from django.db.models import Q

    query = Q()
    for item in references:
        query |= Q(attachments__contains=[item])
    return (
        EmailMessage.objects.filter(template__in=[RECEIPT_KIND, STATEMENT_KIND])
        .filter(query)
        .order_by("-created_at")
    )


# ---------------------------------------------------------------------------
# Drawing the attachments at send time
# ---------------------------------------------------------------------------


def _render_receipt(payment_id: str) -> RenderedAttachment:
    from .receipts import render_receipt_pdf

    payment = FeePayment.objects.select_related(
        "plan__enrollment__student__user",
        "plan__enrollment__course",
        "plan__enrollment__batch",
        "recorded_by",
    ).get(pk=payment_id)
    resolved = _settings()
    content = render_receipt_pdf(
        payment, institution_name=resolved.institution_name, support_line=_support_line(resolved)
    )
    return RenderedAttachment(f"receipt-{payment.receipt_number}.pdf", content)


def _render_statement(plan_id: str) -> RenderedAttachment:
    from .statements import render_statement_pdf

    plan = _plan_for_documents(plan_id)
    resolved = _settings()
    content = render_statement_pdf(
        plan, institution_name=resolved.institution_name, support_line=_support_line(resolved)
    )
    return RenderedAttachment(f"fee-statement-{plan.enrollment.code}.pdf", content)


def register_attachments() -> None:
    register(RECEIPT_KIND, _render_receipt)
    register(STATEMENT_KIND, _render_statement)
