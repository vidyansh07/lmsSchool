"""Authorization foundation.

Rules this module encodes:

* Deny by default. ``IsActiveUser`` is the project-wide default permission, so
  an endpoint is private unless it opts out explicitly.
* Authorization is decided on the server from the persisted role, never from
  anything the client sends.
* Views declare the *capability* they need, not the roles they accept. The
  role-to-capability mapping lives in :mod:`apps.accounts.roles`, so adding a
  role is one table entry rather than an audit of every view.
"""

from __future__ import annotations

from rest_framework.permissions import SAFE_METHODS, BasePermission

from apps.accounts.roles import Capability, UserRole, has_capability


class IsActiveUser(BasePermission):
    """Authenticated *and* still active. The project-wide default."""

    message = "Authentication is required."

    def has_permission(self, request, view) -> bool:
        user = getattr(request, "user", None)
        return bool(user and user.is_authenticated and user.is_active)


class AllowAnyPublic(BasePermission):
    """Explicit marker for the few genuinely public endpoints.

    Using this instead of DRF's ``AllowAny`` makes every public route grep-able
    during a security review.
    """

    def has_permission(self, request, view) -> bool:
        return True


class HasCapability(IsActiveUser):
    """Require a named capability.

    Views set ``required_capability``, or ``required_capabilities`` when several
    are needed together::

        class UserListView(ListAPIView):
            permission_classes = (HasCapability,)
            required_capability = Capability.USER_VIEW_ANY

    Per-method requirements are supported through ``capability_map``, keyed by
    HTTP method, for views that read and write on one route.
    """

    message = "Your role does not permit this action."

    def _required(self, request, view) -> tuple[str, ...]:
        by_method = getattr(view, "capability_map", None)
        if by_method and request.method in by_method:
            required = by_method[request.method]
            return (required,) if isinstance(required, str) else tuple(required)
        single = getattr(view, "required_capability", None)
        if single:
            return (single,)
        return tuple(getattr(view, "required_capabilities", ()))

    def has_permission(self, request, view) -> bool:
        if not super().has_permission(request, view):
            return False
        required = self._required(request, view)
        if not required:
            # A view that asks for this class but names no capability is a bug.
            # Fail closed rather than silently allowing everyone through.
            return False
        return all(has_capability(request.user, capability) for capability in required)


def requires(*capabilities: str) -> type[HasCapability]:
    """Build a permission class for the given capabilities.

    Convenience for views that would otherwise carry a one-line attribute::

        permission_classes = (requires(Capability.USER_CREATE),)
    """
    required = tuple(capabilities)

    class _Requires(HasCapability):
        def _required(self, request, view) -> tuple[str, ...]:
            return required

    _Requires.__name__ = "Requires_" + "_".join(c.replace(".", "_") for c in required)
    return _Requires


class HasRole(IsActiveUser):
    """Role check, kept for readability where a role really is the subject.

    Delegates nothing to the client and stays consistent with the capability
    matrix by reading the same ``UserRole`` values.
    """

    required_roles: tuple[str, ...] = ()
    message = "Your role does not permit this action."

    def has_permission(self, request, view) -> bool:
        if not super().has_permission(request, view):
            return False
        if request.user.is_superuser:
            return True
        return request.user.role in self.required_roles


class IsAdmin(HasRole):
    required_roles = (UserRole.ADMIN,)
    message = "Administrator role required."


class IsTrainer(HasRole):
    required_roles = (UserRole.TRAINER,)
    message = "Trainer role required."


class IsStudent(HasRole):
    required_roles = (UserRole.STUDENT,)
    message = "Student role required."


class IsAdminOrTrainer(HasRole):
    required_roles = (UserRole.ADMIN, UserRole.TRAINER)
    message = "Administrator or trainer role required."


class IsOwnerOrHasCapability(IsActiveUser):
    """Object-level rule: the owner of a record, or a holder of the capability.

    The template for LMS resources that belong to one person (profiles,
    enrollments, submissions, results). Ownership is resolved from the object,
    never from a client-supplied identifier, which is what closes the IDOR gap:
    guessing another record's id gets a 403, not someone else's data.

    Views set ``object_capability`` (and optionally ``owner_field``, default
    ``user``).
    """

    message = "You may only access your own records."

    def has_object_permission(self, request, view, obj) -> bool:
        user = request.user
        capability = getattr(view, "object_capability", None)
        if capability and has_capability(user, capability):
            return True
        owner_field = getattr(view, "owner_field", "user")
        owner = obj if hasattr(obj, "is_authenticated") else getattr(obj, owner_field, None)
        return owner is not None and owner == user


class ReadOnly(BasePermission):
    """Composable modifier: allows only safe HTTP methods."""

    def has_permission(self, request, view) -> bool:
        return request.method in SAFE_METHODS


__all__ = [
    "AllowAnyPublic",
    "Capability",
    "HasCapability",
    "HasRole",
    "IsActiveUser",
    "IsAdmin",
    "IsAdminOrTrainer",
    "IsOwnerOrHasCapability",
    "IsStudent",
    "IsTrainer",
    "ReadOnly",
    "requires",
]
