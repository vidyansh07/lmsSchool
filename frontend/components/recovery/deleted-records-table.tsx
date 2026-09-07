'use client';

/**
 * One kind's deleted records — the bin's drill-down, and the only place
 * restore and purge actually happen.
 *
 * The fetcher is bound to `label` with `useCallback` before it reaches
 * `useList`, the same adapter `BatchRoster` uses to bind its own fetcher to
 * `batchId` — `useList` expects a stable `(query) => Promise<Paginated<T>>`
 * with no kind of its own to thread through. That alone does not cover a
 * `label` changing while this component stays mounted, since `useList`'s
 * refetch keys off `query`/page state, not the fetcher's identity — so the
 * caller (`RecoveryBin`) renders this with `key={label}`, forcing a clean
 * remount (fresh page 1, no leftover state from the previous kind) whenever
 * a different kind is chosen, rather than this component trying to detect
 * and reset that transition itself.
 *
 * Restore and purge are visually and behaviourally lopsided on purpose: one
 * inline button next to a dialog-gated, reason-demanding control that does
 * not even render for someone lacking `record.purge` — see
 * `components/recovery/purge-control.tsx` for that half. Both funnel their
 * success back through `onChanged` as well as `list.reload()`, because a
 * restore or a purge changes not just this table's rows but the count on the
 * kind this record belongs to, which only the parent (holding the kind list)
 * can refresh.
 */
import { useCallback, useState } from 'react';
import { RotateCcw } from 'lucide-react';

import { useAuth } from '@/components/auth-provider';
import { DataTable, type DataTableColumn } from '@/components/data-table';
import { Pagination } from '@/components/pagination';
import { PurgeControl } from '@/components/recovery/purge-control';
import { Alert } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import { useList } from '@/hooks/use-list';
import { ApiError } from '@/lib/api';
import { Capability } from '@/lib/capabilities';
import { fallback, formatDateTime, NO_DATA, UNKNOWN } from '@/lib/format';
import type { ListQuery } from '@/lib/people';
import { listDeletedRecords, restoreRecord, type DeletedRecord } from '@/lib/recovery';

export function DeletedRecordsTable({ label, onChanged }: { label: string; onChanged: () => void }) {
  const { can } = useAuth();
  const fetcher = useCallback((query: ListQuery) => listDeletedRecords(label, query), [label]);
  const list = useList<DeletedRecord>(fetcher, { page_size: 20 });
  const [busyId, setBusyId] = useState<string | null>(null);
  const [rowErrors, setRowErrors] = useState<Record<string, string>>({});

  async function restore(row: DeletedRecord) {
    setBusyId(row.id);
    setRowErrors((current) => ({ ...current, [row.id]: '' }));
    try {
      await restoreRecord(label, row.id);
      list.reload();
      onChanged();
    } catch (cause) {
      setRowErrors((current) => ({
        ...current,
        [row.id]: cause instanceof ApiError ? cause.message : 'Could not restore this record. Please try again.',
      }));
    } finally {
      setBusyId(null);
    }
  }

  function purged() {
    list.reload();
    onChanged();
  }

  const columns: DataTableColumn<DeletedRecord>[] = [
    {
      key: 'describes',
      header: 'Record',
      render: (row) => <span className="font-medium">{fallback(row.describes, NO_DATA)}</span>,
    },
    {
      key: 'deleted_at',
      header: 'Deleted',
      render: (row) => formatDateTime(row.deleted_at),
    },
    {
      key: 'deleted_by',
      header: 'Deleted by',
      render: (row) => fallback(row.deleted_by, UNKNOWN),
    },
    {
      key: 'delete_reason',
      header: 'Reason',
      render: (row) => (
        <span className="block max-w-[18rem] truncate" title={row.delete_reason || undefined}>
          {fallback(row.delete_reason, NO_DATA)}
        </span>
      ),
    },
    {
      key: 'actions',
      header: 'Actions',
      render: (row) => (
        <div className="flex flex-wrap items-start gap-2">
          <div className="space-y-1">
            {can(Capability.recordRestore) ? (
              <Button
                type="button"
                variant="outline"
                size="sm"
                disabled={busyId === row.id}
                onClick={() => void restore(row)}
              >
                <RotateCcw className="size-3.5" aria-hidden="true" />
                {busyId === row.id ? 'Restoring…' : 'Restore'}
              </Button>
            ) : null}
            {rowErrors[row.id] ? (
              <Alert variant="error" className="w-48 p-2 text-xs">
                {rowErrors[row.id]}
              </Alert>
            ) : null}
          </div>
          <PurgeControl record={row} onPurged={purged} />
        </div>
      ),
    },
  ];

  return (
    <div className="space-y-4">
      <DataTable
        columns={columns}
        rows={list.data?.results ?? []}
        getRowId={(row) => row.id}
        isLoading={list.isLoading}
        error={list.error ? { message: list.error.message, requestId: list.error.requestId } : null}
        onRetry={list.reload}
        emptyTitle="Nothing deleted of this kind"
        emptyDescription="Every record of this kind is either active, or has already been restored or destroyed."
        caption="Deleted records"
        densityStorageKey="grras.recovery-records-density"
      />
      {list.data ? (
        <Pagination
          page={list.data.page}
          totalPages={list.data.total_pages}
          count={list.data.count}
          pageSize={list.data.page_size}
          onPageChange={list.setPage}
        />
      ) : null}
    </div>
  );
}
