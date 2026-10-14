"""Malware scanning for uploads.

The validation seam and its failure policy are independent of the scanner
implementation. Staging uses ClamAV over the private Compose network; tests can
select deterministic scanners without touching a live daemon.

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

import socket
import struct
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


_CLAMAV_CHUNK_BYTES = 64 * 1024
_CLAMAV_RESPONSE_BYTES = 4096


def _clamav(uploaded_file: Any) -> ScanResult:
    """Stream a file to ``clamd`` using its bounded INSTREAM protocol.

    The file is not copied to a shared directory and its client filename is
    never sent. Only the bytes cross the private container network. ClamAV's
    TCP protocol has no transport security, so the compose service deliberately
    does not publish port 3310 to the host.
    """
    host = settings.CLAMAV_HOST
    port = settings.CLAMAV_PORT
    timeout = settings.CLAMAV_TIMEOUT_SECONDS

    try:
        uploaded_file.seek(0)
        with socket.create_connection((host, port), timeout=timeout) as connection:
            connection.settimeout(timeout)
            connection.sendall(b"zINSTREAM\0")
            while True:
                chunk = uploaded_file.read(_CLAMAV_CHUNK_BYTES)
                if not chunk:
                    break
                if not isinstance(chunk, bytes):
                    raise ScannerUnavailable("ClamAV received a non-binary upload stream.")
                connection.sendall(struct.pack("!I", len(chunk)))
                connection.sendall(chunk)
            connection.sendall(struct.pack("!I", 0))

            response = bytearray()
            while len(response) < _CLAMAV_RESPONSE_BYTES:
                block = connection.recv(min(1024, _CLAMAV_RESPONSE_BYTES - len(response)))
                if not block:
                    break
                response.extend(block)
                if b"\0" in block:
                    break
    except ScannerUnavailable:
        raise
    except (OSError, ValueError) as exc:
        raise ScannerUnavailable(f"ClamAV could not scan the upload: {exc}") from exc

    answer = bytes(response).split(b"\0", 1)[0].decode("utf-8", "replace").strip()
    if answer.endswith(" OK"):
        return ScanResult(clean=True, detail="clean")
    if answer.endswith(" FOUND"):
        signature = answer.removesuffix(" FOUND").partition(":")[2].strip()
        return ScanResult(clean=False, detail=signature or "malware detected")
    if not answer:
        raise ScannerUnavailable("ClamAV closed the connection without a response.")
    raise ScannerUnavailable(f"ClamAV returned an error: {answer}")


#: name -> scanner. A real scanner is added here and selected by configuration;
#: nothing that calls `scan_upload` changes.
SCANNERS: dict[str, Callable[[Any], ScanResult]] = {
    "clamav": _clamav,
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
