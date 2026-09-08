'use client';

/**
 * The manager's trainers hub — the second of the two screens, built the same
 * way as the batches hub for the same reason: `DataTable` + `useList` is
 * already the right pairing for "server-driven search, filter and sort", and
 * a second implementation of that would only be a second place to keep in
 * sync with it.
 *
 * This table stays close to `admin/trainers/page.tsx`'s column set (reused,
 * not duplicated — see `lib/manage.ts#listManageTrainers`) because that is
 * what the trainer list endpoint reliably returns today. The real "review the
 * trainer" experience — performance figures, reviews, student feedback — is
 * one click away on `/manage/trainers/[trainerId]`; this hub's job is to get
 * a manager to the right trainer quickly, not to repeat that screen in
 * miniature.
 */
import { useRouter, useSearchParams } from 'next/navigation';
import { Suspense } from 'react';

import { DataTable, type DataTableColumn } from '@/components/data-table';
import { ManagerAttentionStrip } from '@/components/manage/attention-strip';
import { ListToolbar } from '@/components/list-toolbar';
import { AttentionChip } from '@/components/manage/attention-chip';
import { Pagination } from '@/components/pagination';
import { RequireAuth } from '@/components/require-auth';
import { LoadingState } from '@/components/states';
import { Badge } from '@/components/ui/badge';
import { useList } from '@/hooks/use-list';
import { Capability } from '@/lib/capabilities';
import { fallback, NO_DATA } from '@/lib/format';
import { listManageTrainers, type ManageTrainerRow } from '@/lib/manage';

export function TrainersHub() {
  const router = useRouter();
  // The attention strip links here with `?attention=…` — "the batches running
  // behind", "the trainers with no review" — so the list opens already
  // narrowed to the thing the person clicked on, rather than to everything.
  const searchParams = useSearchParams();
  const attention = searchParams.get('attention') ?? '';
  const list = useList<ManageTrainerRow>(listManageTrainers, { page_size: 20, ...(attention ? { attention } : {}) });

  const columns: DataTableColumn<ManageTrainerRow>[] = [
    {
      key: 'trainer_id',
      header: 'Trainer ID',
      sticky: 'start',
      sortable: true,
      width: '9rem',
      render: (row) => <span className="font-mono text-xs">{fallback(row.trainer_id)}</span>,
    },
    { key: 'full_name', header: 'Name', render: (row) => <span className="font-medium">{fallback(row.full_name)}</span> },
    { key: 'professional_title', header: 'Title', render: (row) => fallback(row.professional_title) },
    {
      key: 'skills',
      header: 'Skills',
      render: (row) =>
        row.skills.length === 0 ? (
          fallback(null, NO_DATA)
        ) : (
          <div className="flex flex-wrap gap-1">
            {row.skills.slice(0, 3).map((skill) => (
              <Badge key={skill}>{skill}</Badge>
            ))}
            {row.skills.length > 3 ? (
              <span className="text-xs text-muted-foreground">+{row.skills.length - 3}</span>
            ) : null}
          </div>
        ),
    },
    {
      key: 'years_of_experience',
      header: 'Experience',
      align: 'right',
      sortable: true,
      render: (row) => (row.years_of_experience === null ? fallback(null, NO_DATA) : `${row.years_of_experience} yrs`),
    },
    {
      key: 'active_batches',
      header: 'Active batches',
      align: 'right',
      render: (row) =>
        row.active_batches === undefined || row.active_batches === null ? fallback(null, NO_DATA) : row.active_batches,
    },
    {
      key: 'at_risk_students',
      header: 'Students at risk',
      align: 'right',
      render: (row) =>
        row.at_risk_students === undefined || row.at_risk_students === null ? (
          fallback(null, NO_DATA)
        ) : (
          <span className={row.at_risk_students > 0 ? 'font-medium text-destructive' : undefined}>
            {row.at_risk_students}
          </span>
        ),
    },
    {
      key: 'is_accepting_assignments',
      header: 'Availability',
      render: (row) => (
        <Badge variant={row.is_accepting_assignments ? 'success' : 'neutral'}>
          {row.is_accepting_assignments ? 'Accepting' : 'Not accepting'}
        </Badge>
      ),
    },
    {
      key: 'is_active',
      header: 'Account',
      render: (row) => <Badge variant={row.is_active ? 'success' : 'error'}>{row.is_active ? 'Active' : 'Inactive'}</Badge>,
    },
  ];

  return (
    <div className="animate-rise-in space-y-6">
      <div className="space-y-1">
        <h1 className="text-2xl font-semibold tracking-tight">Trainers</h1>
        <p className="text-sm text-muted-foreground">
          Every trainer on staff. Open one for their performance, the reviews written about them and
          the feedback their students have left.
        </p>
      </div>

      <ManagerAttentionStrip />

      <div className="space-y-4">
        <AttentionChip
          value={String(list.query.attention ?? '')}
          onClear={() => list.setQuery({ attention: undefined, page: 1 })}
        />

        <ListToolbar
          search={String(list.query.search ?? '')}
          onSearchChange={(value) => list.setQuery({ search: value })}
          placeholder="Trainer ID, name, email or title"
        />

        <DataTable
          columns={columns}
          rows={list.data?.results ?? []}
          getRowId={(row) => row.id}
          isLoading={list.isLoading}
          error={list.error ? { message: list.error.message, requestId: list.error.requestId } : null}
          onRetry={list.reload}
          emptyTitle="No trainers match these filters"
          emptyDescription="Try a different search term."
          sort={list.query.ordering}
          onSortChange={list.toggleSort}
          onRowActivate={(row) => router.push(`/manage/trainers/${row.id}`)}
          caption="Trainers"
          densityStorageKey="grras.manage-trainers-density"
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

export default function ManageTrainersPage() {
  return (
    <RequireAuth capability={Capability.trainerViewAny}>
      <Suspense fallback={<LoadingState label="Loading…" rows={6} />}>
        <TrainersHub />
      </Suspense>
    </RequireAuth>
  );
}
