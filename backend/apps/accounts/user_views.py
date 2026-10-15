"""User administration endpoints (``/api/v1/users/``).

Every view here requires an explicit capability. Nothing falls back to "is the
caller staff" or an inline role comparison.
"""

from __future__ import annotations

import django_filters
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import serializers, status
from rest_framework.filters import OrderingFilter, SearchFilter
from rest_framework.generics import ListCreateAPIView, RetrieveUpdateAPIView, get_object_or_404
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.access import visible_accounts
from apps.audit.models import AuditAction
from apps.common import bulk
from apps.common.permissions import Capability, HasCapability, IsActiveUser
from apps.common.throttling import BurstThrottle
from apps.organisation.access import resolve_submitted_branch

from . import services, sessions
from .models import User, UserRole
from .serializers import (
    AdminUserCreateSerializer,
    AdminUserDetailSerializer,
    AdminUserUpdateSerializer,
    CredentialActionSerializer,
    SessionSerializer,
    SetActiveSerializer,
    UserAuditEntrySerializer,
    UserBranchSerializer,
    UserRoleTransitionSerializer,
)
from .stepup import StepUpRequired, is_fresh

USERS_TAG = ["users"]


#: The definition moved to `apps.accounts.access` once a second app needed it.
#: The local name stays because six routes in this module resolve through it.
_scoped_users = visible_accounts


class UserFilterSet(django_filters.FilterSet):
    """Server-side filtering for the administrator table.

    Every filter maps to an indexed column or a small enumeration; there is no
    free-form field lookup, so a client cannot craft an expensive query.
    """

    branch = django_filters.UUIDFilter(field_name="branch_id")
    role = django_filters.CharFilter(field_name="role", lookup_expr="exact")
    is_active = django_filters.BooleanFilter(field_name="is_active")
    is_email_verified = django_filters.BooleanFilter(field_name="is_email_verified")
    joined_after = django_filters.DateFilter(field_name="date_joined", lookup_expr="date__gte")
    joined_before = django_filters.DateFilter(field_name="date_joined", lookup_expr="date__lte")

    class Meta:
        model = User
        fields = ("branch", "role", "is_active", "is_email_verified")


class UserListCreateView(ListCreateAPIView):
    """List users, or create one.

    Listing supports search, filtering, ordering and pagination — all executed
    by the database. The page size is capped by ``DefaultPagination``, so no
    request can pull the whole table into a browser.
    """

    permission_classes = (HasCapability,)
    capability_map = {
        "GET": Capability.USER_VIEW_ANY,
        "POST": Capability.USER_CREATE,
    }
    filter_backends = (DjangoFilterBackend, SearchFilter, OrderingFilter)
    filterset_class = UserFilterSet
    #: Matches name, email, and the student/trainer identifiers through the
    #: reverse one-to-one relations.
    search_fields = (
        "email",
        "first_name",
        "last_name",
        "student_profile__student_id",
        "trainer_profile__trainer_id",
    )
    ordering_fields = ("email", "first_name", "last_name", "role", "date_joined", "created_at")
    ordering = ("-created_at",)

    def get_queryset(self):
        # Without this a branch-scoped manager listing accounts would see every
        # one in the institution while seeing none of their batches, which is
        # the kind of inconsistency people report as a data leak.
        return _scoped_users(self.request.user)

    def get_serializer_class(self):
        return (
            AdminUserCreateSerializer
            if self.request.method == "POST"
            else AdminUserDetailSerializer
        )

    @extend_schema(summary="List users", tags=USERS_TAG)
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    @extend_schema(
        summary="Create a user",
        request=AdminUserCreateSerializer,
        responses={
            201: AdminUserDetailSerializer,
            409: OpenApiResponse(description="Email in use."),
        },
        tags=USERS_TAG,
    )
    def post(self, request, *args, **kwargs):
        serializer = AdminUserCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        fields = dict(serializer.validated_data)
        branch = resolve_submitted_branch(request.user, fields.pop("branch", None))
        user = services.create_user(actor=request.user, branch=branch, **fields)
        return Response(
            AdminUserDetailSerializer(user, context={"request": request}).data,
            status=status.HTTP_201_CREATED,
        )


class UserDetailView(RetrieveUpdateAPIView):
    """Retrieve or update one user."""

    permission_classes = (HasCapability,)
    capability_map = {
        "GET": Capability.USER_VIEW_ANY,
        "PATCH": Capability.USER_UPDATE_ANY,
        "PUT": Capability.USER_UPDATE_ANY,
    }
    lookup_url_kwarg = "user_id"

    def get_queryset(self):
        return _scoped_users(self.request.user)

    def get_serializer_class(self):
        return (
            AdminUserDetailSerializer if self.request.method == "GET" else AdminUserUpdateSerializer
        )

    @extend_schema(
        summary="Retrieve a user", responses={200: AdminUserDetailSerializer}, tags=USERS_TAG
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    @extend_schema(
        summary="Update a user",
        request=AdminUserUpdateSerializer,
        responses={200: AdminUserDetailSerializer},
        tags=USERS_TAG,
    )
    def patch(self, request, *args, **kwargs):
        user = self.get_object()
        serializer = AdminUserUpdateSerializer(instance=user, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)

        updated = services.update_user(user=user, actor=request.user, **serializer.validated_data)
        return Response(AdminUserDetailSerializer(updated, context={"request": request}).data)


class UserRoleTransitionView(APIView):
    """Change authorization role without treating it as an ordinary field edit."""

    permission_classes = (HasCapability,)
    required_capability = Capability.USER_CHANGE_ROLE

    @extend_schema(
        summary="Transition a user's role",
        request=UserRoleTransitionSerializer,
        responses={
            200: AdminUserDetailSerializer,
            403: OpenApiResponse(description="Outside your authority, or step-up required."),
            409: OpenApiResponse(
                description="A persona conversion or last-superadmin guard refused it."
            ),
        },
        tags=USERS_TAG,
    )
    def post(self, request, user_id):
        user = get_object_or_404(_scoped_users(request.user), pk=user_id)
        serializer = UserRoleTransitionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        # Granting authority is at least as dangerous as ending a session or
        # locking a permission, both of which already ask for a fresh step-up.
        # Checked after the scoped lookup, so a cross-centre id still 404s.
        if not is_fresh(request):
            raise StepUpRequired()
        updated = services.transition_user_role(
            user=user, actor=request.user, **serializer.validated_data
        )
        return Response(AdminUserDetailSerializer(updated, context={"request": request}).data)


class UserSetActiveView(APIView):
    """Activate or deactivate an account.

    A separate, separately-authorised endpoint rather than a field on the patch
    body: account status is a security control, and it should not be possible to
    flip it as a side effect of editing a phone number.
    """

    permission_classes = (HasCapability,)
    required_capability = Capability.USER_SET_ACTIVE

    @extend_schema(
        summary="Activate or deactivate a user",
        request=SetActiveSerializer,
        responses={
            200: AdminUserDetailSerializer,
            409: OpenApiResponse(description="Not permitted."),
        },
        tags=USERS_TAG,
    )
    def post(self, request, user_id):
        # Resolved through the scoped queryset, like its sibling routes.
        # `services.set_user_active` still calls `_guard_administration` and is
        # still the authority — but resolving by raw pk first and letting the
        # guard answer 403 would tell a caller in Jaipur that a uuid they
        # guessed names a real account in Pune, which is exactly the
        # enumeration oracle the 404 discipline exists to close.
        user = get_object_or_404(_scoped_users(request.user), pk=user_id)
        serializer = SetActiveSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        # Deactivating yourself would lock you out with no way back in.
        if user.pk == request.user.pk and not serializer.validated_data["is_active"]:
            return Response(
                {
                    "error": {
                        "code": "conflict",
                        "message": "You cannot deactivate your own account.",
                        "request_id": getattr(request, "request_id", "-"),
                    }
                },
                status=status.HTTP_409_CONFLICT,
            )

        updated = services.set_user_active(
            user=user,
            is_active=serializer.validated_data["is_active"],
            actor=request.user,
            reason=serializer.validated_data.get("reason", ""),
        )
        return Response(AdminUserDetailSerializer(updated, context={"request": request}).data)


class UserCredentialActionView(APIView):
    """Send somebody a password-reset or email-verification link.

    An administrator who has just corrected a typo in an address, or unlocked an
    account that had been dormant, needs a way to get that person back in. The
    alternative people reach for otherwise is worse: setting a password on
    somebody's behalf and telling it to them, which means two people know it and
    the audit trail says "administrator changed a password" rather than "the
    owner set one".

    So this sends a link and nothing else. No administrator ever learns the
    resulting credential.
    """

    permission_classes = (HasCapability,)
    required_capability = Capability.USER_UPDATE_ANY

    ACTIONS = ("password_reset", "email_verification")

    @extend_schema(
        summary="Send a credential link to a user",
        request=CredentialActionSerializer,
        responses={
            202: OpenApiResponse(description="Accepted; a link has been sent if it could be."),
            403: OpenApiResponse(description="Outside your authority."),
        },
        tags=USERS_TAG,
    )
    def post(self, request, user_id):
        # Scoped like its siblings: a 403 here for an account in another centre
        # would confirm that the id is real.
        user = get_object_or_404(_scoped_users(request.user), pk=user_id)
        serializer = CredentialActionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        action = serializer.validated_data["action"]

        services.send_credential_link(user=user, actor=request.user, action=action)
        # 202, and the same answer whichever branch ran: whether an address is
        # deliverable is not something this endpoint should report.
        return Response(
            {"detail": "If the account can receive it, a link has been sent."},
            status=status.HTTP_202_ACCEPTED,
        )


class UserBulkRequestSerializer(bulk.BulkTargetSerializer):
    """`POST /users/bulk/`: one action across many accounts."""

    ACTIONS = ("resend_invitation", "move_centre")

    action = serializers.ChoiceField(choices=ACTIONS)
    branch_id = serializers.UUIDField(required=False)
    reason = serializers.CharField(required=False, allow_blank=True, max_length=255)

    def validate(self, attrs):
        attrs = super().validate(attrs)
        if attrs["action"] == "move_centre":
            if not attrs.get("branch_id"):
                raise serializers.ValidationError({"branch_id": ["Choose the centre."]})
            if not (attrs.get("reason") or "").strip():
                raise serializers.ValidationError(
                    {"reason": ["Say why these accounts are moving; it goes in the audit trail."]}
                )
        return attrs


#: What each bulk action needs on top of reading the accounts list.
_BULK_USER_CAPABILITY = {
    "resend_invitation": Capability.USER_UPDATE_ANY,
    "move_centre": Capability.ORGANISATION_ASSIGN_USERS,
}


class UserBulkView(APIView):
    """Resend invitations to, or move to a centre, many accounts at once.

    The rows are the ticked ids or everything the list's filters match, out of
    the accounts this caller may see (`apps.common.bulk`). Each one goes
    through the same service as the single-account screen — the authority
    ladder, the centre rule and the audit entry all apply per account — and an
    account a rule refuses is skipped with the reason, not failed silently.
    """

    permission_classes = (IsActiveUser,)
    throttle_classes = (BurstThrottle,)

    @extend_schema(
        summary="Act on many accounts at once",
        request=UserBulkRequestSerializer,
        responses={200: bulk.BulkResultSerializer},
        tags=USERS_TAG,
    )
    def post(self, request):
        from apps.accounts.roles import has_capability
        from apps.common.exceptions import AuthorityError
        from apps.organisation import access as organisation_access

        serializer = UserBulkRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        action = data["action"]
        if not (
            has_capability(request.user, Capability.USER_VIEW_ANY)
            and has_capability(request.user, _BULK_USER_CAPABILITY[action])
        ):
            raise AuthorityError({"action": ["You cannot do this to accounts."]})

        branch = None
        if action == "move_centre":
            branch = get_object_or_404(
                organisation_access.visible_branches(request.user), pk=data["branch_id"]
            )

        rows, missing = bulk.resolve_targets(
            _scoped_users(request.user),
            data,
            filterset="apps.accounts.user_views.UserFilterSet",
            search_fields=UserListCreateView.search_fields,
        )

        def resend(user: User) -> str | None:
            return services.resend_invitation(user=user, actor=request.user)

        def move(user: User) -> str | None:
            if user.pk == request.user.pk:
                return "You cannot move your own account."
            if user.role == UserRole.STUDENT:
                return "A student stays at the centre they were admitted to; transfer their class."
            if user.branch_id == branch.pk:
                return f"Already at {branch.name}."
            services.move_user_to_branch(
                user=user, branch=branch, actor=request.user, reason=data["reason"].strip()
            )
            return None

        result = bulk.apply_each(
            bulk.BulkResult(action=action),
            rows,
            missing,
            resend if action == "resend_invitation" else move,
            lambda user: user.get_full_name() or user.email,
        )
        return Response(bulk.BulkResultSerializer(result).data)


class UserBranchView(APIView):
    """Move an account to another centre.

    Its own endpoint, and its own capability, because it is the one change to an
    account that alters what its owner can see rather than what they are. Folded
    into the patch body it would be flippable while somebody corrected a phone
    number, and an administrator could move themselves.
    """

    permission_classes = (HasCapability,)
    required_capability = Capability.ORGANISATION_ASSIGN_USERS

    @extend_schema(
        summary="Move a user to another branch",
        request=UserBranchSerializer,
        responses={
            200: AdminUserDetailSerializer,
            403: OpenApiResponse(description="Outside your authority."),
        },
        tags=USERS_TAG,
    )
    def post(self, request, user_id):
        from apps.organisation import access as organisation_access

        user = get_object_or_404(_scoped_users(request.user), pk=user_id)
        serializer = UserBranchSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        # Resolved out of the caller's own visible branches, so a bounded
        # administrator cannot hand somebody to a centre they cannot see.
        branch = get_object_or_404(
            organisation_access.visible_branches(request.user),
            pk=serializer.validated_data["branch_id"],
        )
        updated = services.move_user_to_branch(
            user=user,
            branch=branch,
            actor=request.user,
            reason=serializer.validated_data.get("reason", ""),
        )
        return Response(AdminUserDetailSerializer(updated, context={"request": request}).data)


class UserAuditView(APIView):
    """What has been done to this account, most recent first.

    On the same screen as the fields themselves, because "who changed this?" is
    asked at the moment somebody notices the change — not later, in a different
    tool, by a different person.

    Reading it needs `audit.view`: an audit trail that everyone can read is a
    convenient map of who administers whom.
    """

    permission_classes = (HasCapability,)
    required_capability = Capability.AUDIT_VIEW

    #: Enough to answer the question, few enough that the screen stays a screen.
    LIMIT = 25

    @extend_schema(
        summary="Recent audit history for a user",
        responses={200: UserAuditEntrySerializer(many=True)},
        tags=USERS_TAG,
    )
    def get(self, request, user_id):
        from apps.audit.models import AuditLog

        # Resolved out of the scoped queryset, not `User.objects.all()`: this
        # view has no authority guard of its own, so `audit.view` plus a guessed
        # uuid would otherwise return another centre's account history. The fix
        # has to be the queryset rather than a check after the fetch, or the
        # 404 becomes a 403 that confirms the id is real.
        user = get_object_or_404(_scoped_users(request.user), pk=user_id)
        entries = (
            AuditLog.objects.filter(resource_type="user", resource_id=str(user.pk))
            .select_related("actor")
            .order_by("-created_at")[: self.LIMIT]
        )
        return Response(UserAuditEntrySerializer(entries, many=True).data)


class UserSessionListView(APIView):
    """An administrator's view of somebody else's active sessions (ERP Phase
    6, ADR-06). Read-only; ending one is the sibling revoke endpoint below."""

    permission_classes = (HasCapability,)
    required_capability = Capability.SESSION_VIEW_ANY

    @extend_schema(
        summary="List a user's active sessions",
        responses={200: SessionSerializer(many=True)},
        tags=USERS_TAG,
    )
    def get(self, request, user_id):
        # Resolved out of the scoped queryset (rule §2): a cross-centre id
        # 404s here rather than confirming a real account exists elsewhere.
        target = get_object_or_404(_scoped_users(request.user), pk=user_id)
        # Devices and addresses are as sensitive as the sign-out itself:
        # nobody reads them for an account above their own.
        services.ensure_may_administer(
            actor=request.user, target=target, action=AuditAction.SESSION_REVOKED_BY_ADMIN
        )
        rows = sessions.list_active_sessions(user=target)
        return Response(SessionSerializer(rows, many=True).data)


class UserSessionRevokeView(APIView):
    """An administrator ending somebody else's session (ERP Phase 6, ADR-06).

    Requires a fresh step-up on top of the capability, the same pattern
    ``MfaTotpDisableView`` uses for another account-security act: refuse with
    ``403 step_up_required`` and let the interface open the step-up dialog
    and retry. The target user is audited and emailed.
    """

    permission_classes = (HasCapability,)
    required_capability = Capability.SESSION_REVOKE_ANY

    @extend_schema(
        summary="Revoke a user's session",
        request=None,
        responses={
            204: None,
            403: OpenApiResponse(description="Step-up required."),
            404: OpenApiResponse(description="No such active session for that user."),
        },
        tags=USERS_TAG,
    )
    def delete(self, request, user_id, session_id):
        # Resolved out of the scoped queryset first (rule §2): a cross-centre
        # id 404s regardless of the caller's step-up state, rather than the
        # step-up check answering a fixed 403 for an id that was never
        # reachable in the first place.
        target = get_object_or_404(_scoped_users(request.user), pk=user_id)
        services.ensure_may_administer(
            actor=request.user, target=target, action=AuditAction.SESSION_REVOKED_BY_ADMIN
        )
        row = get_object_or_404(sessions.list_active_sessions(user=target), pk=session_id)
        if not is_fresh(request):
            raise StepUpRequired()
        sessions.revoke_session(session=row, actor=request.user)
        return Response(status=status.HTTP_204_NO_CONTENT)
