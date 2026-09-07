'use client';

/**
 * A short, supplementary label shown on hover or keyboard focus — the name
 * behind an icon-only button, the full value behind a truncated cell.
 *
 * Showing is delayed; hiding is not. That is deliberately asymmetric, which
 * is why this reaches for a plain `setTimeout` instead of the existing
 * `useDebouncedValue` hook — that hook delays *every* change by the same
 * amount in both directions, and a tooltip that lingers for 300ms after the
 * pointer has already left reads as unresponsive. The delay only guards
 * against a mouse passing *over* the trigger on its way somewhere else;
 * keyboard focus shows it immediately, because there is no equivalent
 * "passing through" for a Tab press.
 *
 * `aria-describedby` has to live on the trigger element itself, not a
 * wrapping `<span>`, for a screen reader to pick it up — so the single child
 * is cloned to add it, the same `React.isValidElement` guard `field.tsx`
 * uses for the same reason. The hover/focus handlers, which don't have that
 * constraint, stay on the wrapper: React's synthetic `onMouseEnter`/
 * `onFocus` already fire correctly for the whole subtree underneath it.
 */
import * as React from 'react';

import { usePresence } from '@/hooks/use-presence';
import { cn } from '@/lib/utils';

const OPEN_DELAY_MS = 300;
const EXIT_DURATION_MS = 90; // mirrors --duration-instant, the reverse of --duration-quick below

export interface TooltipProps {
  content: React.ReactNode;
  children: React.ReactElement;
  side?: 'top' | 'bottom';
  className?: string;
}

export function Tooltip({ content, children, side = 'top', className }: TooltipProps) {
  const [open, setOpen] = React.useState(false);
  const mounted = usePresence(open, EXIT_DURATION_MS);
  const showTimer = React.useRef<ReturnType<typeof setTimeout> | null>(null);
  const id = React.useId();

  function scheduleShow() {
    if (showTimer.current) clearTimeout(showTimer.current);
    showTimer.current = setTimeout(() => setOpen(true), OPEN_DELAY_MS);
  }

  function hideNow() {
    if (showTimer.current) clearTimeout(showTimer.current);
    setOpen(false);
  }

  React.useEffect(() => () => {
    if (showTimer.current) clearTimeout(showTimer.current);
  }, []);

  const trigger = React.isValidElement(children)
    ? React.cloneElement(children as React.ReactElement<Record<string, unknown>>, {
        'aria-describedby': open ? id : undefined,
      })
    : children;

  return (
    <span
      className="relative inline-block"
      onMouseEnter={scheduleShow}
      onMouseLeave={hideNow}
      onFocus={() => setOpen(true)}
      onBlur={hideNow}
      onKeyDown={(event: React.KeyboardEvent) => {
        if (event.key === 'Escape') hideNow();
      }}
    >
      {trigger}
      {mounted ? (
        <span
          role="tooltip"
          id={id}
          className={cn(
            'pointer-events-none absolute z-50 whitespace-nowrap rounded-md bg-foreground px-2 py-1 text-xs text-surface shadow-md',
            side === 'top' ? 'bottom-full left-1/2 -translate-x-1/2 mb-1.5' : 'top-full left-1/2 -translate-x-1/2 mt-1.5',
            className,
          )}
          style={{
            // A quicker fade than `.animate-fade-in`'s built-in --duration-base:
            // the utility class is tuned for a modal-sized surface, and 220ms
            // for two words of hint text reads as sluggish rather than smooth.
            animation: open
              ? 'fade-in var(--duration-quick) var(--ease-out-quick) both'
              : `fade-in ${EXIT_DURATION_MS}ms var(--ease-out-quick) reverse both`,
          }}
        >
          {content}
        </span>
      ) : null}
    </span>
  );
}
