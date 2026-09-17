"""Export the ERP's own configuration as one reviewable file (Phase 23,
`docs/erp/BACKUP_AND_RECOVERY.md`).

Roles, permissions, policies, forms, activity types, automation rules and
message templates are already rows in the nightly database dump — this
command does not replace that backup. What it adds is *reviewability*:
``manage.py export_configuration > config-<date>.json`` writes a snapshot an
operator can read, diff against yesterday's, or hand to someone debugging a
"who changed this" question, without restoring anything.

Read-only, deliberately. Every category below is read through the same
manager and, where one already exists, the same serializer a real endpoint
uses — never a second hand-rolled shape for a model that already has one
(`apps.authorization.serializers.RoleSerializer`,
`apps.forms.serializers.FormDefinitionDetailSerializer`, and so on). Nothing
here calls ``.save()``, ``.create()`` or ``.delete()`` on anything; an empty
table for any category is not an error — it is an empty list.
"""

from __future__ import annotations

import json
from typing import Any

from django.core.management.base import BaseCommand
from django.db.models import Count, Q
from django.utils import timezone

from apps.authorization.models import Permission, Role
from apps.authorization.serializers import PermissionSerializer, RoleSerializer
from apps.automation.models import AutomationRule
from apps.automation.serializers import AutomationRuleSerializer
from apps.communication.models import MessageTemplate
from apps.communication.serializers import MessageTemplateSerializer
from apps.forms.serializers import FormDefinitionDetailSerializer
from apps.forms.views import _definitions_queryset
from apps.policies.serializers import PolicyEntrySerializer
from apps.policies.services import list_policies
from apps.work.models import ActivityType
from apps.work.serializers import ActivityTypeSerializer


def _roles() -> list[dict[str, Any]]:
    # Same annotation `apps.authorization.views._annotated` uses: `RoleSerializer`
    # reads `user_count`/`permission_count` as plain fields, not related lookups.
    queryset = Role.objects.with_related().annotate(
        user_count=Count("users", filter=Q(users__is_active=True), distinct=True),
        permission_count=Count("grants", distinct=True),
    )
    return RoleSerializer(queryset, many=True).data


def _permissions() -> list[dict[str, Any]]:
    return PermissionSerializer(Permission.objects.order_by("category", "code"), many=True).data


def _policies() -> list[dict[str, Any]]:
    # Every schema key, resolved institution-wide (no branch override applied).
    # A key nobody has ever configured still appears, at its schema default —
    # exactly what `list_policies()` already returns for the settings screen.
    return PolicyEntrySerializer(list_policies(), many=True).data


def _forms() -> list[dict[str, Any]]:
    return FormDefinitionDetailSerializer(_definitions_queryset(), many=True).data


def _activity_types() -> list[dict[str, Any]]:
    return ActivityTypeSerializer(
        ActivityType.objects.with_related().order_by("name"), many=True
    ).data


def _automation_rules() -> list[dict[str, Any]]:
    return AutomationRuleSerializer(
        AutomationRule.objects.with_related().order_by("name"), many=True
    ).data


def _message_templates() -> list[dict[str, Any]]:
    return MessageTemplateSerializer(
        MessageTemplate.objects.with_related().order_by("key"), many=True
    ).data


class Command(BaseCommand):
    help = (
        "Write roles, permissions, policies, forms, activity types, automation "
        "rules and message templates as one JSON document to stdout. Read-only."
    )

    def handle(self, *args, **options) -> None:
        document = {
            "generated_at": timezone.now().isoformat(),
            "roles": _roles(),
            "permissions": _permissions(),
            "policies": _policies(),
            "forms": _forms(),
            "activity_types": _activity_types(),
            "automation_rules": _automation_rules(),
            "message_templates": _message_templates(),
        }
        self.stdout.write(json.dumps(document, indent=2, default=str))
