"""The recycle bin, and the endpoint shape that would have made it a hole.

Two things are being checked here, and only one of them is about recovery.

The first is the feature: an administrator can see what was deleted, put it
back, and — if they are a superadmin — destroy it.

The second is the endpoint's own design. It takes a model label from the URL,
which is a shape that becomes an arbitrary-model-read vulnerability the moment
somebody implements it with `get_model(label)`. The label is matched against a
closed set instead, and the tests below try the obvious ways in: the user table,
the audit log, the session table, a dotted path, and a made-up name.
"""

from __future__ import annotations

import pytest

from apps.common.deletion import soft_delete

BIN = "/api/v1/recovery/"
BATCH_LABEL = "batches.batch"


@pytest.fixture
def superadmin(db):
    from apps.accounts.models import User, UserRole

    return User.objects.create_user(
        email="super@recovery.grras.invalid",
        password="Str0ng-Passphrase!42",
        first_name="Sena",
        last_name="Superadmin",
        role=UserRole.SUPERADMIN,
    )


@pytest.fixture
def deleted_batch(admin_user, batch):
    soft_delete(instance=batch, actor=admin_user, reason="Cohort never ran")
    batch.refresh_from_db()
    return batch


# ---------------------------------------------------------------------------
# The closed set — the reason this endpoint is not a vulnerability
# ---------------------------------------------------------------------------


@pytest.mark.django_db
@pytest.mark.parametrize(
    "label",
    [
        "accounts.user",
        "audit.auditlog",
        "sessions.session",
        "accounts.accounttoken",
        "contenttypes.contenttype",
        "auth.permission",
        "does.notexist",
        "batches",
        "../../etc/passwd",
    ],
)
def test_only_soft_deletable_models_can_be_addressed(api_client_no_csrf, admin_user, label):
    """A model label from a URL must never be used to *find* a model.

    Every entry here is something `get_model` would have been happy to return —
    the user table, the audit trail, the session store. The registry is built
    from the models that inherit `SoftDeleteModel`, so none of them is
    reachable, and the answer is a bare 404 rather than a message naming what
    is valid.
    """
    api_client_no_csrf.force_login(admin_user)
    assert api_client_no_csrf.get(f"{BIN}{label}/").status_code == 404


@pytest.mark.django_db
def test_the_registry_is_not_empty(api_client_no_csrf, admin_user):
    """Otherwise every test above passes on a bin that can address nothing."""
    from apps.common.recovery import recoverable_models

    assert len(recoverable_models()) >= 3
    assert BATCH_LABEL in recoverable_models()


# ---------------------------------------------------------------------------
# Seeing the bin
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_the_bin_lists_kinds_with_counts(api_client_no_csrf, admin_user, deleted_batch):
    api_client_no_csrf.force_login(admin_user)

    response = api_client_no_csrf.get(BIN)

    assert response.status_code == 200
    entry = next(row for row in response.data if row["label"] == BATCH_LABEL)
    assert entry["deleted_count"] == 1
    assert entry["verbose_name"]


@pytest.mark.django_db
def test_the_bin_omits_kinds_with_nothing_in_them(api_client_no_csrf, admin_user, batch):
    """A screen for what needs attention should not list what does not."""
    api_client_no_csrf.force_login(admin_user)

    labels = [row["label"] for row in api_client_no_csrf.get(BIN).data]

    assert BATCH_LABEL not in labels


@pytest.mark.django_db
def test_a_deleted_record_carries_who_and_why(api_client_no_csrf, admin_user, deleted_batch):
    api_client_no_csrf.force_login(admin_user)

    rows = api_client_no_csrf.get(f"{BIN}{BATCH_LABEL}/").data["results"]

    assert len(rows) == 1
    row = rows[0]
    assert row["id"] == str(deleted_batch.pk)
    assert row["describes"] == deleted_batch.code
    assert row["deleted_by"] == admin_user.email
    assert row["delete_reason"] == "Cohort never ran"
    assert row["deleted_at"] is not None


@pytest.mark.django_db
def test_a_live_record_is_not_in_the_bin(api_client_no_csrf, admin_user, batch):
    api_client_no_csrf.force_login(admin_user)

    rows = api_client_no_csrf.get(f"{BIN}{BATCH_LABEL}/").data["results"]

    assert rows == []


@pytest.mark.django_db
def test_every_field_is_present_even_when_null(api_client_no_csrf, admin_user, batch):
    """A screen must never have to ask whether a key exists.

    `deleted_by` is null once the account that removed the record is itself
    removed, and that is a fact to render — "Unknown" — not a missing key to
    branch on.
    """
    soft_delete(instance=batch, actor=None, reason="Removed by a management command")
    api_client_no_csrf.force_login(admin_user)

    row = api_client_no_csrf.get(f"{BIN}{BATCH_LABEL}/").data["results"][0]

    assert set(row) == {"id", "label", "describes", "deleted_at", "deleted_by", "delete_reason"}
    assert row["deleted_by"] is None


# ---------------------------------------------------------------------------
# Restoring
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_an_administrator_can_restore(api_client_no_csrf, admin_user, deleted_batch):
    from apps.batches.models import Batch

    api_client_no_csrf.force_login(admin_user)

    response = api_client_no_csrf.post(f"{BIN}{BATCH_LABEL}/{deleted_batch.pk}/restore/")

    assert response.status_code == 200
    assert Batch.objects.filter(pk=deleted_batch.pk).exists()


@pytest.mark.django_db
def test_restoring_something_that_is_not_deleted_is_a_404(api_client_no_csrf, admin_user, batch):
    """A 404 rather than a 409: the id genuinely is not in the bin."""
    api_client_no_csrf.force_login(admin_user)

    assert api_client_no_csrf.post(f"{BIN}{BATCH_LABEL}/{batch.pk}/restore/").status_code == 404


@pytest.mark.django_db
def test_restore_is_audited(api_client_no_csrf, admin_user, deleted_batch):
    from apps.audit.models import AuditAction, AuditLog

    api_client_no_csrf.force_login(admin_user)
    api_client_no_csrf.post(f"{BIN}{BATCH_LABEL}/{deleted_batch.pk}/restore/")

    assert AuditLog.objects.filter(
        action=AuditAction.RECORD_RESTORED, resource_id=str(deleted_batch.pk)
    ).exists()


# ---------------------------------------------------------------------------
# Destroying — the one act that cannot be undone
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_an_administrator_cannot_destroy(api_client_no_csrf, admin_user, deleted_batch):
    """Everything else an administrator does here is reversible. This is not."""
    from apps.batches.models import Batch

    api_client_no_csrf.force_login(admin_user)

    response = api_client_no_csrf.post(
        f"{BIN}{BATCH_LABEL}/{deleted_batch.pk}/purge/",
        {"reason": "Retention policy"},
        format="json",
    )

    assert response.status_code == 403
    assert Batch.all_objects.filter(pk=deleted_batch.pk).exists()


@pytest.mark.django_db
def test_a_superadmin_can(api_client_no_csrf, superadmin, deleted_batch):
    from apps.batches.models import Batch

    api_client_no_csrf.force_login(superadmin)

    response = api_client_no_csrf.post(
        f"{BIN}{BATCH_LABEL}/{deleted_batch.pk}/purge/",
        {"reason": "Created during a demo"},
        format="json",
    )

    assert response.status_code == 204
    assert not Batch.all_objects.filter(pk=deleted_batch.pk).exists()


@pytest.mark.django_db
def test_destroying_asks_for_a_reason_and_refuses_a_blank_one(
    api_client_no_csrf, superadmin, deleted_batch
):
    """The reason is the only thing that will still exist afterwards."""
    from apps.batches.models import Batch

    api_client_no_csrf.force_login(superadmin)

    assert (
        api_client_no_csrf.post(
            f"{BIN}{BATCH_LABEL}/{deleted_batch.pk}/purge/", {"reason": ""}, format="json"
        ).status_code
        == 400
    )
    assert (
        api_client_no_csrf.post(
            f"{BIN}{BATCH_LABEL}/{deleted_batch.pk}/purge/", {}, format="json"
        ).status_code
        == 400
    )
    assert Batch.all_objects.filter(pk=deleted_batch.pk).exists()


@pytest.mark.django_db
def test_a_live_record_cannot_be_destroyed(api_client_no_csrf, superadmin, batch):
    """Destruction is a second decision, not a stronger first one."""
    api_client_no_csrf.force_login(superadmin)

    response = api_client_no_csrf.post(
        f"{BIN}{BATCH_LABEL}/{batch.pk}/purge/", {"reason": "Skip the bin"}, format="json"
    )

    assert response.status_code == 404


@pytest.mark.django_db
def test_the_audit_entry_outlives_the_record(api_client_no_csrf, superadmin, deleted_batch):
    """ "What was destroyed?" is the whole question, so the entry describes it."""
    from apps.audit.models import AuditAction, AuditLog

    code = deleted_batch.code
    api_client_no_csrf.force_login(superadmin)
    api_client_no_csrf.post(
        f"{BIN}{BATCH_LABEL}/{deleted_batch.pk}/purge/",
        {"reason": "Retention policy"},
        format="json",
    )

    entry = AuditLog.objects.filter(
        action=AuditAction.RECORD_PURGED, resource_id=str(deleted_batch.pk)
    ).first()
    assert entry is not None
    assert entry.context["describes"] == code
    assert entry.context["reason"] == "Retention policy"


# ---------------------------------------------------------------------------
# Who may open it at all
# ---------------------------------------------------------------------------


@pytest.mark.django_db
@pytest.mark.parametrize("fixture", ["manager_user", "counsellor_user"])
def test_the_bin_is_not_open_to_the_rungs_below(
    api_client_no_csrf, request, fixture, deleted_batch
):
    """A list of what was deleted is a map of what somebody wanted hidden."""
    api_client_no_csrf.force_login(request.getfixturevalue(fixture))

    assert api_client_no_csrf.get(BIN).status_code == 403
    assert api_client_no_csrf.get(f"{BIN}{BATCH_LABEL}/").status_code == 403
    assert (
        api_client_no_csrf.post(f"{BIN}{BATCH_LABEL}/{deleted_batch.pk}/restore/").status_code
        == 403
    )


@pytest.mark.django_db
def test_a_student_is_refused(api_client_no_csrf, student_profile, deleted_batch):
    api_client_no_csrf.force_login(student_profile.user)

    assert api_client_no_csrf.get(BIN).status_code == 403


@pytest.mark.django_db
def test_nobody_anonymous_gets_in(api_client_no_csrf, deleted_batch):
    assert api_client_no_csrf.get(BIN).status_code in (401, 403)
