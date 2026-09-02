"""Assignment file security — §4.4.

Each test names the rule it defends. The upload path a student can reach is the
most hostile one in the product: the uploader is a member of the public, the
payload is often source code, and the bytes are later opened by a trainer.
"""

from __future__ import annotations

import hashlib
from datetime import timedelta
from decimal import Decimal
from pathlib import PurePosixPath

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone

from apps.assignments.models import AssignmentStatus, AssignmentSubmission, SubmissionFile
from apps.audit.models import AuditAction, AuditLog
from apps.common.uploads import MAX_SUBMISSION_BYTES, MAX_SUBMISSION_FILES


@pytest.fixture
def assignment(admin_user, published_course, batch):
    from apps.assignments.services import create_assignment, set_assignment_status

    created = create_assignment(
        actor=admin_user,
        course=published_course,
        title="Upload exercise",
        max_marks=Decimal("100.00"),
        due_at=timezone.now() + timedelta(days=5),
    )
    return set_assignment_status(
        assignment=created, actor=admin_user, status=AssignmentStatus.PUBLISHED
    )


def _submit(client, assignment, *files):
    return client.post(
        f"/api/v1/assignments/{assignment.id}/submit/",
        {"files": list(files)},
        format="multipart",
    )


def _upload(name: str, body: bytes, content_type: str = "application/octet-stream"):
    return SimpleUploadedFile(name, body, content_type=content_type)


# ---------------------------------------------------------------------------
# The allowlist
# ---------------------------------------------------------------------------


@pytest.mark.django_db
@pytest.mark.parametrize(
    "name,body",
    [
        ("main.py", b"def main():\n    return 0\n"),
        ("App.java", b"class App { }\n"),
        ("index.html", b"<!doctype html><p>hi</p>"),
        ("notes.md", b"# Notes\n"),
        ("data.json", b'{"ok": true}'),
        ("query.sql", b"select 1;\n"),
    ],
)
def test_source_code_and_documents_are_accepted(
    api_client_no_csrf, assignment, student_profile, enrollment, name, body
):
    """§4.4 asks for code files to be supported, not refused."""
    api_client_no_csrf.force_login(student_profile.user)
    response = _submit(api_client_no_csrf, assignment, _upload(name, body))

    assert response.status_code == 201, response.json()
    assert response.json()["files"][0]["original_filename"] == name


@pytest.mark.django_db
def test_a_pdf_is_accepted_and_a_forged_one_is_not(
    api_client_no_csrf, assignment, student_profile, enrollment, pdf_bytes
):
    api_client_no_csrf.force_login(student_profile.user)

    # A PHP script wearing a .pdf name. The extension says PDF; the bytes do
    # not, and the pair is what gets validated. Tried first, so the refusal
    # cannot be mistaken for the one-attempt rule.
    forged = _submit(
        api_client_no_csrf, assignment, _upload("shell.pdf", b"<?php system($_GET['c']); ?>")
    )
    assert forged.status_code == 400
    assert "do not match" in str(forged.json())
    assert AssignmentSubmission.objects.count() == 0

    real = _submit(api_client_no_csrf, assignment, _upload("report.pdf", pdf_bytes))
    assert real.status_code == 201


@pytest.mark.django_db
@pytest.mark.parametrize("name", ["payload.exe", "tool.dll", "app.jar", "setup.msi", "run.bat"])
def test_executables_are_refused(api_client_no_csrf, assignment, student_profile, enrollment, name):
    """'no executable upload path' starts by refusing the obvious ones."""
    api_client_no_csrf.force_login(student_profile.user)
    response = _submit(api_client_no_csrf, assignment, _upload(name, b"MZ\x90\x00binary"))

    assert response.status_code == 400
    assert "Executable" in str(response.json())
    assert SubmissionFile.objects.count() == 0


@pytest.mark.django_db
def test_a_double_extension_is_judged_by_its_last_suffix(
    api_client_no_csrf, assignment, student_profile, enrollment
):
    """`report.pdf.exe` is an executable, not a PDF."""
    api_client_no_csrf.force_login(student_profile.user)
    response = _submit(api_client_no_csrf, assignment, _upload("report.pdf.exe", b"MZ\x90\x00"))

    assert response.status_code == 400
    assert SubmissionFile.objects.count() == 0


@pytest.mark.django_db
def test_an_unlisted_type_is_refused(api_client_no_csrf, assignment, student_profile, enrollment):
    api_client_no_csrf.force_login(student_profile.user)
    response = _submit(api_client_no_csrf, assignment, _upload("archive.rar", b"Rar!\x1a\x07\x00"))

    assert response.status_code == 400
    assert "Unsupported file type" in str(response.json())


@pytest.mark.django_db
def test_a_binary_wearing_a_text_extension_is_refused(
    api_client_no_csrf, assignment, student_profile, enrollment
):
    """NUL bytes in something claiming to be source code."""
    api_client_no_csrf.force_login(student_profile.user)
    response = _submit(
        api_client_no_csrf, assignment, _upload("script.py", b"\x7fELF\x02\x00\x00\x00binary")
    )

    assert response.status_code == 400
    assert "text" in str(response.json()).lower()


@pytest.mark.django_db
def test_an_empty_file_is_refused(api_client_no_csrf, assignment, student_profile, enrollment):
    api_client_no_csrf.force_login(student_profile.user)
    response = _submit(api_client_no_csrf, assignment, _upload("empty.py", b""))

    assert response.status_code == 400


# ---------------------------------------------------------------------------
# Bounds
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_an_oversized_file_is_refused(api_client_no_csrf, assignment, student_profile, enrollment):
    api_client_no_csrf.force_login(student_profile.user)
    oversized = _upload("big.py", b"# padding\n" * (MAX_SUBMISSION_BYTES // 10 + 1))
    response = _submit(api_client_no_csrf, assignment, oversized)

    assert response.status_code == 400
    assert "MB or smaller" in str(response.json())
    assert SubmissionFile.objects.count() == 0


@pytest.mark.django_db
def test_too_many_files_are_refused(api_client_no_csrf, assignment, student_profile, enrollment):
    api_client_no_csrf.force_login(student_profile.user)
    files = [_upload(f"file{i}.py", b"pass\n") for i in range(MAX_SUBMISSION_FILES + 1)]
    response = _submit(api_client_no_csrf, assignment, *files)

    assert response.status_code == 400
    assert AssignmentSubmission.objects.count() == 0


@pytest.mark.django_db
def test_one_bad_file_rejects_the_whole_submission(
    api_client_no_csrf, assignment, student_profile, enrollment
):
    """All-or-nothing. A half-stored submission looks complete to the student
    and is incomplete to the trainer, which is the worst of both."""
    api_client_no_csrf.force_login(student_profile.user)
    response = _submit(
        api_client_no_csrf,
        assignment,
        _upload("good.py", b"print(1)\n"),
        _upload("bad.exe", b"MZ\x90\x00"),
        _upload("also-good.md", b"# notes\n"),
    )

    assert response.status_code == 400
    assert AssignmentSubmission.objects.count() == 0
    assert SubmissionFile.objects.count() == 0


# ---------------------------------------------------------------------------
# What reaches the filesystem
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_the_stored_path_carries_nothing_the_client_sent(
    api_client_no_csrf, assignment, student_profile, enrollment
):
    """Traversal, control characters and the original name never reach disk."""
    api_client_no_csrf.force_login(student_profile.user)
    hostile = _upload("../../../../etc/passwd.py", b"root:x:0:0\n")
    response = _submit(api_client_no_csrf, assignment, hostile)

    assert response.status_code == 201
    stored = SubmissionFile.objects.get()
    path = PurePosixPath(stored.file.name)

    assert ".." not in stored.file.name
    assert "etc" not in stored.file.name
    assert stored.file.name.startswith("assignment-submissions/")
    # Every submission lands as an inert `.bin`, whatever was uploaded, so
    # there is no `.py` on disk for a mis-configured server to hand to a
    # handler.
    assert path.suffix == ".bin"
    assert len(path.stem) == 32  # a uuid4 hex, not a client string


@pytest.mark.django_db
def test_the_checksum_matches_the_bytes_received(
    api_client_no_csrf, assignment, student_profile, enrollment
):
    body = b"import os\nprint(os.getcwd())\n"
    api_client_no_csrf.force_login(student_profile.user)
    assert _submit(api_client_no_csrf, assignment, _upload("main.py", body)).status_code == 201

    stored = SubmissionFile.objects.get()
    assert stored.checksum == hashlib.sha256(body).hexdigest()
    assert stored.size_bytes == len(body)


# ---------------------------------------------------------------------------
# Download authorization and response headers
# ---------------------------------------------------------------------------


@pytest.fixture
def submitted_file(api_client_no_csrf, assignment, student_profile, enrollment):
    api_client_no_csrf.force_login(student_profile.user)
    _submit(api_client_no_csrf, assignment, _upload("solution.py", b"print('ok')\n"))
    api_client_no_csrf.logout()
    return SubmissionFile.objects.get()


def _download_url(stored) -> str:
    return f"/api/v1/submissions/files/{stored.id}/download/"


@pytest.mark.django_db
def test_the_student_can_download_their_own_file(
    api_client_no_csrf, submitted_file, student_profile
):
    api_client_no_csrf.force_login(student_profile.user)
    response = api_client_no_csrf.get(_download_url(submitted_file))

    assert response.status_code == 200
    assert b"".join(response.streaming_content) == b"print('ok')\n"


@pytest.mark.django_db
def test_a_classmate_cannot_download_it(
    api_client_no_csrf, submitted_file, other_student_profile, other_enrollment
):
    """Being on the same batch is not entitlement to another student's work."""
    api_client_no_csrf.force_login(other_student_profile.user)
    response = api_client_no_csrf.get(_download_url(submitted_file))

    assert response.status_code == 404


@pytest.mark.django_db
def test_an_unrelated_trainer_cannot_download_it(
    api_client_no_csrf, submitted_file, trainer_profile_two
):
    api_client_no_csrf.force_login(trainer_profile_two.user)
    assert api_client_no_csrf.get(_download_url(submitted_file)).status_code == 404


@pytest.mark.django_db
def test_an_anonymous_caller_cannot_download_it(api_client_no_csrf, submitted_file):
    assert api_client_no_csrf.get(_download_url(submitted_file)).status_code in (401, 403)


@pytest.mark.django_db
def test_the_marking_trainer_can_download_it_and_the_read_is_audited(
    api_client_no_csrf, submitted_file, trainer_profile
):
    api_client_no_csrf.force_login(trainer_profile.user)
    response = api_client_no_csrf.get(_download_url(submitted_file))

    assert response.status_code == 200
    assert AuditLog.objects.filter(action=AuditAction.SUBMISSION_FILE_DOWNLOADED).exists()


@pytest.mark.django_db
def test_submitted_bytes_are_never_rendered_by_a_browser(
    api_client_no_csrf, assignment, student_profile, enrollment, trainer_profile
):
    """An `.html` hand-in must not become stored XSS against the marker.

    The defence is the response, not the file: always an attachment, always
    `application/octet-stream`, always `nosniff`.
    """
    api_client_no_csrf.force_login(student_profile.user)
    _submit(
        api_client_no_csrf,
        assignment,
        _upload("page.html", b"<script>alert(document.cookie)</script>"),
    )
    stored = SubmissionFile.objects.get()

    api_client_no_csrf.force_login(trainer_profile.user)
    response = api_client_no_csrf.get(_download_url(stored))

    assert response.status_code == 200
    assert response["Content-Type"] == "application/octet-stream"
    assert response["Content-Disposition"].startswith("attachment;")
    assert response["X-Content-Type-Options"] == "nosniff"
    assert "sandbox" in response["Content-Security-Policy"]
    assert response["Cache-Control"] == "private, no-store"


@pytest.mark.django_db
def test_the_download_name_is_built_by_the_server(
    api_client_no_csrf, assignment, student_profile, enrollment
):
    """Not echoed from the upload, so quotes and newlines cannot reach a header."""
    api_client_no_csrf.force_login(student_profile.user)
    _submit(api_client_no_csrf, assignment, _upload('we"ird\nname.py', b"pass\n"))
    stored = SubmissionFile.objects.get()

    response = api_client_no_csrf.get(_download_url(stored))
    disposition = response["Content-Disposition"]

    assert "\n" not in disposition
    assert disposition == f'attachment; filename="{assignment.code}-attempt-1.py"'


# ---------------------------------------------------------------------------
# Trainer attachments
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_a_trainer_attaches_a_brief_and_the_student_can_read_it(
    api_client_no_csrf, assignment, trainer_profile, student_profile, enrollment, pdf_bytes
):
    api_client_no_csrf.force_login(trainer_profile.user)
    created = api_client_no_csrf.post(
        f"/api/v1/assignments/{assignment.id}/attachments/",
        {"title": "Specification", "file": _upload("spec.pdf", pdf_bytes)},
        format="multipart",
    )
    assert created.status_code == 201, created.json()
    attachment_id = created.json()["id"]

    api_client_no_csrf.force_login(student_profile.user)
    response = api_client_no_csrf.get(f"/api/v1/assignments/attachments/{attachment_id}/")

    assert response.status_code == 200
    assert response["Content-Disposition"] == 'attachment; filename="Specification"'
    assert response["X-Content-Type-Options"] == "nosniff"


@pytest.mark.django_db
def test_a_student_cannot_attach_files_to_a_brief(
    api_client_no_csrf, assignment, student_profile, enrollment, pdf_bytes
):
    api_client_no_csrf.force_login(student_profile.user)
    response = api_client_no_csrf.post(
        f"/api/v1/assignments/{assignment.id}/attachments/",
        {"title": "Mine now", "file": _upload("spec.pdf", pdf_bytes)},
        format="multipart",
    )

    assert response.status_code == 404
    assert assignment.attachments.count() == 0


@pytest.mark.django_db
def test_a_dangerous_attachment_is_refused(api_client_no_csrf, assignment, trainer_profile):
    api_client_no_csrf.force_login(trainer_profile.user)
    response = api_client_no_csrf.post(
        f"/api/v1/assignments/{assignment.id}/attachments/",
        {"title": "Helper", "file": _upload("helper.php", b"<?php echo 1; ?>")},
        format="multipart",
    )

    assert response.status_code == 400
    assert assignment.attachments.count() == 0
