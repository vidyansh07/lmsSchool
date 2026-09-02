"""Profile image upload security.

The upload path is the most dangerous surface added in this phase, so it is
tested against each specific attack rather than only for the happy path.
"""

from __future__ import annotations

from io import BytesIO

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.audit.models import AuditAction, AuditLog

UPLOAD_URL = "/api/v1/auth/me/profile-image/"


def _upload(client, content: bytes, filename: str, content_type: str = "image/png"):
    return client.post(
        UPLOAD_URL,
        {"image": SimpleUploadedFile(filename, content, content_type=content_type)},
        format="multipart",
    )


@pytest.mark.django_db
def test_valid_image_is_accepted_and_re_encoded(api_client_no_csrf, student, png_bytes):
    api_client_no_csrf.force_login(student)
    response = _upload(api_client_no_csrf, png_bytes, "avatar.png")
    assert response.status_code == 200

    student.refresh_from_db()
    assert student.profile_image
    # Stored as JPEG regardless of what was uploaded: the file was re-encoded.
    assert student.profile_image.name.endswith(".jpg")


@pytest.mark.django_db
def test_client_filename_is_discarded(api_client_no_csrf, student, png_bytes):
    """Path traversal and double extensions cannot reach the filesystem."""
    api_client_no_csrf.force_login(student)
    _upload(api_client_no_csrf, png_bytes, "../../../etc/passwd.png")

    student.refresh_from_db()
    stored = student.profile_image.name
    assert ".." not in stored
    assert "etc" not in stored
    assert "passwd" not in stored
    assert stored.startswith("profile-images/")


@pytest.mark.django_db
def test_executable_disguised_as_an_image_is_rejected(api_client_no_csrf, student):
    """A PHP payload with an image content type must not be stored."""
    api_client_no_csrf.force_login(student)
    payload = b"<?php system($_GET['c']); ?>"
    response = _upload(api_client_no_csrf, payload, "shell.php.png", "image/png")

    assert response.status_code == 400
    student.refresh_from_db()
    assert not student.profile_image


@pytest.mark.django_db
def test_svg_is_rejected(api_client_no_csrf, student):
    """SVG is XML and can carry script, so it is not an accepted image format."""
    api_client_no_csrf.force_login(student)
    svg = b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>'
    assert _upload(api_client_no_csrf, svg, "x.svg", "image/svg+xml").status_code == 400


@pytest.mark.django_db
def test_declared_content_type_is_not_trusted(api_client_no_csrf, student):
    api_client_no_csrf.force_login(student)
    response = _upload(api_client_no_csrf, b"not an image at all", "fake.png", "image/png")
    assert response.status_code == 400


@pytest.mark.django_db
def test_oversized_image_is_rejected(api_client_no_csrf, student):
    import os

    from PIL import Image

    api_client_no_csrf.force_login(student)
    buffer = BytesIO()
    # Random pixels are incompressible, so the PNG comfortably exceeds 2 MB.
    size = 1600
    noise = os.urandom(size * size * 3)
    Image.frombytes("RGB", (size, size), noise).save(buffer, format="PNG")
    assert buffer.tell() > 2 * 1024 * 1024

    response = _upload(api_client_no_csrf, buffer.getvalue(), "big.png")
    assert response.status_code == 400


@pytest.mark.django_db
def test_empty_file_is_rejected(api_client_no_csrf, student):
    api_client_no_csrf.force_login(student)
    assert _upload(api_client_no_csrf, b"", "empty.png").status_code == 400


@pytest.mark.django_db
def test_upload_requires_authentication(api_client_no_csrf, png_bytes):
    assert _upload(api_client_no_csrf, png_bytes, "a.png").status_code in (401, 403)


@pytest.mark.django_db
def test_exif_metadata_is_stripped(api_client_no_csrf, student):
    """Uploaded photos routinely carry GPS coordinates. They must not persist."""
    from PIL import Image

    api_client_no_csrf.force_login(student)
    buffer = BytesIO()
    image = Image.new("RGB", (200, 200), (10, 10, 10))
    exif = image.getexif()
    exif[271] = "SecretCameraMake"
    image.save(buffer, format="JPEG", exif=exif)

    _upload(api_client_no_csrf, buffer.getvalue(), "photo.jpg", "image/jpeg")

    student.refresh_from_db()
    with student.profile_image.open("rb") as stored:
        data = stored.read()
    assert b"SecretCameraMake" not in data


@pytest.mark.django_db
def test_image_is_served_only_to_authenticated_callers(
    api_client_no_csrf, student, trainer, png_bytes
):
    api_client_no_csrf.force_login(student)
    _upload(api_client_no_csrf, png_bytes, "avatar.png")
    url = f"/api/v1/users/{student.pk}/profile-image/"

    assert api_client_no_csrf.get(url).status_code == 200

    api_client_no_csrf.logout()
    assert api_client_no_csrf.get(url).status_code in (401, 403)

    # Another signed-in user may see it: names and faces are visible platform-wide.
    api_client_no_csrf.force_login(trainer)
    assert api_client_no_csrf.get(url).status_code == 200


@pytest.mark.django_db
def test_served_image_cannot_be_reinterpreted_by_the_browser(
    api_client_no_csrf, student, png_bytes
):
    api_client_no_csrf.force_login(student)
    _upload(api_client_no_csrf, png_bytes, "avatar.png")
    response = api_client_no_csrf.get(f"/api/v1/users/{student.pk}/profile-image/")
    assert response["Content-Type"] == "image/jpeg"
    assert response["X-Content-Type-Options"] == "nosniff"
    assert response["Content-Disposition"] == "inline"


@pytest.mark.django_db
def test_upload_and_removal_are_audited(api_client_no_csrf, student, png_bytes):
    api_client_no_csrf.force_login(student)
    _upload(api_client_no_csrf, png_bytes, "avatar.png")
    assert AuditLog.objects.filter(action=AuditAction.PROFILE_IMAGE_UPDATED).exists()

    assert api_client_no_csrf.delete(UPLOAD_URL).status_code == 200
    assert AuditLog.objects.filter(action=AuditAction.PROFILE_IMAGE_REMOVED).exists()
    student.refresh_from_db()
    assert not student.profile_image


@pytest.mark.django_db
def test_replacing_an_image_removes_the_previous_file(api_client_no_csrf, student, png_bytes):
    import os

    api_client_no_csrf.force_login(student)
    _upload(api_client_no_csrf, png_bytes, "first.png")
    student.refresh_from_db()
    first_path = student.profile_image.path

    _upload(api_client_no_csrf, png_bytes, "second.png")
    student.refresh_from_db()
    assert student.profile_image.path != first_path
    assert not os.path.exists(first_path)
