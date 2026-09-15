"""Keep the `Permission` rows equal to the `Capability` enum, and the six
system roles equal to `ROLE_CAPABILITIES` the first time they are created.

Runs from the seed migration and from `manage.py sync_permissions` (every
deploy). Idempotent. A system role's *grants* are seeded once and then left
alone — an administrator may have changed them on purpose — except that a
brand-new capability is granted to every system role whose code matrix
holds it, so a feature added in a release is not silently withheld from the
administrators the code expects to have it.
"""

from __future__ import annotations

from apps.accounts.roles import ROLE_CAPABILITIES, Capability, UserRole

CATEGORY_BY_RESOURCE = {
    "user": "people",
    "profile": "people",
    "student": "people",
    "fee": "people",
    "trainer": "people",
    "category": "academic",
    "course": "academic",
    "batch": "academic",
    "enrolment": "academic",
    "assignment": "academic",
    "assessment": "academic",
    "result": "academic",
    "project": "academic",
    "question": "academic",
    "exam": "academic",
    "completion": "academic",
    "certificate": "academic",
    "session": "operations",
    "attendance": "operations",
    "dsr": "operations",
    "performance": "operations",
    "review": "operations",
    "activity": "operations",
    "platform": "configuration",
    "organisation": "configuration",
    "settings": "configuration",
    "academic": "configuration",
    "role": "configuration",
    "permission": "configuration",
    "policy": "configuration",
    "form": "configuration",
    "automation": "configuration",
    "announcement": "communication",
    "requirement": "communication",
    "discussion": "communication",
    "template": "communication",
    "communication": "communication",
    "audit": "system",
    "record": "system",
    "report": "system",
    "data": "system",
    "export": "system",
    "search": "system",
    "saved_filter": "system",
}

LOCKABLE = frozenset(
    {
        "user.create",
        "user.update_any",
        "user.set_active",
        "user.change_role",
        "fee.manage_any",
        "platform.configure",
        "audit.view",
        "organisation.manage",
        "organisation.assign_users",
        "settings.manage",
        "record.purge",
        "academic.configure",
        "completion.approve",
        "certificate.manage",
        "data.export",
        "data.import",
        "role.manage",
        "permission.assign",
        "permission.lock",
        "policy.manage",
    }
)

#: Granted to superadmin only and locked there; refused to any other kind.
SUPERADMIN_ONLY = frozenset({"record.purge", "platform.configure", "permission.lock"})

SYSTEM_ROLE_NAMES = {
    UserRole.SUPERADMIN: "Superadmin",
    UserRole.ADMIN: "Administrator",
    UserRole.MANAGER: "Manager",
    UserRole.COUNSELLOR: "Counsellor",
    UserRole.TRAINER: "Trainer",
    UserRole.STUDENT: "Student",
}


def sync_catalog(apps=None) -> dict[str, int]:
    """Upsert permissions and system roles. Returns counts for the audit row."""
    if apps is None:
        from .models import Permission, Role, RolePermission
    else:
        Permission = apps.get_model("authorization", "Permission")
        Role = apps.get_model("authorization", "Role")
        RolePermission = apps.get_model("authorization", "RolePermission")

    counts = {
        "permissions_created": 0,
        "permissions_retired": 0,
        "roles_created": 0,
        "grants_added": 0,
    }

    wanted = {member.value: str(member.label) for member in Capability}
    existing = {row.code: row for row in Permission.objects.all()}
    for code, label in wanted.items():
        resource, _, action = code.partition(".")
        fields = {
            "resource": resource,
            "action": action,
            "category": CATEGORY_BY_RESOURCE.get(resource, "system"),
            "description": label,
            "is_lockable": code in LOCKABLE,
            "is_active": True,
        }
        row = existing.get(code)
        if row is None:
            Permission.objects.create(code=code, **fields)
            counts["permissions_created"] += 1
            continue
        changed = [name for name, value in fields.items() if getattr(row, name) != value]
        if changed:
            for name in changed:
                setattr(row, name, fields[name])
            row.save(update_fields=changed)
    for code, row in existing.items():
        if code not in wanted and row.is_active:
            row.is_active = False
            row.save(update_fields=["is_active"])
            counts["permissions_retired"] += 1

    by_code = {row.code: row for row in Permission.objects.filter(is_active=True)}
    for kind, name in SYSTEM_ROLE_NAMES.items():
        role = Role.objects.filter(slug=kind, is_system=True, deleted_at__isnull=True).first()
        created = False
        if role is None:
            role = Role.objects.create(
                slug=kind,
                name=name,
                kind=kind,
                is_system=True,
                is_locked=kind == UserRole.SUPERADMIN,
                description=f"The built-in {name.lower()} role.",
            )
            counts["roles_created"] += 1
            created = True
        held = set(
            RolePermission.objects.filter(role=role).values_list("permission__code", flat=True)
        )
        expected = (
            set(Capability.values) if kind == UserRole.SUPERADMIN else set(ROLE_CAPABILITIES[kind])
        )
        for code in sorted(expected - held):
            permission = by_code.get(code)
            if permission is None:
                continue
            # On first creation: the whole matrix. Afterwards: only members the
            # enum gained since the role's grants were last touched, which is
            # what `existing` not knowing the code means.
            if not created and code in existing:
                continue
            RolePermission.objects.create(
                role=role,
                permission=permission,
                is_locked=code in SUPERADMIN_ONLY
                or (kind == UserRole.SUPERADMIN and code in LOCKABLE),
            )
            counts["grants_added"] += 1
    return counts
