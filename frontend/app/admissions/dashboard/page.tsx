'use client';

/**
 * The counsellor's landing page: a fast, repetitive pipeline — register a
 * student, choose a course, place them on a batch, staff it with a trainer,
 * enrol — needs a screen that gets someone into that flow in one click and
 * says what needs chasing before they start. `app/admissions/page.tsx` (the
 * working list) and `app/admissions/new/page.tsx` (the wizard) already do the
 * flow itself; this page is what a counsellor opens before either of those,
 * every morning.
 *
 * Two API gaps shape what is and is not on this page, both worth recording
 * once here rather than re-discovering at each call site below:
 *
 * 1. Bulk imports have no list endpoint. `apps/reporting/views.py` exposes
 *    create (`POST /imports/students/`), detail-by-id, confirm and reject,
 *    but nothing enumerates a user's past imports — `ImportDetailView` can
 *    only look one up if the caller already has its id. "Recent imports and
 *    their status" is therefore not something this page can show without
 *    inventing an endpoint, which the brief this page answers to explicitly
 *    rules out. What is here instead is the "Bulk import" quick action itself
 *    — the entry point the missing history would have summarised.
 *
 * 2. Nothing records who registered a student or who created an enrolment.
 *    `StudentListRow` and `Enrollment` (`types/api.ts`) carry no actor field,
 *    so "their own recent activity" cannot be scoped to the signed-in
 *    counsellor — see the docstring on `recent-activity-panel.tsx` for the
 *    honest substitute shown instead (the pipeline's activity, not
 *    provably *this counsellor's*).
 *
 * Everything else here is a composition of list endpoints that already
 * exist, documented at each fetch below rather than as a wall of prose here.
 *
 * ERP Phase 17 adds `GET /api/v1/dashboards/counsellor/` (`lib/dashboards
 * .ts::getCounsellorDashboard`), one call in place of several for the
 * figures it now computes server-side: registered today, registered this
 * week, pending registrations, and two genuinely new ones this page had no
 * way to show before (follow-ups due/overdue, unassigned batch/trainer). It
 * carries no rows, though, only counts — so every panel below that needs an
 * actual list (batches to watch, the fees corner, recent activity) keeps its
 * own fetch.
 *
 * Two figures on this screen used to be computed here, in the browser, from
 * one page of recent rows, and both were wrong in the same way — a window,
 * mistaken for an answer:
 *
 * - "Registered this week" counted the rows newer than Monday among the
 *   thirty most recent registrations, so a day with sixty-one registrations
 *   rendered "today 61" beside "this week 30": a seven-day figure smaller
 *   than one day inside it. It now reads `new_students_this_week`, a rolling
 *   seven days ending today, which by construction cannot be smaller.
 * - "Registered, not yet enrolled" diffed those thirty registrations against
 *   the hundred most recent *enrolments* — two windows ordered by different
 *   columns, which on real data did not overlap: fifteen students listed as
 *   awaiting a batch while every one of them was enrolled. It now asks
 *   `/api/v1/students/?awaiting_enrolment=true`, the same definition the
 *   "Unassigned batch" tile counts.
 *
 * Which is why every figure in the KPI row now also carries what it counts
 * (`definitions` on the payload, rendered under the grid): both of those
 * contradictions were visible on this screen for anyone who read two tiles
 * together, and neither number said enough about itself to be doubted.
 */

import Link from 'next/link';
import { useCallback, useEffect, useState } from 'react';
import {
  AlertTriangle,
  CalendarClock,
  CalendarRange,
  Clock,
  PlusCircle,
  Rocket,
  UploadCloud,
  UserPlus,
  Users,
  UserX,
  Banknote,
  Filter,
  Hourglass,
} from 'lucide-react';
import type { LucideIcon } from 'lucide-react';

import { useAuth } from '@/components/auth-provider';
import { BatchWatchlist } from '@/components/counsellor/batches-panel';
import { FeesPanel } from '@/components/counsellor/fees-panel';
import { NotYetEnrolledPanel } from '@/components/counsellor/not-yet-enrolled-panel';
import { PendingConfirmationsPanel } from '@/components/counsellor/pending-confirmations-panel';
import { RecentActivityPanel } from '@/components/counsellor/recent-activity-panel';
import {
  AreaChart,
  BarChart,
  ChartCard,
  ComboChart,
  DonutChart,
  HorizontalBarChart,
  StageFunnel,
  paletteColor,
  type CategoryDatum,
  type DonutDatum,
} from '@/components/ui/charts';
import { Grid, GridItem } from '@/components/ui/layout';
import { StatCard } from '@/components/ui/stat';
import { QuickActions, type QuickAction } from '@/components/quick-actions';
import { RequireAuth } from '@/components/require-auth';
import { WarningsStrip } from '@/components/warnings-strip';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { ApiError } from '@/lib/api';
import { listBatches, listEnrollments } from '@/lib/batches';
import { ENROLLMENT_STATUS_LABEL } from '@/lib/batch-labels';
import { Capability } from '@/lib/capabilities';
import { ageingBuckets, formatWeekLabel, mergeByWeek, money, withCumulative } from '@/lib/analytics';
import { getCounsellorDashboard, getCounsellorPipeline } from '@/lib/dashboards';
import { feeCollectionsTrend, getFeesOverview } from '@/lib/fees';
import { formatCurrency, formatNumber } from '@/lib/format';
import { greeting } from '@/lib/greeting';
import { listStudents } from '@/lib/people';
import type {
  BatchListRow,
  CounsellorPipeline,
  FeeCollectionsTrendPoint,
  CounsellorDashboard,
  Enrollment,
  EnrollmentStatus,
  FeesOverview,
  StudentListRow,
} from '@/types/api';

/**
 * One dashboard section's load state, independent of every other section's —
 * the same shape and the same reasoning as the identically-named helper in
 * `app/dashboard/page.tsx` (not shared code: each page owns its own small
 * copy rather than the two dashboards reaching into a third file for four
 * lines of `useEffect`). A slow or failing batches fetch, say, must never
 * block the registrations-not-yet-enrolled panel above it — that panel is,
 * per the brief, the single most useful thing on this screen.
 */
interface SectionState<T> {
  data: T;
  error: ApiError | null;
  isLoading: boolean;
  reload: () => void;
}

function useDashboardSection<T>(loader: () => Promise<T>, empty: T): SectionState<T> {
  const [attempt, setAttempt] = useState(0);
  const [state, setState] = useState<{
    data: T;
    error: ApiError | null;
    isLoading: boolean;
    attempt: number;
  }>({ data: empty, error: null, isLoading: true, attempt });

  // Reset during render when `attempt` moves, not inside the effect below —
  // the same "adjust state during render" pattern `hooks/use-list.ts` and
  // `hooks/use-api.ts` already use, and for the same reason: an unconditional
  // `setState` at the top of an effect body is a synchronous write inside
  // that effect, which is the cascading-render pattern this repo's lint
  // config refuses to let through.
  if (state.attempt !== attempt) {
    setState({ data: empty, error: null, isLoading: true, attempt });
  }

  useEffect(() => {
    let cancelled = false;
    loader()
      .then((result) => {
        if (!cancelled) setState({ data: result, error: null, isLoading: false, attempt });
      })
      .catch((cause: unknown) => {
        if (!cancelled) {
          setState({
            data: empty,
            error: cause instanceof ApiError ? cause : null,
            isLoading: false,
            attempt,
          });
        }
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [attempt]);

  const reload = useCallback(() => setAttempt((value) => value + 1), []);
  return { data: state.data, error: state.error, isLoading: state.isLoading, reload };
}

const REGISTRATION_WINDOW = 30;

/** How many students awaiting a seat the panel lists; the figure beside the
 *  list is the server's own total, so this cap shortens the list and never the
 *  count. */
const AWAITING_ENROLMENT_SHOWN = 10;

/**
 * What each figure in the KPI row counts, and where that wording comes from.
 *
 * `definitions` on the counsellor dashboard payload
 * (`apps.dashboards.views.COUNSELLOR_FIGURE_DEFINITIONS`) is the source for
 * every server-computed figure, so the wording lives next to the query it
 * describes and cannot drift from it. The one tile computed here — batches
 * starting soon, filtered from the batches fetch below — has no server
 * definition to quote, so its own is written here and marked as this screen's.
 *
 * `label` is the tile's label verbatim: this is a reader matching a sentence
 * back to a number they just read, so the two have to be the same words.
 */
const KPI_DEFINITIONS: { key: string; label: string; own?: string }[] = [
  { key: 'new_students_today', label: 'Registered today' },
  { key: 'new_students_this_week', label: 'Registered this week' },
  { key: 'pending_registrations', label: 'Pending registrations' },
  {
    key: 'batches_starting_soon',
    label: 'Batches starting soon',
    own:
      'Batches still marked upcoming, at the centres you can see — including ' +
      'any whose start date has already passed without the batch being made ' +
      'active, which is why the list below can lead with one that was due to ' +
      'start weeks ago.',
  },
  { key: 'follow_ups_due', label: 'Follow-ups due' },
  { key: 'follow_ups_overdue', label: 'Follow-ups overdue' },
  { key: 'unassigned_batch', label: 'Unassigned batch' },
  { key: 'unassigned_trainer', label: 'Unassigned trainer' },
];

/**
 * The definitions behind the KPI row, in a `<details>` under it.
 *
 * Under the grid rather than inside each tile because a definition is a
 * sentence and a tile has room for a phrase — `StatCard`'s `hint` is
 * documented as "one short line, not a paragraph", and a tile that grows to
 * hold three lines of prose stops being a tile. Collapsed by default: this is
 * for the reader who is comparing two numbers and wants to know why they
 * differ, not for every visit.
 */
export function FigureDefinitions({ definitions }: { definitions?: Record<string, string> }) {
  const rows = KPI_DEFINITIONS.map((figure) => ({
    ...figure,
    text: figure.own ?? definitions?.[figure.key],
  })).filter((figure): figure is typeof figure & { text: string } => Boolean(figure.text));

  if (rows.length === 0) return null;

  return (
    <details className="rounded-card border border-line bg-surface px-4 py-3 text-sm">
      <summary className="cursor-pointer font-medium">What these figures count</summary>
      <dl className="mt-2 space-y-2">
        {rows.map((figure) => (
          <div key={figure.key}>
            <dt className="font-medium">{figure.label}</dt>
            <dd className="text-ink-muted">{figure.text}</dd>
          </div>
        ))}
      </dl>
    </details>
  );
}

/**
 * `StatCard` has no loading state of its own — it treats an absent value as
 * "not available", which is the right reading for a report that genuinely
 * has nothing, but the wrong one for a number that simply has not arrived
 * yet. This renders a same-shaped skeleton in its place until it has.
 *
 * Same shape matters literally: the skeleton is the height of the card it
 * replaces, so the grid does not resize when the numbers land.
 */
function KpiTileSection({
  label,
  value,
  isLoading,
  failed,
  icon,
  hint,
  href,
}: {
  label: string;
  value: number;
  isLoading: boolean;
  /** True when the bucket this number comes from failed to load — rendered as
   *  "Not available" rather than a possibly-misleading confirmed zero. The
   *  section below always carries the real error message and a retry. */
  failed?: boolean;
  icon?: LucideIcon;
  hint?: string;
  href?: string;
}) {
  if (isLoading) {
    return (
      <Card className="h-full">
        <CardContent className="flex h-full flex-col justify-between gap-3 p-4">
          <Skeleton className="h-4 w-24" />
          <Skeleton className="h-8 w-16" />
          <Skeleton className="h-3 w-32" />
        </CardContent>
      </Card>
    );
  }
  return (
    <StatCard
      label={label}
      value={failed ? null : value}
      icon={icon}
      hint={hint}
      href={href}
    />
  );
}

/**
 * The five counts on `CounsellorDashboard` that are, in one way or another,
 * a student stuck somewhere in the pipeline — a comparison of *kinds* of
 * bottleneck, not a trend or a composition, so a bar chart rather than a
 * donut: these are not five slices of one whole (a student can be both
 * "pending" and headed for "unassigned batch" at once), just five counts
 * worth comparing side by side. `new_students_today` is deliberately left
 * out — good news, not a bottleneck, and already its own KPI tile above.
 */
function pipelineBottlenecks(dashboard: CounsellorDashboard | null): CategoryDatum[] {
  if (!dashboard) return [];
  return [
    // Deliberately not the same wording as the KPI tiles above ("Follow-ups
    // due", "Unassigned batch", …) — this card's own title and description
    // already give the context, and a shorter, distinct label here means a
    // reader (or a query for either one) never has to guess which of two
    // identical-looking pieces of text they landed on.
    { label: 'Pending', value: dashboard.pending_registrations },
    { label: 'Due', value: dashboard.follow_ups_due },
    { label: 'Overdue', value: dashboard.follow_ups_overdue },
    { label: 'No batch', value: dashboard.unassigned_batch },
    { label: 'No trainer', value: dashboard.unassigned_trainer },
  ];
}

/**
 * The 6 mutually-exclusive `EnrollmentStatus` values, in a fixed display
 * order (never count-sorted, so the same status always lands in the same
 * palette slice run to run) — a real composition, unlike `pipelineBottlenecks`
 * above, whose own comment explains why those five figures overlap. Statuses
 * with nothing in the current window are left out rather than shown as an
 * empty slice, matching `summarizeBatchStatuses` in `app/dashboard/page.tsx`
 * (not imported from there: this page's own two-file scope keeps it a small
 * local copy of the same pattern, not a shared import).
 */
const ENROLLMENT_STATUS_ORDER: EnrollmentStatus[] = [
  'active',
  'pending',
  'suspended',
  'completed',
  'cancelled',
  // `transferred` was missing here as well as from the label map, so a
  // transferred enrolment was silently dropped from a donut whose own caption
  // calls itself a composition of the total.
  'transferred',
];

export function summarizeEnrollmentStatuses(enrollments: Enrollment[]): DonutDatum[] {
  const counts = new Map<EnrollmentStatus, number>();
  for (const enrollment of enrollments) {
    counts.set(enrollment.status, (counts.get(enrollment.status) ?? 0) + 1);
  }
  return ENROLLMENT_STATUS_ORDER.filter((status) => (counts.get(status) ?? 0) > 0).map((status) => ({
    label: ENROLLMENT_STATUS_LABEL[status],
    value: counts.get(status) as number,
  }));
}

export function AdmissionsDashboardContent() {
  const { user } = useAuth();
  // The single-call summary (ERP Phase 17): wherever its figures cover what
  // the older N-call pattern below computed by hand, this wins — see the KPI
  // row. It does not carry the actual rows any panel needs to list (a
  // student, a batch, an enrolment), so those panels keep their own fetches.
  const dashboard = useDashboardSection<CounsellorDashboard | null>(
    () => getCounsellorDashboard(),
    null,
  );

  // Still fetched, but only for "Recent activity" below: the two figures this
  // window used to stand in for — "Registered this week" and "not yet
  // enrolled" — are now asked of the server directly.
  const recentStudents = useDashboardSection(
    () =>
      listStudents({ ordering: '-created_at', page_size: REGISTRATION_WINDOW }).then(
        (page) => page.results,
      ),
    [] as StudentListRow[],
  );

  // "Registered, not yet enrolled", asked as a question rather than assembled
  // from two windows: `awaiting_enrolment` is `apps.students.access
  // .awaiting_enrolment`, the same definition the "Unassigned batch" tile
  // counts, so the list and that tile cannot disagree. `count` is the whole
  // total, not the page — the panel says so.
  const awaitingEnrolment = useDashboardSection(
    () =>
      listStudents({
        awaiting_enrolment: 'true',
        ordering: '-created_at',
        page_size: AWAITING_ENROLMENT_SHOWN,
      }).then((page) => ({ results: page.results, count: page.count })),
    { results: [] as StudentListRow[], count: 0 },
  );

  // A wide recent window, not a targeted one: the point of fetching this many
  // enrolments is to build the set of student codes that already have one, so
  // the not-yet-enrolled panel can check membership instead of searching per
  // student. See that panel's own docstring for the trade-off this implies.
  const recentEnrollments = useDashboardSection(
    () =>
      listEnrollments({ ordering: '-enrolled_at', page_size: 100 }).then((page) => page.results),
    [] as Enrollment[],
  );

  const pending = useDashboardSection(
    () =>
      listEnrollments({ status: 'pending', ordering: '-enrolled_at', page_size: 10 }).then(
        (page) => ({
          results: page.results,
          count: page.count,
        }),
      ),
    { results: [] as Enrollment[], count: 0 },
  );

  // Two requests, not one: `status` on `/api/v1/batches/` is an exact match
  // (`BatchFilterSet`), so there is no single call for "upcoming or active".
  // Fetching without a status filter at all was the first draft of this and
  // was wrong — ordered by `start_date` with no filter, a page of 50 rows on
  // an institution with a long history is mostly old, completed batches
  // crowding out the ones this page actually needs to show.
  const batches = useDashboardSection(
    () =>
      Promise.all([
        listBatches({ status: 'upcoming', ordering: 'start_date', page_size: 30 }),
        listBatches({ status: 'active', ordering: 'start_date', page_size: 30 }),
      ]).then(([upcoming, active]) => [...upcoming.results, ...active.results]),
    [] as BatchListRow[],
  );

  const fees = useDashboardSection<FeesOverview | null>(() => getFeesOverview(), null);
  const pipeline = useDashboardSection<CounsellorPipeline | null>(
    () => getCounsellorPipeline({ weeks: 12 }),
    null,
  );
  const collections = useDashboardSection(
    () => feeCollectionsTrend({ weeks: 12 }),
    [] as FeeCollectionsTrendPoint[],
  );

  const admissionsSeries = mergeByWeek([
    { rows: pipeline.data?.weekly ?? [], keys: ['registered', 'enrolled'] },
  ]).map((row) => ({ ...row, date: formatWeekLabel(String(row.date)) }));

  // Bars from the rows, the running total from the same rows -- so the line
  // and the bars cannot disagree.
  const collectionsSeries = withCumulative(
    mergeByWeek([{ rows: collections.data.map((point) => ({ ...point, amount: money(point.amount) })), keys: ['amount', 'receipts'] }]),
    'amount',
  ).map((row) => ({ ...row, date: formatWeekLabel(String(row.date)) }));

  // Ageing is worse the further right it goes, and says so in colour.
  const AGEING_COLOURS = ['var(--color-info)', 'var(--color-warning)', 'var(--color-danger)', 'var(--color-danger)'];
  const overdueByAge = ageingBuckets(fees.data?.overdue ?? []).map((bucket, index) => ({
    ...bucket,
    colour: AGEING_COLOURS[index] ?? 'var(--color-danger)',
  }));

  // `BatchWatchlist` is given the same date it counts by, so the tile, the
  // list under it and the "was due to start" wording in that list can never be
  // computed from two different days.
  const today = new Date().toISOString().slice(0, 10);
  const startingSoonCount = batches.data.filter((batch) => batch.status === 'upcoming').length;

  const quickActions: QuickAction[] = [
    {
      id: 'register',
      label: 'Register a student',
      href: '/admissions/new',
      icon: <UserPlus className="size-4" />,
    },
    {
      id: 'batch',
      label: 'Create a batch',
      href: '/admissions/batches',
      icon: <PlusCircle className="size-4" />,
    },
    {
      id: 'import',
      label: 'Bulk import',
      href: '/admissions/import',
      icon: <UploadCloud className="size-4" />,
    },
  ];

  return (
    <div className="space-y-4">
      <div className="space-y-1">
        <p className="text-sm font-medium text-ink-muted">
          {greeting(user?.full_name || user?.email)}
        </p>
        <h1 className="text-2xl font-semibold tracking-tight">Admissions dashboard</h1>
        <p className="text-sm text-ink-muted">
          Today&apos;s pipeline, and what needs chasing before you start the next one.
        </p>
      </div>

      <QuickActions actions={quickActions} />

      <WarningsStrip />

      <Grid>
        <GridItem span={3}>
          <KpiTileSection
            label="Registered today"
            value={dashboard.data?.new_students_today ?? 0}
            isLoading={dashboard.isLoading}
            failed={Boolean(dashboard.error)}
            icon={UserPlus}
            hint="New students on the books"
            href="/admissions"
          />
        </GridItem>
        <GridItem span={3}>
          <KpiTileSection
            label="Registered this week"
            value={dashboard.data?.new_students_this_week ?? 0}
            isLoading={dashboard.isLoading}
            failed={Boolean(dashboard.error)}
            icon={CalendarRange}
            hint="Rolling seven days, today included"
            href="/admissions"
          />
        </GridItem>
        <GridItem span={3}>
          <KpiTileSection
            label="Pending registrations"
            value={dashboard.data?.pending_registrations ?? 0}
            isLoading={dashboard.isLoading}
            failed={Boolean(dashboard.error)}
            icon={Clock}
            hint="Waiting on a decision"
          />
        </GridItem>
        <GridItem span={3}>
          <KpiTileSection
            label="Batches starting soon"
            value={startingSoonCount}
            isLoading={batches.isLoading}
            failed={Boolean(batches.error)}
            icon={Rocket}
            hint="Seats still to fill"
            href="/admissions/batches"
          />
        </GridItem>
        <GridItem span={3}>
          <KpiTileSection
            label="Follow-ups due"
            value={dashboard.data?.follow_ups_due ?? 0}
            isLoading={dashboard.isLoading}
            failed={Boolean(dashboard.error)}
            icon={CalendarClock}
            hint="Planned, not yet done"
            href="/activities"
          />
        </GridItem>
        <GridItem span={3}>
          <KpiTileSection
            label="Follow-ups overdue"
            value={dashboard.data?.follow_ups_overdue ?? 0}
            isLoading={dashboard.isLoading}
            failed={Boolean(dashboard.error)}
            icon={AlertTriangle}
            hint="Past their due date"
            href="/activities"
          />
        </GridItem>
        <GridItem span={3}>
          <KpiTileSection
            label="Unassigned batch"
            value={dashboard.data?.unassigned_batch ?? 0}
            isLoading={dashboard.isLoading}
            failed={Boolean(dashboard.error)}
            icon={Users}
            hint="Registered, no batch yet"
            href="/admissions"
          />
        </GridItem>
        <GridItem span={3}>
          <KpiTileSection
            label="Unassigned trainer"
            value={dashboard.data?.unassigned_trainer ?? 0}
            isLoading={dashboard.isLoading}
            failed={Boolean(dashboard.error)}
            icon={UserX}
            hint="Batches with nobody teaching them"
            href="/admissions/batches"
          />
        </GridItem>
      </Grid>

      <FigureDefinitions definitions={dashboard.data?.definitions} />

      <Card className="" data-testid="pipeline-bottlenecks-card">
        <CardHeader>
          <CardTitle as="h2">Where the pipeline is stuck</CardTitle>
          <CardDescription>
            The same figures as the tiles above, compared side by side.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {dashboard.error ? (
            <p className="text-sm text-ink-muted">Not available right now.</p>
          ) : (
            <BarChart
              data={pipelineBottlenecks(dashboard.data)}
              loading={dashboard.isLoading}
              height={220}
              emptyMessage="Nothing waiting on you."
              ariaLabel="Pipeline bottlenecks, by kind"
            />
          )}
        </CardContent>
      </Card>

      <Card className="">
        <CardHeader>
          <CardTitle as="h2">Recent enrolments by status</CardTitle>
          <CardDescription>
            The last 100 enrolments in the pipeline, by where they stand right now.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {recentEnrollments.error ? (
            <p className="text-sm text-ink-muted">Not available right now.</p>
          ) : (
            <DonutChart
              data={summarizeEnrollmentStatuses(recentEnrollments.data)}
              loading={recentEnrollments.isLoading}
              centerLabel="Enrolments"
              emptyMessage="No recent enrolments yet."
              ariaLabel="Recent enrolments by status"
            />
          )}
        </CardContent>
      </Card>

      <Grid>
        <GridItem span={12} lgSpan={6}>
          <ChartCard
            title="Admissions pipeline"
            subtitle="Everyone registered in the last twelve weeks, and how far each got"
            icon={Filter}
            iconTone="info"
            testId="admissions-funnel-card"
          >
            <StageFunnel
              stages={pipeline.data?.stages ?? []}
              height={200}
              loading={pipeline.isLoading}
              emptyMessage="Nobody registered in the last twelve weeks"
            />
          </ChartCard>
        </GridItem>

        <GridItem span={12} lgSpan={6}>
          <ChartCard
            title="Admissions over time"
            subtitle="Students registered each week, and how many of them are enrolled"
            icon={CalendarRange}
            iconTone="info"
            testId="admissions-trend-card"
            legend={[
              { label: 'Registered', color: paletteColor(0) },
              { label: 'Enrolled', color: paletteColor(1) },
            ]}
          >
            <AreaChart
              data={admissionsSeries}
              series={[
                { key: 'registered', label: 'Registered' },
                { key: 'enrolled', label: 'Enrolled' },
              ]}
              gradient
              hideLegend
              xLabel="Week"
              height={200}
              loading={pipeline.isLoading}
              emptyMessage="Nobody registered in the last twelve weeks"
              valueFormatter={(value) => formatNumber(value)}
            />
          </ChartCard>
        </GridItem>

        <GridItem span={12} lgSpan={6}>
          <ChartCard
            title="Fee collections"
            subtitle="Taken each week, and the running total — voided receipts excluded"
            icon={Banknote}
            iconTone="success"
            testId="fee-collections-card"
          >
            <ComboChart
              data={collectionsSeries}
              bars={[{ key: 'amount', label: 'This week' }]}
              lines={[{ key: 'cumulative', label: 'Running total' }]}
              rightAxisKeys={['cumulative']}
              leftLabel="Per week"
              rightLabel="To date"
              xLabel="Week"
              height={220}
              loading={collections.isLoading}
              emptyMessage="Nothing collected in the last twelve weeks"
              valueFormatter={(value) => formatCurrency(value)}
              rightValueFormatter={(value) => formatCurrency(value)}
            />
          </ChartCard>
        </GridItem>

        <GridItem span={12} lgSpan={6}>
          <ChartCard
            title="Overdue, by how late"
            subtitle={`Of the ${fees.data?.overdue.length ?? 0} oldest overdue plans shown on this page, not the whole book`}
            icon={Hourglass}
            iconTone="warning"
            testId="overdue-ageing-card"
          >
            <HorizontalBarChart
              data={overdueByAge}
              series={[{ key: 'value', label: 'Plans' }]}
              colorKey="colour"
              categoryWidth={100}
              height={180}
              loading={fees.isLoading}
              emptyMessage="Nothing is overdue"
              valueFormatter={(value) => formatNumber(value)}
            />
          </ChartCard>
        </GridItem>
      </Grid>

      <Card className="">
        <CardHeader>
          <CardTitle>Registered, not yet enrolled</CardTitle>
          <CardDescription>
            The gap that costs money: a student with nowhere to sit yet.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <NotYetEnrolledPanel
            students={awaitingEnrolment.data.results}
            totalCount={awaitingEnrolment.data.count}
            isLoading={awaitingEnrolment.isLoading}
            error={awaitingEnrolment.error}
            onRetry={awaitingEnrolment.reload}
          />
        </CardContent>
      </Card>

      <section aria-labelledby="fees-heading" className="space-y-3">
        <div className="space-y-0.5">
          <h2 id="fees-heading" className="text-lg font-semibold tracking-tight">
            Fees
          </h2>
          <p className="text-sm text-ink-muted">
            Collections and what is still owed. Record a payment from the student&apos;s record.
          </p>
        </div>
        <FeesPanel
          overview={fees.data}
          isLoading={fees.isLoading}
          error={fees.error}
          onRetry={fees.reload}
        />
      </section>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <Card className="">
          <CardHeader>
            <CardTitle>Pending confirmation</CardTitle>
            <CardDescription>Enrolled, but not yet moved to active.</CardDescription>
          </CardHeader>
          <CardContent>
            <PendingConfirmationsPanel
              enrollments={pending.data.results}
              totalCount={pending.data.count}
              isLoading={pending.isLoading}
              error={pending.error}
              onRetry={pending.reload}
            />
          </CardContent>
        </Card>

        <Card className="">
          <CardHeader>
            <CardTitle>Starting soon</CardTitle>
            <CardDescription>
              Batches not running yet. Any that were due to start and were never
              made active come first — they need a decision today, not a date.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <BatchWatchlist
              batches={batches.data}
              kind="starting-soon"
              today={today}
              isLoading={batches.isLoading}
              error={batches.error}
              onRetry={batches.reload}
            />
          </CardContent>
        </Card>
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <Card className="">
          <CardHeader>
            <CardTitle>Filling up</CardTitle>
            <CardDescription>Batches with few seats left.</CardDescription>
          </CardHeader>
          <CardContent>
            <BatchWatchlist
              batches={batches.data}
              kind="filling-up"
              isLoading={batches.isLoading}
              error={batches.error}
              onRetry={batches.reload}
            />
          </CardContent>
        </Card>

        <Card className="">
          <CardHeader>
            <CardTitle>Recent activity</CardTitle>
            <CardDescription>Registrations and enrolments, most recent first.</CardDescription>
          </CardHeader>
          <CardContent>
            <RecentActivityPanel
              students={recentStudents.data.slice(0, 5)}
              enrollments={recentEnrollments.data.slice(0, 5)}
              isLoading={recentStudents.isLoading || recentEnrollments.isLoading}
              error={recentStudents.error ?? recentEnrollments.error}
              onRetry={() => {
                recentStudents.reload();
                recentEnrollments.reload();
              }}
            />
          </CardContent>
        </Card>
      </div>

      <p className="text-xs text-ink-muted">
        <Link href="/admissions" className="underline hover:text-ink">
          Full admissions list
        </Link>
      </p>
    </div>
  );
}

export default function AdmissionsDashboardPage() {
  return (
    <RequireAuth capability={Capability.enrolmentCreate}>
      <AdmissionsDashboardContent />
    </RequireAuth>
  );
}
