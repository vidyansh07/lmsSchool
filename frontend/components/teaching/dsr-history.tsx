'use client';

/**
 * The change trail behind one daily status report — every submit, review
 * decision and edit already recorded via `apps.audit.services.record()` in
 * `apps.dsr.services` (ERP Phase 15's `GET /dsr/{id}/history/` only reads
 * that trail back; it does not write a second one). Structurally the same
 * on-demand, load-once-opened panel as `components/academics/attendance
 * -history.tsx` (Phase 7's closest analog): most reports have a short,
 * unremarkable history, so this fetches only when a trainer or manager
 * actually asks to see it.
 *
 * `context` is rendered generically rather than per-action, because this
 * screen has no fixed catalogue of every action a future audited change
 * might record: `changes` (`{field: {from, to}}`, the shape `update_dsr`
 * already writes) gets its own "field: from → to" line when present: every
 * other key in `context` — a rejection's `comments`, a status move's `from`/
 * `to` — renders as a plain "label: value" line underneath. That keeps a
 * rejection's reason visible without this component needing to know
 * `apps.dsr.services.review_dsr`'s context shape by name.
 */
import { useState } from 'react';

import { ErrorState, LoadingState } from '@/components/states';
import { Button } from '@/components/ui/button';
import { ApiError } from '@/lib/api';
import { getDsrHistory } from '@/lib/dsr';
import { formatDateTime } from '@/lib/format';
import type { DsrHistoryEntry } from '@/types/api';

/** Mirrors `apps.audit.models.AuditAction`'s `DSR_*` members and their
 *  human labels — falls back to a humanised version of the raw action for
 *  anything not in this list, so an action added later never renders as a
 *  raw dotted string. */
const ACTION_LABEL: Record<string, string> = {
  'dsr.created': 'Report started',
  'dsr.updated': 'Report updated',
  'dsr.submitted': 'Submitted for review',
  'dsr.review.started': 'Review started',
  'dsr.approved': 'Approved',
  'dsr.rejected': 'Rejected',
  'dsr.revision_requested': 'Revision requested',
};

function humanize(value: string): string {
  return value
    .replace(/[._]/g, ' ')
    .trim()
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function actionLabel(action: string): string {
  return ACTION_LABEL[action] ?? humanize(action);
}

function formatContextValue(value: unknown): string {
  if (value === null || value === undefined || value === '') return 'None';
  if (typeof value === 'object') return JSON.stringify(value);
  return String(value);
}

function isChangeMap(value: unknown): value is Record<string, { from?: unknown; to?: unknown }> {
  return (
    typeof value === 'object' &&
    value !== null &&
    Object.values(value).every(
      (entry) => typeof entry === 'object' && entry !== null && ('from' in entry || 'to' in entry),
    )
  );
}

function HistoryEntryContext({ context }: { context: Record<string, unknown> }) {
  const changes = isChangeMap(context.changes) ? context.changes : null;
  const otherEntries = Object.entries(context).filter(([key]) => key !== 'changes');

  if (!changes && otherEntries.length === 0) return null;

  return (
    <ul className="mt-1 space-y-0.5 text-muted-foreground">
      {changes
        ? Object.entries(changes).map(([field, change]) => (
            <li key={field}>
              {humanize(field)}: {formatContextValue(change.from)} → {formatContextValue(change.to)}
            </li>
          ))
        : null}
      {otherEntries.map(([key, value]) => (
        <li key={key}>
          {humanize(key)}: {formatContextValue(value)}
        </li>
      ))}
    </ul>
  );
}

export function DsrHistory({ dsrId }: { dsrId: string }) {
  const [isOpen, setIsOpen] = useState(false);
  const [entries, setEntries] = useState<DsrHistoryEntry[] | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [isLoading, setIsLoading] = useState(false);

  function load() {
    setIsLoading(true);
    setError(null);
    getDsrHistory(dsrId)
      .then((rows) => setEntries(rows))
      .catch((cause: unknown) => setError(cause instanceof ApiError ? cause : null))
      .finally(() => setIsLoading(false));
  }

  function toggle() {
    const next = !isOpen;
    setIsOpen(next);
    if (next && entries === null && !isLoading) load();
  }

  return (
    <div className="space-y-1.5">
      <Button
        type="button"
        variant="ghost"
        size="sm"
        className="h-auto p-0 text-xs underline-offset-4 hover:underline"
        onClick={toggle}
      >
        {isOpen ? 'Hide history' : 'View history'}
      </Button>
      {isOpen ? (
        <div className="animate-rise-in rounded-[var(--radius-card)] border border-border bg-muted/30 p-2 text-xs">
          {isLoading ? <LoadingState label="Loading history…" rows={2} /> : null}
          {error ? (
            <ErrorState
              title="Could not load this report's history"
              message={error.message}
              requestId={error.requestId || undefined}
              onRetry={load}
            />
          ) : null}
          {!isLoading && !error && entries ? (
            entries.length === 0 ? (
              <p className="text-muted-foreground">No changes recorded yet.</p>
            ) : (
              <ul className="space-y-2">
                {entries.map((entry) => (
                  <li key={entry.id}>
                    <span className="font-medium">{actionLabel(entry.action)}</span>{' '}
                    <span className="text-muted-foreground">
                      by {entry.actor?.name ?? 'System'} · {formatDateTime(entry.created_at)}
                    </span>
                    <HistoryEntryContext context={entry.context} />
                  </li>
                ))}
              </ul>
            )
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
