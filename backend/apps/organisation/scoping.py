"""Which centre an actor may reach, and how to narrow a queryset to it.

One definition, in one module, because the alternative is the shape this
codebase already refuses for authorization: a rule restated in twenty
``access.py`` files, nineteen of which are correct. Every access function that
short-circuits on a global capability calls through here instead of writing its
own ``filter(branch_id=...)``.

Two questions, not one
----------------------
"Does this caller see every centre?" and "which centre is this caller in?" are
different questions, and collapsing them into a single nullable answer is what
makes a missing branch dangerous. :func:`is_unbounded` answers the first and is
true only for a platform operator; :func:`actor_branch_id` answers the second
and returns the plain column value. A caller who is neither unbounded nor
bounded — a staff account created through the Django admin, say, which bypasses
``apps.accounts.services.create_user`` — sees **nothing**, not everything.

That is a deliberate reading of the product decision. The worst case becomes a
manager who sees an empty screen and reports it within the hour, instead of a
manager who quietly sees another city's students. An administrator who genuinely
needs the whole institution is made a superadmin, which is one auditable act
rather than the absence of a value.

Called above the anonymous guard
--------------------------------
:func:`scope_to_branch` is invoked on the *capability-holder* branch of an
access function, which by convention sits **above** the
``is_authenticated``/``is_active`` guard (``CONVENTIONS`` §3). Both helpers must
therefore tolerate ``AnonymousUser``, and they do — but only because of their
first line. Removing it turns every anonymous request into an
``AttributeError``, or worse into an unscoped queryset.
"""

from __future__ import annotations

from typing import Any

from django.db.models import Q, QuerySet

from apps.accounts.roles import UserRole


def is_unbounded(user) -> bool:
    """Whether this caller sees every centre.

    Only a platform operator does. The ``is_superuser``/``SUPERADMIN`` pair
    matches ``capabilities_for`` and ``can_administer`` in
    :mod:`apps.accounts.roles`, so "sees everything" means the same thing in all
    three places.
    """
    if user is None or not getattr(user, "is_authenticated", False) or not user.is_active:
        return False
    return bool(getattr(user, "is_superuser", False)) or user.role == UserRole.SUPERADMIN


def actor_branch_id(user) -> Any | None:
    """The centre this caller is bounded to, or ``None`` if they carry none.

    ``None`` here means *no centre*, never *every centre* — ask
    :func:`is_unbounded` for that.
    """
    if user is None or not getattr(user, "is_authenticated", False) or not user.is_active:
        return None
    return getattr(user, "branch_id", None)


#: ``path`` names a *relation*, and a relation's id column is ``<path>_id`` —
#: except when the model being scoped is :class:`~apps.organisation.models.Branch`
#: itself. There is no relation to traverse there because the row *is* the
#: centre, so the caller passes ``"id"``; appending ``_id`` to that asks for a
#: field called ``id_id``, which does not exist, and the branch list raises
#: ``FieldError`` for every bounded caller instead of scoping. Named here rather
#: than special-cased at the one call site, because the next module to scope
#: branch rows would meet the identical trap.
_SELF_PATHS = frozenset({"id", "pk"})


def scope_to_branch(queryset: QuerySet, user, *, path: str = "branch") -> QuerySet:
    """Narrow ``queryset`` to the caller's centre.

    ``path`` is the ORM path from this model to the branch, e.g.
    ``"batch__branch"`` — or ``"id"`` when the model *is* ``Branch``. An
    unbounded caller gets the queryset back untouched — the same object, so
    nothing about their query plan changes.
    """
    if is_unbounded(user):
        return queryset
    branch_id = actor_branch_id(user)
    if branch_id is None:
        # Bounded to nothing is bounded to nothing. See the module docstring.
        return queryset.none()
    lookup = path if path in _SELF_PATHS else f"{path}_id"
    return queryset.filter(**{lookup: branch_id})


def scope_to_branch_or_shared(queryset: QuerySet, user, *, path: str) -> QuerySet:
    """Narrow to the caller's centre, keeping work that belongs to no batch.

    For the models whose ``batch`` is nullable, where ``batch IS NULL`` means
    "set for every batch running the course". ``filter(batch__branch_id=X)`` on
    a nullable foreign key is an INNER JOIN and drops those rows entirely —
    silently hiding every course-wide assignment from every branch-scoped
    manager, with no error and nothing in the logs. So the reasoning lives here
    once rather than at each of the six call sites.

    ``path`` names the branch, e.g. ``"batch__branch"``; the nullable relation
    is everything before the last segment.

    A caller with no centre gets ``.none()``, exactly as in
    :func:`scope_to_branch`. It is tempting to hand them the course-wide rows on
    the grounds that those belong to nobody — but "bounded to nothing is bounded
    to nothing" has to mean one thing in both helpers, and an account with no
    centre is a mis-filed account, not an institution-wide one. The account that
    genuinely sees everything is a superadmin, which :func:`is_unbounded`
    already answers above.
    """
    if is_unbounded(user):
        return queryset
    branch_id = actor_branch_id(user)
    if branch_id is None:
        return queryset.none()
    nullable_relation = path.rsplit("__", 1)[0]
    return queryset.filter(
        Q(**{f"{nullable_relation}__isnull": True}) | Q(**{f"{path}_id": branch_id})
    )


def branch_scope_key(user) -> str:
    """An unambiguous cache segment for this caller's reach.

    ``actor_branch_id`` alone returns ``None`` for both "sees every centre" and
    "sees no centre", and two audiences that must never share a cache entry must
    never share a key segment. Nothing caches anything yet; this exists so the
    caching workstream has one right answer to reach for rather than inventing a
    second one.
    """
    if is_unbounded(user):
        return "*"
    branch_id = actor_branch_id(user)
    return "-" if branch_id is None else str(branch_id)
