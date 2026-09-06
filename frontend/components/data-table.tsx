'use client';

/**
 * The workhorse of every operational screen: a server-paginated, keyboard-
 * operable table. Most of this app's real work happens in a list of rows,
 * not a dashboard tile, so this is the component the "speed" half of the
 * brief is really about.
 *
 * A few things worth explaining rather than discovering by reading the JSX:
 *
 * - `sort` and `onSortChange` are typed to match `use-list.ts`'s `query.ordering`
 *   and `toggleSort` exactly (a plain field name, optionally `-`-prefixed for
 *   descending) so a screen already using `useList` wires this table up with
 *   no adapter in between.
 * - Sticky columns are deliberately capped at one leading and one trailing
 *   column. A table with several independently sticky columns needs to solve
 *   cumulative offsets from unknown rendered widths, which is a real feature
 *   but not one any screen in this app has asked for yet — "the identity
 *   column" and "the action column" is the actual shape of every table here.
 * - Keyboard row navigation uses a roving `tabIndex` (one row is `0`, the rest
 *   are `-1`) rather than focusing every `<tr>`: it is the standard pattern
 *   for keyboard-navigable composite widgets and it means Tab moves *past*
 *   the table in one step instead of through every row.
 * - The density toggle reads and writes `localStorage` inside try/catch: a
 *   private browsing window throws on access, and a table that cannot
 *   remember a viewer's preference should still render, not crash.
 */
import {
  useEffect,
  useMemo,
  useRef,
  useState,
  type KeyboardEvent as ReactKeyboardEvent,
  type ReactNode,
} from 'react';
import { Rows3, Rows4 } from 'lucide-react';

import type { UseBulkSelectionResult } from '@/hooks/use-bulk-selection';
import { EmptyState, ErrorState } from '@/components/states';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import { Table, TableWrapper, Td, Th } from '@/components/ui/table';
import { cn } from '@/lib/utils';

export type DataTableAlign = 'left' | 'right' | 'center';
export type DataTableDensity = 'comfortable' | 'compact';

export interface DataTableColumn<Row> {
  /** Also the sort field sent to `onSortChange`, and the React key for the column. */
  key: string;
  header: string;
  align?: DataTableAlign;
  sortable?: boolean;
  /** Pins this column to the left or right edge of the scroll area. At most
   *  one column of each may be sticky — see the module docstring. */
  sticky?: 'start' | 'end';
  render: (row: Row) => ReactNode;
  /** A CSS width, e.g. `"12rem"`. Columns without one size to their content. */
  width?: string;
}

const ALIGN_CLASS: Record<DataTableAlign, string> = {
  left: 'text-left',
  right: 'text-right',
  center: 'text-center',
};

const DEFAULT_DENSITY_STORAGE_KEY = 'grras.data-table-density';

function readDensity(storageKey: string): DataTableDensity {
  try {
    const stored = window.localStorage.getItem(storageKey);
    return stored === 'compact' ? 'compact' : 'comfortable';
  } catch {
    return 'comfortable';
  }
}

function writeDensity(storageKey: string, density: DataTableDensity): void {
  try {
    window.localStorage.setItem(storageKey, density);
  } catch {
    // No persistence available (private window, storage disabled). The
    // toggle still works for the rest of this session.
  }
}

function HeaderCheckbox({
  state,
  onToggle,
  label,
}: {
  state: 'all' | 'some' | 'none';
  onToggle: () => void;
  label: string;
}) {
  const ref = useRef<HTMLInputElement>(null);
  useEffect(() => {
    if (ref.current) ref.current.indeterminate = state === 'some';
  }, [state]);

  return (
    <input
      ref={ref}
      type="checkbox"
      aria-label={label}
      checked={state === 'all'}
      onChange={onToggle}
      className="size-4 rounded border-border accent-primary"
    />
  );
}

export function DataTable<Row>({
  columns,
  rows,
  getRowId,
  isLoading = false,
  error,
  onRetry,
  emptyTitle = 'No results',
  emptyDescription,
  sort,
  onSortChange,
  selection,
  onRowActivate,
  densityStorageKey = DEFAULT_DENSITY_STORAGE_KEY,
  caption,
  className,
}: {
  columns: DataTableColumn<Row>[];
  rows: Row[];
  getRowId: (row: Row) => string;
  isLoading?: boolean;
  error?: { message: string; requestId?: string } | null;
  onRetry?: () => void;
  emptyTitle?: string;
  emptyDescription?: string;
  /** The active ordering, e.g. `"name"` or `"-name"` — matches `ListQuery.ordering`. */
  sort?: string;
  /** Matches `useList`'s `toggleSort`: called with the plain field name. */
  onSortChange?: (field: string) => void;
  /** Wire up `useBulkSelection` here to get header/row checkboxes and shift-click ranges. */
  selection?: UseBulkSelectionResult<string>;
  onRowActivate?: (row: Row) => void;
  /** `localStorage` key for the density preference. Share one across a family
   *  of tables, or give each screen its own — both are reasonable. */
  densityStorageKey?: string;
  caption?: string;
  className?: string;
}) {
  // A lazy initializer, not an effect: it runs once, during the first
  // render, which is the one place a "read an external value" like
  // `localStorage` is allowed to feed straight into state. The trade-off is
  // that a server-rendered shell cannot know the viewer's stored preference
  // (there is no `localStorage` on the server, so `readDensity` falls back to
  // `'comfortable'` there) — an acceptable one-time mismatch for a purely
  // cosmetic padding value, and one every "remembered UI preference" reading
  // from browser storage in a server-rendered app has to accept somewhere.
  const [density, setDensity] = useState<DataTableDensity>(() => readDensity(densityStorageKey));
  const [rawFocusedIndex, setFocusedIndex] = useState(0);
  const rowRefs = useRef<(HTMLTableRowElement | null)[]>([]);

  // Clamped during render (not an effect) when the row count shrinks out
  // from under the current focus — e.g. a filter now matches fewer rows.
  // Comparing state here, not a ref, is what makes this the sanctioned
  // "adjust state during render" pattern rather than a banned one.
  const focusedIndex = rows.length === 0 ? 0 : Math.min(rawFocusedIndex, rows.length - 1);
  if (focusedIndex !== rawFocusedIndex) {
    setFocusedIndex(focusedIndex);
  }

  function toggleDensity() {
    setDensity((current) => {
      const next = current === 'comfortable' ? 'compact' : 'comfortable';
      writeDensity(densityStorageKey, next);
      return next;
    });
  }

  const rowIds = useMemo(() => rows.map(getRowId), [rows, getRowId]);
  const cellPadding = density === 'compact' ? 'py-1' : 'py-2.5';

  function handleRowKeyDown(event: ReactKeyboardEvent<HTMLTableRowElement>, index: number) {
    if (event.key === 'ArrowDown') {
      event.preventDefault();
      const next = Math.min(index + 1, rows.length - 1);
      setFocusedIndex(next);
      rowRefs.current[next]?.focus();
    } else if (event.key === 'ArrowUp') {
      event.preventDefault();
      const previous = Math.max(index - 1, 0);
      setFocusedIndex(previous);
      rowRefs.current[previous]?.focus();
    } else if (event.key === 'Enter' && onRowActivate) {
      event.preventDefault();
      const row = rows[index];
      if (row !== undefined) onRowActivate(row);
    }
  }

  // Positioning only — the background colour is applied separately by the
  // header (opaque `bg-muted`, matching the rest of the header row) and body
  // cells (`bg-surface`, or `bg-accent` once selected), because a sticky cell
  // needs an opaque background to hide the content scrolling underneath it,
  // and that background differs between the two.
  //
  // A selection checkbox column, if present, always owns the left edge (at
  // `left-0`); a column marked `sticky: 'start'` sits immediately after it.
  function stickyPositionClass(column: DataTableColumn<Row>): string | undefined {
    if (column.sticky === 'start') return cn('sticky z-10', selection ? 'left-10' : 'left-0');
    if (column.sticky === 'end') return 'sticky right-0 z-10';
    return undefined;
  }

  return (
    <div className={cn('space-y-2', className)}>
      <div className="flex justify-end">
        <Button
          type="button"
          variant="ghost"
          size="sm"
          aria-pressed={density === 'compact'}
          onClick={toggleDensity}
          className="gap-1.5 text-xs text-muted-foreground"
        >
          {density === 'compact' ? (
            <Rows4 className="size-3.5" aria-hidden="true" />
          ) : (
            <Rows3 className="size-3.5" aria-hidden="true" />
          )}
          {density === 'compact' ? 'Comfortable' : 'Compact'} view
        </Button>
      </div>

      {error ? (
        <ErrorState message={error.message} requestId={error.requestId} onRetry={onRetry} />
      ) : !isLoading && rows.length === 0 ? (
        <EmptyState title={emptyTitle} description={emptyDescription} />
      ) : (
        <TableWrapper>
          <Table aria-busy={isLoading || undefined}>
            {caption ? <caption className="sr-only">{caption}</caption> : null}
            <thead>
              <tr>
                {selection ? (
                  <Th className={cn('sticky left-0 z-10 w-10 bg-muted', cellPadding)}>
                    <HeaderCheckbox
                      state={selection.pageSelectionState(rowIds)}
                      onToggle={() => selection.toggleAll(rowIds)}
                      label="Select all rows on this page"
                    />
                  </Th>
                ) : null}
                {columns.map((column) => {
                  const isActive = sort === column.key || sort === `-${column.key}`;
                  const direction = sort?.startsWith('-') ? 'desc' : 'asc';
                  return (
                    <Th
                      key={column.key}
                      style={column.width ? { width: column.width } : undefined}
                      sortable={column.sortable}
                      active={isActive}
                      direction={direction}
                      onSort={column.sortable ? () => onSortChange?.(column.key) : undefined}
                      className={cn(
                        ALIGN_CLASS[column.align ?? 'left'],
                        cellPadding,
                        column.sticky && 'bg-muted',
                        stickyPositionClass(column),
                      )}
                    >
                      {column.header}
                    </Th>
                  );
                })}
              </tr>
            </thead>
            <tbody>
              {isLoading
                ? Array.from({ length: 5 }, (_, index) => (
                    <tr key={index}>
                      {selection ? (
                        <Td className={cellPadding}>
                          <Skeleton className="size-4" />
                        </Td>
                      ) : null}
                      {columns.map((column) => (
                        <Td key={column.key} className={cellPadding}>
                          <Skeleton className="h-4 w-full max-w-[10rem]" />
                        </Td>
                      ))}
                    </tr>
                  ))
                : rows.map((row, index) => {
                    const rowId = rowIds[index] as string;
                    const isSelected = selection?.isSelected(rowId) ?? false;
                    return (
                      <tr
                        key={rowId}
                        ref={(node) => {
                          rowRefs.current[index] = node;
                        }}
                        tabIndex={focusedIndex === index ? 0 : -1}
                        aria-selected={selection ? isSelected : undefined}
                        onFocus={() => setFocusedIndex(index)}
                        onKeyDown={(event) => handleRowKeyDown(event, index)}
                        onClick={() => onRowActivate?.(row)}
                        className={cn(
                          'outline-none',
                          onRowActivate && 'cursor-pointer hover:bg-muted/60',
                          isSelected && 'bg-accent',
                          focusedIndex === index && 'ring-1 ring-inset ring-primary',
                        )}
                      >
                        {selection ? (
                          <Td
                            className={cn('sticky left-0 z-10 bg-surface', isSelected && 'bg-accent', cellPadding)}
                            onClick={(event) => event.stopPropagation()}
                          >
                            <input
                              type="checkbox"
                              aria-label="Select row"
                              checked={isSelected}
                              readOnly
                              // A native `onClick` carries `shiftKey` reliably;
                              // the `change` event's modifier state is not
                              // guaranteed across browsers, and shift-click
                              // range selection depends on it.
                              onClick={(event) => selection.toggle(rowId, index, rowIds, event.shiftKey)}
                              className="size-4 rounded border-border accent-primary"
                            />
                          </Td>
                        ) : null}
                        {columns.map((column) => (
                          <Td
                            key={column.key}
                            className={cn(
                              ALIGN_CLASS[column.align ?? 'left'],
                              cellPadding,
                              column.sticky && (isSelected ? 'bg-accent' : 'bg-surface'),
                              stickyPositionClass(column),
                            )}
                          >
                            {column.render(row)}
                          </Td>
                        ))}
                      </tr>
                    );
                  })}
            </tbody>
          </Table>
        </TableWrapper>
      )}
    </div>
  );
}
