"""The seam where a malware scanner attaches to uploads.

§14.3 asks for the *architecture*, not a scanner. The distinction matters:
bolting ClamAV onto this deployment today would add a daemon, a signature feed
and an operational failure mode nobody has agreed to run, while leaving the
actual question — "what happens to an upload when the scanner says no, and what
happens when the scanner is down?" — unanswered. Those two answers are the hard
part, so they are written down and tested here, and the scanner itself is a
named function that arrives later without touching a single caller.

How it attaches
---------------
``scan_upload`` is called by the upload validators after the cheap checks (size,
extension, magic bytes) and before the file is stored. Cheap checks first is
deliberate: a scanner is the most expensive check and the easiest to overload,
so it only ever sees files that already look legitimate.

The two answers
---------------
**Infected** — the upload is refused with a validation error that says the file
was rejected by a security scan and nothing else. The specific signature name is
recorded in the audit log, not returned: telling an uploader *which* detection
fired turns the endpoint into an oracle for tuning a payload until it passes.

**Scanner unavailable** — governed by ``UPLOAD_SCAN_FAIL_OPEN``, and it defaults
to *closed*: if the scanner cannot answer, the upload is refused. Failing open is
the tempting choice because it keeps the site working during an outage, and it
means an attacker can bypass scanning entirely by taking the scanner down. An
institution that cannot accept assignments for an hour is having a bad day; one
that accepted a malicious file because a health check flapped has a different
kind of problem.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _


class ScannerUnavailable(RuntimeError):
    """The scanner could not be reached or did not answer in time."""


@dataclass(frozen=True, slots=True)
class ScanResult:
    """What a scanner reports about one file."""

    clean: bool
    #: Signature or reason. Audit-only — never returned to the uploader.
    detail: str = ""


def _disabled(uploaded_file: Any) -> ScanResult:
    """No scanner configured. Every file passes the (absent) scan."""
    return ScanResult(clean=True, detail="scanning disabled")


def _reject_all(uploaded_file: Any) -> ScanResult:
    """Refuse everything. Exists so the rejection path is exercised by tests
    and can be switched on deliberately to prove the wiring in an environment."""
    return ScanResult(clean=False, detail="test scanner: reject-all")


#: name -> scanner. A real scanner is added here and selected by configuration;
#: nothing that calls `scan_upload` changes.
SCANNERS: dict[str, Callable[[Any], ScanResult]] = {
    "disabled": _disabled,
    "reject_all": _reject_all,
}


def scanner_name() -> str:
    return getattr(settings, "UPLOAD_SCANNER", "disabled")


def fail_open() -> bool:
    return bool(getattr(settings, "UPLOAD_SCAN_FAIL_OPEN", False))


def scan_upload(uploaded_file: Any, *, kind: str = "upload") -> ScanResult:
    """Scan one uploaded file, raising ``ValidationError`` if it is refused.

    ``kind`` names the upload site ("submission", "resource") and is recorded so
    a refusal can be traced back to where it happened.
    """
    name = scanner_name()
    scanner = SCANNERS.get(name)
    if scanner is None:
        # An unknown scanner name is a configuration error, and treating it as
        # "no scanner" would silently disable the control that was asked for.
        raise ScannerUnavailable(f"Unknown upload scanner {name!r}.")

    position = None
    try:
        position = uploaded_file.tell()
    except (AttributeError, OSError):  # pragma: no cover - non-seekable inputs
        position = None

    try:
        result = scanner(uploaded_file)
    except ScannerUnavailable as exc:
        _record_event("unavailable", kind=kind, detail=str(exc))
        if fail_open():
            return ScanResult(clean=True, detail="scanner unavailable; failed open")
        raise ValidationError(
            _("Uploads are temporarily unavailable. Please try again shortly."),
            code="scanner_unavailable",
        ) from exc
    finally:
        if position is not None:
            try:
                uploaded_file.seek(position)
            except (AttributeError, OSError):  # pragma: no cover
                pass

    if not result.clean:
        _record_event("rejected", kind=kind, detail=result.detail)
        raise ValidationError(
            _("This file was rejected by a security scan."),
            code="malware_detected",
        )
    return result


def _record_event(outcome: str, *, kind: str, detail: str) -> None:
    """Audit a file security event.

    Imported lazily: `apps.common` is imported by settings, and reaching for the
    audit app at module scope would make storage configuration depend on the
    app registry being ready.
    """
    from apps.audit.models import AuditAction, AuditResult
    from apps.audit.services import record

    record(
        action=AuditAction.UPLOAD_REJECTED,
        result=AuditResult.DENIED,
        resource_type=kind,
        context={"outcome": outcome, "scanner": scanner_name(), "detail": detail},
    )
