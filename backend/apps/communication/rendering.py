"""Rendering a template version against real data (ERP Phase 19, D-051).

Two rules, and neither is negotiable:

1. **Substitution only, never evaluation.** `{{path.to.value}}` is looked up
   in a plain dict with the exact same bounded, dotted-path walk
   `apps.automation.actions.render_template` already built (`get_path`,
   below) — reused, not re-implemented, so there is exactly one
   "how does `{{...}}` get replaced" in this codebase. There is no `.format()`,
   no f-string over caller-supplied text, and no `eval` anywhere near a
   template body: a template author (or a recipient's own name/notes field,
   which is exactly the same class of attacker for this purpose) cannot make
   the substitution step itself do anything but look up and stringify.
2. **Only allowlisted paths.** `version.variables` is that specific version's
   own allowlist. A path in the body that is not on it is never looked up —
   it is dropped (renders empty) and reported in `warnings`, which is what
   keeps a template author from smuggling in a path nobody reviewed when the
   version was approved.

The HTML output additionally passes through `apps.forms.validation`'s
allowlist-tag sanitiser — reused rather than a second one — *after*
substitution, so a `<script>` tag reaches this function from either
direction (typed into the template body, or sitting in a recipient's own
data) and is stripped either way.

That sanitiser is deliberately permissive of a small set of *safe* tags
(``<b>``, ``<a>``, ``<p>``, ...) — correct for markup the template's own
author typed, wrong for a value pulled from a real record. Left
unescaped, a recipient whose name happens to contain ``<b>`` or
``<a href="...">`` would have that interpreted as live markup rather than
shown as the literal characters it is — D-051's own second scenario,
named in exactly those words. So HTML substitution escapes every
substituted *value* (never the template's own surrounding markup) before
the sanitiser ever sees the string: the escaped value can no longer be
parsed as a tag by anything downstream, whether or not that tag would
otherwise have been on the allowlist. The plain-text and subject outputs
carry no such risk (nothing downstream interprets them as markup) and so
are substituted without escaping, exactly as typed.
"""

from __future__ import annotations

import html
import re
from typing import Any

from apps.automation.evaluator import MISSING, get_path
from apps.forms.validation import sanitise_richtext

_VARIABLE_RE = re.compile(r"\{\{\s*([a-zA-Z0-9_.]+)\s*\}\}")


def _substitute(
    text: str,
    variables: dict[str, Any],
    allowlist: frozenset[str],
    warnings: list[str],
    *,
    escape_values: bool = False,
) -> str:
    seen: set[str] = set()

    def _replace(match: re.Match[str]) -> str:
        path = match.group(1)
        if path not in allowlist:
            if path not in seen:
                seen.add(path)
                warnings.append(f"'{{{{{path}}}}}' is not in this version's variable allowlist.")
            return ""
        value = get_path(variables, path)
        if value is MISSING or value is None:
            return ""
        rendered = str(value)
        return html.escape(rendered) if escape_values else rendered

    return _VARIABLE_RE.sub(_replace, text or "")


def render_template(version, variables: dict[str, Any]) -> dict[str, Any]:
    """Render one `TemplateVersion` against a resolved variable context.

    Returns ``{"subject", "html", "text", "warnings"}``. Never raises for a
    bad or missing variable — an unlisted `{{...}}` reference is dropped and
    named in `warnings`, exactly the D-051 "never causing an error" contract.
    """
    allowlist = frozenset(str(path) for path in (version.variables or []))
    warnings: list[str] = []

    subject = _substitute(version.subject, variables, allowlist, warnings)
    text = _substitute(version.body_text, variables, allowlist, warnings)
    raw_html = _substitute(version.body_html, variables, allowlist, warnings, escape_values=True)
    rendered_html = sanitise_richtext(raw_html)

    return {"subject": subject, "html": rendered_html, "text": text, "warnings": warnings}
