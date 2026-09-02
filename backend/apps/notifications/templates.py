"""Email templates — §7.2.

Named renderers in code, not rows in a table.

That is a deliberate choice. A database-editable email template is a text field
that ends up in somebody's inbox, and making it rich enough to be worth editing
means accepting HTML, which means accepting an injection surface on a document
this system sends *out* under the institution's name. What an operator actually
needs to change — the institution name, the signature — is configuration, and
lives in settings.

Each template is a function taking a context dictionary and returning
``(subject, body)``. Plain text, for the same reason as the credential mail in
`apps.accounts.emails`: no escaping responsibility, no rendering surprises.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from django.conf import settings


def _footer() -> str:
    return (
        "\n\n—\n"
        f"{getattr(settings, 'EMAIL_SIGNATURE_NAME', 'Grras Solutions')}\n"
        "You are receiving this because of your enrolment. "
        "You can turn these emails off in your notification settings."
    )


def _link(path: str) -> str:
    """An absolute link built from configuration, never from stored data."""
    base = str(getattr(settings, "FRONTEND_BASE_URL", "")).rstrip("/")
    return f"{base}{path}" if path else base


def generic(context: dict[str, Any]) -> tuple[str, str]:
    """The default. Used for any notification without a bespoke template."""
    title = context.get("title", "An update from your course")
    body = context.get("body", "")
    path = context.get("link_path", "")

    lines = [f"Hello {context.get('first_name', 'there')},", "", title]
    if body:
        lines += ["", body]
    if path:
        lines += ["", f"See it here: {_link(path)}"]
    return title, "\n".join(lines) + _footer()


def assignment_due(context: dict[str, Any]) -> tuple[str, str]:
    subject = f"Due soon: {context.get('title', 'an assignment')}"
    body = "\n".join(
        [
            f"Hello {context.get('first_name', 'there')},",
            "",
            f"{context.get('title')} is due on "
            f"{context.get('due_at', 'a date set by your trainer')}.",
            "",
            f"Hand it in here: {_link(context.get('link_path', '/my-assignments'))}",
        ]
    )
    return subject, body + _footer()


def result_published(context: dict[str, Any]) -> tuple[str, str]:
    subject = f"Result published: {context.get('title', 'your test')}"
    body = "\n".join(
        [
            f"Hello {context.get('first_name', 'there')},",
            "",
            f"Your result for {context.get('title')} has been published.",
            "",
            f"See it here: {_link(context.get('link_path', '/my-results'))}",
        ]
    )
    return subject, body + _footer()


def certificate_issued(context: dict[str, Any]) -> tuple[str, str]:
    subject = f"Your certificate for {context.get('title', 'your course')}"
    body = "\n".join(
        [
            f"Hello {context.get('first_name', 'there')},",
            "",
            f"Your certificate for {context.get('title')} has been issued.",
            "",
            f"Download it here: {_link(context.get('link_path', '/my-progress'))}",
        ]
    )
    return subject, body + _footer()


def attendance_warning(context: dict[str, Any]) -> tuple[str, str]:
    subject = "Your attendance needs attention"
    body = "\n".join(
        [
            f"Hello {context.get('first_name', 'there')},",
            "",
            context.get("body", "Your attendance is below what the course requires."),
            "",
            f"See where you stand: {_link(context.get('link_path', '/my-attendance'))}",
        ]
    )
    return subject, body + _footer()


#: Template name → renderer. A notification names a template; an unknown name
#: falls back to `generic` rather than failing to send.
TEMPLATES: dict[str, Callable[[dict[str, Any]], tuple[str, str]]] = {
    "generic": generic,
    "assignment_due": assignment_due,
    "result_published": result_published,
    "certificate_issued": certificate_issued,
    "attendance_warning": attendance_warning,
}


def render(name: str, context: dict[str, Any]) -> tuple[str, str]:
    return TEMPLATES.get(name, generic)(context)
