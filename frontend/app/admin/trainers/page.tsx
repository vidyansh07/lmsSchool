'use client';

import { useState } from 'react';

import { useAuth } from '@/components/auth-provider';
import { DataTable, type DataTableColumn } from '@/components/data-table';
import { ExportMenu } from '@/components/export-menu';
import { ListToolbar } from '@/components/list-toolbar';
import { Pagination } from '@/components/pagination';
import { RequireAuth } from '@/components/require-auth';
import { Alert } from '@/components/ui/alert';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input, Select } from '@/components/ui/input';
import { useList } from '@/hooks/use-list';
import { ApiError } from '@/lib/api';
import { Capability } from '@/lib/capabilities';
import { listTrainers, updateTrainer } from '@/lib/people';
import type { TrainerListRow } from '@/types/api';
import { CreateTrainerDialog } from './create-trainer-dialog';

function TrainersTable() {
  const { can } = useAuth();
  const list = useList<TrainerListRow>(listTrainers);
  const [actionError, setActionError] = useState('');
  const [showCreate, setShowCreate] = useState(false);

  async function toggleAvailability(row: TrainerListRow) {
    setActionError('');
    try {
      await updateTrainer(row.id, { is_accepting_assignments: !row.is_accepting_assignments });
      list.reload();
    } catch (cause) {
      setActionError(cause instanceof ApiError ? cause.message : 'Could not update availability.');
    }
  }

  const columns: DataTableColumn<TrainerListRow>[] = [
    {
      key: 'trainer_id',
      header: 'Trainer ID',
      sticky: 'start',
      sortable: true,
      width: '9rem',
      render: (row) => <span className="font-mono text-xs">{row.trainer_id}</span>,
    },
    { key: 'full_name', header: 'Name', render: (row) => <span className="font-medium">{row.full_name || '—'}</span> },
    { key: 'professional_title', header: 'Title', render: (row) => row.professional_title || '—' },
    {
      key: 'skills',
      header: 'Skills',
      render: (row) => (
        <div className="flex flex-wrap gap-1">
          {row.skills.length === 0
            ? '—'
            : row.skills.slice(0, 3).map((skill) => <Badge key={skill}>{skill}</Badge>)}
          {row.skills.length > 3 ? (
            <span className="text-xs text-muted-foreground">+{row.skills.length - 3}</span>
          ) : null}
        </div>
      ),
    },
    {
      key: 'years_of_experience',
      header: 'Experience',
      sortable: true,
      render: (row) => row.years_of_experience ?? '—',
    },
    {
      key: 'availability',
      header: 'Availability',
      render: (row) =>
        can(Capability.trainerUpdateAny) ? (
          <Button
            size="sm"
            variant={row.is_accepting_assignments ? 'outline' : 'primary'}
            onClick={() => void toggleAvailability(row)}
          >
            {row.is_accepting_assignments ? 'Accepting' : 'Not accepting'}
          </Button>
        ) : (
          <Badge variant={row.is_accepting_assignments ? 'success' : 'neutral'}>
            {row.is_accepting_assignments ? 'Accepting' : 'Not accepting'}
          </Badge>
        ),
    },
    {
      key: 'is_active',
      header: 'Account',
      render: (row) => (
        <Badge variant={row.is_active ? 'success' : 'error'}>
          {row.is_active ? 'Active' : 'Inactive'}
        </Badge>
      ),
    },
  ];

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="space-y-1">
          <h1 className="text-2xl font-semibold tracking-tight">Trainers</h1>
          <p className="text-sm text-muted-foreground">
            Trainer records, skills and availability for future assignments.
          </p>
        </div>
        <div className="flex gap-2">
          <ExportMenu reportKey="trainer_activity" count={list.data?.count ?? null} size="md" />
          {can(Capability.trainerCreate) ? (
            <Button onClick={() => setShowCreate(true)}>Add trainer</Button>
          ) : null}
        </div>
      </div>

      {showCreate ? (
        <CreateTrainerDialog
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
        placeholder="Trainer ID, name, email or title"
      >
        <div>
          <label htmlFor="filter-skill" className="mb-1.5 block text-sm font-medium">
            Skill
          </label>
          <Input
            id="filter-skill"
            placeholder="e.g. Linux"
            defaultValue={String(list.query.skill ?? '')}
            onBlur={(event) => list.setQuery({ skill: event.target.value })}
          />
        </div>
        <div>
          <label htmlFor="filter-availability" className="mb-1.5 block text-sm font-medium">
            Availability
          </label>
          <Select
            id="filter-availability"
            value={String(list.query.is_accepting_assignments ?? '')}
            onChange={(event) => list.setQuery({ is_accepting_assignments: event.target.value })}
          >
            <option value="">All</option>
            <option value="true">Accepting</option>
            <option value="false">Not accepting</option>
          </Select>
        </div>
      </ListToolbar>

      {actionError ? <Alert variant="error">{actionError}</Alert> : null}

      <DataTable
        columns={columns}
        rows={list.data?.results ?? []}
        getRowId={(row) => row.id}
        isLoading={list.isLoading}
        loadingLabel="Loading trainers…"
        error={list.error ? { message: list.error.message, requestId: list.error.requestId } : null}
        errorTitle="Could not load trainers"
        onRetry={list.reload}
        emptyTitle="No trainers match these filters"
        emptyDescription="Try a different search term, or add the first trainer."
        sort={list.query.ordering}
        onSortChange={list.toggleSort}
        caption="Trainers"
        densityStorageKey="grras.admin-trainers-density"
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

export default function AdminTrainersPage() {
  return (
    <RequireAuth capability={Capability.trainerViewAny}>
      <TrainersTable />
    </RequireAuth>
  );
}
