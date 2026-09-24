'use client';

import { Eye } from 'lucide-react';
import Link from 'next/link';
import { useState } from 'react';

import { useAuth } from '@/components/auth-provider';
import { DataTable, type DataTableColumn } from '@/components/data-table';
import { ExportMenu } from '@/components/export-menu';
import { ListToolbar } from '@/components/list-toolbar';
import { Pagination } from '@/components/pagination';
import { RequireAuth } from '@/components/require-auth';
import { Alert } from '@/components/ui/alert';
import { Avatar, AvatarFallback } from '@/components/ui/avatar';
import { Badge, categoryVariant } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input, Select } from '@/components/ui/input';
import { Tooltip } from '@/components/ui/tooltip';
import { useList } from '@/hooks/use-list';
import { ApiError } from '@/lib/api';
import { formatCurrency, formatDate } from '@/lib/format';
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

  const columns: DataTableColumn<StudentListRow>[] = [
    {
      key: 'student_id',
      header: 'ID',
      sticky: 'start',
      sortable: true,
      width: '9rem',
      render: (row) => (
        <span className="font-mono text-xs font-semibold text-foreground">
          {row.student_id}
          {row.roll_number ? (
            <span className="mt-0.5 block font-normal text-muted-foreground">
              {row.roll_number}
            </span>
          ) : null}
        </span>
      ),
    },
    {
      key: 'student',
      header: 'Student',
      // Name and email in one cell, as the reference does it: the two are
      // one identity, and a column each spent a fifth of the table saying
      // the same thing twice.
      render: (row) => (
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
      ),
    },
    { key: 'city', header: 'City', render: (row) => row.city || '—' },
    {
      key: 'qualification',
      header: 'Qualification',
      render: (row) =>
        row.qualification ? (
          <Badge variant={categoryVariant(row.qualification)}>
            {QUALIFICATION_LABEL[row.qualification]}
          </Badge>
        ) : (
          '—'
        ),
    },
    {
      key: 'fee_payable',
      header: 'Fee',
      align: 'right',
      // From the ledger, summed over the student's courses. "Not decided"
      // rather than a dash when nothing has been agreed on any course yet —
      // that blank is a question the counsellor still has to answer.
      render: (row) =>
        Number(row.fee_payable) > 0 ? (
          <span className="font-medium">{formatCurrency(row.fee_payable)}</span>
        ) : row.fee_amount !== null ? (
          <span className="font-medium">{formatCurrency(row.fee_amount)}</span>
        ) : (
          <span className="text-xs text-muted-foreground">Not decided</span>
        ),
    },
    {
      key: 'fee_paid',
      header: 'Paid',
      align: 'right',
      render: (row) =>
        Number(row.fee_paid) > 0 ? (
          <span className="text-emerald">{formatCurrency(row.fee_paid)}</span>
        ) : (
          <span className="text-muted-foreground">—</span>
        ),
    },
    {
      key: 'fee_balance',
      header: 'Balance',
      align: 'right',
      render: (row) =>
        Number(row.fee_balance) > 0 ? (
          <>
            <span className="font-medium text-amber">{formatCurrency(row.fee_balance)}</span>
            <span className="block text-xs text-muted-foreground">
              {row.fee_next_due_on ? `Expected ${formatDate(row.fee_next_due_on)}` : 'No date set'}
            </span>
          </>
        ) : Number(row.fee_payable) > 0 ? (
          <span className="text-xs font-medium text-emerald">Settled</span>
        ) : (
          <span className="text-muted-foreground">—</span>
        ),
    },
    {
      key: 'fee_status',
      header: 'Fee status',
      sortable: true,
      render: (row) =>
        can(Capability.studentSetFeeStatus) ? (
          <Select
            aria-label={`Fee status for ${row.student_id}`}
            className="h-8 w-40 text-xs"
            value={row.fee_status}
            onChange={(event) => void changeFeeStatus(row, event.target.value as FeeStatus)}
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
        ),
    },
    {
      key: 'is_active',
      header: 'Account',
      render: (row) => (
        <Badge variant={row.is_active ? 'success' : 'neutral'}>
          {row.is_active ? 'Active' : 'Inactive'}
        </Badge>
      ),
    },
    {
      key: 'actions',
      header: 'Actions',
      align: 'right',
      sticky: 'end',
      render: (row) => (
        <Tooltip content="Open the student's record">
          <Button asChild variant="ghost" size="sm" className="size-8 p-0 text-muted-foreground">
            <Link
              href={`/admissions/${row.id}`}
              onClick={(event) => event.stopPropagation()}
              aria-label={`Open ${row.full_name || row.email}`}
            >
              <Eye className="size-4" aria-hidden="true" />
            </Link>
          </Button>
        </Tooltip>
      ),
    },
  ];

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="space-y-1">
          <h1 className="text-2xl font-semibold tracking-tight">Students</h1>
          <p className="text-sm text-muted-foreground">
            Student records, admissions detail and fee status.
          </p>
        </div>
        <div className="flex gap-2">
          <ExportMenu
            reportKey="students"
            filters={{ search: String(list.query.search ?? '') || undefined }}
            count={list.data?.count ?? null}
            size="md"
          />
          {can(Capability.studentCreate) ? (
            <Button onClick={() => setShowCreate(true)}>Add student</Button>
          ) : null}
        </div>
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

      <DataTable
        columns={columns}
        rows={list.data?.results ?? []}
        getRowId={(row) => row.id}
        isLoading={list.isLoading}
        loadingLabel="Loading students…"
        error={list.error ? { message: list.error.message, requestId: list.error.requestId } : null}
        errorTitle="Could not load students"
        onRetry={list.reload}
        emptyTitle="No students match these filters"
        emptyDescription="Try a different search term, or add the first student."
        sort={list.query.ordering}
        onSortChange={list.toggleSort}
        caption="Students"
        densityStorageKey="grras.admin-students-density"
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

export default function AdminStudentsPage() {
  return (
    <RequireAuth capability={Capability.studentViewAny}>
      <StudentsTable />
    </RequireAuth>
  );
}
