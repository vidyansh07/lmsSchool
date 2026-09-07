'use client';

/**
 * The bin's landing view: every kind of record currently holding a deletion,
 * and how many.
 *
 * Built on `DataTable` rather than a bespoke card grid, on the same reasoning
 * `RecoveryBin`'s own docstring gives for the drill-down table: this is still
 * an operational list somebody scans and picks a row from, and reusing the
 * one table component the rest of the app already knows (keyboard row
 * navigation, a working empty/error/loading contract) beats a second,
 * one-off "list of things to click" built just for this screen. There is no
 * pagination here because there is nothing to paginate — `listRecoveryKinds`
 * returns the whole, short list in one response, already stripped of any
 * kind with nothing deleted in it.
 */
import { DataTable, type DataTableColumn } from '@/components/data-table';
import { formatNumber } from '@/lib/format';
import type { BinSummary } from '@/lib/recovery';

export function RecoveryKindList({
  kinds,
  isLoading,
  error,
  onRetry,
  onSelect,
}: {
  kinds: BinSummary[];
  isLoading: boolean;
  error?: { message: string; requestId?: string } | null;
  onRetry?: () => void;
  onSelect: (kind: BinSummary) => void;
}) {
  const columns: DataTableColumn<BinSummary>[] = [
    {
      key: 'verbose_name',
      header: 'Kind',
      render: (row) => <span className="font-medium capitalize">{row.verbose_name}</span>,
    },
    {
      key: 'deleted_count',
      header: 'Deleted records',
      align: 'right',
      render: (row) => <span className="tabular-nums">{formatNumber(row.deleted_count)}</span>,
    },
  ];

  return (
    <DataTable
      columns={columns}
      rows={kinds}
      getRowId={(row) => row.label}
      isLoading={isLoading}
      error={error}
      onRetry={onRetry}
      emptyTitle="The bin is empty"
      emptyDescription="Nothing anywhere in the system is currently deleted."
      onRowActivate={onSelect}
      caption="Kinds of deleted record"
      densityStorageKey="grras.recovery-kinds-density"
    />
  );
}
