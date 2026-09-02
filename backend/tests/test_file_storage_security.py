"""§14.3 — student files are private wherever they are stored.

Two halves. The first exercises the S3 backend against a mocked bucket, so the
claims about privacy are demonstrated rather than asserted about settings: a
file goes in, comes back byte-for-byte, and the URL it produces is signed and
expiring. The second half is the boot guard, which is the control that actually
prevents the accident — a deployment configured to make the bucket public.
"""

from __future__ import annotations

import io
from urllib.parse import parse_qs, urlparse

import boto3
import pytest
from django.core.exceptions import ImproperlyConfigured, ValidationError
from django.core.files.base import ContentFile
from moto import mock_aws

from apps.common import scanning
from apps.common.storage import (
    BACKENDS,
    PrivateMediaStorage,
    check_storage_configuration,
    storage_settings,
)

BUCKET = "grras-lms-test-bucket"


@pytest.fixture
def s3_bucket(monkeypatch):
    """A mocked S3 bucket with throwaway credentials.

    The credentials are literals that exist only inside the mock — moto refuses
    to talk to AWS — which is how this test can prove the S3 path works without
    a real account, and why no real credential is ever needed in the repository.
    """
    for name, value in {
        "AWS_ACCESS_KEY_ID": "testing",
        "AWS_SECRET_ACCESS_KEY": "testing",
        "AWS_SECURITY_TOKEN": "testing",
        "AWS_SESSION_TOKEN": "testing",
        "AWS_DEFAULT_REGION": "ap-south-1",
    }.items():
        monkeypatch.setenv(name, value)
    with mock_aws():
        client = boto3.client("s3", region_name="ap-south-1")
        client.create_bucket(
            Bucket=BUCKET,
            CreateBucketConfiguration={"LocationConstraint": "ap-south-1"},
        )
        yield client


def _storage() -> PrivateMediaStorage:
    return PrivateMediaStorage(bucket_name=BUCKET, region_name="ap-south-1", location="media")


# ---------------------------------------------------------------------------
# The S3 backend
# ---------------------------------------------------------------------------


def test_a_file_survives_a_round_trip_through_s3(s3_bucket):
    storage = _storage()
    name = storage.save("submissions/report.pdf", ContentFile(b"%PDF-1.7 student work"))

    with storage.open(name) as handle:
        assert handle.read() == b"%PDF-1.7 student work"


def test_two_uploads_of_the_same_name_do_not_overwrite_each_other(s3_bucket):
    storage = _storage()
    first = storage.save("submissions/report.pdf", ContentFile(b"first student"))
    second = storage.save("submissions/report.pdf", ContentFile(b"second student"))

    assert first != second
    with storage.open(first) as handle:
        assert handle.read() == b"first student"


def test_the_object_url_is_signed_and_expires(s3_bucket):
    storage = _storage()
    name = storage.save("submissions/report.pdf", ContentFile(b"private"))

    query = parse_qs(urlparse(storage.url(name)).query)

    # A signature and an expiry are what make the URL useless once it leaks.
    # Specifically SigV4: accepting the SigV2 names here would pass against a
    # custom endpoint and then fail on a real AWS bucket, because every region
    # created after 2014 rejects SigV2.
    assert "X-Amz-Signature" in query, f"not a SigV4 signature: {sorted(query)}"
    assert query.get("X-Amz-Expires"), f"object URL carries no expiry: {sorted(query)}"


def test_the_signature_version_is_pinned():
    """Left to boto3 it is inferred from the endpoint, and infers wrong."""
    assert PrivateMediaStorage.signature_version == "s3v4"


def test_uploads_are_never_stamped_with_a_public_acl(s3_bucket):
    storage = _storage()
    name = storage.save("submissions/report.pdf", ContentFile(b"private"))

    grants = s3_bucket.get_object_acl(Bucket=BUCKET, Key=f"media/{name}")["Grants"]
    readers = [
        grant["Grantee"].get("URI", "") for grant in grants if grant["Grantee"]["Type"] == "Group"
    ]
    assert not any("AllUsers" in uri or "AuthenticatedUsers" in uri for uri in readers)


def test_stored_objects_are_marked_uncacheable(s3_bucket):
    storage = _storage()
    name = storage.save("submissions/report.pdf", ContentFile(b"private"))

    head = s3_bucket.head_object(Bucket=BUCKET, Key=f"media/{name}")
    assert "no-store" in head.get("CacheControl", "")


# ---------------------------------------------------------------------------
# Backend selection and the boot guard
# ---------------------------------------------------------------------------


def test_only_the_two_known_backends_are_selectable():
    assert set(BACKENDS) == {"local", "s3"}
    with pytest.raises(ImproperlyConfigured, match="FILE_STORAGE_BACKEND"):
        storage_settings("dropbox")


def test_selecting_s3_produces_the_private_backend():
    entry = storage_settings("s3", {"bucket_name": BUCKET})
    assert entry["BACKEND"] == "apps.common.storage.PrivateMediaStorage"
    assert entry["OPTIONS"]["bucket_name"] == BUCKET


class _Settings:
    def __init__(self, options):
        self.STORAGES = {
            "default": {"BACKEND": "apps.common.storage.PrivateMediaStorage", "OPTIONS": options}
        }


def test_the_boot_guard_ignores_local_storage():
    module = _Settings({})
    module.STORAGES["default"]["BACKEND"] = "django.core.files.storage.FileSystemStorage"
    check_storage_configuration(module)  # does not raise


def test_s3_without_a_bucket_refuses_to_boot():
    with pytest.raises(ImproperlyConfigured, match="AWS_STORAGE_BUCKET_NAME"):
        check_storage_configuration(_Settings({}))


@pytest.mark.parametrize("acl", ["public-read", "public-read-write", "authenticated-read"])
def test_a_public_acl_refuses_to_boot(acl):
    with pytest.raises(ImproperlyConfigured, match="must not be stored"):
        check_storage_configuration(_Settings({"bucket_name": BUCKET, "default_acl": acl}))


def test_unsigned_object_urls_refuse_to_boot():
    with pytest.raises(ImproperlyConfigured, match="AWS_QUERYSTRING_AUTH"):
        check_storage_configuration(_Settings({"bucket_name": BUCKET, "querystring_auth": False}))


def test_a_correctly_configured_bucket_boots():
    check_storage_configuration(_Settings({"bucket_name": BUCKET}))
    check_storage_configuration(_Settings({"bucket_name": BUCKET, "default_acl": "private"}))


# ---------------------------------------------------------------------------
# The malware scanning hook
# ---------------------------------------------------------------------------


def test_no_scanner_is_configured_by_default(settings):
    assert settings.UPLOAD_SCANNER == "disabled"
    assert settings.UPLOAD_SCAN_FAIL_OPEN is False
    assert scanning.scan_upload(io.BytesIO(b"anything")).clean is True


@pytest.mark.django_db
def test_a_rejected_file_is_refused_without_naming_the_detection(settings):
    settings.UPLOAD_SCANNER = "reject_all"
    with pytest.raises(ValidationError) as excinfo:
        scanning.scan_upload(io.BytesIO(b"payload"), kind="submission")

    message = str(excinfo.value)
    assert "rejected by a security scan" in message
    # The signature name would let an uploader tune a payload until it passes.
    assert "reject-all" not in message


@pytest.mark.django_db
def test_a_rejection_is_recorded_as_a_file_security_event(settings):
    from apps.audit.models import AuditAction, AuditLog
    from apps.audit.services import flush_deferred
    from apps.common.request_context import take_deferred_audits

    settings.UPLOAD_SCANNER = "reject_all"
    with pytest.raises(ValidationError):
        scanning.scan_upload(io.BytesIO(b"payload"), kind="submission")

    # A refused upload aborts the request, and `ATOMIC_REQUESTS` would roll an
    # inline write back with it — so the entry is queued and flushed afterwards,
    # which in a real request is the middleware's job.
    flush_deferred(take_deferred_audits())

    entry = AuditLog.objects.filter(action=AuditAction.UPLOAD_REJECTED).latest("created_at")
    assert entry.resource_type == "submission"
    assert entry.context["detail"] == "test scanner: reject-all"


@pytest.mark.django_db
def test_an_unavailable_scanner_fails_closed(settings, monkeypatch):
    def broken(uploaded_file):
        raise scanning.ScannerUnavailable("connection refused")

    monkeypatch.setitem(scanning.SCANNERS, "broken", broken)
    settings.UPLOAD_SCANNER = "broken"

    with pytest.raises(ValidationError, match="temporarily unavailable"):
        scanning.scan_upload(io.BytesIO(b"payload"))


@pytest.mark.django_db
def test_failing_open_is_possible_but_must_be_chosen(settings, monkeypatch):
    def broken(uploaded_file):
        raise scanning.ScannerUnavailable("connection refused")

    monkeypatch.setitem(scanning.SCANNERS, "broken", broken)
    settings.UPLOAD_SCANNER = "broken"
    settings.UPLOAD_SCAN_FAIL_OPEN = True

    assert scanning.scan_upload(io.BytesIO(b"payload")).clean is True


def test_an_unknown_scanner_name_is_a_configuration_error(settings):
    settings.UPLOAD_SCANNER = "clamav-that-was-never-added"
    with pytest.raises(scanning.ScannerUnavailable, match="Unknown upload scanner"):
        scanning.scan_upload(io.BytesIO(b"payload"))


def test_the_scan_does_not_consume_the_file(settings):
    handle = io.BytesIO(b"student work")
    handle.read(4)
    scanning.scan_upload(handle)
    assert handle.read() == b"ent work"
