'use client';

import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { ChevronRight } from 'lucide-react';

import { DataTable, type DataTableColumn } from '@/components/data-table';
import { ListToolbar } from '@/components/list-toolbar';
import { Pagination } from '@/components/pagination';
import { RequireAuth } from '@/components/require-auth';
import { Badge } from '@/components/ui/badge';
import { Select } from '@/components/ui/input';
import { useList } from '@/hooks/use-list';
import { Capability } from '@/lib/capabilities';
import { ROLE_LABEL, ROLE_OPTIONS } from '@/lib/labels';
import { listUsers } from '@/lib/people';
import type { AdminUser } from '@/types/api';

function UsersTable() {
  const list = useList<AdminUser>(listUsers);
  const router = useRouter();

  const columns: DataTableColumn<AdminUser>[] = [
    {
      key: 'email',
      header: 'Email',
      sticky: 'start',
      sortable: true,
      render: (row) => <span className="font-medium">{row.email}</span>,
    },
    { key: 'full_name', header: 'Name', render: (row) => row.full_name || '—' },
    { key: 'role', header: 'Role', sortable: true, render: (row) => <Badge>{ROLE_LABEL[row.role]}</Badge> },
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
        <span className="whitespace-nowrap text-muted-foreground">
          {new Date(row.date_joined).toLocaleDateString()}
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
          className="inline-flex items-center gap-0.5 text-sm font-medium text-muted-foreground hover:text-primary hover:underline"
        >
          Manage
          <ChevronRight className="size-3.5" aria-hidden="true" />
        </Link>
      ),
    },
  ];

  return (
    <div className="animate-rise-in space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="space-y-1">
          <h1 className="text-2xl font-semibold tracking-tight">Users</h1>
          <p className="text-sm text-muted-foreground">
            Every account on the platform, across all roles.
          </p>
        </div>
      </div>

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
        caption="Users"
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

      <p className="text-xs text-muted-foreground">
        Students and trainers have richer records under{' '}
        <Link href="/admin/students" className="underline hover:text-foreground">
          Students
        </Link>{' '}
        and{' '}
        <Link href="/admin/trainers" className="underline hover:text-foreground">
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
