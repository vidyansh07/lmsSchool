import * as React from 'react';

import { cn } from '@/lib/utils';

/**
 * Table primitives.
 *
 * The wrapper scrolls horizontally on its own so a wide table never forces the
 * whole page sideways on a phone.
 */
export function TableWrapper({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn(
        'w-full overflow-x-auto rounded-[var(--radius-card)] border border-border bg-surface shadow-[var(--shadow-card)]',
        className,
      )}
      {...props}
    />
  );
}

export function Table({ className, ...props }: React.TableHTMLAttributes<HTMLTableElement>) {
  return <table className={cn('w-full min-w-[42rem] text-sm', className)} {...props} />;
}

export function Th({
  className,
  sortable,
  active,
  direction,
  onSort,
  children,
  ...props
}: React.ThHTMLAttributes<HTMLTableCellElement> & {
  sortable?: boolean;
  active?: boolean;
  direction?: 'asc' | 'desc';
  onSort?: () => void;
}) {
  return (
    <th
      scope="col"
      aria-sort={active ? (direction === 'asc' ? 'ascending' : 'descending') : undefined}
      className={cn(
        // Small caps and tracking, as in the reference: a header that is
        // visibly a different *kind* of text from the rows needs no heavy
        // fill to separate itself.
        'border-b border-border bg-surface px-4 py-3 text-left text-2xs font-semibold uppercase tracking-[0.08em] text-muted-foreground whitespace-nowrap',
        className,
      )}
      {...props}
    >
      {sortable ? (
        <button
          type="button"
          onClick={onSort}
          // `uppercase` again, on purpose: Tailwind's preflight resets
          // `text-transform` on buttons, so the header's own small-caps do not
          // reach a sortable heading and it came out in sentence case beside
          // its uppercase neighbours.
          className="inline-flex items-center gap-1 uppercase tracking-[0.08em] hover:text-primary"
        >
          {children}
          <span aria-hidden="true" className="text-xs">
            {active ? (direction === 'asc' ? '▲' : '▼') : '↕'}
          </span>
        </button>
      ) : (
        children
      )}
    </th>
  );
}

/** A row that lights on hover, with the transition the rest of the product
 *  uses. Opt-in via the primitive so a static table stays static. */
export function Tr({ className, ...props }: React.HTMLAttributes<HTMLTableRowElement>) {
  return (
    <tr
      className={cn(
        'transition-colors duration-[var(--duration-quick)] hover:bg-muted',
        className,
      )}
      {...props}
    />
  );
}

export function Td({ className, ...props }: React.TdHTMLAttributes<HTMLTableCellElement>) {
  return <td className={cn('border-b border-border px-4 py-3 align-middle', className)} {...props} />;
}
