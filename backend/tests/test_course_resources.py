"""Lesson resource upload, access control and download safety."""

from __future__ import annotations

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.audit.models import AuditAction, AuditLog
from apps.courses.models import PublishStatus


def _upload(client, lesson_id, content: bytes, filename: str, content_type="application/pdf"):
    return client.post(
        f"/api/v1/lessons/{lesson_id}/resources/",
        {
            "title": "Course handout",
            "file": SimpleUploadedFile(filename, content, content_type=content_type),
        },
        format="multipart",
    )


# ---------------------------------------------------------------------------
# Accepted uploads
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_a_valid_pdf_is_accepted(api_client_no_csrf, admin_user, preview_lesson, pdf_bytes):
    api_client_no_csrf.force_login(admin_user)
    response = _upload(api_client_no_csrf, preview_lesson.id, pdf_bytes, "handout.pdf")
    assert response.status_code == 201

    body = response.json()
    assert body["content_type"] == "application/pdf"
    assert body["original_filename"] == "handout.pdf"
    assert body["download_url"] == f"/api/v1/resources/{body['id']}/download/"


@pytest.mark.django_db
def test_an_office_document_is_accepted(api_client_no_csrf, admin_user, preview_lesson):
    """.docx is a ZIP container, so the signature check must allow that pairing."""
    api_client_no_csrf.force_login(admin_user)
    docx = b"PK\x03\x04" + b"\x00" * 64
    response = _upload(
        api_client_no_csrf,
        preview_lesson.id,
        docx,
        "slides.docx",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )
    assert response.status_code == 201


@pytest.mark.django_db
def test_an_image_and_a_text_file_are_accepted(
    api_client_no_csrf, admin_user, preview_lesson, png_bytes
):
    api_client_no_csrf.force_login(admin_user)
    assert (
        _upload(
            api_client_no_csrf, preview_lesson.id, png_bytes, "diagram.png", "image/png"
        ).status_code
        == 201
    )
    assert (
        _upload(
            api_client_no_csrf,
            preview_lesson.id,
            b"cheat sheet\nline two\n",
            "notes.txt",
            "text/plain",
        ).status_code
        == 201
    )


@pytest.mark.django_db
def test_a_link_resource_can_be_attached(api_client_no_csrf, admin_user, preview_lesson):
    api_client_no_csrf.force_login(admin_user)
    response = api_client_no_csrf.post(
        f"/api/v1/lessons/{preview_lesson.id}/resources/link/",
        {"title": "Official docs", "external_url": "https://docs.example.test/guide"},
        format="json",
    )
    assert response.status_code == 201
    assert response.json()["kind"] == "link"
    assert response.json()["download_url"] is None


@pytest.mark.django_db
def test_insecure_resource_links_are_refused(api_client_no_csrf, admin_user, preview_lesson):
    api_client_no_csrf.force_login(admin_user)
    response = api_client_no_csrf.post(
        f"/api/v1/lessons/{preview_lesson.id}/resources/link/",
        {"title": "Bad", "external_url": "http://docs.example.test/guide"},
        format="json",
    )
    assert response.status_code == 400


# ---------------------------------------------------------------------------
# Rejected uploads
# ---------------------------------------------------------------------------


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("content", "filename", "declared_type"),
    [
        (b"<?php system($_GET['c']); ?>", "shell.php", "application/x-php"),
        (b"<?php system($_GET['c']); ?>", "shell.php.pdf", "application/pdf"),
        (b'<svg xmlns="http://www.w3.org/2000/svg"><script/></svg>', "x.svg", "image/svg+xml"),
        (b"<html><script>alert(1)</script></html>", "page.html", "text/html"),
        (b"#!/bin/sh\nrm -rf /\n", "run.sh", "application/x-sh"),
        (b"MZ\x90\x00", "tool.exe", "application/octet-stream"),
    ],
)
def test_dangerous_file_types_are_refused(
    api_client_no_csrf, admin_user, preview_lesson, content, filename, declared_type
):
    api_client_no_csrf.force_login(admin_user)
    response = _upload(api_client_no_csrf, preview_lesson.id, content, filename, declared_type)
    assert response.status_code == 400
    assert preview_lesson.resources.count() == 0


@pytest.mark.django_db
def test_content_must_match_the_extension(api_client_no_csrf, admin_user, preview_lesson):
    """A .pdf that is not a PDF is refused, whatever the declared type says."""
    api_client_no_csrf.force_login(admin_user)
    response = _upload(api_client_no_csrf, preview_lesson.id, b"not a pdf at all", "fake.pdf")
    assert response.status_code == 400
    assert preview_lesson.resources.count() == 0


@pytest.mark.django_db
def test_a_binary_disguised_as_text_is_refused(api_client_no_csrf, admin_user, preview_lesson):
    api_client_no_csrf.force_login(admin_user)
    response = _upload(
        api_client_no_csrf, preview_lesson.id, b"\x00\x01\x02binary", "notes.txt", "text/plain"
    )
    assert response.status_code == 400


@pytest.mark.django_db
def test_an_empty_file_is_refused(api_client_no_csrf, admin_user, preview_lesson):
    api_client_no_csrf.force_login(admin_user)
    assert _upload(api_client_no_csrf, preview_lesson.id, b"", "empty.pdf").status_code == 400


@pytest.mark.django_db
def test_an_oversized_file_is_refused(api_client_no_csrf, admin_user, preview_lesson, pdf_bytes):
    api_client_no_csrf.force_login(admin_user)
    oversized = pdf_bytes + b"0" * (26 * 1024 * 1024)
    assert _upload(api_client_no_csrf, preview_lesson.id, oversized, "big.pdf").status_code == 400


# ---------------------------------------------------------------------------
# Filenames and paths
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_the_client_filename_never_reaches_the_filesystem(
    api_client_no_csrf, admin_user, preview_lesson, pdf_bytes
):
    api_client_no_csrf.force_login(admin_user)
    response = _upload(api_client_no_csrf, preview_lesson.id, pdf_bytes, "../../../etc/passwd.pdf")
    assert response.status_code == 201

    resource = preview_lesson.resources.first()
    assert ".." not in resource.file.name
    assert "etc" not in resource.file.name
    assert "passwd" not in resource.file.name
    assert resource.file.name.startswith("course-resources/")
    # The original is retained as display text only.
    assert "passwd" in resource.original_filename


@pytest.mark.django_db
def test_the_download_filename_is_built_by_the_server(
    api_client_no_csrf, admin_user, preview_lesson, pdf_bytes
):
    """A malicious title must not be echoed into a response header."""
    api_client_no_csrf.force_login(admin_user)
    api_client_no_csrf.post(
        f"/api/v1/lessons/{preview_lesson.id}/resources/",
        {
            "title": 'evil"; filename="owned.sh',
            "file": SimpleUploadedFile("ok.pdf", pdf_bytes, content_type="application/pdf"),
        },
        format="multipart",
    )
    resource = preview_lesson.resources.first()
    response = api_client_no_csrf.get(f"/api/v1/resources/{resource.id}/download/")
    disposition = response["Content-Disposition"]

    # No header injection: quotes balanced, no extra separators or newlines.
    assert disposition.count('"') == 2
    assert ";" not in disposition[disposition.index('"') :]
    assert "\n" not in disposition and "\r" not in disposition
    # The extension is the server's, and there is no second one smuggled in.
    assert disposition.endswith('.pdf"')
    assert disposition.count(".") == 1
    assert "owned.sh" not in disposition


# ---------------------------------------------------------------------------
# Download access control
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_downloads_are_served_as_attachments_with_nosniff(
    api_client_no_csrf, admin_user, preview_lesson, pdf_bytes
):
    api_client_no_csrf.force_login(admin_user)
    _upload(api_client_no_csrf, preview_lesson.id, pdf_bytes, "handout.pdf")
    resource = preview_lesson.resources.first()

    response = api_client_no_csrf.get(f"/api/v1/resources/{resource.id}/download/")
    assert response.status_code == 200
    assert response["Content-Disposition"].startswith("attachment;")
    assert response["X-Content-Type-Options"] == "nosniff"
    assert response["Cache-Control"] == "private, no-store"


@pytest.mark.django_db
def test_anonymous_callers_cannot_download(
    api_client_no_csrf, admin_user, preview_lesson, pdf_bytes
):
    api_client_no_csrf.force_login(admin_user)
    _upload(api_client_no_csrf, preview_lesson.id, pdf_bytes, "handout.pdf")
    resource = preview_lesson.resources.first()

    api_client_no_csrf.logout()
    response = api_client_no_csrf.get(f"/api/v1/resources/{resource.id}/download/")
    assert response.status_code in (401, 403)


@pytest.mark.django_db
def test_a_resource_on_a_draft_course_is_not_downloadable_by_students(
    api_client_no_csrf, admin_user, student, draft_course, pdf_bytes
):
    from apps.courses import services

    module = services.create_module(course=draft_course, actor=admin_user, title="M")
    lesson = services.create_lesson(
        module=module, actor=admin_user, title="L", content_type="text", text_content="Body"
    )
    api_client_no_csrf.force_login(admin_user)
    _upload(api_client_no_csrf, lesson.id, pdf_bytes, "secret.pdf")
    resource = lesson.resources.first()

    api_client_no_csrf.force_login(student)
    assert api_client_no_csrf.get(f"/api/v1/resources/{resource.id}/download/").status_code == 404


@pytest.mark.django_db
def test_resources_respect_the_enrolment_gate(
    api_client_no_csrf, settings, admin_user, student, paid_lesson, pdf_bytes
):
    api_client_no_csrf.force_login(admin_user)
    _upload(api_client_no_csrf, paid_lesson.id, pdf_bytes, "paid.pdf")
    resource = paid_lesson.resources.first()

    settings.COURSE_CONTENT_REQUIRES_ENROLMENT = True
    api_client_no_csrf.force_login(student)
    assert api_client_no_csrf.get(f"/api/v1/lessons/{paid_lesson.id}/resources/").status_code == 403
    assert api_client_no_csrf.get(f"/api/v1/resources/{resource.id}/download/").status_code == 403


@pytest.mark.django_db
def test_a_resource_marked_not_downloadable_is_listed_but_not_served(
    api_client_no_csrf, admin_user, preview_lesson, pdf_bytes
):
    api_client_no_csrf.force_login(admin_user)
    _upload(api_client_no_csrf, preview_lesson.id, pdf_bytes, "handout.pdf")
    resource = preview_lesson.resources.first()
    api_client_no_csrf.patch(
        f"/api/v1/resources/{resource.id}/", {"is_downloadable": False}, format="json"
    )
    assert api_client_no_csrf.get(f"/api/v1/resources/{resource.id}/download/").status_code == 404


@pytest.mark.django_db
def test_a_trainer_cannot_upload_to_an_unassigned_course(
    api_client_no_csrf, trainer, preview_lesson, pdf_bytes
):
    api_client_no_csrf.force_login(trainer)
    response = _upload(api_client_no_csrf, preview_lesson.id, pdf_bytes, "injected.pdf")
    assert response.status_code == 404
    assert preview_lesson.resources.count() == 0


@pytest.mark.django_db
def test_a_student_cannot_upload_resources(api_client_no_csrf, student, preview_lesson, pdf_bytes):
    api_client_no_csrf.force_login(student)
    response = _upload(api_client_no_csrf, preview_lesson.id, pdf_bytes, "student.pdf")
    assert response.status_code == 404
    assert preview_lesson.resources.count() == 0


@pytest.mark.django_db
def test_upload_and_deletion_are_audited(api_client_no_csrf, admin_user, preview_lesson, pdf_bytes):
    api_client_no_csrf.force_login(admin_user)
    _upload(api_client_no_csrf, preview_lesson.id, pdf_bytes, "handout.pdf")
    resource = preview_lesson.resources.first()
    assert AuditLog.objects.filter(action=AuditAction.RESOURCE_UPLOADED).exists()

    assert api_client_no_csrf.delete(f"/api/v1/resources/{resource.id}/").status_code == 204
    assert AuditLog.objects.filter(action=AuditAction.RESOURCE_DELETED).exists()
    assert preview_lesson.resources.count() == 0


@pytest.mark.django_db
def test_deleting_a_resource_removes_the_stored_file(
    api_client_no_csrf, admin_user, preview_lesson, pdf_bytes
):
    import os

    api_client_no_csrf.force_login(admin_user)
    _upload(api_client_no_csrf, preview_lesson.id, pdf_bytes, "handout.pdf")
    path = preview_lesson.resources.first().file.path
    assert os.path.exists(path)

    api_client_no_csrf.delete(f"/api/v1/resources/{preview_lesson.resources.first().id}/")
    assert not os.path.exists(path)


@pytest.mark.django_db
def test_students_can_download_from_a_published_preview_lesson(
    api_client_no_csrf, admin_user, student, preview_lesson, pdf_bytes
):
    api_client_no_csrf.force_login(admin_user)
    _upload(api_client_no_csrf, preview_lesson.id, pdf_bytes, "handout.pdf")
    resource = preview_lesson.resources.first()

    api_client_no_csrf.force_login(student)
    assert preview_lesson.status == PublishStatus.PUBLISHED
    assert api_client_no_csrf.get(f"/api/v1/resources/{resource.id}/download/").status_code == 200
