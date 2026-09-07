"""Who may see which centres.

One audience distinction, and it is the point of the whole module: a bounded
caller sees **their own centre and no other**, while a platform operator sees the
list. That is the difference between "render the name of the place I work" and
"browse the institution" — a manager in Pune has no business enumerating the
other centres, and a dropdown that offered them would be a dropdown that makes
promises the querysets refuse to keep.
"""

from __future__ import annotations

from django.db.models import QuerySet

from apps.accounts.roles import Capability, has_capability
from apps.organisation.scoping import is_unbounded, scope_to_branch

from .models import Branch


def visible_branches(user) -> QuerySet[Branch]:
    """Every centre the caller may see, as a queryset."""
    base = Branch.objects.with_related()

    if not has_capability(user, Capability.ORGANISATION_VIEW_ANY):
        return base.none()
    # `path="id"` narrows to the caller's own row rather than to a relation —
    # the branch a caller is bounded to *is* the branch they may read.
    return scope_to_branch(base, user, path="id")


def resolve_submitted_branch(actor, branch_id) -> Branch | None:
    """Turn a submitted branch id into a centre, for the callers it applies to.

    The write-side companion to
    :func:`apps.accounts.services.resolve_branch_for_new_record`, which requires
    an unbounded actor to *name* the centre a new record belongs to and forces a
    bounded actor's own. Until this existed no create serializer accepted the
    field at all, so the one role that exists to run a multi-centre institution
    could read every centre and create nothing in any of them: the refusal half
    of that rule was proved a hundred times over and the positive half nowhere.

    A bounded caller's value is dropped rather than validated. Their own centre
    is forced regardless, and validating the id would answer "does this name a
    real centre?" for anybody who can create a record — the enumeration oracle
    the 404-not-403 rule exists to close.
    """
    if branch_id is None or not is_unbounded(actor):
        return None
    return visible_branches(actor).filter(pk=branch_id).first()


def can_manage_branch(user, branch: Branch | None = None) -> bool:
    """Open a centre, rename one, or close one.

    ``branch`` is unused today — managing branches is a global capability held
    only by unbounded operators — but the signature matches every other check in
    this codebase so a per-branch rule can arrive without touching a call site.
    """
    return has_capability(user, Capability.ORGANISATION_MANAGE)
