'use client';

/**
 * The bar that appears once a row is selected, offering actions across the
 * whole selection at once instead of one row at a time.
 *
 * The one thing this component exists to get right: "every row on this page"
 * and "every row this filter matches" are different sets that can differ by
 * orders of magnitude, and confusing them is how somebody means to archive
 * the 20 rows in front of them and instead archives all 4,000 that match the
 * filter. So the bar always states which one is active in plain words, and
 * "select all matching" is a distinct, deliberate second step — never the
 * silent behaviour of a page-level checkbox.
 */
import { AlertTriangle } from 'lucide-react';

import { Button, type ButtonProps } from '@/components/ui/button';
import { formatCount } from '@/lib/format';
import { cn } from '@/lib/utils';

export interface BulkAction {
  id: string;
  label: string;
  onClick: () => void;
  variant?: ButtonProps['variant'];
  disabled?: boolean;
}

export function BulkActionsBar({
  selectedCount,
  totalMatchingCount,
  selectAllMatching,
  onSelectAllMatching,
  onClear,
  actions,
  itemNoun = 'row',
  className,
}: {
  /** Rows individually selected (from the current page, typically). */
  selectedCount: number;
  /** How many rows the active filter matches in total, if known — enables "select all matching". */
  totalMatchingCount?: number;
  /** Whether "select all matching the filter" (rather than just the page) is active. */
  selectAllMatching?: boolean;
  onSelectAllMatching?: () => void;
  onClear: () => void;
  actions: BulkAction[];
  itemNoun?: string;
  className?: string;
}) {
  if (selectedCount === 0 && !selectAllMatching) return null;

  const canOfferSelectAll =
    !selectAllMatching &&
    onSelectAllMatching &&
    typeof totalMatchingCount === 'number' &&
    totalMatchingCount > selectedCount;

  return (
    <div
      role="region"
      aria-label="Bulk actions"
      className={cn(
        'flex flex-wrap items-center gap-3 rounded-[var(--radius-card)] border border-primary/30 bg-accent px-4 py-3 text-sm',
        className,
      )}
    >
      <p aria-live="polite" className="font-medium">
        {selectAllMatching
          ? `All ${formatCount(totalMatchingCount ?? selectedCount, itemNoun)} matching the current filter are selected`
          : `${formatCount(selectedCount, itemNoun)} selected`}
      </p>

      {canOfferSelectAll ? (
        <button
          type="button"
          onClick={onSelectAllMatching}
          className="text-primary underline-offset-2 hover:underline"
        >
          Select all {totalMatchingCount} matching this filter
        </button>
      ) : null}

      {selectAllMatching ? (
        <span className="inline-flex items-center gap-1 text-xs text-warning">
          <AlertTriangle className="size-3.5" aria-hidden="true" />
          Actions below apply to every matching row, not just this page
        </span>
      ) : null}

      <div className="ml-auto flex flex-wrap items-center gap-2">
        {actions.map((action) => (
          <Button
            key={action.id}
            size="sm"
            variant={action.variant ?? 'outline'}
            disabled={action.disabled}
            onClick={action.onClick}
          >
            {action.label}
          </Button>
        ))}
        <Button size="sm" variant="ghost" onClick={onClear}>
          Clear selection
        </Button>
      </div>
    </div>
  );
}
