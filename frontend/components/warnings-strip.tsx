'use client';

/**
 * The warnings strip: what needs doing, most urgent first, on every staff
 * dashboard. Each line is a server-computed warning over what the caller can
 * see, with a count, a place to fix it, and the first few names behind the
 * number on demand. Nothing is computed here.
 */

import Link from 'next/link';
import { useState } from 'react';
import {
  AlertOctagon,
  AlertTriangle,
  ChevronDown,
  ChevronUp,
  Info,
  ShieldCheck,
} from 'lucide-react';

import { ErrorState } from '@/components/states';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { useApi } from '@/hooks/use-api';
import { cn } from '@/lib/utils';
import type { StaffWarning, WarningSeverity } from '@/types/api';

const TONE: Record<
  WarningSeverity,
  { icon: typeof Info; row: string; badge: 'error' | 'warning' | 'neutral' }
> = {
  error: { icon: AlertOctagon, row: 'text-danger', badge: 'error' },
  warning: { icon: AlertTriangle, row: 'text-warning', badge: 'warning' },
  info: { icon: Info, row: 'text-info', badge: 'neutral' },
};

function WarningRow({ warning }: { warning: StaffWarning }) {
  const [open, setOpen] = useState(false);
  const tone = TONE[warning.severity];
  const Icon = tone.icon;
  return (
    <li className="py-2.5 first:pt-0 last:pb-0">
      <div className="flex items-start gap-3">
        <Icon className={cn('mt-0.5 size-4 shrink-0', tone.row)} aria-hidden="true" />
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            {warning.href ? (
              <Link href={warning.href} className="font-medium text-ink hover:text-action">
                {warning.label}
              </Link>
            ) : (
              <span className="font-medium text-ink">{warning.label}</span>
            )}
            <Badge variant={tone.badge}>{warning.count}</Badge>
          </div>
          {warning.items.length > 0 ? (
            <button
              type="button"
              className="mt-1 inline-flex items-center gap-1 text-xs text-ink-muted hover:text-ink"
              onClick={() => setOpen((value) => !value)}
              aria-expanded={open}
            >
              {open ? 'Hide' : 'Show'} {Math.min(warning.items.length, warning.count)} of{' '}
              {warning.count}
              {open ? (
                <ChevronUp className="size-3" aria-hidden="true" />
              ) : (
                <ChevronDown className="size-3" aria-hidden="true" />
              )}
            </button>
          ) : null}
          {open ? (
            <ul className="mt-1.5 space-y-1 text-sm">
              {warning.items.map((item) => (
                <li key={`${item.href}-${item.label}`}>
                  {item.href ? (
                    <Link href={item.href} className="text-ink-muted hover:text-action">
                      {item.label}
                    </Link>
                  ) : (
                    <span className="text-ink-muted">{item.label}</span>
                  )}
                </li>
              ))}
            </ul>
          ) : null}
        </div>
      </div>
    </li>
  );
}

export function WarningsStrip({ className }: { className?: string }) {
  const { data, error, isLoading, reload } = useApi<StaffWarning[]>('/api/v1/warnings/');
  const errors = data?.filter((warning) => warning.severity === 'error').length ?? 0;

  return (
    <Card className={cn('', className)} data-testid="warnings-strip">
      <CardHeader className="flex-row items-start justify-between gap-3">
        <div className="space-y-1">
          <CardTitle className="flex items-center gap-2">
            {data && data.length === 0 ? (
              <ShieldCheck className="size-5 text-success" aria-hidden="true" />
            ) : (
              <AlertTriangle className="size-5 text-warning" aria-hidden="true" />
            )}
            Needs attention
          </CardTitle>
          <CardDescription>
            {data === null && !error
              ? 'Checking…'
              : data && data.length === 0
                ? 'Nothing is waiting on you.'
                : `${data?.length ?? 0} ${data?.length === 1 ? 'thing' : 'things'} to look at${errors ? `, ${errors} today` : ''}.`}
          </CardDescription>
        </div>
      </CardHeader>
      <CardContent>
        {error ? (
          <ErrorState
            title="Could not check"
            message={error.message}
            requestId={error.requestId || undefined}
            onRetry={reload}
          />
        ) : isLoading || data === null ? (
          <div className="space-y-2">
            <Skeleton className="h-4 w-2/3" />
            <Skeleton className="h-4 w-1/2" />
          </div>
        ) : data.length === 0 ? null : (
          <ul className="divide-y divide-line">
            {data.map((warning) => (
              <WarningRow key={warning.kind} warning={warning} />
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}
