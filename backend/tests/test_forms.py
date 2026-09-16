"""Dynamic forms (ERP Phase 8).

- one pass and one fail case for every field type the validator knows;
- a published version's fields are immutable (`set_fields` refused 409);
- publishing computes and checks `schema_hash`, refuses an unchanged
  republish, and archives the version it replaces;
- cloning a published version's fields into a new draft copies them
  exactly;
- a relation field is scoped to the caller's own `visible_*` set;
- `form.view` and `form.manage` are enforced separately on every route;
- the seed migration's forms exist, published, with their catalog fields.
"""

from __future__ import annotations

import uuid

import pytest

from apps.common.exceptions import ApplicationError, AuthorityError, ConflictError
from apps.forms import services
from apps.forms.models import FormDefinition, FormField, FormVersion, FormVersionStatus
from apps.forms.validation import validate_payload

FORMS = "/api/v1/forms/"


def _make_definition(slug=None, entity="activity"):
    slug = slug or f"test-form-{uuid.uuid4().hex[:8]}"
    return FormDefinition.objects.create(slug=slug, name="Test form", entity=entity)


def _make_version(definition=None, status=FormVersionStatus.DRAFT, number=1):
    definition = definition or _make_definition()
    return FormVersion.objects.create(definition=definition, number=number, status=status)


def _add_field(version, **kwargs):
    defaults = {
        "key": "field_one",
        "label": "Field One",
        "type": "text",
        "required": False,
        "options": [],
        "validation": {},
    }
    defaults.update(kwargs)
    return FormField.objects.create(version=version, **defaults)


def _validate_one(field_kwargs, value, *, actor=None):
    version = _make_version()
    _add_field(version, **field_kwargs)
    return validate_payload(version=version, values={field_kwargs["key"]: value}, actor=actor)


# ---------------------------------------------------------------------------
# Per-field-type validation: one pass, one fail, each.
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_text_field_pass_and_fail():
    field = {"key": "note", "type": "text", "validation": {"min_length": 2, "max_length": 5}}
    assert _validate_one(field, "abc")["note"] == "abc"
    with pytest.raises(ApplicationError):
        _validate_one(field, "a")


@pytest.mark.django_db
def test_textarea_field_pass_and_fail():
    field = {"key": "body", "type": "textarea", "validation": {"max_length": 10}}
    assert _validate_one(field, "short")["body"] == "short"
    with pytest.raises(ApplicationError):
        _validate_one(field, "this is much too long")


@pytest.mark.django_db
def test_richtext_field_sanitises_and_fails_on_wrong_type():
    field = {"key": "content", "type": "richtext", "validation": {}}
    cleaned = _validate_one(field, "<p>Hi<script>alert(1)</script></p><b onclick='x()'>bold</b>")
    assert "<script>" not in cleaned["content"]
    assert "onclick" not in cleaned["content"]
    assert "<b>bold</b>" in cleaned["content"]
    with pytest.raises(ApplicationError):
        _validate_one(field, 12345)


@pytest.mark.django_db
def test_number_field_pass_and_fail():
    field = {"key": "count", "type": "number", "validation": {"min": 1, "max": 10}}
    assert _validate_one(field, 5)["count"] == 5
    with pytest.raises(ApplicationError):
        _validate_one(field, 50)


@pytest.mark.django_db
def test_decimal_field_pass_and_fail_kept_as_string():
    field = {"key": "score", "type": "decimal", "validation": {"min": 0, "max": 10}}
    cleaned = _validate_one(field, "7.5")
    assert cleaned["score"] == "7.5"
    assert isinstance(cleaned["score"], str)
    with pytest.raises(ApplicationError):
        _validate_one(field, "11")


@pytest.mark.django_db
def test_date_field_pass_and_fail():
    field = {"key": "day", "type": "date", "validation": {"not_future": True}}
    assert _validate_one(field, "2020-01-01")["day"] == "2020-01-01"
    with pytest.raises(ApplicationError):
        _validate_one(field, "2099-01-01")


@pytest.mark.django_db
def test_datetime_field_pass_and_fail():
    field = {"key": "when", "type": "datetime", "validation": {"not_past": True}}
    assert _validate_one(field, "2099-01-01T10:00:00+00:00")["when"] == "2099-01-01T10:00:00+00:00"
    with pytest.raises(ApplicationError):
        _validate_one(field, "2020-01-01T10:00:00+00:00")


@pytest.mark.django_db
def test_boolean_field_pass_and_fail():
    field = {"key": "flag", "type": "boolean"}
    assert _validate_one(field, True)["flag"] is True
    with pytest.raises(ApplicationError):
        _validate_one(field, "yes")


@pytest.mark.django_db
def test_select_field_pass_and_fail():
    field = {
        "key": "outcome",
        "type": "select",
        "options": [
            {"value": "ready", "label": "Ready"},
            {"value": "not_ready", "label": "Not ready"},
        ],
    }
    assert _validate_one(field, "ready")["outcome"] == "ready"
    with pytest.raises(ApplicationError):
        _validate_one(field, "unknown")


@pytest.mark.django_db
def test_radio_field_pass_and_fail():
    field = {
        "key": "mode",
        "type": "radio",
        "options": [{"value": "a", "label": "A"}, {"value": "b", "label": "B"}],
    }
    assert _validate_one(field, "a")["mode"] == "a"
    with pytest.raises(ApplicationError):
        _validate_one(field, "c")


@pytest.mark.django_db
def test_multiselect_field_pass_and_fail():
    field = {
        "key": "topics",
        "type": "multiselect",
        "options": [{"value": "a", "label": "A"}, {"value": "b", "label": "B"}],
        "validation": {"max_items": 1},
    }
    assert _validate_one(field, ["a"])["topics"] == ["a"]
    with pytest.raises(ApplicationError):
        _validate_one(field, ["a", "b"])


@pytest.mark.django_db
def test_checkbox_field_pass_and_fail():
    field = {
        "key": "agree",
        "type": "checkbox",
        "options": [{"value": "a", "label": "A"}, {"value": "b", "label": "B"}],
    }
    assert _validate_one(field, ["a", "b"])["agree"] == ["a", "b"]
    with pytest.raises(ApplicationError):
        _validate_one(field, ["a", "z"])


@pytest.mark.django_db
def test_email_field_pass_and_fail():
    field = {"key": "contact", "type": "email"}
    assert _validate_one(field, "a@b.com")["contact"] == "a@b.com"
    with pytest.raises(ApplicationError):
        _validate_one(field, "not-an-email")


@pytest.mark.django_db
def test_phone_field_pass_and_fail():
    field = {"key": "phone", "type": "phone"}
    assert _validate_one(field, "+919876543210")["phone"] == "+919876543210"
    with pytest.raises(ApplicationError):
        _validate_one(field, "12")


@pytest.mark.django_db
def test_url_field_pass_and_fail():
    field = {"key": "site", "type": "url"}
    assert _validate_one(field, "https://example.com")["site"] == "https://example.com"
    with pytest.raises(ApplicationError):
        _validate_one(field, "http://example.com")


@pytest.mark.django_db
def test_file_field_pass_and_fail(monkeypatch):
    field = {"key": "resume", "type": "file", "validation": {"accept": [".pdf"], "max_mb": 1}}
    monkeypatch.setattr(
        "apps.forms.validation.UPLOAD_RESOLVER",
        lambda upload_id: (
            {"content_type": "application/pdf", "filename": "r.pdf", "size_bytes": 1000}
            if upload_id == "good"
            else None
        ),
    )
    assert _validate_one(field, "good")["resume"] == "good"
    with pytest.raises(ApplicationError):
        _validate_one(field, "missing")


@pytest.mark.django_db
def test_image_field_pass_and_fail(monkeypatch):
    field = {"key": "photo", "type": "image", "validation": {}}
    monkeypatch.setattr(
        "apps.forms.validation.UPLOAD_RESOLVER",
        lambda upload_id: (
            {"content_type": "image/png", "filename": "p.png", "size_bytes": 100}
            if upload_id == "img"
            else {"content_type": "application/pdf", "filename": "p.pdf", "size_bytes": 100}
        ),
    )
    assert _validate_one(field, "img")["photo"] == "img"
    with pytest.raises(ApplicationError):
        _validate_one(field, "not-an-image")


@pytest.mark.django_db
def test_relation_field_pass_and_fail(admin_user, student_profile):
    field = {"key": "student", "type": "relation", "options": {"model": "student"}}
    cleaned = _validate_one(field, str(student_profile.pk), actor=admin_user)
    assert cleaned["student"] == str(student_profile.pk)
    with pytest.raises(ApplicationError):
        _validate_one(field, "not-a-uuid", actor=admin_user)


@pytest.mark.django_db
def test_required_field_missing_is_refused():
    version = _make_version()
    _add_field(version, key="required_field", type="text", required=True)
    with pytest.raises(ApplicationError) as excinfo:
        validate_payload(version=version, values={}, actor=None)
    assert "required_field" in excinfo.value.detail


@pytest.mark.django_db
def test_unknown_key_is_refused():
    version = _make_version()
    _add_field(version, key="known", type="text", required=False)
    with pytest.raises(ApplicationError) as excinfo:
        validate_payload(version=version, values={"unknown": "x"}, actor=None)
    assert "unknown" in excinfo.value.detail


@pytest.mark.django_db
def test_every_field_error_is_reported_at_once():
    version = _make_version()
    _add_field(version, key="a", type="email", required=True)
    _add_field(version, key="b", type="number", required=True)
    with pytest.raises(ApplicationError) as excinfo:
        validate_payload(
            version=version, values={"a": "not-an-email", "b": "not-a-number"}, actor=None
        )
    assert set(excinfo.value.detail) == {"a", "b"}


# ---------------------------------------------------------------------------
# Relation scoping against the CALLER
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_relation_field_refuses_a_record_outside_the_caller_visibility(trainer, student_profile):
    """A trainer with no batch assignment cannot see any student, so a
    relation to that student is refused even though the id is real."""
    field = {"key": "student", "type": "relation", "options": {"model": "student"}}
    with pytest.raises(ApplicationError):
        _validate_one(field, str(student_profile.pk), actor=trainer)


# ---------------------------------------------------------------------------
# Immutability
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_set_fields_on_a_published_version_is_refused(admin_user):
    version = _make_version(status=FormVersionStatus.PUBLISHED)
    with pytest.raises(ConflictError):
        services.set_fields(
            actor=admin_user,
            version=version,
            fields=[{"key": "a", "label": "A", "type": "text"}],
        )


@pytest.mark.django_db
def test_set_fields_on_a_draft_replaces_them_fully(admin_user):
    version = _make_version()
    _add_field(version, key="old_field")
    services.set_fields(
        actor=admin_user,
        version=version,
        fields=[{"key": "new_field", "label": "New", "type": "text"}],
    )
    keys = set(version.fields.values_list("key", flat=True))
    assert keys == {"new_field"}


@pytest.mark.django_db
def test_set_fields_refuses_duplicate_or_non_snake_case_keys(admin_user):
    version = _make_version()
    with pytest.raises(ApplicationError):
        services.set_fields(
            actor=admin_user,
            version=version,
            fields=[
                {"key": "dup", "label": "A", "type": "text"},
                {"key": "dup", "label": "B", "type": "text"},
            ],
        )
    with pytest.raises(ApplicationError):
        services.set_fields(
            actor=admin_user,
            version=version,
            fields=[{"key": "NotSnakeCase", "label": "A", "type": "text"}],
        )


@pytest.mark.django_db
def test_set_fields_requires_form_manage(manager_user):
    """A manager holds `form.view` but not `form.manage`."""
    version = _make_version()
    with pytest.raises(AuthorityError):
        services.set_fields(
            actor=manager_user,
            version=version,
            fields=[{"key": "a", "label": "A", "type": "text"}],
        )


# ---------------------------------------------------------------------------
# Versioning
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_publish_computes_hash_and_archives_the_previous_version(admin_user):
    definition = _make_definition()
    v1 = _make_version(definition, number=1)
    _add_field(v1, key="a", type="text")
    services.publish_version(actor=admin_user, version=v1)
    v1.refresh_from_db()
    assert v1.status == FormVersionStatus.PUBLISHED
    assert len(v1.schema_hash) == 64

    v2 = services.create_draft_version(actor=admin_user, definition=definition)
    services.set_fields(
        actor=admin_user, version=v2, fields=[{"key": "b", "label": "B", "type": "text"}]
    )
    services.publish_version(actor=admin_user, version=v2)
    v1.refresh_from_db()
    v2.refresh_from_db()
    assert v1.status == FormVersionStatus.ARCHIVED
    assert v2.status == FormVersionStatus.PUBLISHED


@pytest.mark.django_db
def test_publish_refuses_an_unchanged_republish(admin_user):
    definition = _make_definition()
    v1 = _make_version(definition, number=1)
    _add_field(v1, key="a", type="text")
    services.publish_version(actor=admin_user, version=v1)

    v2 = services.create_draft_version(actor=admin_user, definition=definition, cloned_from=v1)
    with pytest.raises(ConflictError):
        services.publish_version(actor=admin_user, version=v2)


@pytest.mark.django_db
def test_clone_from_published_creates_a_matching_draft(admin_user):
    definition = _make_definition()
    v1 = _make_version(definition, number=1)
    _add_field(v1, key="a", type="text", label="A")
    services.publish_version(actor=admin_user, version=v1)

    v2 = services.create_draft_version(actor=admin_user, definition=definition, cloned_from=v1)
    assert v2.status == FormVersionStatus.DRAFT
    assert v2.cloned_from_id == v1.pk
    assert list(v2.fields.values_list("key", "type", "label")) == [("a", "text", "A")]


@pytest.mark.django_db
def test_create_draft_version_refuses_a_second_draft(admin_user):
    definition = _make_definition()
    _make_version(definition, number=1)
    with pytest.raises(ConflictError):
        services.create_draft_version(actor=admin_user, definition=definition)


@pytest.mark.django_db
def test_unpublish_returns_a_published_version_to_draft(admin_user):
    definition = _make_definition()
    v1 = _make_version(definition, number=1)
    services.publish_version(actor=admin_user, version=v1)
    services.unpublish_version(actor=admin_user, version=v1)
    v1.refresh_from_db()
    assert v1.status == FormVersionStatus.DRAFT
    with pytest.raises(ConflictError):
        services.unpublish_version(actor=admin_user, version=v1)


# ---------------------------------------------------------------------------
# Capability gating on every route
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_form_view_capability_gates_read_routes(api_client_no_csrf, manager_user, student):
    api_client_no_csrf.force_login(manager_user)
    assert api_client_no_csrf.get(FORMS).status_code == 200

    api_client_no_csrf.force_login(student)
    assert api_client_no_csrf.get(FORMS).status_code == 403


@pytest.mark.django_db
def test_form_manage_capability_gates_write_routes(api_client_no_csrf, manager_user, admin_user):
    body = {"slug": "gate-test", "name": "Gate test", "entity": "activity"}

    api_client_no_csrf.force_login(manager_user)
    refused = api_client_no_csrf.post(FORMS, body, format="json")
    assert refused.status_code == 403

    api_client_no_csrf.force_login(admin_user)
    created = api_client_no_csrf.post(FORMS, body, format="json")
    assert created.status_code == 201
    slug = created.json()["slug"]

    version_number = created.json()["draft_version"]["number"]

    fields_url = f"{FORMS}{slug}/versions/{version_number}/fields/"
    fields_body = {"fields": [{"key": "a", "label": "A", "type": "text"}]}

    api_client_no_csrf.force_login(manager_user)
    assert api_client_no_csrf.put(fields_url, fields_body, format="json").status_code == 403

    api_client_no_csrf.force_login(admin_user)
    assert api_client_no_csrf.put(fields_url, fields_body, format="json").status_code == 200

    publish_url = f"{FORMS}{slug}/versions/{version_number}/publish/"
    api_client_no_csrf.force_login(manager_user)
    assert api_client_no_csrf.post(publish_url, {}, format="json").status_code == 403

    api_client_no_csrf.force_login(admin_user)
    assert api_client_no_csrf.post(publish_url, {}, format="json").status_code == 200

    unpublish_url = f"{FORMS}{slug}/versions/{version_number}/unpublish/"
    api_client_no_csrf.force_login(manager_user)
    assert api_client_no_csrf.post(unpublish_url, {}, format="json").status_code == 403

    preview_url = f"{FORMS}{slug}/preview/"
    api_client_no_csrf.force_login(manager_user)
    assert api_client_no_csrf.post(preview_url, {"values": {}}, format="json").status_code == 403

    version_create_url = f"{FORMS}{slug}/versions/"
    api_client_no_csrf.force_login(manager_user)
    assert api_client_no_csrf.post(version_create_url, {}, format="json").status_code == 403


@pytest.mark.django_db
def test_published_route_requires_only_form_view(
    api_client_no_csrf, admin_user, counsellor_user, student
):
    body = {"slug": "publish-view-test", "name": "Publish view test", "entity": "activity"}
    api_client_no_csrf.force_login(admin_user)
    created = api_client_no_csrf.post(FORMS, body, format="json").json()
    number = created["draft_version"]["number"]
    slug = created["slug"]
    api_client_no_csrf.put(
        f"{FORMS}{slug}/versions/{number}/fields/",
        {"fields": [{"key": "a", "label": "A", "type": "text"}]},
        format="json",
    )
    api_client_no_csrf.post(f"{FORMS}{slug}/versions/{number}/publish/", {}, format="json")

    api_client_no_csrf.force_login(counsellor_user)
    published = api_client_no_csrf.get(f"{FORMS}published/{slug}/")
    assert published.status_code == 200
    assert published.json()["fields"][0]["key"] == "a"

    api_client_no_csrf.force_login(student)
    assert api_client_no_csrf.get(f"{FORMS}published/{slug}/").status_code == 403


@pytest.mark.django_db
def test_preview_reports_errors_without_storing(api_client_no_csrf, admin_user):
    body = {"slug": "preview-test", "name": "Preview test", "entity": "activity"}
    api_client_no_csrf.force_login(admin_user)
    created = api_client_no_csrf.post(FORMS, body, format="json").json()
    slug = created["slug"]
    number = created["draft_version"]["number"]
    api_client_no_csrf.put(
        f"{FORMS}{slug}/versions/{number}/fields/",
        {"fields": [{"key": "email", "label": "Email", "type": "email", "required": True}]},
        format="json",
    )
    from apps.forms.models import FormResponse

    bad = api_client_no_csrf.post(
        f"{FORMS}{slug}/preview/", {"values": {"email": "nope"}}, format="json"
    )
    assert bad.status_code == 200
    assert bad.json()["valid"] is False
    assert "email" in bad.json()["errors"]
    assert FormResponse.objects.count() == 0

    good = api_client_no_csrf.post(
        f"{FORMS}{slug}/preview/", {"values": {"email": "a@b.com"}}, format="json"
    )
    assert good.json()["valid"] is True
    assert FormResponse.objects.count() == 0


# ---------------------------------------------------------------------------
# The seed migration's data
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_seeded_forms_exist_and_are_published():
    expected_slugs = {
        "mock-interview",
        "technical-interview",
        "hr-interview",
        "mentoring-note",
        "counselling-note",
        "doubt-session",
        "code-review",
        "resume-review",
        "project-review",
        "placement-call",
        "feedback-note",
        "parent-meeting",
        "warning-note",
        "follow-up-note",
        "communication-practice",
        "student-custom",
        "registration-extra",
    }
    seen = set(FormDefinition.objects.values_list("slug", flat=True))
    assert expected_slugs <= seen

    mock_interview = FormDefinition.objects.get(slug="mock-interview")
    version = mock_interview.versions.get(number=1)
    assert version.status == FormVersionStatus.PUBLISHED
    assert version.schema_hash
    keys = set(version.fields.values_list("key", flat=True))
    assert keys == {
        "technical",
        "communication",
        "confidence",
        "score",
        "outcome",
        "strengths",
        "improvements",
        "notes",
    }
    score_field = version.fields.get(key="score")
    assert score_field.performance_key == "score"

    for entity_slug in ("student-custom", "registration-extra"):
        entity_definition = FormDefinition.objects.get(slug=entity_slug)
        entity_version = entity_definition.versions.get(number=1)
        assert entity_version.status == FormVersionStatus.PUBLISHED
        assert entity_version.fields.count() == 0
