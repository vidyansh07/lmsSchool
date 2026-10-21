'use client';

/**
 * What needs doing: the rows, and the number on the button that opens them.
 *
 * This used to be a card on five dashboards. It is a tall card — nine kinds,
 * each with an expander — and it sat above the figures people actually opened
 * those dashboards to read, on every one of them. Pushing the day's work below
 * the fold to show a list that is usually unchanged is a poor trade.
 *
 * So the rows live in a panel now, opened from one button in the header that
 * carries the count, and the full list has its own page. Nothing about the
 * data changed: each line is still computed by the server over what the caller
 * can see, with a count, a place to fix it, and the first few names on demand.
 */

import { useState } from 'react';
import Link from 'next/link';
import {
  AlertOctagon,
  AlertTriangle,
  ChevronDown,
  ChevronUp,
  Info,
  ShieldCheck,
} from 'lucide-react';

import { Badge } from '@/components/ui/badge';
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
  // A severity this file does not know reads as informational rather than
  // taking down the five dashboards that mount this strip.
  const tone = TONE[warning.severity] ?? TONE.info;
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

/**
 * The rows alone, with no card around them.
 *
 * Takes its data as a prop rather than fetching: the button that opens this
 * panel already needs the count, and two components fetching the same endpoint
 * a moment apart is two queries and two chances to disagree.
 */
export function WarningsList({ warnings }: { warnings: StaffWarning[] }) {
  if (warnings.length === 0) {
    return (
      <div className="flex flex-col items-center gap-2 py-8 text-center">
        <ShieldCheck className="size-7 text-success" aria-hidden="true" />
        <p className="text-sm font-medium text-ink">Nothing is waiting on you.</p>
      </div>
    );
  }
  return (
    <ul className="divide-y divide-line">
      {warnings.map((warning) => (
        <WarningRow key={warning.kind} warning={warning} />
      ))}
    </ul>
  );
}

/**
 * One fetch of `/warnings/`, shared by the button and the panel it opens.
 *
 * A student is refused this endpoint outright, so `warnings` stays empty for
 * them and the button never appears — the refusal is the authority, and this
 * does not try to second-guess it by checking a role.
 */
export function useWarnings() {
  const { data, error, isLoading, reload } = useApi<StaffWarning[]>('/api/v1/warnings/');
  const warnings = data ?? [];
  return {
    warnings,
    error,
    isLoading,
    reload,
    urgent: warnings.filter((warning) => warning.severity === 'error').length,
  };
}
