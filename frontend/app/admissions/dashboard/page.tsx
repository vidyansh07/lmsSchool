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
 */

import Link from 'next/link';
import { useCallback, useEffect, useState } from 'react';
import { PlusCircle, UploadCloud, UserPlus } from 'lucide-react';

import { BatchWatchlist } from '@/components/counsellor/batches-panel';
import { NotYetEnrolledPanel } from '@/components/counsellor/not-yet-enrolled-panel';
import { PendingConfirmationsPanel } from '@/components/counsellor/pending-confirmations-panel';
import { RecentActivityPanel } from '@/components/counsellor/recent-activity-panel';
import { DashboardGrid } from '@/components/dashboard-grid';
import { KpiTile } from '@/components/kpi-tile';
import { QuickActions, type QuickAction } from '@/components/quick-actions';
import { RequireAuth } from '@/components/require-auth';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { ApiError } from '@/lib/api';
import { listBatches, listEnrollments } from '@/lib/batches';
import { Capability } from '@/lib/capabilities';
import { listStudents } from '@/lib/people';
import type { BatchListRow, Enrollment, StudentListRow } from '@/types/api';

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
  const [state, setState] = useState<{ data: T; error: ApiError | null; isLoading: boolean; attempt: number }>(
    { data: empty, error: null, isLoading: true, attempt },
  );

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
          setState({ data: empty, error: cause instanceof ApiError ? cause : null, isLoading: false, attempt });
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

/** Monday 00:00 of the given date's week, as an ISO instant — matches `DateRangePicker`'s own week start. */
function startOfWeekIso(reference: Date): string {
  const day = reference.getDay();
  const diff = (day + 6) % 7;
  const monday = new Date(reference);
  monday.setDate(monday.getDate() - diff);
  monday.setHours(0, 0, 0, 0);
  return monday.toISOString();
}

function startOfDayIso(reference: Date): string {
  const midnight = new Date(reference);
  midnight.setHours(0, 0, 0, 0);
  return midnight.toISOString();
}

/**
 * How many of `students` were registered at or after `sinceIso`.
 *
 * `students` is only ever the most recent `REGISTRATION_WINDOW` rows (there is
 * no date filter on `/api/v1/students/` to ask the server for "today's"
 * directly — see `StudentFilterSet` in `apps/students/views.py`), so on a day
 * busy enough to exceed that window this undercounts. Exported so that
 * boundary is exactly what a test pins down, rather than something only
 * discoverable by reading the fetch below.
 */
export function countRegisteredSince(students: StudentListRow[], sinceIso: string): number {
  return students.filter((student) => student.created_at >= sinceIso).length;
}

/**
 * `KpiTile` has no loading state of its own — it treats an absent value as
 * "not available", which is the right reading for a report that genuinely
 * has nothing, but the wrong one for a number that simply has not arrived
 * yet. This renders a same-shaped skeleton in its place until it has.
 */
function KpiTileSection({
  label,
  value,
  isLoading,
  failed,
}: {
  label: string;
  value: number;
  isLoading: boolean;
  /** True when the bucket this number comes from failed to load — rendered as
   *  "Not available" rather than a possibly-misleading confirmed zero. The
   *  section below always carries the real error message and a retry. */
  failed?: boolean;
}) {
  if (isLoading) {
    return (
      <Card>
        <CardContent className="flex flex-col gap-2 p-5">
          <Skeleton className="h-4 w-24" />
          <Skeleton className="h-7 w-16" />
        </CardContent>
      </Card>
    );
  }
  return <KpiTile label={label} value={failed ? null : value} />;
}

export function AdmissionsDashboardContent() {
  const recentStudents = useDashboardSection(
    () => listStudents({ ordering: '-created_at', page_size: REGISTRATION_WINDOW }).then((page) => page.results),
    [] as StudentListRow[],
  );

  // A wide recent window, not a targeted one: the point of fetching this many
  // enrolments is to build the set of student codes that already have one, so
  // the not-yet-enrolled panel can check membership instead of searching per
  // student. See that panel's own docstring for the trade-off this implies.
  const recentEnrollments = useDashboardSection(
    () => listEnrollments({ ordering: '-enrolled_at', page_size: 100 }).then((page) => page.results),
    [] as Enrollment[],
  );

  const pending = useDashboardSection(
    () =>
      listEnrollments({ status: 'pending', ordering: '-enrolled_at', page_size: 10 }).then((page) => ({
        results: page.results,
        count: page.count,
      })),
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

  const enrolledStudentCodes = new Set(
    recentEnrollments.data.map((entry) => entry.student_code).filter((code): code is string => Boolean(code)),
  );

  const now = new Date();
  const registeredToday = countRegisteredSince(recentStudents.data, startOfDayIso(now));
  const registeredThisWeek = countRegisteredSince(recentStudents.data, startOfWeekIso(now));
  const startingSoonCount = batches.data.filter((batch) => batch.status === 'upcoming').length;

  const quickActions: QuickAction[] = [
    { id: 'register', label: 'Register a student', href: '/admissions/new', icon: <UserPlus className="size-4" /> },
    { id: 'batch', label: 'Create a batch', href: '/admissions/batches', icon: <PlusCircle className="size-4" /> },
    { id: 'import', label: 'Bulk import', href: '/admissions/import', icon: <UploadCloud className="size-4" /> },
  ];

  return (
    <div className="space-y-6">
      <div className="space-y-1">
        <h1 className="text-2xl font-semibold tracking-tight">Admissions dashboard</h1>
        <p className="text-sm text-muted-foreground">
          Today&apos;s pipeline, and what needs chasing before you start the next one.
        </p>
      </div>

      <QuickActions actions={quickActions} />

      <DashboardGrid>
        <KpiTileSection
          label="Registered today"
          value={registeredToday}
          isLoading={recentStudents.isLoading}
          failed={Boolean(recentStudents.error)}
        />
        <KpiTileSection
          label="Registered this week"
          value={registeredThisWeek}
          isLoading={recentStudents.isLoading}
          failed={Boolean(recentStudents.error)}
        />
        <KpiTileSection
          label="Pending confirmation"
          value={pending.data.count}
          isLoading={pending.isLoading}
          failed={Boolean(pending.error)}
        />
        <KpiTileSection
          label="Batches starting soon"
          value={startingSoonCount}
          isLoading={batches.isLoading}
          failed={Boolean(batches.error)}
        />
      </DashboardGrid>

      <Card>
        <CardHeader>
          <CardTitle>Registered, not yet enrolled</CardTitle>
          <CardDescription>
            The gap that costs money: a student with nowhere to sit yet.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <NotYetEnrolledPanel
            recentStudents={recentStudents.data}
            enrolledStudentCodes={enrolledStudentCodes}
            isLoading={recentStudents.isLoading || recentEnrollments.isLoading}
            error={recentStudents.error ?? recentEnrollments.error}
            onRetry={() => {
              recentStudents.reload();
              recentEnrollments.reload();
            }}
          />
        </CardContent>
      </Card>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
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

        <Card>
          <CardHeader>
            <CardTitle>Starting soon</CardTitle>
            <CardDescription>Upcoming batches, soonest first.</CardDescription>
          </CardHeader>
          <CardContent>
            <BatchWatchlist
              batches={batches.data}
              kind="starting-soon"
              isLoading={batches.isLoading}
              error={batches.error}
              onRetry={batches.reload}
            />
          </CardContent>
        </Card>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
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

        <Card>
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

      <p className="text-xs text-muted-foreground">
        <Link href="/admissions" className="underline hover:text-foreground">
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
