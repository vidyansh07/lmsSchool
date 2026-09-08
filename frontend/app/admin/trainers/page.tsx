'use client';

import { useState } from 'react';

import { useAuth } from '@/components/auth-provider';
import { ListToolbar } from '@/components/list-toolbar';
import { Pagination } from '@/components/pagination';
import { RequireAuth } from '@/components/require-auth';
import { EmptyState, ErrorState, LoadingState } from '@/components/states';
import { Alert } from '@/components/ui/alert';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input, Select } from '@/components/ui/input';
import { Table, TableWrapper, Td, Th } from '@/components/ui/table';
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
      setActionError(
        cause instanceof ApiError ? cause.message : 'Could not update availability.',
      );
    }
  }

  const sortDirection = list.query.ordering?.startsWith('-') ? 'desc' : 'asc';
  const sortField = list.query.ordering?.replace(/^-/, '');

  return (
    <div className="animate-rise-in space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="space-y-1">
          <h1 className="text-2xl font-semibold tracking-tight">Trainers</h1>
          <p className="text-sm text-muted-foreground">
            Trainer records, skills and availability for future assignments.
          </p>
        </div>
        {can(Capability.trainerCreate) ? (
          <Button onClick={() => setShowCreate(true)}>Add trainer</Button>
        ) : null}
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

      {list.isLoading ? (
        <LoadingState label="Loading trainers…" rows={6} />
      ) : list.error ? (
        <ErrorState
          title="Could not load trainers"
          message={list.error.message}
          requestId={list.error.requestId || undefined}
          onRetry={list.reload}
        />
      ) : list.data && list.data.count === 0 ? (
        <EmptyState
          title="No trainers match these filters"
          description="Try a different search term, or add the first trainer."
        />
      ) : (
        <>
          <TableWrapper className="max-h-[min(36rem,65vh)] overflow-y-auto">
            <Table>
              <thead>
                <tr>
                  <Th
                    sortable
                    active={sortField === 'trainer_id'}
                    direction={sortDirection}
                    onSort={() => list.toggleSort('trainer_id')}
                    className="sticky top-0 z-10 bg-muted"
                  >
                    Trainer ID
                  </Th>
                  <Th className="sticky top-0 z-10 bg-muted">Name</Th>
                  <Th className="sticky top-0 z-10 bg-muted">Title</Th>
                  <Th className="sticky top-0 z-10 bg-muted">Skills</Th>
                  <Th
                    sortable
                    active={sortField === 'years_of_experience'}
                    direction={sortDirection}
                    onSort={() => list.toggleSort('years_of_experience')}
                    className="sticky top-0 z-10 bg-muted"
                  >
                    Experience
                  </Th>
                  <Th className="sticky top-0 z-10 bg-muted">Availability</Th>
                  <Th className="sticky top-0 z-10 bg-muted">Account</Th>
                </tr>
              </thead>
              <tbody className="stagger">
                {list.data?.results.map((row) => (
                  <tr key={row.id} className="animate-fade-in transition-colors hover:bg-muted/40">
                    <Td className="font-mono text-xs">{row.trainer_id}</Td>
                    <Td className="font-medium">{row.full_name || '—'}</Td>
                    <Td>{row.professional_title || '—'}</Td>
                    <Td>
                      <div className="flex flex-wrap gap-1">
                        {row.skills.length === 0
                          ? '—'
                          : row.skills.slice(0, 3).map((skill) => (
                              <Badge key={skill}>{skill}</Badge>
                            ))}
                        {row.skills.length > 3 ? (
                          <span className="text-xs text-muted-foreground">
                            +{row.skills.length - 3}
                          </span>
                        ) : null}
                      </div>
                    </Td>
                    <Td>{row.years_of_experience ?? '—'}</Td>
                    <Td>
                      {can(Capability.trainerUpdateAny) ? (
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
                      )}
                    </Td>
                    <Td>
                      <Badge variant={row.is_active ? 'success' : 'error'}>
                        {row.is_active ? 'Active' : 'Inactive'}
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

export default function AdminTrainersPage() {
  return (
    <RequireAuth capability={Capability.trainerViewAny}>
      <TrainersTable />
    </RequireAuth>
  );
}
