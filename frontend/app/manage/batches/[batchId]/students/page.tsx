'use client';

/**
 * A batch's roster, with the performance rollup for every student on it —
 * `/manage/batches/[batchId]/students`, one step down from the batch
 * overview's "Students" and "Attendance" sections.
 *
 * `transferred_in` gets its own marker next to the name deliberately: a
 * student who moved here from another batch already has a history — classes
 * attended, tests sat, assignments handed in — that a roster reading "new
 * student, nothing done yet" would erase. The client raised this by name, so
 * it is not a column to bury in a tooltip; it sits right where the name is
 * read.
 *
 * The fetcher is bound to `batchId` with `useCallback` before it reaches
 * `useList`, because `useList` expects a stable `(query) => Promise<Paginated<T>>`
 * signature with no batch of its own to thread through — the closure is the
 * adapter between a per-batch endpoint and a hook written for the general
 * case.
 */
import Link from 'next/link';
import { use, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import { ArrowLeftRight } from 'lucide-react';

import { DataTable, type DataTableColumn } from '@/components/data-table';
import { RiskFlags } from '@/components/manage/risk-flags';
import { ListToolbar } from '@/components/list-toolbar';
import { Pagination } from '@/components/pagination';
import { RequireAuth } from '@/components/require-auth';
import { Badge } from '@/components/ui/badge';
import { useList } from '@/hooks/use-list';
import { ENROLLMENT_STATUS_LABEL, ENROLLMENT_STATUS_VARIANT } from '@/lib/batch-labels';
import { Capability } from '@/lib/capabilities';
import { fallback, formatPercent, NO_DATA } from '@/lib/format';
import { listBatchStudents, type BatchStudentRow } from '@/lib/manage';
import type { ListQuery } from '@/lib/people';

export function BatchRoster({ batchId }: { batchId: string }) {
  const router = useRouter();
  const fetcher = useCallback((query: ListQuery) => listBatchStudents(batchId, query), [batchId]);
  const list = useList<BatchStudentRow>(fetcher, { page_size: 25 });

  const columns: DataTableColumn<BatchStudentRow>[] = [
    {
      key: 'student_id',
      header: 'Student ID',
      sticky: 'start',
      sortable: true,
      width: '10rem',
      render: (row) => <span className="font-mono text-xs">{fallback(row.student_id)}</span>,
    },
    {
      key: 'name',
      header: 'Name',
      sortable: true,
      render: (row) => (
        <span className="flex items-center gap-2">
          <span className="font-medium">{fallback(row.name)}</span>
          {row.transferred_in ? (
            <Badge
              variant="neutral"
              className="inline-flex items-center gap-1"
              title="Transferred here from another batch"
            >
              <ArrowLeftRight className="size-3" aria-hidden="true" />
              Transferred
            </Badge>
          ) : null}
        </span>
      ),
    },
    {
      key: 'status',
      header: 'Status',
      sortable: true,
      render: (row) => <Badge variant={ENROLLMENT_STATUS_VARIANT[row.status]}>{ENROLLMENT_STATUS_LABEL[row.status]}</Badge>,
    },
    {
      key: 'attendance_percent',
      header: 'Attendance',
      align: 'right',
      sortable: true,
      render: (row) => formatPercent(row.attendance_percent, { fallbackLabel: NO_DATA }),
    },
    {
      key: 'assessment_average',
      header: 'Assessment avg',
      align: 'right',
      sortable: true,
      render: (row) => formatPercent(row.assessment_average, { fallbackLabel: NO_DATA }),
    },
    {
      key: 'assignments',
      header: 'Assignments',
      align: 'right',
      render: (row) => `${row.assignments_submitted} / ${row.assignments_total}`,
    },
    {
      key: 'projects',
      header: 'Projects',
      align: 'right',
      render: (row) => `${row.projects_submitted} / ${row.projects_total}`,
    },
    {
      key: 'progress_percent',
      header: 'Progress',
      align: 'right',
      sortable: true,
      render: (row) => formatPercent(row.progress_percent, { fallbackLabel: NO_DATA }),
    },
    {
      key: 'risk_flags',
      header: 'Risk',
      render: (row) => <RiskFlags flags={row.risk_flags} />,
    },
  ];

  return (
    <div className="space-y-6">
      <Link
        href={`/manage/batches/${batchId}`}
        className="inline-block text-sm text-muted-foreground hover:text-foreground"
      >
        ← Back to batch
      </Link>

      <div className="space-y-1">
        <h1 className="text-2xl font-semibold tracking-tight">Roster</h1>
        <p className="text-sm text-muted-foreground">
          Every student on this batch, with their attendance, assessments, assignments, projects and
          progress. Open a student for the complete picture.
        </p>
      </div>

      <ListToolbar
        search={String(list.query.search ?? '')}
        onSearchChange={(value) => list.setQuery({ search: value })}
        placeholder="Student name or ID"
      />

      <DataTable
        columns={columns}
        rows={list.data?.results ?? []}
        getRowId={(row) => row.enrollment_id}
        isLoading={list.isLoading}
        error={list.error ? { message: list.error.message, requestId: list.error.requestId } : null}
        onRetry={list.reload}
        emptyTitle="No students match these filters"
        emptyDescription="Nobody is enrolled on this batch yet."
        sort={list.query.ordering}
        onSortChange={list.toggleSort}
        onRowActivate={(row) => router.push(`/manage/students/${row.enrollment_id}`)}
        caption="Roster"
        densityStorageKey="grras.manage-roster-density"
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

export default function ManageBatchRosterPage({ params }: { params: Promise<{ batchId: string }> }) {
  const { batchId } = use(params);
  return (
    <RequireAuth capability={Capability.batchViewAny}>
      <BatchRoster batchId={batchId} />
    </RequireAuth>
  );
}
