'use client';

/**
 * The manager's trainers hub — the second of the two screens, built the same
 * way as the batches hub for the same reason: `DataTable` + `useList` is
 * already the right pairing for "server-driven search, filter and sort", and
 * a second implementation of that would only be a second place to keep in
 * sync with it.
 *
 * This is the canonical trainer workspace for both administrators and
 * managers; the former admin-only URL redirects here. The real "review the
 * trainer" experience — performance figures, reviews, student feedback — is
 * one click away on `/manage/trainers/[trainerId]`; this hub's job is to get a
 * manager to the right trainer quickly, not to repeat that screen in miniature.
 */
import { CalendarDays, Eye, Pencil } from 'lucide-react';
import { useRouter, useSearchParams } from 'next/navigation';
import { Suspense, useState } from 'react';

import { CreateTrainerDialog } from '@/app/admin/trainers/create-trainer-dialog';
import { useAuth } from '@/components/auth-provider';
import { RowActions } from '@/components/row-actions';
import { BulkActionsBar, type BulkAction } from '@/components/bulk-actions';
import { DataTable, type DataTableColumn } from '@/components/data-table';
import { ExportMenu } from '@/components/export-menu';
import { ManagerAttentionStrip } from '@/components/manage/attention-strip';
import { SavedViews } from '@/components/saved-views';
import { ActiveFilters } from '@/components/active-filters';
import { useBranches } from '@/components/organisation/branch-field';
import { ListToolbar } from '@/components/list-toolbar';
import { AttentionChip } from '@/components/manage/attention-chip';
import { Pagination } from '@/components/pagination';
import { useResendInvitations } from '@/components/resend-invitations-action';
import { RequireAuth } from '@/components/require-auth';
import { LoadingState } from '@/components/states';
import { Alert } from '@/components/ui/alert';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input, Select } from '@/components/ui/input';
import { PageHeader } from '@/components/ui/layout';
import { useDebouncedValue } from '@/hooks/use-debounced-value';
import { useBulkSelection } from '@/hooks/use-bulk-selection';
import { useCreateParam } from '@/hooks/use-create-param';
import { useList } from '@/hooks/use-list';
import { ApiError } from '@/lib/api';
import { bulkTarget, bulkTrainers, selectionKey } from '@/lib/bulk';
import { Capability } from '@/lib/capabilities';
import { fallback, NO_DATA } from '@/lib/format';
import { listManageTrainers, type ManageTrainerRow } from '@/lib/manage';
import { getUser, updateTrainer } from '@/lib/people';
import type { TrainerProfile } from '@/types/api';

const TRAINER_FILTER_KEYS = [
  'attention',
  'skill',
  'is_accepting_assignments',
  'branch',
  'min_experience',
] as const;

export function TrainersHub() {
  const router = useRouter();
  const { user: viewer, can } = useAuth();
  const seesEveryCentre = viewer?.role === 'superadmin' || viewer?.role === 'admin';
  const { branches } = useBranches(seesEveryCentre);
  // The attention strip links here with `?attention=…` — "the batches running
  // behind", "the trainers with no review" — so the list opens already
  // narrowed to the thing the person clicked on, rather than to everything.
  const searchParams = useSearchParams();
  const attention = searchParams.get('attention') ?? '';
  const list = useList<ManageTrainerRow>(
    listManageTrainers,
    { page_size: 20, ...(attention ? { attention } : {}) },
    { urlKeys: [...TRAINER_FILTER_KEYS] },
  );
  // Ticked rows survive paging but never a change of filter.
  const selection = useBulkSelection<string>(selectionKey(list.query, TRAINER_FILTER_KEYS));
  const [showCreate, setShowCreate] = useCreateParam(can(Capability.trainerCreate));
  // Typed into a box and applied after a pause (or on Enter) — not only on
  // blur, which left a typed skill doing nothing until focus moved away.
  const [skillDraft, setSkillDraft] = useState(String(list.query.skill ?? ''));
  const debouncedSkill = useDebouncedValue(skillDraft.trim(), 400);
  const appliedSkill = String(list.query.skill ?? '');
  // A skill set from outside (a saved view, the address bar) is shown in the
  // box, so the debounce below never writes the old one back over it.
  const [seenSkill, setSeenSkill] = useState(appliedSkill);
  if (appliedSkill !== seenSkill) {
    setSeenSkill(appliedSkill);
    if (skillDraft.trim() !== appliedSkill) setSkillDraft(appliedSkill);
  }
  if (debouncedSkill !== appliedSkill && debouncedSkill === skillDraft.trim()) {
    list.setQuery({ skill: debouncedSkill });
  }
  // Exactly what the table is showing, so "Export" produces these rows.
  const exportFilters = {
    search: String(list.query.search ?? '') || undefined,
    skill: appliedSkill || undefined,
    is_accepting_assignments: String(list.query.is_accepting_assignments ?? '') || undefined,
    attention: String(list.query.attention ?? '') || undefined,
    branch: String(list.query.branch ?? '') || undefined,
    min_experience: String(list.query.min_experience ?? '') || undefined,
  };
  const [actionError, setActionError] = useState('');
  const [notice, setNotice] = useState('');
  const [busyTrainerId, setBusyTrainerId] = useState<string | null>(null);
  const selectedCount = selection.selectAllMatching
    ? (list.data?.count ?? 0)
    : selection.selectedCount;
  const resend = useResendInvitations({
    count: selectedCount,
    itemNoun: 'trainer',
    send: () =>
      bulkTrainers({
        ...bulkTarget(selection, list.query, TRAINER_FILTER_KEYS),
        action: 'resend_invitation',
      }),
    onDone: () => {
      selection.clear();
      list.reload();
    },
  });
  // A manager brings trainers in, so may resend their invitations too.
  const bulkActions: BulkAction[] =
    can(Capability.userUpdateAny) || can(Capability.trainerUpdateAny)
      ? [{ id: 'resend', label: 'Resend invitations', onClick: resend.open }]
      : [];

  /** Say whether the new trainer's invitation actually went — the email is
   *  sent as the account is saved, so its outcome is already on the record. */
  async function reportInvitation(created: TrainerProfile) {
    const name = created.user.full_name || created.user.email;
    if (!can(Capability.userViewAny)) {
      setNotice(`${name} is added. Their invitation to set a password was sent to ${created.user.email}.`);
      return;
    }
    try {
      const record = await getUser(created.user.id);
      const last = record.last_account_email;
      if (last?.kind === 'invitation' && !last.sent) {
        setActionError(
          `${name} is added, but the invitation could not be sent: ${last.error} Use "Resend invitations" once email works.`,
        );
      } else {
        setNotice(`${name} is added. Their invitation to set a password went to ${created.user.email}.`);
      }
    } catch {
      setNotice(`${name} is added.`);
    }
  }

  async function toggleAvailability(row: ManageTrainerRow) {
    setBusyTrainerId(row.id);
    setActionError('');
    setNotice('');
    try {
      await updateTrainer(row.id, {
        is_accepting_assignments: !row.is_accepting_assignments,
      });
      setNotice(
        row.is_accepting_assignments
          ? `${row.full_name || row.email} no longer takes new batches.`
          : `${row.full_name || row.email} now takes new batches.`,
      );
      list.reload();
    } catch (cause) {
      setActionError(
        cause instanceof ApiError ? cause.message : 'Could not update trainer availability.',
      );
    } finally {
      setBusyTrainerId(null);
    }
  }

  const columns: DataTableColumn<ManageTrainerRow>[] = [
    {
      key: 'trainer_id',
      header: 'Trainer ID',
      sticky: 'start',
      sortable: true,
      width: '9rem',
      render: (row) => <span className="font-mono text-xs">{fallback(row.trainer_id)}</span>,
    },
    {
      key: 'full_name',
      header: 'Name',
      render: (row) => (
        <span className="inline-flex flex-wrap items-center gap-1.5">
          <span className="font-medium">{fallback(row.full_name)}</span>
          {row.role === 'manager' ? <Badge variant="neutral">Manager · also teaches</Badge> : null}
        </span>
      ),
    },
    { key: 'professional_title', header: 'Title', render: (row) => fallback(row.professional_title) },
    {
      key: 'skills',
      header: 'Skills',
      render: (row) =>
        row.skills.length === 0 ? (
          fallback(null, NO_DATA)
        ) : (
          <div className="flex flex-wrap gap-1">
            {row.skills.slice(0, 3).map((skill) => (
              <Badge key={skill}>{skill}</Badge>
            ))}
            {row.skills.length > 3 ? (
              <span className="text-xs text-ink-muted">+{row.skills.length - 3}</span>
            ) : null}
          </div>
        ),
    },
    {
      key: 'years_of_experience',
      header: 'Experience',
      align: 'right',
      sortable: true,
      render: (row) => (row.years_of_experience === null ? fallback(null, NO_DATA) : `${row.years_of_experience} yrs`),
    },
    {
      key: 'active_batches',
      header: 'Active batches',
      align: 'right',
      render: (row) =>
        row.active_batches === undefined || row.active_batches === null ? fallback(null, NO_DATA) : row.active_batches,
    },
    {
      key: 'at_risk_students',
      header: 'Students at risk',
      align: 'right',
      render: (row) =>
        row.at_risk_students === undefined || row.at_risk_students === null ? (
          fallback(null, NO_DATA)
        ) : (
          <span className={row.at_risk_students > 0 ? 'font-medium text-danger' : undefined}>
            {row.at_risk_students}
          </span>
        ),
    },
    {
      key: 'is_accepting_assignments',
      header: 'Availability',
      render: (row) =>
        can(Capability.trainerUpdateAny) ? (
          <Button
            type="button"
            size="sm"
            variant="outline"
            disabled={busyTrainerId === row.id}
            aria-label={
              row.is_accepting_assignments
                ? `Pause assignments for ${row.full_name || row.email}`
                : `Accept assignments for ${row.full_name || row.email}`
            }
            onClick={(event) => {
              event.stopPropagation();
              void toggleAvailability(row);
            }}
          >
            {busyTrainerId === row.id
              ? 'Updating…'
              : row.is_accepting_assignments
                ? 'Pause assignments'
                : 'Accept assignments'}
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
      render: (row) => <Badge variant={row.is_active ? 'success' : 'error'}>{row.is_active ? 'Active' : 'Inactive'}</Badge>,
    },
    {
      key: 'invitation_accepted',
      header: 'Signed up',
      render: (row) => (
        <Badge variant={row.invitation_accepted ? 'success' : 'warning'}>
          {row.invitation_accepted ? 'Yes' : 'Invitation pending'}
        </Badge>
      ),
    },
    {
      key: 'actions',
      header: 'Actions',
      align: 'right',
      sticky: 'end',
      // The row already opens the trainer on click; these are the things
      // somebody wants without leaving the list, and each needs the capability
      // its own screen enforces.
      render: (row) => (
        <RowActions
          subject={row.full_name || row.email}
          actions={[
            { label: 'Open', icon: Eye, href: `/manage/trainers/${row.id}` },
            {
              label: 'Edit',
              icon: Pencil,
              href: `/manage/trainers/${row.id}?edit=1`,
              capability: Capability.trainerUpdateAny,
            },
            {
              label: 'Classes',
              icon: CalendarDays,
              href: `/manage/batches?trainer=${row.id}`,
              capability: Capability.batchViewAny,
            },
          ]}
        />
      ),
    },
  ];

  return (
    <div className="space-y-6">
      <PageHeader
        title="Trainers"
        meta="People, assignment readiness, workload and review in one place."
      >
        <ExportMenu
          reportKey="trainer_activity"
          filters={exportFilters}
          count={list.data?.count ?? null}
          size="md"
        />
        {can(Capability.trainerCreate) ? (
          <Button type="button" onClick={() => setShowCreate(true)}>
            Add trainer
          </Button>
        ) : null}
      </PageHeader>

      <CreateTrainerDialog
        open={showCreate}
        onClose={() => setShowCreate(false)}
        onCreated={(created) => {
          setShowCreate(false);
          list.reload();
          if (created) void reportInvitation(created);
        }}
      />

      <ManagerAttentionStrip />

      <div className="space-y-4">
        <AttentionChip
          value={String(list.query.attention ?? '')}
          onClear={() => list.setQuery({ attention: undefined, page: 1 })}
        />

        <SavedViews
          screen="manage-trainers"
          keys={['search', 'ordering', 'attention', 'skill', 'is_accepting_assignments', 'branch', 'min_experience']}
          query={list.query}
          onApply={list.setQuery}
        />
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
              value={skillDraft}
              onChange={(event) => setSkillDraft(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === 'Enter') list.setQuery({ skill: skillDraft.trim() });
              }}
            />
          </div>
          <div>
            <label htmlFor="filter-availability" className="mb-1.5 block text-sm font-medium">
              Availability
            </label>
            <Select
              id="filter-availability"
              value={String(list.query.is_accepting_assignments ?? '')}
              onChange={(event) =>
                list.setQuery({ is_accepting_assignments: event.target.value })
              }
            >
              <option value="">All</option>
              <option value="true">Accepting</option>
              <option value="false">Not accepting</option>
            </Select>
          </div>
          <div>
            <label htmlFor="filter-experience" className="mb-1.5 block text-sm font-medium">
              Experience
            </label>
            <Select
              id="filter-experience"
              value={String(list.query.min_experience ?? '')}
              onChange={(event) => list.setQuery({ min_experience: event.target.value })}
            >
              <option value="">Any</option>
              <option value="1">1+ years</option>
              <option value="3">3+ years</option>
              <option value="5">5+ years</option>
              <option value="10">10+ years</option>
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
        <ActiveFilters
          query={list.query}
          onChange={list.setQuery}
          filters={[
            { key: 'search', label: 'Search' },
            { key: 'skill', label: 'Skill' },
            {
              key: 'is_accepting_assignments',
              label: 'Availability',
              display: (value) => (value === 'true' ? 'Accepting' : 'Not accepting'),
            },
            { key: 'min_experience', label: 'Experience', display: (value) => `${value}+ years` },
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
          itemNoun="trainer"
        >
          <ExportMenu
            reportKey="trainer_activity"
            label={selection.selectAllMatching ? 'Export all matching' : 'Export'}
            filters={exportFilters}
            selectedIds={selection.selectAllMatching ? undefined : [...selection.selectedIds]}
          />
        </BulkActionsBar>
        {resend.dialogs}

        <DataTable
          columns={columns}
          rows={list.data?.results ?? []}
          getRowId={(row) => row.id}
          selection={selection}
          getRowLabel={(row) => row.full_name || row.email}
          isLoading={list.isLoading}
          error={list.error ? { message: list.error.message, requestId: list.error.requestId } : null}
          onRetry={list.reload}
          emptyTitle="No trainers match these filters"
          emptyDescription="Try a different search or filter, or add the first trainer."
          sort={list.query.ordering}
          onSortChange={list.toggleSort}
          onRowActivate={(row) => router.push(`/manage/trainers/${row.id}`)}
          caption="Trainers"
          densityStorageKey="grras.manage-trainers-density"
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
    </div>
  );
}

export default function ManageTrainersPage() {
  return (
    <RequireAuth capability={Capability.trainerViewAny}>
      <Suspense fallback={<LoadingState label="Loading…" rows={6} />}>
        <TrainersHub />
      </Suspense>
    </RequireAuth>
  );
}
