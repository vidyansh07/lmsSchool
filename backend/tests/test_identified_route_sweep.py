"""Every endpoint that takes an id, swept for the caller who should not reach it.

`tests/test_authorization_matrix.py` walks the URL resolver and refuses
anything parameterless to a caller without the capability. It skips every route
with an id in it on purpose, leaving those to an object sweep written by hand —
and a hand-written list is incomplete the day somebody adds a route. Two
endpoints added this week (a course's price history, refunding a payment) were
in exactly that gap: guarded in their own feature tests, invisible to the sweep
that is supposed to catch the ones nobody thought about.

So this does for identified routes what the other does for parameterless ones.
It cannot use a real record — building one per endpoint is the hand-written
list again — so it uses a well-formed id that belongs to nobody. That is enough
for the question being asked, because the answer must not depend on whether the
record exists: a caller without the capability is refused either way, and a
caller who is refused only because the row is missing is a caller who would
have been served if it were not.

What counts as a pass:

* **not 200, and not 2xx** — the caller must not be served;
* **not 500** — a bad id is a refusal, not a crash, and a stack trace is its
  own disclosure;
* **404 rather than 403 is fine and often better** — it refuses without
  confirming that the id names anything.
"""

from __future__ import annotations

import re

import pytest
from django.urls import URLPattern, URLResolver, get_resolver

from tests.test_authorization_matrix import _declared_capabilities

#: A syntactically valid id that belongs to nobody.
NOBODY = "00000000-0000-4000-8000-000000000000"

_CONVERTERS = {
    "uuid": NOBODY,
    "int": "1",
    "str": "nobody",
    "slug": "nobody",
    "path": "nobody",
}


def _fill(route: str) -> str | None:
    """A concrete URL for a parameterised route, or ``None`` if it uses a
    converter this sweep does not know how to fill — better to skip loudly
    than to invent a path that resolves somewhere else."""
    out = route
    for match in re.finditer(r"<([a-z]+):([a-z_]+)>", route):
        converter, _name = match.groups()
        value = _CONVERTERS.get(converter)
        if value is None:
            return None
        out = out.replace(match.group(0), value)
    return None if "<" in out else out


def _identified_routes() -> list[tuple[str, object]]:
    found: list[tuple[str, object]] = []

    def walk(patterns, prefix: str) -> None:
        for entry in patterns:
            if isinstance(entry, URLResolver):
                walk(entry.url_patterns, prefix + str(entry.pattern))
            elif isinstance(entry, URLPattern):
                route = prefix + str(entry.pattern)
                if "<" not in route or not route.startswith("api/v1/"):
                    continue
                view = getattr(entry.callback, "cls", None) or getattr(
                    entry.callback, "view_class", None
                )
                if view is not None:
                    found.append(("/" + route, view))

    walk(get_resolver().url_patterns, "")
    return sorted(set(found), key=lambda pair: pair[0])


ROUTES = _identified_routes()
GUARDED = [(route, view) for route, view in ROUTES if _declared_capabilities(view) and _fill(route)]


def test_the_sweep_found_the_identified_api():
    """A sweep that silently matched nothing would pass forever."""
    assert len(ROUTES) > 40, f"only {len(ROUTES)} identified routes found"
    assert len(GUARDED) > 5, f"only {len(GUARDED)} of them declare a capability"


def test_every_identified_route_can_be_filled():
    """A converter this sweep cannot fill is a route it is not covering.

    Named rather than skipped quietly, because the reason to have this is the
    routes nobody remembered.
    """
    unfillable = [route for route, _ in ROUTES if _fill(route) is None]
    assert unfillable == [], f"cannot build a URL for: {unfillable}"


@pytest.mark.django_db
@pytest.mark.parametrize("route,view", GUARDED, ids=[route for route, _ in GUARDED])
def test_a_student_is_refused_every_guarded_identified_route(
    route, view, api_client_no_csrf, student
):
    """A student holds three capabilities. Everything guarded by another one
    must refuse them, whether or not the id names a real record."""
    required = _declared_capabilities(view)
    from apps.accounts.roles import has_capability

    if all(has_capability(student, capability) for capability in required):
        pytest.skip("a student legitimately holds this capability")

    api_client_no_csrf.force_authenticate(user=student)
    response = api_client_no_csrf.get(_fill(route))

    assert response.status_code not in range(200, 300), (
        f"{route} served a student without {required}"
    )
    assert response.status_code != 500, f"{route} crashed on an id that belongs to nobody"


@pytest.mark.django_db
@pytest.mark.parametrize("route,view", GUARDED, ids=[route for route, _ in GUARDED])
def test_an_anonymous_caller_is_refused_every_guarded_identified_route(
    route, view, api_client_no_csrf
):
    response = api_client_no_csrf.get(_fill(route))

    assert response.status_code in (401, 403, 404), (
        f"{route} answered an anonymous caller with {response.status_code}"
    )


@pytest.mark.django_db
@pytest.mark.parametrize("route,view", ROUTES, ids=[route for route, _ in ROUTES])
def test_no_identified_route_crashes_on_an_id_that_belongs_to_nobody(
    route, view, api_client_no_csrf, student
):
    """A stack trace is its own disclosure.

    Run for every identified route, not only the guarded ones: an unguarded
    endpoint that 500s on a stranger's id is still leaking its internals.
    """
    url = _fill(route)
    if url is None:
        pytest.skip("converter not fillable")

    api_client_no_csrf.force_authenticate(user=student)
    response = api_client_no_csrf.get(url)

    assert response.status_code != 500, f"{route} crashed on a well-formed unknown id"


@pytest.mark.django_db
def test_the_endpoints_added_this_week_are_in_the_sweep():
    """The gap that prompted this, pinned so it cannot quietly reopen."""
    covered = {route for route, _ in ROUTES}
    for route in (
        "/api/v1/courses/<str:identifier>/price/",
        "/api/v1/fees/payments/<uuid:payment_id>/refund/",
    ):
        assert route in covered, f"{route} is not being swept"
