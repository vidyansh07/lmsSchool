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
      className={cn('w-full overflow-x-auto rounded-[var(--radius-card)] border border-border', className)}
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
        'border-b border-border bg-muted/60 px-3 py-2 text-left font-medium whitespace-nowrap',
        className,
      )}
      {...props}
    >
      {sortable ? (
        <button
          type="button"
          onClick={onSort}
          className="inline-flex items-center gap-1 hover:text-primary"
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

export function Td({ className, ...props }: React.TdHTMLAttributes<HTMLTableCellElement>) {
  return <td className={cn('border-b border-border px-3 py-2 align-middle', className)} {...props} />;
}
