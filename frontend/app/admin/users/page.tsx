'use client';

import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useState } from 'react';
import { ChevronRight, UserPlus } from 'lucide-react';

import { useAuth } from '@/components/auth-provider';
import { useBranches } from '@/components/organisation/branch-field';
import { Button } from '@/components/ui/button';

import { DataTable, type DataTableColumn } from '@/components/data-table';
import { ListToolbar } from '@/components/list-toolbar';
import { Pagination } from '@/components/pagination';
import { RequireAuth } from '@/components/require-auth';
import { Badge } from '@/components/ui/badge';
import { Select } from '@/components/ui/input';
import { useList } from '@/hooks/use-list';
import { Capability } from '@/lib/capabilities';
import { formatDate } from '@/lib/format';
import { ROLE_LABEL, ROLE_OPTIONS, labelFor } from '@/lib/labels';
import { listUsers } from '@/lib/people';
import type { AdminUser } from '@/types/api';

import { CreateStaffDialog } from './create-staff-dialog';

function UsersTable() {
  const list = useList<AdminUser>(listUsers);
  const router = useRouter();
  const { user: viewer, can } = useAuth();
  const [showCreate, setShowCreate] = useState(false);
  // Administrators and the platform operator see every centre, so they get a
  // centre filter. Anyone bounded to one sees which one, not a control that
  // could only ever hold a single value.
  const seesEveryCentre = viewer?.role === 'superadmin' || viewer?.role === 'admin';
  const { branches } = useBranches(seesEveryCentre);

  const columns: DataTableColumn<AdminUser>[] = [
    {
      key: 'email',
      header: 'Email',
      sticky: 'start',
      sortable: true,
      render: (row) => <span className="font-medium">{row.email}</span>,
    },
    { key: 'full_name', header: 'Name', render: (row) => row.full_name || '—' },
    {
      key: 'branch',
      header: 'Centre',
      render: (row) =>
        row.branch_name ? (
          <span className="whitespace-nowrap">{row.branch_name}</span>
        ) : (
          <span className="text-ink-muted">Every centre</span>
        ),
    },
    { key: 'role', header: 'Role', sortable: true, render: (row) => <Badge>{labelFor(ROLE_LABEL, row.role)}</Badge> },
    {
      key: 'is_active',
      header: 'Status',
      render: (row) => (
        <Badge variant={row.is_active ? 'success' : 'error'}>
          {row.is_active ? 'Active' : 'Inactive'}
        </Badge>
      ),
    },
    {
      key: 'is_email_verified',
      header: 'Email verified',
      render: (row) => (
        <Badge variant={row.is_email_verified ? 'success' : 'warning'}>
          {row.is_email_verified ? 'Yes' : 'No'}
        </Badge>
      ),
    },
    {
      key: 'date_joined',
      header: 'Joined',
      sortable: true,
      render: (row) => (
        <span className="whitespace-nowrap text-ink-muted">
          {formatDate(row.date_joined)}
        </span>
      ),
    },
    {
      key: 'actions',
      header: 'Actions',
      sticky: 'end',
      render: (row) => (
        // One way in, rather than a row of controls per row: everything an
        // administrator can do to an account lives on that account's own
        // screen, where the audit history sits beside it. The row itself is
        // the click target (see `onRowActivate` below); this stays a real
        // link underneath for keyboard and screen-reader users, just no
        // longer the only visible affordance.
        <Link
          href={`/admin/users/${row.id}`}
          onClick={(event) => event.stopPropagation()}
          className="inline-flex items-center gap-0.5 text-sm font-medium text-ink-muted hover:text-action hover:underline"
        >
          Manage
          <ChevronRight className="size-3.5" aria-hidden="true" />
        </Link>
      ),
    },
  ];

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="space-y-1">
          <h1 className="text-2xl font-semibold tracking-tight">User accounts</h1>
          <p className="text-sm text-ink-muted">
            {seesEveryCentre || !viewer?.branch_name
              ? 'Every account on the platform, across all roles.'
              : `Every account at ${viewer.branch_name}, across all roles.`}
          </p>
        </div>
        {can(Capability.userCreate) ? (
          <Button type="button" onClick={() => setShowCreate(true)}>
            <UserPlus className="size-4" aria-hidden="true" />
            Add staff account
          </Button>
        ) : null}
      </div>

      <CreateStaffDialog
        open={showCreate}
        onClose={() => setShowCreate(false)}
        onCreated={(created) => {
          setShowCreate(false);
          router.push(`/admin/users/${created.id}`);
        }}
      />

      <ListToolbar
        search={String(list.query.search ?? '')}
        onSearchChange={(value) => list.setQuery({ search: value })}
        placeholder="Name, email, student ID or trainer ID"
      >
        <div>
          <label htmlFor="filter-role" className="mb-1.5 block text-sm font-medium">
            Role
          </label>
          <Select
            id="filter-role"
            value={String(list.query.role ?? '')}
            onChange={(event) => list.setQuery({ role: event.target.value })}
          >
            <option value="">All roles</option>
            {ROLE_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </Select>
        </div>
        <div>
          <label htmlFor="filter-status" className="mb-1.5 block text-sm font-medium">
            Status
          </label>
          <Select
            id="filter-status"
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

      <DataTable
        columns={columns}
        rows={list.data?.results ?? []}
        getRowId={(row) => row.id}
        isLoading={list.isLoading}
        loadingLabel="Loading users…"
        error={list.error ? { message: list.error.message, requestId: list.error.requestId } : null}
        errorTitle="Could not load users"
        onRetry={list.reload}
        emptyTitle="No users match these filters"
        emptyDescription="Try a different search term or clear the filters."
        sort={list.query.ordering}
        onSortChange={list.toggleSort}
        onRowActivate={(row) => router.push(`/admin/users/${row.id}`)}
        caption="User accounts"
        densityStorageKey="grras.admin-users-density"
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

      <p className="text-xs text-ink-muted">
        Students and trainers have richer records under{' '}
        <Link href="/admin/students" className="underline hover:text-ink">
          Students
        </Link>{' '}
        and{' '}
        <Link href="/manage/trainers" className="underline hover:text-ink">
          Trainers
        </Link>
        .
      </p>
    </div>
  );
}

export default function AdminUsersPage() {
  return (
    <RequireAuth capability={Capability.userViewAny}>
      <UsersTable />
    </RequireAuth>
  );
}
