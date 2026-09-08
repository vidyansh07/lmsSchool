'use client';

import { Eye } from 'lucide-react';
import Link from 'next/link';
import { useState } from 'react';

import { useAuth } from '@/components/auth-provider';
import { ListToolbar } from '@/components/list-toolbar';
import { Pagination } from '@/components/pagination';
import { RequireAuth } from '@/components/require-auth';
import { EmptyState, ErrorState, LoadingState } from '@/components/states';
import { Alert } from '@/components/ui/alert';
import { Avatar, AvatarFallback } from '@/components/ui/avatar';
import { Badge, categoryVariant } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input, Select } from '@/components/ui/input';
import { Table, TableWrapper, Td, Th, Tr } from '@/components/ui/table';
import { Tooltip } from '@/components/ui/tooltip';
import { useList } from '@/hooks/use-list';
import { ApiError } from '@/lib/api';
import { formatCurrency } from '@/lib/format';
import { Capability } from '@/lib/capabilities';
import {
  FEE_STATUS_LABEL,
  FEE_STATUS_OPTIONS,
  FEE_STATUS_VARIANT,
  QUALIFICATION_LABEL,
} from '@/lib/labels';
import { listStudents, setFeeStatus } from '@/lib/people';
import type { FeeStatus, StudentListRow } from '@/types/api';
import { CreateStudentDialog } from './create-student-dialog';

function StudentsTable() {
  const { can } = useAuth();
  const list = useList<StudentListRow>(listStudents);
  const [actionError, setActionError] = useState('');
  const [showCreate, setShowCreate] = useState(false);

  async function changeFeeStatus(row: StudentListRow, value: FeeStatus) {
    setActionError('');
    try {
      await setFeeStatus(row.id, value);
      list.reload();
    } catch (cause) {
      setActionError(
        cause instanceof ApiError ? cause.message : 'Could not update the fee status.',
      );
    }
  }

  const sortDirection = list.query.ordering?.startsWith('-') ? 'desc' : 'asc';
  const sortField = list.query.ordering?.replace(/^-/, '');

  return (
    <div className="animate-rise-in space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="space-y-1">
          <h1 className="text-2xl font-semibold tracking-tight">Students</h1>
          <p className="text-sm text-muted-foreground">
            Student records, admissions detail and fee status.
          </p>
        </div>
        {can(Capability.studentCreate) ? (
          <Button onClick={() => setShowCreate(true)}>Add student</Button>
        ) : null}
      </div>

      {showCreate ? (
        <CreateStudentDialog
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
        placeholder="Student ID, name, email or institution"
      >
        <div>
          <label htmlFor="filter-institution" className="mb-1.5 block text-sm font-medium">
            College or employer
          </label>
          <Input
            id="filter-institution"
            placeholder="e.g. Infosys"
            value={String(list.query.institution ?? '')}
            onChange={(event) => list.setQuery({ institution: event.target.value })}
          />
        </div>
        <div>
          <label htmlFor="filter-fee" className="mb-1.5 block text-sm font-medium">
            Fee status
          </label>
          <Select
            id="filter-fee"
            value={String(list.query.fee_status ?? '')}
            onChange={(event) => list.setQuery({ fee_status: event.target.value })}
          >
            <option value="">All</option>
            {FEE_STATUS_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </Select>
        </div>
        <div>
          <label htmlFor="filter-active" className="mb-1.5 block text-sm font-medium">
            Status
          </label>
          <Select
            id="filter-active"
            value={String(list.query.is_active ?? '')}
            onChange={(event) => list.setQuery({ is_active: event.target.value })}
          >
            <option value="">All</option>
            <option value="true">Active</option>
            <option value="false">Inactive</option>
          </Select>
        </div>
      </ListToolbar>

      {actionError ? <Alert variant="error">{actionError}</Alert> : null}

      {list.isLoading ? (
        <LoadingState label="Loading students…" rows={6} />
      ) : list.error ? (
        <ErrorState
          title="Could not load students"
          message={list.error.message}
          requestId={list.error.requestId || undefined}
          onRetry={list.reload}
        />
      ) : list.data && list.data.count === 0 ? (
        <EmptyState
          title="No students match these filters"
          description="Try a different search term, or add the first student."
        />
      ) : (
        <>
          <TableWrapper className="max-h-[min(36rem,65vh)] overflow-y-auto">
            <Table>
              <thead>
                <tr>
                  <Th
                    sortable
                    active={sortField === 'student_id'}
                    direction={sortDirection}
                    onSort={() => list.toggleSort('student_id')}
                    className="sticky top-0 z-10 bg-surface"
                  >
                    ID
                  </Th>
                  <Th className="sticky top-0 z-10 bg-surface">Student</Th>
                  <Th className="sticky top-0 z-10 bg-surface">City</Th>
                  <Th className="sticky top-0 z-10 bg-surface">Qualification</Th>
                  <Th className="sticky top-0 z-10 bg-surface text-right">Agreed fee</Th>
                  <Th
                    sortable
                    active={sortField === 'fee_status'}
                    direction={sortDirection}
                    onSort={() => list.toggleSort('fee_status')}
                    className="sticky top-0 z-10 bg-surface"
                  >
                    Fee status
                  </Th>
                  <Th className="sticky top-0 z-10 bg-surface">Account</Th>
                  <Th className="sticky top-0 z-10 bg-surface text-right">Actions</Th>
                </tr>
              </thead>
              <tbody className="stagger">
                {list.data?.results.map((row) => (
                  <Tr key={row.id} className="animate-fade-in">
                    <Td className="font-mono text-xs font-semibold text-foreground">{row.student_id}</Td>
                    {/* Name and email in one cell, as the reference does it: the
                        two are one identity, and a column each spent a fifth of
                        the table saying the same thing twice. */}
                    <Td>
                      <div className="flex items-center gap-3">
                        <Avatar size="sm" className="bg-accent">
                          <AvatarFallback className="text-primary">
                            {(row.full_name || row.email).slice(0, 1)}
                          </AvatarFallback>
                        </Avatar>
                        <div className="min-w-0 leading-tight">
                          <p className="truncate font-semibold text-foreground">{row.full_name || '—'}</p>
                          <p className="truncate text-xs text-muted-foreground">{row.email}</p>
                          {row.institution ? (
                            <p className="truncate text-xs text-muted-foreground">
                              {row.institution_kind === 'employer' ? 'Works at' : 'Studies at'} {row.institution}
                            </p>
                          ) : null}
                        </div>
                      </div>
                    </Td>
                    <Td>{row.city || '—'}</Td>
                    <Td>
                      {row.qualification ? (
                        <Badge variant={categoryVariant(row.qualification)}>
                          {QUALIFICATION_LABEL[row.qualification]}
                        </Badge>
                      ) : (
                        '—'
                      )}
                    </Td>
                    <Td className="text-right tabular-nums">
                      {/* Whole rupees: the paise are noise in a column. "Not
                          decided" rather than a dash, because a blank here is
                          a question the counsellor still has to answer. */}
                      {row.fee_amount === null ? (
                        <span className="text-xs text-muted-foreground">Not decided</span>
                      ) : (
                        <span className="font-medium">{formatCurrency(row.fee_amount)}</span>
                      )}
                    </Td>
                    <Td>
                      {can(Capability.studentSetFeeStatus) ? (
                        <Select
                          aria-label={`Fee status for ${row.student_id}`}
                          className="h-8 w-40 text-xs"
                          value={row.fee_status}
                          onChange={(event) =>
                            void changeFeeStatus(row, event.target.value as FeeStatus)
                          }
                        >
                          {FEE_STATUS_OPTIONS.map((option) => (
                            <option key={option.value} value={option.value}>
                              {option.label}
                            </option>
                          ))}
                        </Select>
                      ) : (
                        <Badge variant={FEE_STATUS_VARIANT[row.fee_status]}>
                          {FEE_STATUS_LABEL[row.fee_status]}
                        </Badge>
                      )}
                    </Td>
                    <Td>
                      <Badge variant={row.is_active ? 'success' : 'neutral'}>
                        {row.is_active ? 'Active' : 'Inactive'}
                      </Badge>
                    </Td>
                    <Td className="text-right">
                      <Tooltip content="Open the student's record">
                        <Button asChild variant="ghost" size="sm" className="size-8 p-0 text-muted-foreground">
                          <Link href={`/admissions/${row.id}`} aria-label={`Open ${row.full_name || row.email}`}>
                            <Eye className="size-4" aria-hidden="true" />
                          </Link>
                        </Button>
                      </Tooltip>
                    </Td>
                  </Tr>
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

export default function AdminStudentsPage() {
  return (
    <RequireAuth capability={Capability.studentViewAny}>
      <StudentsTable />
    </RequireAuth>
  );
}
