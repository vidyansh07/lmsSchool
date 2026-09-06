/**
 * A dashboard's work queue — "12 assignments to grade", "3 imports awaiting review".
 *
 * Distinct from `alert-list.tsx`: an alert is a notice ("something is wrong,
 * here is what"), a pending action is a unit of work with a count and a
 * button to go do it. Keeping them as two components means a screen that
 * needs only one does not import UI for the other, and neither's markup has
 * to compromise between "read this" and "do this".
 */
import { ArrowRight, PartyPopper } from 'lucide-react';
import Link from 'next/link';

import { ErrorState, LoadingState } from '@/components/states';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { formatCount } from '@/lib/format';

export interface PendingAction {
  id: string;
  /** The noun being counted, singular — "assignment", "import". */
  label: string;
  /** Plural form, if not simply `${label}s`. */
  labelPlural?: string;
  count: number;
  href: string;
  actionText?: string;
  urgent?: boolean;
}

export function PendingActions({
  items,
  isLoading,
  error,
  onRetry,
  emptyTitle = 'Nothing needs attention',
  emptyDescription = 'Your queue is clear.',
  title,
}: {
  items: PendingAction[];
  isLoading?: boolean;
  error?: { message: string; requestId?: string } | null;
  onRetry?: () => void;
  emptyTitle?: string;
  emptyDescription?: string;
  title?: string;
}) {
  if (isLoading) {
    return <LoadingState label={title ? `Loading ${title}…` : 'Loading pending actions…'} rows={3} />;
  }
  if (error) {
    return <ErrorState message={error.message} requestId={error.requestId} onRetry={onRetry} />;
  }

  const withWork = items.filter((item) => item.count > 0);

  if (withWork.length === 0) {
    return (
      <div className="flex items-center gap-2 rounded-[var(--radius-card)] border border-dashed border-border px-4 py-6 text-sm text-muted-foreground">
        <PartyPopper className="size-4 shrink-0 text-success" aria-hidden="true" />
        <div>
          <p className="font-medium text-foreground">{emptyTitle}</p>
          <p>{emptyDescription}</p>
        </div>
      </div>
    );
  }

  return (
    <ul className="divide-y divide-border rounded-[var(--radius-card)] border border-border">
      {withWork.map((item) => (
        <li key={item.id} className="flex items-center justify-between gap-3 px-4 py-3">
          <div className="flex min-w-0 items-center gap-2">
            {item.urgent ? <Badge variant="error">Urgent</Badge> : null}
            <p className="truncate text-sm">{formatCount(item.count, item.label, item.labelPlural)}</p>
          </div>
          <Button asChild variant="outline" size="sm" className="shrink-0">
            <Link href={item.href}>
              {item.actionText ?? 'Review'}
              <ArrowRight className="size-3.5" aria-hidden="true" />
            </Link>
          </Button>
        </li>
      ))}
    </ul>
  );
}
