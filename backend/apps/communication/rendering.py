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


# ---------------------------------------------------------------------------
# Email HTML
# ---------------------------------------------------------------------------
#
# An email body needs more than `sanitise_richtext` allows. That allowlist —
# `p`, `b`, `a`, lists — is right for a form's rich-text answer, and it
# silently drops every heading, image, rule and table a composed email is
# made of: the block composer would show a heading and a button in its
# preview, and the recipient would get neither, because the tags were
# unwrapped on the way out. Two sanitisers for two jobs is the honest answer;
# one permissive enough for both would be the dishonest one.
#
# What is allowed here is still an allowlist, and still no attributes beyond
# the handful named below. In particular:
#
# * `style` is **not** allowed anywhere. Inline CSS is how marketing email is
#   normally built, and it is also `background:url(javascript:…)`, position
#   tricks and content hiding; the composer therefore emits presentational
#   *attributes* (`align`, `width`, `valign`) and one fixed button rendering
#   rather than author-supplied CSS.
# * `href` and `src` must be `https://` — the same rule `sanitise_richtext`
#   applies to links, extended to images, so no `javascript:` and no
#   `http://` tracking pixel either.
# * `on*` handlers cannot survive, because every attribute that is not on
#   the per-tag list is dropped rather than filtered.

_EMAIL_ALLOWED_TAGS: dict[str, frozenset[str]] = {
    "p": frozenset({"align"}),
    "br": frozenset(),
    "b": frozenset(),
    "strong": frozenset(),
    "i": frozenset(),
    "em": frozenset(),
    "u": frozenset(),
    "ul": frozenset(),
    "ol": frozenset(),
    "li": frozenset(),
    "blockquote": frozenset(),
    "code": frozenset(),
    "pre": frozenset(),
    "a": frozenset({"href"}),
    "h1": frozenset(),
    "h2": frozenset(),
    "h3": frozenset(),
    "hr": frozenset(),
    "img": frozenset({"src", "alt", "width"}),
    "table": frozenset({"width", "role", "bgcolor"}),
    "thead": frozenset(),
    "tbody": frozenset(),
    "tr": frozenset(),
    "td": frozenset({"width", "valign", "align", "bgcolor"}),
    "th": frozenset({"width", "valign", "align", "bgcolor"}),
    "div": frozenset(),
    "span": frozenset(),
}

#: Attributes whose value must be an `https://` URL or be dropped with the
#: whole attribute.
_URL_ATTRIBUTES = frozenset({"href", "src"})

#: `bgcolor` is how a button gets its colour without inline CSS — the old
#: "bulletproof button" a cell and a link. Only a plain hex colour is kept;
#: anything else (a named colour is harmless, a `url(...)` is not) is dropped
#: with the attribute.
_HEX_COLOUR_RE = re.compile(r"^#[0-9a-fA-F]{3,8}$")

_EMAIL_SCRIPT_RE = re.compile(r"(?is)<(script|style)\b.*?</\1\s*>")
_EMAIL_TAG_RE = re.compile(r"<(/?)([a-zA-Z][a-zA-Z0-9]*)((?:\s*/)?[^>]*)>")
_ATTR_RE = re.compile(r'([a-zA-Z-]+)\s*=\s*"([^"<>]*)"')


def sanitise_email_html(value: str) -> str:
    """Strip an email body down to the tags and attributes above.

    Script and style blocks go with their content; any other disallowed tag
    is unwrapped, keeping what it contained — the same shape
    `sanitise_richtext` uses, so an unexpected tag loses its markup rather
    than its words.
    """
    value = _EMAIL_SCRIPT_RE.sub("", value)

    def _replace(match: re.Match[str]) -> str:
        closing, tag, attrs = match.group(1), match.group(2).lower(), match.group(3)
        allowed = _EMAIL_ALLOWED_TAGS.get(tag)
        if allowed is None:
            return ""
        if closing:
            return f"</{tag}>"
        kept: list[str] = []
        for name, attr_value in _ATTR_RE.findall(attrs):
            name = name.lower()
            if name not in allowed:
                continue
            if name in _URL_ATTRIBUTES and not attr_value.lower().startswith("https://"):
                continue
            if name == "bgcolor" and not _HEX_COLOUR_RE.match(attr_value.strip()):
                continue
            kept.append(f'{name}="{html.escape(attr_value, quote=True)}"')
        spelled = (" " + " ".join(kept)) if kept else ""
        void = "/" if tag in {"br", "hr", "img"} else ""
        return f"<{tag}{spelled}{void}>"

    return _EMAIL_TAG_RE.sub(_replace, value)


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
    rendered_html = sanitise_email_html(raw_html)

    return {"subject": subject, "html": rendered_html, "text": text, "warnings": warnings}
