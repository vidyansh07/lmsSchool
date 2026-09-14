"""Which accounts a caller may reach.

Small, and in its own module rather than private to ``user_views`` because a
second app now needs the same answer: an announcement addressed to named people
resolves those people, and it has to resolve them inside the writer's own
centre. Two definitions of "the accounts I may name" is two rules that will
eventually disagree, and the one that disagrees quietly is the one that puts a
notice from Jaipur into a Pune student's tray.
"""

from __future__ import annotations

from django.db.models import QuerySet

from apps.organisation.scoping import scope_to_branch

from .models import User


def visible_accounts(user) -> QuerySet[User]:
    """Accounts this caller may reach, narrowed to their own centre.

    A queryset rather than a filter applied afterwards, so an account outside
    the caller's centre is a 404 on every route that resolves through it rather
    than a 403 that would confirm the person exists.
    """
    return scope_to_branch(
        User.objects.select_related("student_profile", "trainer_profile", "branch"),
        user,
        path="branch",
    )
