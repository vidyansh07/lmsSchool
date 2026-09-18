'use client';

import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useState } from 'react';

import { useAuth } from '@/components/auth-provider';
import { DataTable, type DataTableColumn } from '@/components/data-table';
import { ExportMenu } from '@/components/export-menu';
import { ListToolbar } from '@/components/list-toolbar';
import { Pagination } from '@/components/pagination';
import { RequireAuth } from '@/components/require-auth';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Select } from '@/components/ui/input';
import { useList } from '@/hooks/use-list';
import {
  BATCH_STATUS_LABEL,
  BATCH_STATUS_OPTIONS,
  BATCH_STATUS_VARIANT,
  formatDate,
} from '@/lib/batch-labels';
import { listBatches } from '@/lib/batches';
import { Capability } from '@/lib/capabilities';
import type { BatchListRow } from '@/types/api';
import { CreateBatchDialog } from './create-batch-dialog';

/**
 * One page for administrators and trainers.
 *
 * The API scopes the list: an administrator sees every batch, a trainer sees
 * only the ones they teach. The page just renders what comes back.
 */
function BatchList() {
  const { can } = useAuth();
  const list = useList<BatchListRow>(listBatches, { page_size: 20 });
  const [showCreate, setShowCreate] = useState(false);
  const router = useRouter();

  const isAdmin = can(Capability.batchViewAny);

  const columns: DataTableColumn<BatchListRow>[] = [
    { key: 'code', header: 'Code', sticky: 'start', width: '8rem', render: (batch) => batch.code },
    {
      key: 'name',
      header: 'Batch',
      render: (batch) => (
        <Link
          href={`/admin/batches/${batch.id}`}
          className="font-medium hover:text-primary hover:underline"
        >
          {batch.name}
        </Link>
      ),
    },
    { key: 'course_title', header: 'Course', render: (batch) => batch.course_title },
    { key: 'trainer_name', header: 'Trainer', render: (batch) => batch.trainer_name || '—' },
    {
      key: 'start_date',
      header: 'Runs',
      sortable: true,
      render: (batch) => (
        <span className="whitespace-nowrap text-muted-foreground">
          {formatDate(batch.start_date)} – {formatDate(batch.end_date)}
        </span>
      ),
    },
    {
      key: 'seats',
      header: 'Seats',
      render: (batch) => (
        <>
          {batch.enrolled_count} / {batch.capacity}
          {batch.seats_available === 0 ? (
            <Badge variant="warning" className="ml-2">
              Full
            </Badge>
          ) : null}
        </>
      ),
    },
    {
      key: 'status',
      header: 'Status',
      render: (batch) => (
        <Badge variant={BATCH_STATUS_VARIANT[batch.status]}>
          {BATCH_STATUS_LABEL[batch.status]}
        </Badge>
      ),
    },
  ];

  return (
    <div className="animate-rise-in space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="space-y-1">
          <h1 className="text-2xl font-semibold tracking-tight">
            {isAdmin ? 'Batches' : 'My batches'}
          </h1>
          <p className="text-sm text-muted-foreground">
            {isAdmin
              ? 'Every cohort running a course, with its trainer and seats.'
              : 'The cohorts you have been assigned to teach.'}
          </p>
        </div>
        <div className="flex gap-2">
          <ExportMenu reportKey="batches" count={list.data?.count ?? null} size="md" />
          {can(Capability.batchCreate) ? (
            <Button onClick={() => setShowCreate(true)}>New batch</Button>
          ) : null}
        </div>
      </div>

      {showCreate ? (
        <CreateBatchDialog
          onClose={() => setShowCreate(false)}
          onCreated={() => {
            setShowCreate(false);
            list.reload();
          }}
        />
      ) : null}

      <ListToolbar
        search={String(list.query.search ?? '')}
        onSearchChange={(value) => list.setQuery({ search: value })}
        placeholder="Batch code, name or course"
      >
        <div>
          <label htmlFor="filter-batch-status" className="mb-1.5 block text-sm font-medium">
            Status
          </label>
          <Select
            id="filter-batch-status"
            value={String(list.query.status ?? '')}
            onChange={(event) => list.setQuery({ status: event.target.value })}
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
        getRowId={(batch) => batch.id}
        isLoading={list.isLoading}
        loadingLabel="Loading batches…"
        error={list.error ? { message: list.error.message, requestId: list.error.requestId } : null}
        errorTitle="Could not load batches"
        onRetry={list.reload}
        emptyTitle={isAdmin ? 'No batches yet' : 'No batches assigned to you'}
        emptyDescription={
          isAdmin
            ? 'Create the first batch to start enrolling students.'
            : 'An administrator assigns the batches you teach.'
        }
        sort={list.query.ordering}
        onSortChange={list.toggleSort}
        onRowActivate={(batch) => router.push(`/admin/batches/${batch.id}`)}
        caption="Batches"
        densityStorageKey="grras.admin-batches-density"
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

export default function AdminBatchesPage() {
  return (
    <RequireAuth>
      <BatchList />
    </RequireAuth>
  );
}
