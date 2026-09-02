"""Authentication audit receivers.

Django emits these signals from every authentication path — the API, the
admin, and any future one — so hooking them here guarantees no login goes
unrecorded, even if a later feature bypasses the API views.
"""

from __future__ import annotations

from django.contrib.auth.signals import user_logged_in, user_logged_out, user_login_failed
from django.dispatch import receiver

from apps.audit.services import AuditAction, AuditResult, record


@receiver(user_logged_in)
def on_user_logged_in(sender, request, user, **kwargs):
    record(
        action=AuditAction.LOGIN_SUCCEEDED,
        actor=user,
        resource_type="user",
        resource_id=user.pk,
    )


@receiver(user_logged_out)
def on_user_logged_out(sender, request, user, **kwargs):
    if user is None:
        return
    record(
        action=AuditAction.LOGOUT,
        actor=user,
        resource_type="user",
        resource_id=user.pk,
    )


@receiver(user_login_failed)
def on_user_login_failed(sender, credentials, request=None, **kwargs):
    # ``credentials`` is already masked by Django, but the attempted username
    # is recorded explicitly (and only the username) so brute-force patterns
    # are detectable without storing any candidate password.
    attempted = credentials.get("username") or credentials.get("email") or ""
    record(
        action=AuditAction.LOGIN_FAILED,
        actor=None,
        actor_label=str(attempted)[:254],
        resource_type="user",
        result=AuditResult.FAILURE,
    )
