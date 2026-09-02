/**
 * The three states every data-driven view needs.
 *
 * Having them as shared components means loading, error and empty views look
 * the same everywhere and no screen quietly forgets one of them.
 */
import type { ReactNode } from 'react';
import { AlertTriangle, Inbox, RefreshCw } from 'lucide-react';

import { Alert, AlertTitle } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import { cn } from '@/lib/utils';

export function LoadingState({ label = 'Loading…', rows = 3 }: { label?: string; rows?: number }) {
  return (
    <div role="status" aria-live="polite" aria-busy="true" className="space-y-3">
      <span className="sr-only">{label}</span>
      {Array.from({ length: rows }, (_, index) => (
        <Skeleton key={index} className={cn('h-4', index === 0 ? 'w-1/3' : 'w-full')} />
      ))}
    </div>
  );
}

export function ErrorState({
  title = 'Something went wrong',
  message,
  requestId,
  onRetry,
}: {
  title?: string;
  message: string;
  requestId?: string;
  onRetry?: () => void;
}) {
  return (
    <Alert variant="error" className="space-y-2">
      <AlertTitle className="flex items-center gap-2">
        <AlertTriangle className="size-4" aria-hidden="true" />
        {title}
      </AlertTitle>
      <p className="text-muted-foreground">{message}</p>
      {requestId ? (
        // Quoting the request id lets support find the matching server log
        // without the user having to share anything sensitive.
        <p className="text-xs text-muted-foreground">
          Reference: <code className="font-mono">{requestId}</code>
        </p>
      ) : null}
      {onRetry ? (
        <Button variant="outline" size="sm" onClick={onRetry}>
          <RefreshCw className="size-3.5" aria-hidden="true" />
          Try again
        </Button>
      ) : null}
    </Alert>
  );
}

export function EmptyState({
  title,
  description,
  action,
}: {
  title: string;
  description?: string;
  action?: ReactNode;
}) {
  return (
    <div className="flex flex-col items-center gap-2 rounded-[var(--radius-card)] border border-dashed border-border px-6 py-12 text-center">
      <Inbox className="size-6 text-muted-foreground" aria-hidden="true" />
      <p className="font-medium">{title}</p>
      {description ? <p className="text-sm text-muted-foreground">{description}</p> : null}
      {action}
    </div>
  );
}
