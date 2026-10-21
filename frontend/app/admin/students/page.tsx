'use client';

import { Eye, IndianRupee, Pencil, Send } from 'lucide-react';
import { useRouter } from 'next/navigation';
import { useEffect, useState } from 'react';

import { useAuth } from '@/components/auth-provider';
import { BulkActionsBar, type BulkAction } from '@/components/bulk-actions';
import { DataTable, type DataTableColumn } from '@/components/data-table';
import { ExportMenu } from '@/components/export-menu';
import { exportFiltersFrom } from '@/lib/reporting';
import { SavedViews } from '@/components/saved-views';
import { ActiveFilters } from '@/components/active-filters';
import { useBranches } from '@/components/organisation/branch-field';
import {
  FilterBuilder,
  fromQuery,
  parameterFor,
  toQuery,
  type FilterCondition,
  type FilterFieldSpec,
} from '@/components/filter-builder';
import { ListToolbar } from '@/components/list-toolbar';
import { Pagination } from '@/components/pagination';
import { useResendInvitations } from '@/components/resend-invitations-action';
import { RequireAuth } from '@/components/require-auth';
import { RowActions } from '@/components/row-actions';
import { Alert } from '@/components/ui/alert';
import { Avatar, AvatarFallback } from '@/components/ui/avatar';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input, Select } from '@/components/ui/input';
import { useBulkSelection } from '@/hooks/use-bulk-selection';
import { useList } from '@/hooks/use-list';
import { bulkStudents, bulkTarget, selectionKey } from '@/lib/bulk';
import { ApiError } from '@/lib/api';
import { formatCurrency, formatDate } from '@/lib/format';
import { Capability } from '@/lib/capabilities';
import {
  FEE_STATUS_LABEL,
  FEE_STATUS_OPTIONS,
  FEE_STATUS_VARIANT,
  QUALIFICATION_LABEL,
  labelFor,
} from '@/lib/labels';
import { listStudents, setFeeStatus, studentFilterFields } from '@/lib/people';
import type { FeeStatus, StudentListRow } from '@/types/api';
import { CreateStudentDialog } from './create-student-dialog';

// `referred_by` arrives from a student's "Has referred N students" link.
const STUDENT_FILTER_KEYS = ['institution', 'fee_status', 'is_active', 'branch', 'referred_by'] as const;

function StudentsTable() {
  const { user: viewer, can } = useAuth();
  const list = useList<StudentListRow>(listStudents, {}, {
    urlKeys: [...STUDENT_FILTER_KEYS],
    // A filter somebody builds has a parameter name this screen cannot know in
    // advance — it depends on the field and operator they chose. Matching on
    // the shape keeps such a view in the address bar, so it can be bookmarked
    // or sent to a colleague like any other.
    urlKeyMatch: (key) => key.includes('__'),
  });

  // The fields come from the server, which is the same declaration it enforces
  // the list against. A copy kept here would drift: the server drops a field,
  // the control stays, and the list quietly stops narrowing.
  const [filterFields, setFilterFields] = useState<FilterFieldSpec[]>([]);
  useEffect(() => {
    const controller = new AbortController();
    studentFilterFields(controller.signal)
      .then((response) => setFilterFields(response.fields))
      // A filter bar that cannot load is a missing feature, not a broken page:
      // search, the fixed filters and the list itself all still work.
      .catch(() => setFilterFields([]));
    return () => controller.abort();
  }, []);

  const conditions = fromQuery(list.query as Record<string, unknown>, filterFields);

  function applyConditions(next: FilterCondition[]) {
    // Clearing has to be explicit: `setQuery` merges, so a parameter that is
    // simply absent from the new set would otherwise stay applied.
    const cleared: Record<string, string> = {};
    for (const condition of conditions) cleared[parameterFor(condition)] = '';
    list.setQuery({ ...cleared, ...toQuery(next) });
  }
  // Ticked rows survive paging but never a change of filter.
  const selection = useBulkSelection<string>(selectionKey(list.query, STUDENT_FILTER_KEYS));
  const exportFilters = exportFiltersFrom(list.query, ['search', ...STUDENT_FILTER_KEYS]);
  const resend = useResendInvitations({
    count: selection.selectAllMatching ? (list.data?.count ?? 0) : selection.selectedCount,
    itemNoun: 'student',
    send: () =>
      bulkStudents({
        ...bulkTarget(selection, list.query, STUDENT_FILTER_KEYS),
        action: 'resend_invitation',
      }),
    onDone: () => {
      selection.clear();
      list.reload();
    },
  });
  const bulkActions: BulkAction[] = can(Capability.userUpdateAny)
    ? [{ id: 'resend', label: 'Resend invitations', onClick: resend.open }]
    : [];
  // Administrators and the platform operator see every centre; a centre
  // filter only means something to them.
  const seesEveryCentre = viewer?.role === 'superadmin' || viewer?.role === 'admin';
  const { branches } = useBranches(seesEveryCentre);
  const [actionError, setActionError] = useState('');
  // An inline change is said when it lands, so a select that quietly
  // re-renders is not the only sign anything happened.
  const [notice, setNotice] = useState('');
  const router = useRouter();
  const [showCreate, setShowCreate] = useState(false);

  async function changeFeeStatus(row: StudentListRow, value: FeeStatus) {
    setActionError('');
    setNotice('');
    try {
      await setFeeStatus(row.id, value);
      setNotice(`${row.full_name || row.email}: fee status is now ${labelFor(FEE_STATUS_LABEL, value)}.`);
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
        <span className="font-mono text-xs font-semibold text-ink">
          {row.student_id}
          {row.roll_number ? (
            <span className="mt-0.5 block font-normal text-ink-muted">
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
          <Avatar size="sm" className="bg-selected">
            <AvatarFallback className="text-action">
              {/* A placeholder account can have neither a name nor an email. */}
              {(row.full_name || row.email || '').trim().slice(0, 1) || '?'}
            </AvatarFallback>
          </Avatar>
          <div className="min-w-0 leading-tight">
            <p className="truncate font-semibold text-ink">{row.full_name || '—'}</p>
            <p className="truncate text-xs text-ink-muted">{row.email}</p>
            {row.institution ? (
              <p className="truncate text-xs text-ink-muted">
                {row.institution_kind === 'employer' ? 'Works at' : 'Studies at'} {row.institution}
              </p>
            ) : null}
          </div>
        </div>
      ),
    },
    { key: 'city', header: 'City', hideBelow: 'md', render: (row) => row.city || '—' },
    {
      key: 'qualification',
      hideBelow: 'md',
      header: 'Qualification',
      render: (row) =>
        row.qualification ? (
          <Badge>
            {labelFor(QUALIFICATION_LABEL, row.qualification)}
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
          <span className="text-xs text-ink-muted">Not decided</span>
        ),
    },
    {
      key: 'fee_paid',
      header: 'Paid',
      align: 'right',
      render: (row) =>
        Number(row.fee_paid) > 0 ? (
          <span className="text-success">{formatCurrency(row.fee_paid)}</span>
        ) : (
          <span className="text-ink-muted">—</span>
        ),
    },
    {
      key: 'fee_balance',
      header: 'Balance',
      align: 'right',
      render: (row) =>
        Number(row.fee_balance) > 0 ? (
          <>
            <span className="font-medium text-warning">{formatCurrency(row.fee_balance)}</span>
            <span className="block text-xs text-ink-muted">
              {row.fee_next_due_on ? `Expected ${formatDate(row.fee_next_due_on)}` : 'No date set'}
            </span>
          </>
        ) : Number(row.fee_payable) > 0 ? (
          <span className="text-xs font-medium text-success">Settled</span>
        ) : (
          <span className="text-ink-muted">—</span>
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
      // What this person may do to this student, and nothing they may not.
      // Each of these needs the capability its endpoint already enforces, so
      // the column never offers an action that would be refused.
      render: (row) => (
        <RowActions
          subject={row.full_name || row.email}
          actions={[
            { label: 'Open', icon: Eye, href: `/admissions/${row.id}` },
            {
              label: 'Edit',
              icon: Pencil,
              href: `/admissions/${row.id}?edit=1`,
              capability: Capability.studentUpdateAny,
            },
            {
              label: 'Fees',
              icon: IndianRupee,
              href: `/fees?student=${row.id}`,
              capability: Capability.feeViewAny,
            },
            {
              label: 'Message',
              icon: Send,
              href: `/communication/new?student=${row.id}`,
              capability: Capability.communicationSend,
            },
          ]}
        />
      ),
    },
  ];

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="space-y-1">
          <h1 className="text-2xl font-semibold tracking-tight">Students</h1>
          <p className="text-sm text-ink-muted">
            Student records, admissions detail and fee status.
          </p>
        </div>
        <div className="flex gap-2">
          <ExportMenu
            reportKey="students"
            filters={exportFilters}
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

      <SavedViews
        screen="admin-students"
        keys={['search', 'ordering', ...STUDENT_FILTER_KEYS]}
        query={list.query}
        onApply={list.setQuery}
      />
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
        {seesEveryCentre && branches.length > 1 ? (
          <div>
            <label htmlFor="filter-branch" className="mb-1.5 block text-sm font-medium">
              Centre
            </label>
            <Select
              id="filter-branch"
              value={String(list.query.branch ?? '')}
              onChange={(event) => list.setQuery({ branch: event.target.value })}
            >
              <option value="">All centres</option>
              {branches.map((branch) => (
                <option key={branch.id} value={branch.id}>
                  {branch.name} ({branch.code})
                </option>
              ))}
            </Select>
          </div>
        ) : null}
      </ListToolbar>

      {/* The fixed controls above answer the questions this screen was built
          for; this answers the rest, without turning the toolbar into a wall of
          dropdowns nobody uses. */}
      <FilterBuilder
        fields={filterFields}
        conditions={conditions}
        onChange={applyConditions}
      />
      <ActiveFilters
        query={list.query}
        onChange={list.setQuery}
        filters={[
          { key: 'search', label: 'Search' },
          { key: 'referred_by', label: 'Referred by', display: () => 'the student you came from' },
          { key: 'institution', label: 'College or employer' },
          { key: 'fee_status', label: 'Fee status', display: (value) => labelFor(FEE_STATUS_LABEL, value) },
          { key: 'is_active', label: 'Status', display: (value) => (value === 'true' ? 'Active' : 'Inactive') },
          {
            key: 'branch',
            label: 'Centre',
            display: (value) => branches.find((branch) => branch.id === value)?.name ?? value,
          },
        ]}
      />

      {actionError ? <Alert variant="error">{actionError}</Alert> : null}
      {notice ? (
        <Alert variant="success" role="status">
          {notice}
        </Alert>
      ) : null}

      <BulkActionsBar
        selectedCount={selection.selectedCount}
        totalMatchingCount={list.data?.count}
        selectAllMatching={selection.selectAllMatching}
        onSelectAllMatching={selection.selectAllMatchingFilter}
        onClear={selection.clear}
        actions={bulkActions}
        itemNoun="student"
      >
        <ExportMenu
          reportKey="students"
          label={selection.selectAllMatching ? 'Export all matching' : 'Export'}
          filters={exportFilters}
          selectedIds={selection.selectAllMatching ? undefined : [...selection.selectedIds]}
        />
      </BulkActionsBar>
      {resend.dialogs}

      <DataTable
        onRowActivate={(row) => router.push(`/admissions/${row.id}`)}
        columns={columns}
        rows={list.data?.results ?? []}
        getRowId={(row) => row.id}
        selection={selection}
        getRowLabel={(row) => row.full_name || row.email}
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
