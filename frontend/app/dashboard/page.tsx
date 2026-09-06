'use client';

/**
 * The signed-in landing page — routed by role, per `Dashboard` below.
 *
 * The trainer branch (`TrainerView`) and the routing/loading/error shell
 * around both branches are untouched from the original build; only
 * `StudentView` was rebuilt. A student opens this to answer two questions —
 * "what do I owe" and "am I OK" — so it leads with pending work and the next
 * week's classes and deadlines, then standing (progress, attendance,
 * assessment average, risk flags shown as information rather than a
 * verdict), then everything else the brief asks for: courses, batches,
 * certificates, feedback and notifications.
 *
 * The primary payload (`StudentDashboard`, from `/api/v1/dashboard/student/`)
 * still drives courses/batches/continue-learning/upcoming-classes exactly as
 * before. Everything the rebuild adds — pending work, standing, certificates,
 * feedback, notifications — is a *secondary* fetch, each independent of the
 * others via `useDashboardSection` below: a slow or failing endpoint for one
 * of those must never blank out the primary content or the other secondary
 * sections, which is why there are five small loading/error units on this
 * page instead of one that gates everything.
 */

import Link from 'next/link';
import { useCallback, useEffect, useState } from 'react';
import { BookOpen, CalendarClock, ClipboardList, GraduationCap, PlayCircle, TrendingUp, Users } from 'lucide-react';

import { useAuth } from '@/components/auth-provider';
import { ProgressBar } from '@/components/progress-bar';
import { RequireAuth } from '@/components/require-auth';
import { EmptyState, ErrorState, LoadingState } from '@/components/states';
import { CertificatesPanel } from '@/components/student/certificates-panel';
import { FeedbackPanel } from '@/components/student/feedback-panel';
import { NotificationsPanel } from '@/components/student/notifications-panel';
import { PendingWorkPanel, tallyAssignments, tallyProjects } from '@/components/student/pending-work-panel';
import { StandingPanel, collectRiskItems } from '@/components/student/standing-panel';
import { UpcomingTimeline } from '@/components/student/upcoming-timeline';
import { Alert } from '@/components/ui/alert';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { ApiError } from '@/lib/api';
import { listMyAssignments } from '@/lib/assignments';
import { getStudentDashboard, getTrainerDashboard } from '@/lib/batches';
import {
  BATCH_STATUS_LABEL,
  BATCH_STATUS_VARIANT,
  ENROLLMENT_STATUS_LABEL,
  ENROLLMENT_STATUS_VARIANT,
  formatDate,
  formatEventDay,
  formatEventTime,
} from '@/lib/batch-labels';
import { listNotifications } from '@/lib/communication';
import { getMyPerformance, listMyFeedback, type PerformanceFeedback, type StudentPerformanceEntry } from '@/lib/performance';
import { listMyCertificates } from '@/lib/progress';
import { listMyProjects } from '@/lib/projects';
import type {
  AppNotification,
  CalendarEvent,
  Certificate,
  StudentAssignment,
  StudentDashboard,
  StudentProject,
  TrainerDashboard,
} from '@/types/api';

function ClassList({ events, empty }: { events: CalendarEvent[]; empty: string }) {
  if (events.length === 0) return <p className="text-sm text-muted-foreground">{empty}</p>;
  return (
    <ul className="divide-y divide-border">
      {events.map((event, index) => (
        <li key={`${event.start}-${index}`} className="flex flex-wrap items-center gap-3 py-2 text-sm">
          <span className="w-24 shrink-0 text-muted-foreground">
            {formatEventDay(event.start)}
          </span>
          {!event.all_day ? (
            <span className="w-16 shrink-0 text-muted-foreground">
              {formatEventTime(event.start)}
            </span>
          ) : null}
          <span className="min-w-0 flex-1 truncate">{event.title}</span>
          {event.location ? (
            <span className="text-xs text-muted-foreground">{event.location}</span>
          ) : null}
        </li>
      ))}
    </ul>
  );
}

/**
 * One dashboard section's load state, kept independent of every other
 * section's. A student dashboard composes half a dozen endpoints (pending
 * work, standing, certificates, feedback, notifications) on top of the
 * primary payload above; if one of those is slow or down, the rest of the
 * page — and in particular "what do I owe", the section that matters most —
 * must still render.
 */
interface SectionState<T> {
  data: T;
  error: ApiError | null;
  isLoading: boolean;
  reload: () => void;
}

/**
 * Loads one dashboard section. Not `hooks/use-api.ts`: that hook fetches a
 * single GET path directly, and every section here composes two endpoints (or
 * post-processes one), which a bare path string cannot express. Modelled on
 * the same shape regardless — data/error/isLoading/reload — so every panel
 * below is driven exactly the way `PendingActions`, `AlertList` and
 * `DataTable` already expect to be.
 */
function useDashboardSection<T>(loader: () => Promise<T>, empty: T): SectionState<T> {
  const [attempt, setAttempt] = useState(0);
  const [state, setState] = useState<{ data: T; error: ApiError | null; isLoading: boolean; attempt: number }>(
    { data: empty, error: null, isLoading: true, attempt },
  );

  // The reset-on-refetch this used to do at the top of the effect below is
  // exactly the pattern `hooks/use-list.ts` and `hooks/use-api.ts` both avoid,
  // for the same reason theirs do: a `setState` that runs unconditionally the
  // instant an effect fires is a synchronous write inside that effect, and
  // React (and this repo's lint config) flags it as the cascading-render
  // anti-pattern it is. Comparing `attempt` here, during render, is the
  // sanctioned alternative both of those hooks already use.
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
    // `loader` closes over no per-render props for every call site below — it
    // always fetches the same caller-scoped "mine" endpoints — so `attempt` is
    // the only thing that should re-trigger this effect.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [attempt]);

  const reload = useCallback(() => setAttempt((value) => value + 1), []);
  return { data: state.data, error: state.error, isLoading: state.isLoading, reload };
}

function pluralize(count: number, singular: string, plural: string): string {
  return count === 1 ? singular : plural;
}

/** "What do I owe, and am I OK?" as one line, once there is enough loaded to answer it. */
function buildStatusLine(pendingTotal: number, riskCount: number): string {
  if (pendingTotal === 0 && riskCount === 0) {
    return "You're all caught up, and everything looks on track.";
  }
  const pendingPhrase = `${pendingTotal} ${pluralize(pendingTotal, 'thing', 'things')} waiting on you`;
  if (riskCount === 0) {
    return `${pendingPhrase} — otherwise, you're on track.`;
  }
  const riskPhrase = `${riskCount} ${pluralize(riskCount, 'thing', 'things')} below worth a look`;
  if (pendingTotal === 0) {
    return `Nothing is waiting on you right now, but ${riskPhrase}.`;
  }
  return `${pendingPhrase}, and ${riskPhrase}.`;
}

export function StudentView({ data }: { data: StudentDashboard }) {
  const assignments = useDashboardSection(
    () => listMyAssignments({ page_size: 100, ordering: 'due_at' }).then((page) => page.results),
    [] as StudentAssignment[],
  );
  const projects = useDashboardSection(
    () => listMyProjects({ page_size: 100, ordering: 'end_date' }).then((page) => page.results),
    [] as StudentProject[],
  );
  const performance = useDashboardSection(() => getMyPerformance(), [] as StudentPerformanceEntry[]);
  const certificates = useDashboardSection(() => listMyCertificates(), [] as Certificate[]);
  const feedback = useDashboardSection(() => listMyFeedback(), [] as PerformanceFeedback[]);
  const notifications = useDashboardSection(
    () =>
      // The dashboard only ever shows a short preview, so the default page
      // size is sliced down further client-side rather than asking the
      // endpoint for a size it does not expose a parameter for; `count` still
      // carries the true total regardless of how many rows came back.
      listNotifications({ unread: 'true' }).then((page) => ({
        items: page.results.slice(0, 5),
        unread: page.count,
      })),
    { items: [] as AppNotification[], unread: 0 },
  );

  const pendingLoaded = !assignments.isLoading && !projects.isLoading;
  const pendingFailed = Boolean(assignments.error || projects.error);
  const pendingTotal =
    tallyAssignments(assignments.data).count + tallyProjects(projects.data).count;
  const riskCount = collectRiskItems(performance.data).length;
  const showStatusLine = pendingLoaded && !pendingFailed && !performance.isLoading && !performance.error;

  return (
    <div className="space-y-6">
      {showStatusLine ? (
        <p aria-live="polite" className="text-sm text-muted-foreground">
          {buildStatusLine(pendingTotal, riskCount)}
        </p>
      ) : null}

      {data.continue_learning?.last_lesson_id ? (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <PlayCircle className="size-5 text-primary" aria-hidden="true" />
              Continue learning
            </CardTitle>
            <CardDescription>{data.continue_learning.course_title}</CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            <p className="text-sm font-medium">{data.continue_learning.last_lesson_title}</p>
            <ProgressBar
              percent={data.continue_learning.progress_percent}
              label={`${data.continue_learning.completed_lessons} of ${data.continue_learning.total_lessons} lessons complete`}
            />
            <Button asChild size="sm">
              <Link
                href={`/courses/${data.continue_learning.course_slug}/learn/${data.continue_learning.last_lesson_id}`}
              >
                Resume
              </Link>
            </Button>
          </CardContent>
        </Card>
      ) : null}

      <section className="space-y-3">
        <h2 className="text-lg font-semibold tracking-tight">Next up</h2>
        <div className="grid gap-4 lg:grid-cols-2">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <ClipboardList className="size-5 text-primary" aria-hidden="true" />
                Pending work
              </CardTitle>
              <CardDescription>Assignments and projects still needing you.</CardDescription>
            </CardHeader>
            <CardContent>
              <PendingWorkPanel
                assignments={assignments.data}
                projects={projects.data}
                isLoading={assignments.isLoading || projects.isLoading}
                error={assignments.error ?? projects.error}
                onRetry={() => {
                  assignments.reload();
                  projects.reload();
                }}
              />
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <CalendarClock className="size-5 text-primary" aria-hidden="true" />
                Coming up
              </CardTitle>
              <CardDescription>Classes and deadlines over the next week.</CardDescription>
            </CardHeader>
            <CardContent>
              <UpcomingTimeline events={data.upcoming_classes} />
              <Button asChild variant="ghost" size="sm" className="mt-2">
                <Link href="/calendar">Open the calendar</Link>
              </Button>
            </CardContent>
          </Card>
        </div>
      </section>

      <section className="space-y-3">
        <h2 className="flex items-center gap-2 text-lg font-semibold tracking-tight">
          <TrendingUp className="size-5 text-primary" aria-hidden="true" />
          How you&apos;re doing
        </h2>
        <StandingPanel
          performance={performance.data}
          isLoading={performance.isLoading}
          error={performance.error}
          onRetry={performance.reload}
        />
      </section>

      <section className="space-y-3">
        <h2 className="text-lg font-semibold tracking-tight">My courses</h2>
        {data.courses.length === 0 ? (
          <EmptyState
            title="No active courses"
            description="You are not currently enrolled on a course. Browse the catalogue to see what is available."
            action={
              <Button asChild variant="outline">
                <Link href="/courses">Browse courses</Link>
              </Button>
            }
          />
        ) : (
          <div className="grid gap-4 sm:grid-cols-2">
            {data.courses.map((course) => (
              <Card key={course.enrollment_id}>
                <CardHeader className="gap-1">
                  <CardTitle>
                    <Link
                      href={`/courses/${course.course_slug}`}
                      className="hover:text-primary"
                    >
                      {course.course_title}
                    </Link>
                  </CardTitle>
                  <CardDescription className="font-mono text-xs">
                    {course.batch_code} · {course.batch_name}
                  </CardDescription>
                </CardHeader>
                <CardContent className="space-y-3">
                  <ProgressBar
                    percent={course.progress_percent}
                    label={`${course.completed_lessons} of ${course.total_lessons} lessons`}
                  />
                  {course.last_lesson_id ? (
                    <Button asChild variant="outline" size="sm">
                      <Link
                        href={`/courses/${course.course_slug}/learn/${course.last_lesson_id}`}
                      >
                        Continue
                      </Link>
                    </Button>
                  ) : (
                    <Button asChild variant="outline" size="sm">
                      <Link href={`/courses/${course.course_slug}`}>Open course</Link>
                    </Button>
                  )}
                </CardContent>
              </Card>
            ))}
          </div>
        )}
      </section>

      <section className="space-y-3">
        <h2 className="text-lg font-semibold tracking-tight">More for you</h2>
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <GraduationCap className="size-5 text-primary" aria-hidden="true" />
                My batches
              </CardTitle>
            </CardHeader>
            <CardContent>
              {data.batches.length === 0 ? (
                <p className="text-sm text-muted-foreground">No batches yet.</p>
              ) : (
                <ul className="divide-y divide-border text-sm">
                  {data.batches.map((batch) => (
                    <li key={batch.id} className="flex flex-wrap items-center gap-2 py-2">
                      <span className="min-w-0 flex-1 truncate">{batch.name}</span>
                      {batch.enrollment_status ? (
                        <Badge variant={ENROLLMENT_STATUS_VARIANT[batch.enrollment_status]}>
                          {ENROLLMENT_STATUS_LABEL[batch.enrollment_status]}
                        </Badge>
                      ) : null}
                    </li>
                  ))}
                </ul>
              )}
              <Button asChild variant="ghost" size="sm" className="mt-2">
                <Link href="/my-batches">All my batches</Link>
              </Button>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Certificates</CardTitle>
            </CardHeader>
            <CardContent>
              <CertificatesPanel
                certificates={certificates.data}
                isLoading={certificates.isLoading}
                error={certificates.error}
                onRetry={certificates.reload}
              />
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Feedback</CardTitle>
              <CardDescription>From your trainers and managers.</CardDescription>
            </CardHeader>
            <CardContent>
              <FeedbackPanel
                feedback={feedback.data}
                isLoading={feedback.isLoading}
                error={feedback.error}
                onRetry={feedback.reload}
              />
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Notifications</CardTitle>
            </CardHeader>
            <CardContent>
              <NotificationsPanel
                notifications={notifications.data.items}
                unreadCount={notifications.data.unread}
                isLoading={notifications.isLoading}
                error={notifications.error}
                onRetry={notifications.reload}
              />
            </CardContent>
          </Card>
        </div>
      </section>
    </div>
  );
}

function TrainerView({ data }: { data: TrainerDashboard }) {
  return (
    <div className="space-y-6">
      <div className="grid gap-4 sm:grid-cols-3">
        <Card>
          <CardHeader className="gap-1">
            <CardDescription>Assigned batches</CardDescription>
            <CardTitle className="text-2xl">{data.batches.length}</CardTitle>
          </CardHeader>
        </Card>
        <Card>
          <CardHeader className="gap-1">
            <CardDescription>Students</CardDescription>
            <CardTitle className="text-2xl">{data.student_count}</CardTitle>
          </CardHeader>
        </Card>
        <Card>
          <CardHeader className="gap-1">
            <CardDescription>Courses taught</CardDescription>
            <CardTitle className="text-2xl">{data.courses.length}</CardTitle>
          </CardHeader>
        </Card>
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <CalendarClock className="size-5 text-primary" aria-hidden="true" />
              Today
            </CardTitle>
          </CardHeader>
          <CardContent>
            <ClassList events={data.today_classes} empty="No classes today." />
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>This week</CardTitle>
          </CardHeader>
          <CardContent>
            <ClassList events={data.upcoming_classes} empty="Nothing in the next week." />
          </CardContent>
        </Card>
      </div>

      <section className="space-y-3">
        <h2 className="flex items-center gap-2 text-lg font-semibold tracking-tight">
          <Users className="size-5 text-primary" aria-hidden="true" />
          My batches
        </h2>
        {data.batches.length === 0 ? (
          <EmptyState
            title="No batches assigned"
            description="An administrator assigns the batches you teach."
          />
        ) : (
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {data.batches.map((batch) => (
              <Card key={batch.id}>
                <CardHeader className="gap-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <Badge variant={BATCH_STATUS_VARIANT[batch.status]}>
                      {BATCH_STATUS_LABEL[batch.status]}
                    </Badge>
                    <span className="font-mono text-xs text-muted-foreground">{batch.code}</span>
                  </div>
                  <CardTitle>
                    <Link href={`/admin/batches/${batch.id}`} className="hover:text-primary">
                      {batch.name}
                    </Link>
                  </CardTitle>
                  <CardDescription>{batch.course_title}</CardDescription>
                </CardHeader>
                <CardContent className="space-y-1 text-sm text-muted-foreground">
                  <p>
                    {formatDate(batch.start_date)} – {formatDate(batch.end_date)}
                  </p>
                  <p>
                    {batch.enrolled_count ?? 0} of {batch.capacity ?? 0} seats taken
                  </p>
                </CardContent>
              </Card>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}

export function Dashboard() {
  const { user } = useAuth();
  const isTrainer = user?.role === 'trainer';
  const [attempt, setAttempt] = useState(0);
  // Identifies one fetch: which dashboard, and which retry. Comparing it
  // during render (below) rather than resetting state from inside the effect
  // is the same pattern `hooks/use-list.ts` and `hooks/use-api.ts` use, and
  // for the same reason — an unconditional `setState` at the top of an effect
  // body reads as a synchronous write inside that effect, which this repo's
  // lint config (correctly) refuses.
  const requestKey = `${isTrainer}#${attempt}`;

  const [state, setState] = useState<{
    student: StudentDashboard | null;
    trainer: TrainerDashboard | null;
    error: ApiError | null;
    isLoading: boolean;
    requestKey: string;
  }>({ student: null, trainer: null, error: null, isLoading: true, requestKey });

  if (state.requestKey !== requestKey) {
    setState({ student: null, trainer: null, error: null, isLoading: true, requestKey });
  }

  useEffect(() => {
    let cancelled = false;
    const load = isTrainer ? getTrainerDashboard() : getStudentDashboard();

    load
      .then((result) => {
        if (cancelled) return;
        setState((current) =>
          isTrainer
            ? { ...current, trainer: result as TrainerDashboard, error: null, isLoading: false }
            : { ...current, student: result as StudentDashboard, error: null, isLoading: false },
        );
      })
      .catch((cause: unknown) => {
        if (!cancelled) {
          setState((current) => ({
            ...current,
            error: cause instanceof ApiError ? cause : null,
            isLoading: false,
          }));
        }
      });

    return () => {
      cancelled = true;
    };
    // `requestKey` already encodes `isTrainer`; including it too would be
    // redundant, not a missing dependency.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [requestKey]);

  const { student, trainer, error, isLoading } = state;

  if (isLoading) return <LoadingState label="Loading your dashboard…" rows={6} />;
  if (error) {
    return (
      <ErrorState
        title="Could not load your dashboard"
        message={error.message}
        requestId={error.requestId || undefined}
        onRetry={() => setAttempt((value) => value + 1)}
      />
    );
  }

  return (
    <div className="space-y-6">
      <div className="space-y-1">
        <h1 className="text-2xl font-semibold tracking-tight">
          Welcome back, {user?.first_name || user?.email}
        </h1>
        <p className="text-sm text-muted-foreground">
          {isTrainer ? 'Your batches, classes and students.' : 'Your courses, classes and progress.'}
        </p>
      </div>

      {isTrainer && trainer ? (
        trainer.is_trainer ? (
          <TrainerView data={trainer} />
        ) : (
          <Alert variant="info">Your trainer profile is not set up yet.</Alert>
        )
      ) : null}

      {!isTrainer && student ? (
        student.is_student ? (
          <StudentView data={student} />
        ) : (
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <BookOpen className="size-5 text-primary" aria-hidden="true" />
                Nothing to show here
              </CardTitle>
              <CardDescription>
                This dashboard is for students. Administrators manage the platform from the
                sections in the navigation.
              </CardDescription>
            </CardHeader>
            <CardContent>
              <Button asChild variant="outline">
                <Link href="/admin/batches">Go to batches</Link>
              </Button>
            </CardContent>
          </Card>
        )
      ) : null}
    </div>
  );
}

export default function DashboardPage() {
  return (
    <RequireAuth>
      <Dashboard />
    </RequireAuth>
  );
}
