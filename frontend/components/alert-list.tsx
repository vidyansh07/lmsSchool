/**
 * A dashboard's "things worth noticing" panel — overdue fees, failed imports,
 * a batch with no trainer assigned.
 *
 * The empty state is deliberately not the shared `EmptyState` from
 * `states.tsx`: an empty alert list is not a missing-content problem to
 * explain, it is the best possible outcome, and it should say so rather than
 * rendering the same dashed box a screen shows when a search finds nothing.
 */
import { AlertTriangle, CheckCircle2, Info, XCircle } from 'lucide-react';
import Link from 'next/link';

import { ErrorState, LoadingState } from '@/components/states';
import { fallback } from '@/lib/format';
import { cn } from '@/lib/utils';

export type AlertSeverity = 'info' | 'warning' | 'error';

export interface AlertItem {
  id: string;
  severity: AlertSeverity;
  title: string;
  description?: string;
  /** How many records this alert covers, e.g. 12 overdue fee payments. */
  count?: number;
  href?: string;
}

const SEVERITY_ICON: Record<AlertSeverity, typeof Info> = {
  info: Info,
  warning: AlertTriangle,
  error: XCircle,
};

const SEVERITY_TONE: Record<AlertSeverity, string> = {
  info: 'text-muted-foreground',
  warning: 'text-warning',
  error: 'text-destructive',
};

export function AlertList({
  items,
  isLoading,
  error,
  onRetry,
  emptyTitle = 'Nothing needs attention',
  emptyDescription = 'No open alerts right now.',
  title,
}: {
  items: AlertItem[];
  isLoading?: boolean;
  error?: { message: string; requestId?: string } | null;
  onRetry?: () => void;
  emptyTitle?: string;
  emptyDescription?: string;
  title?: string;
}) {
  if (isLoading) return <LoadingState label={title ? `Loading ${title}…` : 'Loading alerts…'} rows={3} />;
  if (error) {
    return (
      <ErrorState message={error.message} requestId={error.requestId} onRetry={onRetry} />
    );
  }

  if (items.length === 0) {
    return (
      <div className="flex items-center gap-2 rounded-[var(--radius-card)] border border-dashed border-border px-4 py-6 text-sm text-muted-foreground">
        <CheckCircle2 className="size-4 shrink-0 text-success" aria-hidden="true" />
        <div>
          <p className="font-medium text-foreground">{emptyTitle}</p>
          <p>{emptyDescription}</p>
        </div>
      </div>
    );
  }

  return (
    <ul className="divide-y divide-border rounded-[var(--radius-card)] border border-border">
      {items.map((item) => {
        const Icon = SEVERITY_ICON[item.severity];
        const body = (
          <div className="flex items-start gap-3 px-4 py-3">
            <Icon className={cn('mt-0.5 size-4 shrink-0', SEVERITY_TONE[item.severity])} aria-hidden="true" />
            <div className="min-w-0 flex-1">
              <p className="truncate text-sm font-medium">{fallback(item.title, 'Unknown')}</p>
              {item.description ? (
                <p className="text-xs text-muted-foreground">{item.description}</p>
              ) : null}
            </div>
            {typeof item.count === 'number' ? (
              <span className="shrink-0 rounded-full bg-muted px-2 py-0.5 text-xs font-medium tabular-nums">
                {item.count}
              </span>
            ) : null}
          </div>
        );

        return (
          <li key={item.id}>
            {item.href ? (
              <Link href={item.href} className="block transition-colors hover:bg-muted">
                {body}
              </Link>
            ) : (
              body
            )}
          </li>
        );
      })}
    </ul>
  );
}
