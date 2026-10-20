"""Refusing to post anywhere a webhook should not reach.

A webhook URL is typed by an administrator, but the request leaves from inside
the deployment, where `http://169.254.169.254/` is the cloud metadata service
and `http://localhost:8000/` is this application's own unauthenticated side.
So: HTTPS only (plain HTTP only when `INTEGRATION_ALLOW_HTTP` is on, for local
development), and every address the host resolves to must be a public one.
The check is repeated at send time, because a name that resolved to a public
address when the webhook was saved can resolve elsewhere later.
"""

from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlsplit

from django.conf import settings

from apps.common.exceptions import ApplicationError


def _refuse(message: str) -> None:
    raise ApplicationError({"url": [message]})


def check_url(url: str, *, resolve: bool = True) -> None:
    parts = urlsplit(url)
    allow_http = getattr(settings, "INTEGRATION_ALLOW_HTTP", False)
    if parts.scheme != "https" and not (allow_http and parts.scheme == "http"):
        _refuse("Use an https:// address.")
    if not parts.hostname:
        _refuse("The address has no host name.")
    if parts.username or parts.password:
        _refuse("Put credentials in the headers, not in the address.")
    if not resolve or allow_http:
        return
    try:
        infos = socket.getaddrinfo(parts.hostname, parts.port or 443, proto=socket.IPPROTO_TCP)
    except OSError:
        _refuse("That host name does not resolve.")
    for info in infos:
        address = ipaddress.ip_address(info[4][0])
        if not address.is_global or address.is_multicast:
            _refuse("That address is inside a private network; only public addresses are allowed.")
