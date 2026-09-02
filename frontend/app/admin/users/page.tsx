'use client';

import Link from 'next/link';
import { useState } from 'react';

import { ListToolbar } from '@/components/list-toolbar';
import { Pagination } from '@/components/pagination';
import { RequireAuth } from '@/components/require-auth';
import { EmptyState, ErrorState, LoadingState } from '@/components/states';
import { useAuth } from '@/components/auth-provider';
import { Alert } from '@/components/ui/alert';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Select } from '@/components/ui/input';
import { Table, TableWrapper, Td, Th } from '@/components/ui/table';
import { useList } from '@/hooks/use-list';
import { ApiError } from '@/lib/api';
import { Capability } from '@/lib/capabilities';
import { ROLE_LABEL, ROLE_OPTIONS } from '@/lib/labels';
import { listUsers, setUserActive } from '@/lib/people';
import type { AdminUser } from '@/types/api';

function UsersTable() {
  const { user: currentUser, can } = useAuth();
  const list = useList<AdminUser>(listUsers);
  const [actionError, setActionError] = useState('');

  async function toggleActive(target: AdminUser) {
    setActionError('');
    try {
      await setUserActive(target.id, !target.is_active);
      list.reload();
    } catch (cause) {
      setActionError(
        cause instanceof ApiError ? cause.message : 'Could not update the account status.',
      );
    }
  }

  const sortDirection = list.query.ordering?.startsWith('-') ? 'desc' : 'asc';
  const sortField = list.query.ordering?.replace(/^-/, '');

  return (
    <div className="space-y-4">
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

      {actionError ? <Alert variant="error">{actionError}</Alert> : null}

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
          <TableWrapper>
            <Table>
              <thead>
                <tr>
                  <Th
                    sortable
                    active={sortField === 'email'}
                    direction={sortDirection}
                    onSort={() => list.toggleSort('email')}
                  >
                    Email
                  </Th>
                  <Th>Name</Th>
                  <Th
                    sortable
                    active={sortField === 'role'}
                    direction={sortDirection}
                    onSort={() => list.toggleSort('role')}
                  >
                    Role
                  </Th>
                  <Th>Status</Th>
                  <Th>Email verified</Th>
                  <Th
                    sortable
                    active={sortField === 'date_joined'}
                    direction={sortDirection}
                    onSort={() => list.toggleSort('date_joined')}
                  >
                    Joined
                  </Th>
                  <Th>Actions</Th>
                </tr>
              </thead>
              <tbody>
                {list.data?.results.map((row) => (
                  <tr key={row.id}>
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
                      {can(Capability.userSetActive) && row.id !== currentUser?.id ? (
                        <Button
                          size="sm"
                          variant={row.is_active ? 'outline' : 'primary'}
                          onClick={() => void toggleActive(row)}
                        >
                          {row.is_active ? 'Deactivate' : 'Activate'}
                        </Button>
                      ) : (
                        <span className="text-xs text-muted-foreground">—</span>
                      )}
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
