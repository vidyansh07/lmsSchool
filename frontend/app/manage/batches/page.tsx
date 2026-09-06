'use client';

/**
 * The manager's batches hub — §"two hub screens".
 *
 * Three layouts (exceptions-first, KPI-first, split-queue) were offered and
 * rejected in favour of this: one dense table that is the whole page, with a
 * KPI strip on top that summarises it rather than replacing it. Nothing here
 * is a widget a manager reads and moves on from — every row is one click from
 * the batch's full picture (`/manage/batches/[batchId]`), which is where the
 * actual review happens.
 *
 * Built on `DataTable` + `useList` exactly the way `admin/batches/page.tsx`
 * already does, because that pairing — server-driven search, filter, sort and
 * pagination in one hook — is precisely what this table needs and there is no
 * reason for a second implementation of it. What differs from the admin
 * table is the column set: this one is dense on purpose (kind, attendance,
 * plan variance, DSR state alongside the basics), because the whole point of
 * a manager's hub is not having to open a row to see whether it needs
 * attention. See `lib/manage.ts` for which of those columns are backed by
 * data today and which render an honest "No data" until the list endpoint
 * carries them.
 */
import Link from 'next/link';
import { useRouter } from 'next/navigation';

import { ManagerAttentionStrip } from '@/components/manage/attention-strip';
import { DataTable, type DataTableColumn } from '@/components/data-table';
import { ListToolbar } from '@/components/list-toolbar';
import { Pagination } from '@/components/pagination';
import { RequireAuth } from '@/components/require-auth';
import { Badge } from '@/components/ui/badge';
import { Select } from '@/components/ui/input';
import { useList } from '@/hooks/use-list';
import { BATCH_STATUS_LABEL, BATCH_STATUS_OPTIONS, BATCH_STATUS_VARIANT } from '@/lib/batch-labels';
import { Capability } from '@/lib/capabilities';
import { fallback, formatPercent, NOT_ASSIGNED, NO_DATA } from '@/lib/format';
import {
  DSR_STATUS_LABEL,
  DSR_STATUS_VARIANT,
  listManageBatches,
  TIMELINE_STATUS_LABEL,
  TIMELINE_STATUS_VARIANT,
  type DsrStatus,
  type ManageBatchRow,
} from '@/lib/manage';

function StudentsCell({ row }: { row: ManageBatchRow }) {
  return (
    <span className="tabular-nums">
      {row.enrolled_count} / {row.capacity}
      {row.seats_available === 0 ? (
        <Badge variant="warning" className="ml-2">
          Full
        </Badge>
      ) : null}
    </span>
  );
}

function KindCell({ row }: { row: ManageBatchRow }) {
  if (!row.kind) return <span className="text-muted-foreground">{fallback(null, NO_DATA)}</span>;
  const label = row.kind.replace(/_/g, ' ');
  return <Badge>{label.charAt(0).toUpperCase() + label.slice(1)}</Badge>;
}

function PlanVarianceCell({ row }: { row: ManageBatchRow }) {
  if (!row.timeline_status) return <span className="text-muted-foreground">{fallback(null, NO_DATA)}</span>;
  return (
    <Badge variant={TIMELINE_STATUS_VARIANT[row.timeline_status]}>
      {TIMELINE_STATUS_LABEL[row.timeline_status]}
    </Badge>
  );
}

function DsrStateCell({ row }: { row: ManageBatchRow }) {
  const known = row.dsr_state && row.dsr_state in DSR_STATUS_LABEL;
  if (!row.dsr_state) return <span className="text-muted-foreground">{fallback(null, NO_DATA)}</span>;
  if (known) {
    const status = row.dsr_state as DsrStatus;
    return <Badge variant={DSR_STATUS_VARIANT[status]}>{DSR_STATUS_LABEL[status]}</Badge>;
  }
  return <span>{row.dsr_state}</span>;
}

export function BatchesHub() {
  const router = useRouter();
  const list = useList<ManageBatchRow>(listManageBatches, { page_size: 20 });

  const columns: DataTableColumn<ManageBatchRow>[] = [
    {
      key: 'code',
      header: 'Code',
      sticky: 'start',
      sortable: true,
      width: '9rem',
      render: (row) => (
        <Link
          href={`/manage/batches/${row.id}`}
          className="font-mono text-xs text-foreground hover:text-primary hover:underline"
        >
          {row.code}
        </Link>
      ),
    },
    { key: 'name', header: 'Name', render: (row) => <span className="font-medium">{row.name}</span> },
    { key: 'course_title', header: 'Course', render: (row) => row.course_title },
    {
      key: 'trainer_name',
      header: 'Trainer',
      render: (row) => fallback(row.trainer_name, NOT_ASSIGNED),
    },
    { key: 'kind', header: 'Kind', render: (row) => <KindCell row={row} /> },
    { key: 'students', header: 'Students', align: 'right', render: (row) => <StudentsCell row={row} /> },
    {
      key: 'attendance',
      header: 'Attendance',
      align: 'right',
      render: (row) => formatPercent(row.attendance_percent, { fallbackLabel: NO_DATA }),
    },
    { key: 'variance', header: 'Plan variance', render: (row) => <PlanVarianceCell row={row} /> },
    { key: 'dsr_state', header: 'DSR', render: (row) => <DsrStateCell row={row} /> },
    {
      key: 'status',
      header: 'Status',
      sortable: true,
      render: (row) => <Badge variant={BATCH_STATUS_VARIANT[row.status]}>{BATCH_STATUS_LABEL[row.status]}</Badge>,
    },
  ];

  return (
    <div className="space-y-6">
      <div className="space-y-1">
        <h1 className="text-2xl font-semibold tracking-tight">Batches</h1>
        <p className="text-sm text-muted-foreground">
          Every cohort running a course. Behind-schedule, at-risk and overdue reports are visible in
          the row — open a batch for the full picture.
        </p>
      </div>

      <ManagerAttentionStrip />

      <div className="space-y-4">
        <ListToolbar
          search={String(list.query.search ?? '')}
          onSearchChange={(value) => list.setQuery({ search: value })}
          placeholder="Batch code, name or course"
        >
          <div>
            <label htmlFor="filter-manage-batch-status" className="mb-1.5 block text-sm font-medium">
              Status
            </label>
            <Select
              id="filter-manage-batch-status"
              value={String(list.query.status ?? '')}
              onChange={(event) => list.setQuery({ status: event.target.value })}
              className="sm:w-48"
            >
              <option value="">All statuses</option>
              {BATCH_STATUS_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </Select>
          </div>
        </ListToolbar>

        <DataTable
          columns={columns}
          rows={list.data?.results ?? []}
          getRowId={(row) => row.id}
          isLoading={list.isLoading}
          error={list.error ? { message: list.error.message, requestId: list.error.requestId } : null}
          onRetry={list.reload}
          emptyTitle="No batches match these filters"
          emptyDescription="Try a different search term or status."
          sort={list.query.ordering}
          onSortChange={list.toggleSort}
          onRowActivate={(row) => router.push(`/manage/batches/${row.id}`)}
          caption="Batches"
          densityStorageKey="grras.manage-batches-density"
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
    </div>
  );
}

export default function ManageBatchesPage() {
  return (
    <RequireAuth capability={Capability.batchViewAny}>
      <BatchesHub />
    </RequireAuth>
  );
}
