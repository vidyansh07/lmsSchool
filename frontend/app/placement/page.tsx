'use client';

/**
 * The placement desk.
 *
 * Placement work was spread across three places that each knew a third of
 * it: a student's `open_to_placement` flag said who wanted a job, the
 * activity catalogue's `mock-interview`/`resume-review`/`placement-call`
 * types recorded the work done about it, and *where somebody ended up* was
 * recorded nowhere at all. This page is that third, with the first two
 * gathered beside it.
 *
 * Three questions, in the order the desk asks them:
 *
 * 1. How are we doing — offers out, people placed, offers this month.
 * 2. Who is still looking — the students who said they are open to
 *    placement, which is their own answer and not an assumption.
 * 3. Every offer, and what became of it.
 *
 * Deliberately not here: employers, openings and applications. A job board
 * is a different product; the officer who knows the companies and rings them
 * needs the outcome recorded, not a vacancy feed.
 *
 * `placement.view_any` opens the page; `placement.manage` adds the buttons
 * that write. Both are re-checked by the server on every request, so a
 * hidden button is a courtesy and never the control.
 */

import { Briefcase, CheckCircle2, Clock, Plus, UserRound } from 'lucide-react';
import Link from 'next/link';
import { useState } from 'react';

import { useAuth } from '@/components/auth-provider';
import { DataTable, type DataTableColumn } from '@/components/data-table';
import { PlacementDialog } from '@/components/placement/placement-dialog';
import { RequireAuth } from '@/components/require-auth';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { Field } from '@/components/ui/field';
import { Select } from '@/components/ui/input';
import { Grid, GridItem, PageHeader, Section } from '@/components/ui/layout';
import { StatCard } from '@/components/ui/stat';
import { useSection } from '@/hooks/use-section';
import { Capability } from '@/lib/capabilities';
import { formatCurrency, formatDate, NOT_AVAILABLE } from '@/lib/format';
import { listStudents } from '@/lib/people';
import { PLACEMENT_STATUS_LABEL, PLACEMENT_STATUS_VARIANT } from '@/lib/placement-labels';
import { listPlacements, placementSummary } from '@/lib/placements';
import type { Placement, PlacementStatus, PlacementSummary, StudentListRow } from '@/types/api';

/** `''` is every offer; `placed` is the two statuses that mean a job. */
type OfferFilter = '' | 'placed' | PlacementStatus;

const OFFER_FILTERS: { value: OfferFilter; label: string }[] = [
  { value: '', label: 'Every offer' },
  { value: 'placed', label: 'Became a job' },
  { value: 'offered', label: 'Still open' },
  { value: 'declined', label: 'Declined' },
  { value: 'withdrawn', label: 'Withdrawn' },
];

function queryFor(filter: OfferFilter) {
  if (filter === '') return {};
  if (filter === 'placed') return { placed: true };
  return { status: filter };
}

export function PlacementWorkspace() {
  const { can } = useAuth();
  const mayManage = can(Capability.placementManage);
  const mayReadStudents = can(Capability.studentViewAny);
  const [filter, setFilter] = useState<OfferFilter>('');
  const [editing, setEditing] = useState<Placement | null>(null);
  const [isDialogOpen, setIsDialogOpen] = useState(false);

  const summary = useSection<PlacementSummary | null>(() => placementSummary(), null);
  const offers = useSection(
    () => listPlacements({ ...queryFor(filter), page_size: 50 }).then((page) => page.results),
    [] as Placement[],
    [filter],
  );
  // Who is still looking. Only for somebody who may read students at all — a
  // role with placement rights and no student list gets the offers and no
  // 403-shaped hole where this section would be.
  const looking = useSection(
    () =>
      mayReadStudents
        ? listStudents({ open_to_placement: 'true', page_size: 10 }).then((page) => page.results)
        : Promise.resolve([] as StudentListRow[]),
    [] as StudentListRow[],
  );

  function openFor(placement: Placement | null) {
    setEditing(placement);
    setIsDialogOpen(true);
  }

  function reload() {
    summary.reload();
    offers.reload();
  }

  const columns: DataTableColumn<Placement>[] = [
    {
      key: 'student_name',
      header: 'Student',
      sticky: 'start',
      render: (row) => (
        <Link href={`/students/${row.student_id}`} className="font-medium hover:underline">
          {row.student_name}
        </Link>
      ),
    },
    { key: 'company', header: 'Company', sortable: true, render: (row) => row.company },
    { key: 'role_title', header: 'Role', hideBelow: 'md', render: (row) => row.role_title },
    {
      key: 'status',
      header: 'Status',
      render: (row) => (
        <Badge variant={PLACEMENT_STATUS_VARIANT[row.status]}>
          {PLACEMENT_STATUS_LABEL[row.status]}
        </Badge>
      ),
    },
    {
      key: 'annual_package',
      header: 'Package',
      align: 'right',
      sortable: true,
      render: (row) => (
        <span className="tabular-nums">
          {row.annual_package ? formatCurrency(row.annual_package) : NOT_AVAILABLE}
        </span>
      ),
    },
    {
      key: 'offered_on',
      // "Offered on", not "Offered": the status column holds a badge reading
      // "Offered", and two columns a word apart is how somebody reads the
      // wrong one.
      header: 'Offered on',
      sortable: true,
      hideBelow: 'sm',
      render: (row) => <span className="tabular-nums">{formatDate(row.offered_on)}</span>,
    },
    {
      key: 'actions',
      header: '',
      align: 'right',
      render: (row) =>
        mayManage ? (
          <Button variant="ghost" size="sm" onClick={() => openFor(row)}>
            Edit
          </Button>
        ) : null,
    },
  ];

  return (
    <div className="space-y-6">
      <PageHeader
        title="Placement"
        meta="Offers, who has been placed, and who is still looking — across the students you are allowed to see."
      >
        {mayManage ? (
          <Button onClick={() => openFor(null)}>
            <Plus className="size-4" aria-hidden="true" />
            Record an offer
          </Button>
        ) : null}
      </PageHeader>

      <Grid>
        <GridItem span={3}>
          <StatCard
            label="Students placed"
            value={summary.data ? summary.data.placed_students : null}
            icon={CheckCircle2}
            hint="Accepted or joined. Counts people, not offers."
          />
        </GridItem>
        <GridItem span={3}>
          <StatCard
            label="Offers still open"
            value={summary.data ? summary.data.open_offers : null}
            icon={Clock}
            hint="Made, not yet accepted or declined"
          />
        </GridItem>
        <GridItem span={3}>
          <StatCard
            label="Offers this month"
            value={summary.data ? summary.data.offers_this_month : null}
            icon={Briefcase}
          />
        </GridItem>
        <GridItem span={3}>
          <StatCard
            label="Offers in all"
            value={summary.data ? summary.data.offers : null}
            icon={Briefcase}
            hint={summary.data ? `${summary.data.closed_offers} declined or withdrawn` : undefined}
          />
        </GridItem>
      </Grid>

      {mayReadStudents ? (
        <Section
          title="Still looking"
          meta="Students who said they are open to placement — their own answer, not an assumption"
        >
          <Card>
            <CardContent className="pt-5">
              {looking.error ? (
                <p className="text-sm text-ink-muted">
                  The list of students open to placement did not load.
                </p>
              ) : looking.data.length === 0 ? (
                <p className="text-sm text-ink-muted">
                  Nobody has said they are open to placement yet. A student sets it on their own
                  profile.
                </p>
              ) : (
                <ul className="divide-y divide-line">
                  {looking.data.map((student) => (
                    <li
                      key={student.id}
                      className="flex flex-wrap items-center justify-between gap-2 py-2"
                    >
                      <span className="flex min-w-0 items-center gap-2">
                        <UserRound className="size-4 shrink-0 text-ink-faint" aria-hidden="true" />
                        <Link
                          href={`/students/${student.id}`}
                          className="truncate text-sm font-medium hover:underline"
                        >
                          {student.full_name}
                        </Link>
                        <span className="shrink-0 font-mono text-xs text-ink-muted">
                          {student.student_id}
                        </span>
                      </span>
                      <span className="text-sm text-ink-muted">{student.institution || ''}</span>
                    </li>
                  ))}
                </ul>
              )}
            </CardContent>
          </Card>
        </Section>
      ) : null}

      <Section title="Offers" meta="One row per offer: four interviews and one job is four rows">
        <Field label="Show" htmlFor="placement-filter" className="mb-3 max-w-xs">
          <Select
            id="placement-filter"
            value={filter}
            onChange={(event) => setFilter(event.target.value as OfferFilter)}
          >
            {OFFER_FILTERS.map((option) => (
              <option key={option.value || 'all'} value={option.value}>
                {option.label}
              </option>
            ))}
          </Select>
        </Field>
        <DataTable
          columns={columns}
          rows={offers.data}
          getRowId={(row) => row.id}
          isLoading={offers.isLoading}
          loadingLabel="Loading offers…"
          error={
            offers.error
              ? { message: offers.error.message, requestId: offers.error.requestId || undefined }
              : null
          }
          onRetry={offers.reload}
          emptyTitle="No offers recorded"
          emptyDescription="Record the first one when a company makes it."
          caption="Placement offers"
          densityStorageKey="placement-offers"
        />
      </Section>

      {isDialogOpen ? (
        <PlacementDialog
          key={editing?.id ?? 'new'}
          placement={editing}
          open={isDialogOpen}
          onClose={() => setIsDialogOpen(false)}
          onSaved={reload}
        />
      ) : null}
    </div>
  );
}

export default function PlacementPage() {
  return (
    <RequireAuth capability={Capability.placementViewAny}>
      <PlacementWorkspace />
    </RequireAuth>
  );
}
