"""Secure file upload handling.

Every rule here exists because the naive version of it is a known vulnerability:

* **Never trust the client filename.** It can carry path traversal
  (``../../etc/passwd``), a double extension (``avatar.php.jpg``) or characters
  that confuse a downstream web server. Stored names are generated server-side.
* **Never trust the declared content type.** ``Content-Type`` is client-supplied.
  The bytes are opened with Pillow and verified to be a real image of an allowed
  format before anything is written.
* **Re-encode rather than store the original.** This drops EXIF metadata (which
  routinely contains GPS coordinates), normalises the format, and neutralises
  polyglot files that are simultaneously a valid image and a valid script.
* **Bound the work.** Size and pixel-dimension limits are enforced before
  decoding, so a decompression bomb cannot exhaust memory.

Uploaded files are stored outside any directory a web server serves directly;
they are delivered by an authenticated Django view (see
``apps.accounts.views.ProfileImageFileView``).
"""

from __future__ import annotations

import uuid
from io import BytesIO
from pathlib import PurePosixPath
from typing import Any

from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.utils.translation import gettext_lazy as _

#: Formats accepted for profile images. JPEG and PNG cover every real client;
#: WEBP is included because modern browsers produce it. SVG is deliberately
#: absent: it is XML, can carry script, and is not safe to serve as an image.
ALLOWED_IMAGE_FORMATS: dict[str, str] = {"JPEG": ".jpg", "PNG": ".png", "WEBP": ".webp"}

MAX_IMAGE_BYTES = 2 * 1024 * 1024  # 2 MB
MAX_IMAGE_PIXELS = 6000 * 6000  # guards against decompression bombs
PROFILE_IMAGE_SIZE = (512, 512)  # stored square thumbnail


def profile_image_upload_to(instance: Any, filename: str) -> str:
    """Generate the stored path. The client filename is discarded entirely."""
    suffix = PurePosixPath(filename or "").suffix.lower()
    extension = suffix if suffix in ALLOWED_IMAGE_FORMATS.values() else ".jpg"
    name = uuid.uuid4().hex
    # Two levels of sharding keep directory sizes reasonable at scale.
    return f"profile-images/{name[:2]}/{name[2:4]}/{name}{extension}"


def validate_image_upload(uploaded_file) -> None:
    """Validate size and real content type. Raises ``ValidationError``."""
    size = getattr(uploaded_file, "size", None)
    if size is None:
        raise ValidationError(_("The uploaded file could not be read."), code="invalid_upload")
    if size == 0:
        raise ValidationError(_("The uploaded file is empty."), code="empty_file")
    if size > MAX_IMAGE_BYTES:
        raise ValidationError(
            _("Image must be %(limit)d MB or smaller.")
            % {"limit": MAX_IMAGE_BYTES // (1024 * 1024)},
            code="file_too_large",
        )

    from PIL import Image, UnidentifiedImageError

    uploaded_file.seek(0)
    try:
        with Image.open(uploaded_file) as image:
            image_format = (image.format or "").upper()
            width, height = image.size
            # `verify` walks the file and raises on structural corruption. It
            # leaves the image unusable, so decoding happens separately later.
            image.verify()
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise ValidationError(
            _("The uploaded file is not a valid image."), code="invalid_image"
        ) from exc
    finally:
        uploaded_file.seek(0)

    if image_format not in ALLOWED_IMAGE_FORMATS:
        raise ValidationError(
            _("Unsupported image format. Use JPEG, PNG or WEBP."),
            code="unsupported_image_format",
        )
    if width * height > MAX_IMAGE_PIXELS:
        raise ValidationError(
            _("Image dimensions are too large."), code="image_dimensions_too_large"
        )


def normalise_profile_image(uploaded_file) -> ContentFile:
    """Validate, then re-encode to a fixed-size JPEG with no metadata.

    Returning a fresh file means the bytes that reach storage were produced by
    this process, not by the client.
    """
    validate_image_upload(uploaded_file)

    from PIL import Image, ImageOps

    uploaded_file.seek(0)
    with Image.open(uploaded_file) as image:
        # Honour the EXIF orientation flag before discarding metadata, so the
        # stored image is the right way up.
        image = ImageOps.exif_transpose(image)
        image = image.convert("RGB")
        image.thumbnail(PROFILE_IMAGE_SIZE, Image.Resampling.LANCZOS)

        buffer = BytesIO()
        # No `exif=` argument: metadata is intentionally not carried over.
        image.save(buffer, format="JPEG", quality=85, optimize=True)

    return ContentFile(buffer.getvalue(), name=f"{uuid.uuid4().hex}.jpg")


# ---------------------------------------------------------------------------
# Course resource documents
# ---------------------------------------------------------------------------
#
# Documents cannot be re-encoded the way images are: there is no safe, lossless
# "re-save a PDF" step that neutralises embedded content. So the defence is
# different — the file is never served in a way a browser will execute, and the
# declared extension must agree with what the bytes actually are.
#
# Rules:
#   * Extension allowlist. Anything not listed is refused outright.
#   * Magic-byte check, paired with the extension. A signature check alone is
#     not enough: .docx, .pptx, .xlsx and .zip are all ZIP containers, so the
#     pair (extension, signature family) is what gets validated.
#   * Server-generated filename. The client's is discarded, so traversal
#     (`../../etc/passwd`), double extensions (`report.pdf.php`) and control
#     characters cannot reach the filesystem.
#   * Served only through an authenticated view, as an attachment, with
#     `nosniff` — never from a directory a web server exposes.

MAX_RESOURCE_BYTES = 25 * 1024 * 1024  # 25 MB

#: Signature families. A file is accepted when its extension is allowed *and*
#: its leading bytes match the family that extension belongs to.
_SIGNATURE_FAMILIES: dict[str, tuple[bytes, ...]] = {
    "pdf": (b"%PDF-",),
    # Every modern Office format is a ZIP container. `PK\x03\x04` is a populated
    # archive; the other two are empty and spanned archives.
    "zip": (b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08"),
    "png": (b"\x89PNG\r\n\x1a\n",),
    "jpeg": (b"\xff\xd8\xff",),
    "webp": (b"RIFF",),
    # Legacy Office (.doc/.ppt/.xls) compound files, accepted for older material.
    "ole": (b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1",),
    #: Plain text has no signature. Validated by decoding instead.
    "text": (),
}

#: extension -> (signature family, stored content type)
ALLOWED_RESOURCE_TYPES: dict[str, tuple[str, str]] = {
    ".pdf": ("pdf", "application/pdf"),
    ".docx": ("zip", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
    ".pptx": ("zip", "application/vnd.openxmlformats-officedocument.presentationml.presentation"),
    ".xlsx": ("zip", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
    ".doc": ("ole", "application/msword"),
    ".ppt": ("ole", "application/vnd.ms-powerpoint"),
    ".xls": ("ole", "application/vnd.ms-excel"),
    # ZIP is accepted deliberately (§6 "where explicitly allowed") for exercise
    # bundles. It is never unpacked by the server, and it is only ever served as
    # an attachment.
    ".zip": ("zip", "application/zip"),
    ".png": ("png", "image/png"),
    ".jpg": ("jpeg", "image/jpeg"),
    ".jpeg": ("jpeg", "image/jpeg"),
    ".webp": ("webp", "image/webp"),
    ".txt": ("text", "text/plain"),
    ".csv": ("text", "text/csv"),
    ".md": ("text", "text/markdown"),
}

#: Extensions that would be executed or interpreted by some server or client if
#: they ever escaped the attachment path. Listed explicitly so the refusal
#: message is unambiguous during a security review.
DANGEROUS_EXTENSIONS = frozenset(
    {
        ".php",
        ".phtml",
        ".phar",
        ".jsp",
        ".jspx",
        ".asp",
        ".aspx",
        ".cgi",
        ".pl",
        ".py",
        ".rb",
        ".sh",
        ".bash",
        ".exe",
        ".dll",
        ".so",
        ".bat",
        ".cmd",
        ".com",
        ".scr",
        ".msi",
        ".js",
        ".mjs",
        ".jar",
        ".html",
        ".htm",
        ".svg",
        ".xml",
        ".xhtml",
    }
)

_TEXT_SAMPLE_BYTES = 4096


def resource_upload_to(instance: Any, filename: str) -> str:
    """Generate the stored path. The client filename is discarded entirely."""
    suffix = PurePosixPath(filename or "").suffix.lower()
    extension = suffix if suffix in ALLOWED_RESOURCE_TYPES else ".bin"
    name = uuid.uuid4().hex
    return f"course-resources/{name[:2]}/{name[2:4]}/{name}{extension}"


def _matches_family(head: bytes, family: str) -> bool:
    signatures = _SIGNATURE_FAMILIES.get(family, ())
    if not signatures:  # text: no signature to match
        return True
    return any(head.startswith(signature) for signature in signatures)


def validate_resource_upload(uploaded_file) -> tuple[str, str]:
    """Validate a course resource file.

    Returns ``(extension, content_type)`` for the caller to store. Raises
    ``ValidationError`` describing the first failure.
    """
    original_name = getattr(uploaded_file, "name", "") or ""
    suffix = PurePosixPath(original_name).suffix.lower()

    size = getattr(uploaded_file, "size", None)
    if not size:
        raise ValidationError(_("The uploaded file is empty."), code="empty_file")
    if size > MAX_RESOURCE_BYTES:
        raise ValidationError(
            _("File must be %(limit)d MB or smaller.")
            % {"limit": MAX_RESOURCE_BYTES // (1024 * 1024)},
            code="file_too_large",
        )

    # Checked before the allowlist so the message names the real problem.
    if suffix in DANGEROUS_EXTENSIONS:
        raise ValidationError(
            _("Files of this type cannot be uploaded."), code="forbidden_file_type"
        )
    if suffix not in ALLOWED_RESOURCE_TYPES:
        raise ValidationError(
            _("Unsupported file type. Allowed: %(types)s.")
            % {"types": ", ".join(sorted(ALLOWED_RESOURCE_TYPES))},
            code="unsupported_file_type",
        )

    family, content_type = ALLOWED_RESOURCE_TYPES[suffix]

    uploaded_file.seek(0)
    head = uploaded_file.read(_TEXT_SAMPLE_BYTES)
    uploaded_file.seek(0)

    if family == "text":
        # No signature exists, so prove it decodes as UTF-8 and carries no NUL
        # bytes — which is what a binary masquerading as .txt would contain.
        if b"\x00" in head:
            raise ValidationError(
                _("This file does not appear to be plain text."), code="invalid_file_content"
            )
        try:
            head.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ValidationError(
                _("This file does not appear to be plain text."), code="invalid_file_content"
            ) from exc
    elif not _matches_family(head, family):
        raise ValidationError(
            _("The file contents do not match its %(suffix)s extension.") % {"suffix": suffix},
            code="content_extension_mismatch",
        )

    return suffix, content_type


def course_thumbnail_upload_to(instance: Any, filename: str) -> str:
    """Stored path for a course thumbnail. Client filename discarded."""
    suffix = PurePosixPath(filename or "").suffix.lower()
    extension = suffix if suffix in ALLOWED_IMAGE_FORMATS.values() else ".jpg"
    name = uuid.uuid4().hex
    return f"course-thumbnails/{name[:2]}/{name[2:4]}/{name}{extension}"


COURSE_THUMBNAIL_SIZE = (1280, 720)


def normalise_course_thumbnail(uploaded_file) -> ContentFile:
    """Validate and re-encode a course thumbnail.

    Same pipeline as a profile image, at a 16:9-friendly size: the stored bytes
    are produced here, not supplied by the client, and metadata is dropped.
    """
    validate_image_upload(uploaded_file)

    from PIL import Image, ImageOps

    uploaded_file.seek(0)
    with Image.open(uploaded_file) as image:
        image = ImageOps.exif_transpose(image)
        image = image.convert("RGB")
        image.thumbnail(COURSE_THUMBNAIL_SIZE, Image.Resampling.LANCZOS)

        buffer = BytesIO()
        image.save(buffer, format="JPEG", quality=85, optimize=True)

    return ContentFile(buffer.getvalue(), name=f"{uuid.uuid4().hex}.jpg")
