'use client';

import Link from 'next/link';
import { useState } from 'react';

import { useAuth } from '@/components/auth-provider';
import { ListToolbar } from '@/components/list-toolbar';
import { Pagination } from '@/components/pagination';
import { RequireAuth } from '@/components/require-auth';
import { EmptyState, ErrorState, LoadingState } from '@/components/states';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Select } from '@/components/ui/input';
import { Table, TableWrapper, Td, Th } from '@/components/ui/table';
import { useList } from '@/hooks/use-list';
import { BATCH_STATUS_LABEL, BATCH_STATUS_OPTIONS, BATCH_STATUS_VARIANT, formatDate } from '@/lib/batch-labels';
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

  const isAdmin = can(Capability.batchViewAny);
  const sortDirection = list.query.ordering?.startsWith('-') ? 'desc' : 'asc';
  const sortField = list.query.ordering?.replace(/^-/, '');

  return (
    <div className="space-y-4">
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
        {can(Capability.batchCreate) ? (
          <Button onClick={() => setShowCreate(true)}>New batch</Button>
        ) : null}
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

      {list.isLoading ? (
        <LoadingState label="Loading batches…" rows={6} />
      ) : list.error ? (
        <ErrorState
          title="Could not load batches"
          message={list.error.message}
          requestId={list.error.requestId || undefined}
          onRetry={list.reload}
        />
      ) : list.data && list.data.count === 0 ? (
        <EmptyState
          title={isAdmin ? 'No batches yet' : 'No batches assigned to you'}
          description={
            isAdmin
              ? 'Create the first batch to start enrolling students.'
              : 'An administrator assigns the batches you teach.'
          }
        />
      ) : (
        <>
          <TableWrapper>
            <Table>
              <thead>
                <tr>
                  <Th>Code</Th>
                  <Th>Batch</Th>
                  <Th>Course</Th>
                  <Th>Trainer</Th>
                  <Th
                    sortable
                    active={sortField === 'start_date'}
                    direction={sortDirection}
                    onSort={() => list.toggleSort('start_date')}
                  >
                    Runs
                  </Th>
                  <Th>Seats</Th>
                  <Th>Status</Th>
                </tr>
              </thead>
              <tbody>
                {list.data?.results.map((batch) => (
                  <tr key={batch.id}>
                    <Td className="font-mono text-xs">{batch.code}</Td>
                    <Td className="font-medium">
                      <Link href={`/admin/batches/${batch.id}`} className="hover:text-primary">
                        {batch.name}
                      </Link>
                    </Td>
                    <Td>{batch.course_title}</Td>
                    <Td>{batch.trainer_name || '—'}</Td>
                    <Td className="whitespace-nowrap text-muted-foreground">
                      {formatDate(batch.start_date)} – {formatDate(batch.end_date)}
                    </Td>
                    <Td>
                      {batch.enrolled_count} / {batch.capacity}
                      {batch.seats_available === 0 ? (
                        <Badge variant="warning" className="ml-2">
                          Full
                        </Badge>
                      ) : null}
                    </Td>
                    <Td>
                      <Badge variant={BATCH_STATUS_VARIANT[batch.status]}>
                        {BATCH_STATUS_LABEL[batch.status]}
                      </Badge>
                    </Td>
                  </tr>
                ))}
              </tbody>
            </Table>
          </TableWrapper>

          {list.data ? (
            <Pagination
              page={list.data.page}
              totalPages={list.data.total_pages}
              count={list.data.count}
              pageSize={list.data.page_size}
              onPageChange={list.setPage}
            />
          ) : null}
        </>
      )}
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
