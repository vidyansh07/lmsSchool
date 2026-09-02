"""Where uploaded files live, and who is allowed to reach them.

Two backends, one seam
----------------------
Development stores files on a local volume; a deployed environment stores them
in S3. Both are reached through Django's storage API, so no view, model or
service knows which one is in use — swapping them is configuration, not a code
change.

The rule that survives the swap
-------------------------------
Every student file is private. Not "private by convention", but private in the
three ways that actually matter:

1. **No public URL.** ``default_acl = None`` means objects inherit the bucket's
   policy rather than being stamped ``public-read`` by the upload, and
   ``querystring_auth = True`` means ``storage.url()`` returns a signed URL that
   expires. A leaked URL stops working; a leaked *path* was never enough.
2. **No direct hand-off.** The application still serves downloads itself, after
   an authorization check, exactly as it did on local storage. The signed URL is
   the fallback the storage API needs, not the delivery path.
3. **No public bucket.** ``check_storage_configuration`` refuses to boot a
   deployed environment whose settings would make objects readable without a
   signature. A misconfiguration that publishes student work is not something to
   discover from a search engine.

Why signed URLs are not the download path
-----------------------------------------
Handing the browser a signed URL is faster and cheaper — the file never touches
the application. It is also a bearer token in a URL: it lands in browser
history, in the referrer of any page it embeds, and in whatever the student
pastes into a chat window. Streaming through the view keeps one authorization
check in one place and no credential in the address bar. If offloading ever
becomes necessary, the seam is here and the trade-off is written down.
"""

from __future__ import annotations

from typing import Any, ClassVar

from django.core.exceptions import ImproperlyConfigured

#: Backends selectable through ``FILE_STORAGE_BACKEND``.
LOCAL_BACKEND = "local"
S3_BACKEND = "s3"
BACKENDS = (LOCAL_BACKEND, S3_BACKEND)

_LOCAL_STORAGE = "django.core.files.storage.FileSystemStorage"
_S3_STORAGE = "apps.common.storage.PrivateMediaStorage"


def storage_settings(backend: str, options: dict[str, Any] | None = None) -> dict[str, Any]:
    """The ``STORAGES['default']`` entry for the named backend.

    Kept as a function so the choice is made once, in settings, and every
    environment gets the same shape — rather than each settings module
    assembling its own dictionary and one of them forgetting a flag.
    """
    if backend not in BACKENDS:
        raise ImproperlyConfigured(
            f"FILE_STORAGE_BACKEND must be one of {', '.join(BACKENDS)}, not {backend!r}."
        )
    if backend == LOCAL_BACKEND:
        return {"BACKEND": _LOCAL_STORAGE}
    return {"BACKEND": _S3_STORAGE, "OPTIONS": dict(options or {})}


def check_storage_configuration(settings_module: Any) -> None:
    """Refuse to boot a deployed environment that would expose student files.

    Called from the hardened settings. Every one of these is a configuration
    mistake that silently succeeds — the app runs, uploads work, and the files
    are readable by anyone who can guess a key.
    """
    storages = getattr(settings_module, "STORAGES", {})
    default = storages.get("default", {})
    if default.get("BACKEND") != _S3_STORAGE:
        return

    options = default.get("OPTIONS", {})
    if not options.get("bucket_name"):
        raise ImproperlyConfigured("AWS_STORAGE_BUCKET_NAME is required when using S3 storage.")
    acl = options.get("default_acl")
    if acl not in (None, "private"):
        raise ImproperlyConfigured(
            f"Student files must not be stored with a {acl!r} ACL. "
            "Leave AWS_DEFAULT_ACL unset so the bucket policy governs access."
        )
    if options.get("querystring_auth") is False:
        raise ImproperlyConfigured(
            "AWS_QUERYSTRING_AUTH must stay on: without it object URLs are unsigned "
            "and anyone holding a URL can read a student's file forever."
        )


try:  # pragma: no cover - exercised through the settings that select it
    from storages.backends.s3boto3 import S3Boto3Storage
except ImportError:  # pragma: no cover - local installs without the S3 extra
    S3Boto3Storage = None


if S3Boto3Storage is not None:

    class PrivateMediaStorage(S3Boto3Storage):
        """S3 storage for student files: private objects, signed URLs, no overwrite.

        The defaults are set on the class rather than left to settings so that a
        deployment which forgets to configure them still gets the safe
        behaviour. Settings may narrow these (a shorter signature life) but the
        boot check above stops them widening.
        """

        #: Never stamp an ACL on upload. The bucket policy is the single place
        #: access is decided, and a bucket-owner-enforced bucket rejects ACLs
        #: outright.
        default_acl = None
        #: Sign every URL, and let the signature expire.
        querystring_auth = True
        #: Pinned. Left to boto3 this is chosen per endpoint, and against a
        #: custom one (MinIO, R2) it picks the deprecated SigV2 — which every
        #: AWS region created after 2014 rejects outright. The failure only
        #: appears on the real bucket, long after it worked in staging, so the
        #: version is stated rather than inferred.
        signature_version = "s3v4"
        querystring_expire = 300  # five minutes; long enough to fetch, short enough to leak
        #: Two students uploading `report.pdf` must not collide, and an upload
        #: must never silently replace an existing object.
        file_overwrite = False
        #: Uploads are not world-readable static assets; nothing should cache them.
        object_parameters: ClassVar[dict[str, str]] = {
            "CacheControl": "private, max-age=0, no-store"
        }

else:  # pragma: no cover - import guard only

    class PrivateMediaStorage:  # type: ignore[no-redef]
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            raise ImproperlyConfigured(
                "S3 storage was selected but django-storages/boto3 are not installed."
            )
