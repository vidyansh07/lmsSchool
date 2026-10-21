'use client';

/**
 * The header button that opens what needs doing.
 *
 * These warnings used to be a card on five dashboards. It is a tall card —
 * nine kinds, each with its own expander — and it sat above the figures people
 * opened those dashboards to read. Pushing the day's work below the fold to
 * show a list that is usually unchanged since yesterday is a poor trade, and
 * paying for it five times over is worse.
 *
 * So it is one button, in the header, on every page rather than only on the
 * five that happened to mount the card. It carries the count, so the thing the
 * card was really for — noticing that something needs doing — survives
 * without the height.
 *
 * The button is absent when there is nothing to show. A permanent zero is
 * furniture: people stop seeing it, and then they stop seeing it when it is
 * not zero. It is also absent for a student, not because this checks their
 * role but because the endpoint refuses them and the list stays empty — the
 * server's refusal is the authority.
 */

import Link from 'next/link';
import { ArrowRight, TriangleAlert } from 'lucide-react';
import { useState } from 'react';

import { ErrorState } from '@/components/states';
import { Button } from '@/components/ui/button';
import {
  Sheet,
  SheetContent,
  SheetFooter,
  SheetHeader,
  SheetTitle,
} from '@/components/ui/sheet';
import { Skeleton } from '@/components/ui/skeleton';
import { Tooltip } from '@/components/ui/tooltip';
import { WarningsList, useWarnings } from '@/components/warnings-strip';
import { cn } from '@/lib/utils';

export function WarningsButton() {
  const [open, setOpen] = useState(false);
  const { warnings, error, isLoading, reload, urgent } = useWarnings();

  // Nothing to say, and no reason to take up header space saying it.
  if (!error && warnings.length === 0) return null;

  const label = error
    ? 'What needs attention — could not check'
    : `What needs attention — ${warnings.length} ${warnings.length === 1 ? 'thing' : 'things'}${
        urgent ? `, ${urgent} today` : ''
      }`;

  return (
    <>
      <Tooltip content="What needs attention">
        <Button
          variant="ghost"
          size="sm"
          onClick={() => setOpen(true)}
          aria-label={label}
          className="relative size-9 p-0 text-ink-muted"
        >
          <TriangleAlert className="size-[18px]" aria-hidden="true" />
          {warnings.length > 0 ? (
            // The count rides on the icon rather than sitting beside it, so the
            // header's spacing does not change as the number does.
            <span
              aria-hidden="true"
              className={cn(
                'absolute -right-0.5 -top-0.5 min-w-4 rounded-full px-1 text-[0.625rem] font-semibold leading-4',
                urgent > 0 ? 'bg-danger text-danger-fg' : 'bg-warning text-warning-fg',
              )}
            >
              {warnings.length > 9 ? '9+' : warnings.length}
            </span>
          ) : null}
        </Button>
      </Tooltip>

      <Sheet open={open} onOpenChange={setOpen}>
        <SheetContent size="lg">
          <SheetHeader>
            <SheetTitle>Needs attention</SheetTitle>
          </SheetHeader>
          <div className="min-h-0 flex-1 overflow-y-auto px-4 pb-2">
            {error ? (
              <ErrorState
                title="Could not check"
                message={error.message}
                requestId={error.requestId || undefined}
                onRetry={reload}
              />
            ) : isLoading ? (
              <div className="space-y-2 py-2">
                <Skeleton className="h-4 w-2/3" />
                <Skeleton className="h-4 w-1/2" />
              </div>
            ) : (
              <WarningsList warnings={warnings} />
            )}
          </div>
          <SheetFooter>
            {/* The panel shows the kinds; the page groups them by urgency and
                says what each one means. */}
            <Button asChild variant="outline" size="sm" className="gap-1.5">
              <Link href="/needs-attention" onClick={() => setOpen(false)}>
                See all, with what each means
                <ArrowRight className="size-3.5" aria-hidden="true" />
              </Link>
            </Button>
          </SheetFooter>
        </SheetContent>
      </Sheet>
    </>
  );
}
