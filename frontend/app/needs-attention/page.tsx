'use client';

/**
 * Everything waiting on you, in full.
 *
 * The dashboard strip is a glance: a line per kind, a count, and the first few
 * names folded away behind "show". That is right for a card sharing a screen
 * with six others, and it is the wrong shape for actually working through the
 * list — which is what somebody does at the start of a day.
 *
 * So this is the same data with room to breathe. Three differences, each one
 * the reason the page exists rather than a prettier strip:
 *
 * - **Grouped by when.** `error` is today, `warning` is this week, `info` is
 *   worth knowing. The strip sorts by urgency and still reads as one list, so
 *   the eye has to do the grouping. Here the headings do it.
 * - **Each kind says what it means.** The strip has a label and a number. "12
 *   batches overrun" tells somebody who already knows the system what to do
 *   and tells a new administrator nothing. The wording comes from the server,
 *   beside the rule that produces it.
 * - **The names are shown, not hidden.** No expand step: if there are five
 *   students at risk, they are on the page.
 *
 * Nothing is computed here. Every warning, every count and every link is what
 * `/warnings/` returned, over the caller's own visible querysets — a manager
 * sees their centre, a trainer their own classes.
 */

import Link from 'next/link';
import {
  AlertOctagon,
  AlertTriangle,
  ArrowRight,
  Info,
  ShieldCheck,
} from 'lucide-react';

import { RequireAuth } from '@/components/require-auth';
import { ErrorState } from '@/components/states';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { useApi } from '@/hooks/use-api';
import { cn } from '@/lib/utils';
import type { StaffWarning, WarningSeverity } from '@/types/api';

const TONE: Record<
  WarningSeverity,
  {
    icon: typeof Info;
    accent: string;
    badge: 'error' | 'warning' | 'neutral';
  }
> = {
  error: { icon: AlertOctagon, accent: 'text-danger', badge: 'error' },
  warning: { icon: AlertTriangle, accent: 'text-warning', badge: 'warning' },
  info: { icon: Info, accent: 'text-info', badge: 'neutral' },
};

/** The three groups, in the order a day is worked through. */
const GROUPS: { severity: WarningSeverity; title: string; blurb: string }[] = [
  { severity: 'error', title: 'Today', blurb: 'Left any longer, these cost something.' },
  { severity: 'warning', title: 'This week', blurb: 'Not urgent yet. They become urgent.' },
  { severity: 'info', title: 'Worth knowing', blurb: 'Nothing is broken; these are loose ends.' },
];

function WarningCard({ warning }: { warning: StaffWarning }) {
  // A severity this page does not know reads as informational rather than
  // taking down the whole list — the same rule the strip follows.
  const tone = TONE[warning.severity] ?? TONE.info;
  const Icon = tone.icon;

  return (
    <Card>
      <CardHeader className="gap-2 pb-3">
        <div className="flex items-start justify-between gap-3">
          <CardTitle as="h3" className="flex min-w-0 items-start gap-2 text-base">
            <Icon className={cn('mt-0.5 size-4 shrink-0', tone.accent)} aria-hidden="true" />
            <span className="min-w-0">{warning.label}</span>
          </CardTitle>
          <Badge variant={tone.badge} className="shrink-0">
            {warning.count}
          </Badge>
        </div>
        {warning.explanation ? (
          <p className="text-sm text-ink-muted">{warning.explanation}</p>
        ) : null}
      </CardHeader>
      <CardContent className="space-y-3">
        {warning.items.length > 0 ? (
          <ul className="space-y-1 text-sm">
            {warning.items.map((item) => (
              <li key={`${item.href}-${item.label}`} className="truncate">
                {item.href ? (
                  <Link
                    href={item.href}
                    className="text-ink-muted underline-offset-2 hover:text-action hover:underline"
                  >
                    {item.label}
                  </Link>
                ) : (
                  <span className="text-ink-muted">{item.label}</span>
                )}
              </li>
            ))}
            {warning.count > warning.items.length ? (
              // Said plainly rather than quietly truncated: somebody counting
              // names against the badge should not have to wonder.
              <li className="text-ink-faint">
                and {warning.count - warning.items.length} more
              </li>
            ) : null}
          </ul>
        ) : null}
        {warning.href ? (
          <Button asChild variant="outline" size="sm" className="gap-1.5">
            <Link href={warning.href}>
              Go and fix this
              <ArrowRight className="size-3.5" aria-hidden="true" />
            </Link>
          </Button>
        ) : null}
      </CardContent>
    </Card>
  );
}

function NeedsAttention() {
  const { data, error, isLoading, reload } = useApi<StaffWarning[]>('/api/v1/warnings/');

  const grouped = GROUPS.map((group) => ({
    ...group,
    warnings: (data ?? []).filter((warning) => warning.severity === group.severity),
  })).filter((group) => group.warnings.length > 0);

  // Anything with a severity none of the three groups claims still has to
  // appear. A warning nobody shows is worse than one shown under the wrong
  // heading.
  const known = new Set(GROUPS.map((group) => group.severity as string));
  const other = (data ?? []).filter((warning) => !known.has(warning.severity));

  return (
    <div className="space-y-6">
      <div className="space-y-1">
        <h1 className="text-2xl font-semibold tracking-tight">Needs attention</h1>
        <p className="text-sm text-ink-muted">
          Everything waiting on you, grouped by how soon it matters. Only what you
          can already see.
        </p>
      </div>

      {error ? (
        <ErrorState
          title="Could not check"
          message={error.message}
          requestId={error.requestId || undefined}
          onRetry={reload}
        />
      ) : isLoading || data === null ? (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {Array.from({ length: 3 }, (_, index) => (
            <Card key={index}>
              <CardHeader className="gap-2 pb-3">
                <Skeleton className="h-5 w-2/3" />
                <Skeleton className="h-4 w-full" />
              </CardHeader>
              <CardContent>
                <Skeleton className="h-4 w-1/2" />
              </CardContent>
            </Card>
          ))}
        </div>
      ) : data.length === 0 ? (
        <Card>
          <CardContent className="flex flex-col items-center gap-3 py-12 text-center">
            <ShieldCheck className="size-8 text-success" aria-hidden="true" />
            <div className="space-y-1">
              <p className="font-medium text-ink">Nothing is waiting on you.</p>
              <p className="text-sm text-ink-muted">
                Fees, classes, reports and accounts are all where they should be.
              </p>
            </div>
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-8">
          {grouped.map((group) => (
            <section key={group.severity} className="space-y-3">
              <div className="space-y-0.5">
                <h2 className="text-sm font-semibold uppercase tracking-[0.12em] text-ink-faint">
                  {group.title}
                </h2>
                <p className="text-sm text-ink-muted">{group.blurb}</p>
              </div>
              <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
                {group.warnings.map((warning) => (
                  <WarningCard key={warning.kind} warning={warning} />
                ))}
              </div>
            </section>
          ))}
          {other.length > 0 ? (
            <section className="space-y-3">
              <h2 className="text-sm font-semibold uppercase tracking-[0.12em] text-ink-faint">
                Other
              </h2>
              <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
                {other.map((warning) => (
                  <WarningCard key={warning.kind} warning={warning} />
                ))}
              </div>
            </section>
          ) : null}
        </div>
      )}
    </div>
  );
}

export default function NeedsAttentionPage() {
  // No capability of its own: the endpoint computes over what the caller can
  // already see and refuses students outright, so any staff member has
  // something true to be shown here.
  return (
    <RequireAuth>
      <NeedsAttention />
    </RequireAuth>
  );
}
