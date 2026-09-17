'use client';

/**
 * Renders a template preview's `html` — the one place in this screen set
 * that shows HTML the server built from an administrator-written body plus
 * real recipient data (D-051).
 *
 * This never uses `dangerouslySetInnerHTML`. Two independent reasons, not
 * one:
 *
 *  1. The backend's own sanitiser (an allowlist of safe tags/attributes) is
 *     the thing standing between an injected `<script>` and a browser
 *     executing it, and this screen has no way to confirm from here that
 *     sanitisation actually ran — a future backend bug that skips it would
 *     turn `dangerouslySetInnerHTML` into a stored-XSS delivery vector the
 *     moment an admin opens "Preview".
 *  2. This codebase has no existing precedent for `dangerouslySetInnerHTML`
 *     rendering server-sanitised HTML to check the sanitisation contract
 *     against (grepped before writing this file) — course lesson bodies,
 *     announcement bodies and DSR notes are all plain text rendered with
 *     `white-space: pre-wrap`, never HTML.
 *
 * An `<iframe sandbox="">` (no `allow-scripts`, no `allow-same-origin`) gives
 * a second, independent layer even if sanitisation somehow failed: the
 * browser itself refuses to execute anything inside a sandboxed frame with
 * scripts not allowed, and the frame's `about:srcdoc` origin cannot reach
 * this page's cookies, storage or DOM even with `allow-same-origin` (which
 * is deliberately not granted here). `srcdoc` is used instead of a `src`
 * blob/data URL so nothing is written to the network or object URLs that
 * would need cleaning up.
 */

import { useMemo } from 'react';

export function TemplateHtmlPreview({
  html,
  title = 'Template preview',
}: {
  html: string;
  title?: string;
}) {
  // A minimal, fixed wrapper document — no external stylesheet or script can
  // be pulled in from inside a sandboxed frame anyway, but keeping the shell
  // itself inert (no <script>, no meta-refresh) means the only thing this
  // component ever hands the frame is the server's own sanitised markup.
  const doc = useMemo(
    () =>
      `<!doctype html><html><head><meta charset="utf-8"><style>` +
      `body{font:14px/1.5 system-ui,sans-serif;color:#0f172a;margin:0;padding:12px;` +
      `overflow-wrap:anywhere}img{max-width:100%}</style></head><body>${html}</body></html>`,
    [html],
  );

  return (
    <iframe
      title={title}
      srcDoc={doc}
      sandbox=""
      className="h-64 w-full rounded-md border border-border bg-white"
      data-testid="template-html-preview"
    />
  );
}
