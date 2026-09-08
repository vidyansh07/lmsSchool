'use client';

import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { ChevronRight } from 'lucide-react';

import { ListToolbar } from '@/components/list-toolbar';
import { Pagination } from '@/components/pagination';
import { RequireAuth } from '@/components/require-auth';
import { EmptyState, ErrorState, LoadingState } from '@/components/states';
import { Badge } from '@/components/ui/badge';
import { Select } from '@/components/ui/input';
import { Table, TableWrapper, Td, Th } from '@/components/ui/table';
import { useList } from '@/hooks/use-list';
import { Capability } from '@/lib/capabilities';
import { ROLE_LABEL, ROLE_OPTIONS } from '@/lib/labels';
import { listUsers } from '@/lib/people';
import type { AdminUser } from '@/types/api';

function UsersTable() {
  const list = useList<AdminUser>(listUsers);
  const router = useRouter();

  const sortDirection = list.query.ordering?.startsWith('-') ? 'desc' : 'asc';
  const sortField = list.query.ordering?.replace(/^-/, '');

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

      {list.isLoading ? (
        <LoadingState label="Loading users…" rows={6} />
      ) : list.error ? (
        <ErrorState
          title="Could not load users"
          message={list.error.message}
          requestId={list.error.requestId || undefined}
          onRetry={list.reload}
        />
      ) : list.data && list.data.count === 0 ? (
        <EmptyState
          title="No users match these filters"
          description="Try a different search term or clear the filters."
        />
      ) : (
        <>
          <TableWrapper className="max-h-[min(36rem,65vh)] overflow-y-auto">
            <Table>
              <thead>
                <tr>
                  <Th
                    sortable
                    active={sortField === 'email'}
                    direction={sortDirection}
                    onSort={() => list.toggleSort('email')}
                    className="sticky top-0 z-10 bg-muted"
                  >
                    Email
                  </Th>
                  <Th className="sticky top-0 z-10 bg-muted">Name</Th>
                  <Th
                    sortable
                    active={sortField === 'role'}
                    direction={sortDirection}
                    onSort={() => list.toggleSort('role')}
                    className="sticky top-0 z-10 bg-muted"
                  >
                    Role
                  </Th>
                  <Th className="sticky top-0 z-10 bg-muted">Status</Th>
                  <Th className="sticky top-0 z-10 bg-muted">Email verified</Th>
                  <Th
                    sortable
                    active={sortField === 'date_joined'}
                    direction={sortDirection}
                    onSort={() => list.toggleSort('date_joined')}
                    className="sticky top-0 z-10 bg-muted"
                  >
                    Joined
                  </Th>
                  <Th className="sticky top-0 z-10 bg-muted">Actions</Th>
                </tr>
              </thead>
              <tbody className="stagger">
                {list.data?.results.map((row) => (
                  <tr
                    key={row.id}
                    onClick={() => router.push(`/admin/users/${row.id}`)}
                    className="animate-fade-in cursor-pointer transition-colors hover:bg-muted/60 active:bg-muted"
                  >
                    <Td className="font-medium">{row.email}</Td>
                    <Td>{row.full_name || '—'}</Td>
                    <Td>
                      <Badge>{ROLE_LABEL[row.role]}</Badge>
                    </Td>
                    <Td>
                      <Badge variant={row.is_active ? 'success' : 'error'}>
                        {row.is_active ? 'Active' : 'Inactive'}
                      </Badge>
                    </Td>
                    <Td>
                      <Badge variant={row.is_email_verified ? 'success' : 'warning'}>
                        {row.is_email_verified ? 'Yes' : 'No'}
                      </Badge>
                    </Td>
                    <Td className="whitespace-nowrap text-muted-foreground">
                      {new Date(row.date_joined).toLocaleDateString()}
                    </Td>
                    <Td>
                      {/* One way in, rather than a row of controls per row:
                          everything an administrator can do to an account lives
                          on that account's own screen, where the audit history
                          sits beside it. The row itself is the click target
                          (see the `<tr onClick>` above); this stays a real link
                          underneath for keyboard and screen-reader users, just
                          no longer the only visible affordance. */}
                      <Link
                        href={`/admin/users/${row.id}`}
                        onClick={(event) => event.stopPropagation()}
                        className="inline-flex items-center gap-0.5 text-sm font-medium text-muted-foreground hover:text-primary hover:underline"
                      >
                        Manage
                        <ChevronRight className="size-3.5" aria-hidden="true" />
                      </Link>
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

      <p className="text-xs text-muted-foreground">
        Students and trainers have richer records under{' '}
        <Link href="/admin/students" className="underline">
          Students
        </Link>{' '}
        and{' '}
        <Link href="/admin/trainers" className="underline">
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
