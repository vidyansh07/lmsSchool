'use client';

/**
 * Student 360 — one page, every staff role (DESIGN_DECISIONS.md, "Student
 * 360"; API_CONTRACTS.md, `GET /students/{id}/360/`).
 *
 * Purpose: the single place any staff member lands on one student — who
 * they are, where they sit (batch/trainer/counsellor), how they are doing
 * (progress, attendance, performance) and how worried anyone should be
 * (risk), plus their work queue and a timeline of everything that has
 * happened to their record. User: any staff role holding `student.view_any`
 * (the same capability `/admin/students` and the old
 * `/students/[id]/timeline` route already gated on — the 360 endpoint scopes
 * by the same `visible_students()` queryset every other student-scoped
 * endpoint uses, so this page does no authorization work of its own beyond
 * the courtesy `RequireAuth` gate).
 *
 * Primary action: none — this is a read surface. Secondary actions: open an
 * activity from the Activities tab (drawer, Phase 9), embedded actions
 * inside the Enrolment tab's `StudentPerformance`. API on load: `GET
 * /students/{id}/360/` for the header and Overview tab; each other tab loads
 * its own data lazily, only once selected (`lib/work.ts`,
 * `lib/timeline.ts`, `getBatchPerformance` via `StudentPerformance`) — one
 * call up front for the page shell, not a bundle of tab data nobody looks
 * at. State model: loading, error, denied and success on the header/
 * Overview fetch; each tab's own body carries its own loading/empty/error/
 * success beneath that. Permissions: gated by `RequireAuth
 * capability="student.view_any"`; the Enrolment tab additionally hides
 * itself when the caller lacks `performance.view_any` (the capability its
 * embedded `StudentPerformance` needs), rather than rendering a tab that can
 * only ever show a 403. Mobile: tabs and header stack full-width; the
 * `TabsList` row scrolls horizontally rather than wrapping, matching
 * `data-table`'s own horizontal-scroll convention for anything that cannot
 * usefully reflow. Confirmation requirements: none — every write on this
 * page happens inside an embedded component (the activity drawer, the
 * enrolment tab) that already owns its own confirmations.
 *
 * The tab lives in the URL (`?tab=`, DESIGN_DECISIONS.md: "Tabs load on
 * open; the URL carries the tab … so Back and sharing work") via
 * `router.push` rather than `replace` — a person switching tabs is making a
 * navigation choice, and DESIGN_DECISIONS.md asks specifically for Back to
 * step through it, not just for the URL to be shareable at rest.
 *
 * Performance and risk are Phase 12/13 placeholders (ADR-10, ADR-11): the
 * endpoint's contract already carries the final shape
 * (`performance.components`/`overall_score`, `risk.level`/`triggered`), just
 * empty until those phases start writing real numbers, so this page renders
 * the neutral empty copy the design calls for ("Not yet computed", "No risk
 * signals") rather than a zero or a fabricated score.
 */
import Link from 'next/link';
import { usePathname, useRouter, useSearchParams } from 'next/navigation';
import { Suspense, use, useEffect, useState } from 'react';
import { ChevronRight, Info } from 'lucide-react';

import { useAuth } from '@/components/auth-provider';
import { RequireAuth } from '@/components/require-auth';
import { StudentPerformance } from '@/app/manage/students/[enrollmentId]/page';
import { StudentActivitiesTab } from '@/components/students/student-activities-tab';
import { StudentTimeline } from '@/components/students/timeline';
import { EmptyState, ErrorState, LoadingState } from '@/components/states';
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { Popover, PopoverContent, PopoverHeading, PopoverTrigger } from '@/components/ui/popover';
import { Progress } from '@/components/ui/progress';
import { Stat, StatGrid } from '@/components/manage/stat';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { ApiError } from '@/lib/api';
import { Capability } from '@/lib/capabilities';
import { formatCount, formatDate, formatNumber, formatPercent, formatRelative, NO_DATA, NOT_AVAILABLE } from '@/lib/format';
import {
  FEE_STATUS_LABEL,
  FEE_STATUS_VARIANT,
  RISK_LEVEL_LABEL,
  RISK_LEVEL_VARIANT,
  RISK_SEVERITY_LABEL,
  RISK_SEVERITY_VARIANT,
} from '@/lib/labels';
import { getStudent360 } from '@/lib/student-360';
import type { Student360FeedItem, Student360Response, Student360RiskTrigger } from '@/types/api';

type TabKey = 'overview' | 'activities' | 'timeline' | 'enrollment' | 'risk';
const DEFAULT_TAB: TabKey = 'overview';
const VALID_TABS: TabKey[] = ['overview', 'activities', 'timeline', 'enrollment', 'risk'];

function isTabKey(value: string | null): value is TabKey {
  return value !== null && (VALID_TABS as string[]).includes(value);
}

function initials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return '?';
  const first = parts[0]?.[0] ?? '';
  const last = parts.length > 1 ? (parts[parts.length - 1]?.[0] ?? '') : '';
  return (first + last).toUpperCase() || '?';
}

function ScorePopover({ performance }: { performance: Student360Response['performance'] }) {
  const hasComponents = performance.components.length > 0;
  return (
    <Popover>
      <PopoverTrigger className="flex items-center gap-1.5 rounded-md border border-line bg-surface px-2.5 py-1 text-sm hover:bg-sunken">
        <span className="text-xs text-ink-muted">Score</span>
        <span className="font-semibold tabular-nums">
          {performance.overall_score === null ? 'Not yet computed' : formatPercent(performance.overall_score)}
        </span>
        <Info className="size-3.5 text-ink-muted" aria-hidden="true" />
      </PopoverTrigger>
      <PopoverContent>
        <PopoverHeading>How this score is built</PopoverHeading>
        {hasComponents ? (
          <ul className="space-y-3 text-sm">
            {performance.components.map((component) => (
              <li key={component.key}>
                <div className="flex items-center justify-between gap-3">
                  <span className="text-ink-muted">{component.label}</span>
                  <span className="tabular-nums">
                    {component.value === null ? NOT_AVAILABLE : formatPercent(component.value)}
                    <span className="ml-1 text-xs text-ink-muted">
                      {/* `weight` is a relative multiplier (`performance.weights`
                          policy), not a fraction of a whole — components do not
                          sum to any total, so this is never `formatPercent`. */}
                      (weight {formatNumber(component.weight, { maximumFractionDigits: 2 })})
                    </span>
                  </span>
                </div>
                {component.sources.length > 0 ? (
                  <ul className="mt-1.5 space-y-1 border-l border-line pl-3">
                    {component.sources.map((source, index) => (
                      // A source carries no id (ADR-10 does not require one),
                      // so the array position is the only stable key here.
                      <li key={index} className="flex items-center justify-between gap-3 text-xs text-ink-muted">
                        <span className="truncate">
                          {source.type}
                          {source.trainer ? ` · ${source.trainer}` : ''}
                        </span>
                        <span className="shrink-0 tabular-nums">
                          {source.score === null ? NOT_AVAILABLE : formatPercent(source.score)}
                          {' · '}
                          {source.date ? formatDate(source.date) : NOT_AVAILABLE}
                        </span>
                      </li>
                    ))}
                  </ul>
                ) : null}
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-sm text-ink-muted">
            Not yet computed. The performance engine (Phase 12) will populate this once it lands.
          </p>
        )}
      </PopoverContent>
    </Popover>
  );
}

function RiskPopover({ risk, onOpenTab }: { risk: Student360Response['risk']; onOpenTab: () => void }) {
  const hasTriggers = risk.triggered.length > 0;
  const badge = (
    <Badge variant={RISK_LEVEL_VARIANT[risk.level]} className="cursor-pointer transition-colors hover:opacity-80">
      {RISK_LEVEL_LABEL[risk.level]}
    </Badge>
  );
  if (!hasTriggers) return badge;
  return (
    <Popover>
      <PopoverTrigger>{badge}</PopoverTrigger>
      <PopoverContent>
        <PopoverHeading>Triggered rules</PopoverHeading>
        <ul className="space-y-2 text-sm">
          {risk.triggered.map((trigger) => (
            <li key={trigger.key} className="space-y-0.5">
              <div className="flex items-center gap-2">
                <p className="font-medium">{trigger.label}</p>
                <Badge variant={RISK_SEVERITY_VARIANT[trigger.severity]}>{RISK_SEVERITY_LABEL[trigger.severity]}</Badge>
              </div>
              <p className="text-ink-muted">{trigger.detail}</p>
            </li>
          ))}
        </ul>
        <button
          type="button"
          onClick={onOpenTab}
          className="mt-2 text-sm text-action underline-offset-2 hover:underline"
        >
          Open the Risk tab for full details
        </button>
      </PopoverContent>
    </Popover>
  );
}

function FeedList({
  items,
  emptyLabel,
  dateField,
}: {
  items: Student360FeedItem[];
  emptyLabel: string;
  dateField: 'occurred_at' | 'due_at';
}) {
  if (items.length === 0) return <p className="text-sm text-ink-muted">{emptyLabel}</p>;
  return (
    <ul className="divide-y divide-line">
      {items.map((item) => {
        const when = dateField === 'occurred_at' ? item.occurred_at : item.due_at;
        const row = (
          <div className="flex items-center justify-between gap-3 py-2 text-sm">
            <span className="truncate font-medium text-ink">{item.title}</span>
            <span className="shrink-0 text-xs text-ink-muted">
              {when ? formatRelative(when) : NOT_AVAILABLE}
            </span>
          </div>
        );
        return <li key={item.id}>{item.href ? <Link href={item.href}>{row}</Link> : row}</li>;
      })}
    </ul>
  );
}

function Header({ data, onOpenRiskTab }: { data: Student360Response; onOpenRiskTab: () => void }) {
  const name = data.profile.user.full_name || data.profile.user.email;
  return (
    <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
      <div className="flex items-center gap-3">
        <Avatar size="lg">
          {data.profile.user.profile_image_url ? (
            <AvatarImage src={data.profile.user.profile_image_url} alt={name} />
          ) : null}
          <AvatarFallback>{initials(name)}</AvatarFallback>
        </Avatar>
        <div className="min-w-0 space-y-0.5">
          <h1 className="truncate text-2xl font-semibold tracking-tight">{name}</h1>
          <p className="truncate text-sm text-ink-muted">
            <span className="font-mono text-xs">{data.profile.student_id}</span>
            {' · '}
            {data.batch ? data.batch.name : 'No batch assigned'}
            {' · '}
            Trainer: {data.trainer ? data.trainer.name : NOT_AVAILABLE}
            {' · '}
            Counsellor: {data.counsellor ? data.counsellor.name : NOT_AVAILABLE}
          </p>
        </div>
      </div>
      <div className="flex shrink-0 items-center gap-2">
        <ScorePopover performance={data.performance} />
        <RiskPopover risk={data.risk} onOpenTab={onOpenRiskTab} />
      </div>
    </div>
  );
}

function OverviewTab({ data }: { data: Student360Response }) {
  return (
    <div className="space-y-6">
      <Card>
        <CardContent className="space-y-4 pt-5">
          <div className="flex items-center justify-between gap-3">
            <p className="text-sm font-medium text-ink">Course progress</p>
            <p className="text-sm text-ink-muted">
              {data.progress
                ? `${formatCount(data.progress.completed_lessons, 'lesson')} of ${formatCount(data.progress.total_lessons, 'lesson')}`
                : NO_DATA}
            </p>
          </div>
          {data.progress ? (
            <Progress label="Course progress" value={data.progress.percent} max={100} />
          ) : (
            <p className="text-sm text-ink-muted">No progress data yet.</p>
          )}
          <div className="flex items-center justify-between gap-3 border-t border-line pt-4">
            <p className="text-sm font-medium text-ink">Attendance</p>
            <p className="text-sm text-ink-muted">
              {data.attendance_summary.has_records
                ? `${formatPercent(data.attendance_summary.percent)} · ${formatCount(
                    data.attendance_summary.attended,
                    'session',
                  )} of ${formatCount(data.attendance_summary.total_sessions, 'session')}`
                : 'No attendance recorded yet'}
            </p>
          </div>
          <div className="flex items-center justify-between gap-3 border-t border-line pt-4">
            <p className="text-sm font-medium text-ink">Fee status</p>
            <Badge variant={FEE_STATUS_VARIANT[data.fee_status]}>{FEE_STATUS_LABEL[data.fee_status]}</Badge>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardContent className="pt-5">
          <p className="mb-3 text-sm font-medium text-ink">Work in progress</p>
          <StatGrid>
            <Stat label="Open activities" value={formatNumberOrDash(data.counts.activities_open)} />
            <Stat
              label="Overdue"
              value={formatNumberOrDash(data.counts.activities_overdue)}
              tone={data.counts.activities_overdue > 0 ? 'warning' : 'default'}
            />
            <Stat label="Assessments" value={formatNumberOrDash(data.counts.assessments)} />
            <Stat label="Assignments" value={formatNumberOrDash(data.counts.assignments)} />
            <Stat label="Projects" value={formatNumberOrDash(data.counts.projects)} />
          </StatGrid>
        </CardContent>
      </Card>

      <div className="grid gap-6 lg:grid-cols-2">
        <Card>
          <CardContent className="pt-5">
            <p className="mb-2 text-sm font-medium text-ink">Recent activity</p>
            <FeedList items={data.recent_activities} emptyLabel="No recent activity." dateField="occurred_at" />
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-5">
            <p className="mb-2 text-sm font-medium text-ink">Next actions</p>
            <FeedList
              items={data.next_actions}
              emptyLabel="Nothing suggested yet. Automation (Phase 14) will populate this."
              dateField="due_at"
            />
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

// `Stat`'s own contract wants an already-formatted string; a plain count has
// no unit worth pluralising here, so this is the one-line equivalent of
// `formatNumber` for the five counters above.
function formatNumberOrDash(value: number): string {
  return Number.isFinite(value) ? value.toLocaleString() : NO_DATA;
}

function EnrollmentTab({ data }: { data: Student360Response }) {
  const { can } = useAuth();
  if (!can(Capability.performanceViewAny)) {
    return (
      <EmptyState
        title="Not available"
        description="Your role does not include access to enrolment performance details."
      />
    );
  }
  if (!data.enrollment) {
    return <EmptyState title="No enrolment on record" description="This student has no enrolment yet." />;
  }
  return <StudentPerformance enrollmentId={data.enrollment.id} variant="embedded" />;
}

// One triggered rule's row, plus a collapsible "numbers" disclosure — a
// native <details>/<summary> rather than a new primitive: this codebase's
// `components/ui/*` has no collapsible yet, and this is the only place that
// needs one, for one purpose (showing the raw inputs a rule computed from).
function RiskOutcomeRow({ trigger }: { trigger: Student360RiskTrigger }) {
  const numberEntries = trigger.numbers ? Object.entries(trigger.numbers) : [];
  return (
    <li className="space-y-1.5 border-b border-line py-3 last:border-b-0">
      <div className="flex items-center gap-2">
        <p className="font-medium text-ink">{trigger.label}</p>
        <Badge variant={RISK_SEVERITY_VARIANT[trigger.severity]}>{RISK_SEVERITY_LABEL[trigger.severity]}</Badge>
      </div>
      <p className="text-sm text-ink-muted">{trigger.detail}</p>
      {numberEntries.length > 0 ? (
        <details className="text-xs text-ink-muted">
          <summary className="cursor-pointer select-none hover:text-ink">Numbers</summary>
          <dl className="mt-1.5 space-y-1 border-l border-line pl-3">
            {numberEntries.map(([key, value]) => (
              <div key={key} className="flex items-center justify-between gap-3">
                <dt className="capitalize">{key.replace(/_/g, ' ')}</dt>
                <dd className="tabular-nums text-ink">{value === null ? NOT_AVAILABLE : String(value)}</dd>
              </div>
            ))}
          </dl>
        </details>
      ) : null}
    </li>
  );
}

function RiskTab({ data }: { data: Student360Response }) {
  const { level, triggered } = data.risk;
  return (
    <Card>
      <CardContent className="space-y-4 pt-5">
        <div className="flex items-center justify-between gap-3">
          <p className="text-sm font-medium text-ink">Current risk level</p>
          <Badge variant={RISK_LEVEL_VARIANT[level]}>{RISK_LEVEL_LABEL[level]}</Badge>
        </div>
        {triggered.length === 0 ? (
          <p className="border-t border-line pt-4 text-sm text-ink-muted">
            No risk signals. None of the risk rules (attendance, assessment average, missed assignments, course
            progress) are currently triggered for this student.
          </p>
        ) : (
          <ul className="border-t border-line">
            {triggered.map((trigger) => (
              <RiskOutcomeRow key={trigger.key} trigger={trigger} />
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}

// Exported (not just the default page below) so the unit test can render it
// directly with a plain `studentId` prop — `app/manage/students/
// [enrollmentId]/page.tsx`'s `StudentPerformance` is the same convention,
// sidestepping `use(params)`, `Suspense` and `RequireAuth` in a test that is
// really about this component's own states and tab wiring.
export function Student360Content({ studentId }: { studentId: string }) {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const requestedTab = searchParams.get('tab');
  const tab: TabKey = isTabKey(requestedTab) ? requestedTab : DEFAULT_TAB;

  // `reloadToken` folds a manual retry into the same request identity as the
  // initial load (mirrors `hooks/use-api.ts`'s `requestKey` and
  // `student-activities-tab.tsx`'s `key`): the render body below reacts to a
  // changed key synchronously, and the effect underneath only ever calls
  // `setState` from inside a promise callback, never directly in its own
  // body — the shape `react-hooks/set-state-in-effect` requires.
  const [reloadToken, setReloadToken] = useState(0);
  const key = `${studentId}#${reloadToken}`;
  const [state, setState] = useState<{ key: string; data: Student360Response | null; error: ApiError | null }>({
    key,
    data: null,
    error: null,
  });
  if (state.key !== key) {
    setState({ key, data: null, error: null });
  }
  const { data, error } = state;

  useEffect(() => {
    let cancelled = false;
    getStudent360(studentId)
      .then((response) => {
        if (!cancelled) setState({ key, data: response, error: null });
      })
      .catch((cause: unknown) => {
        if (!cancelled) {
          setState({
            key,
            data: null,
            error: cause instanceof ApiError ? cause : new ApiError(0, 'unknown_error', 'The request failed.', ''),
          });
        }
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);

  function load() {
    setReloadToken((value) => value + 1);
  }

  function setTab(next: TabKey) {
    const params = new URLSearchParams(searchParams.toString());
    params.set('tab', next);
    router.push(`${pathname}?${params.toString()}`);
  }

  if (error) {
    if (error.status === 404) {
      return (
        <EmptyState
          title="Student not found"
          description="This student does not exist, or their record is not available to you."
          action={
            <Button asChild variant="outline">
              <Link href="/admin/students">Back to students</Link>
            </Button>
          }
        />
      );
    }
    return (
      <ErrorState
        title="Could not load this student"
        message={error.message}
        requestId={error.requestId || undefined}
        onRetry={load}
      />
    );
  }

  if (!data) return <LoadingState label="Loading student…" rows={6} />;

  const name = data.profile.user.full_name || data.profile.user.email;

  return (
    <div className="space-y-6">
      <nav aria-label="Breadcrumb" className="flex items-center gap-1.5 text-sm">
        <Link href="/admin/students" className="text-ink-muted transition-colors hover:text-ink">
          Students
        </Link>
        <ChevronRight className="size-3.5 text-ink-muted/60" aria-hidden="true" />
        <span aria-current="page" className="truncate font-medium text-ink">
          {name}
        </span>
      </nav>

      <Header data={data} onOpenRiskTab={() => setTab('risk')} />

      <Tabs value={tab} onValueChange={(value) => setTab(value as TabKey)}>
        <TabsList>
          <TabsTrigger value="overview">Overview</TabsTrigger>
          <TabsTrigger value="activities">Activities</TabsTrigger>
          <TabsTrigger value="timeline">Timeline</TabsTrigger>
          <TabsTrigger value="enrollment">Enrolment</TabsTrigger>
          <TabsTrigger value="risk">Risk</TabsTrigger>
        </TabsList>

        <TabsContent value="overview">
          <OverviewTab data={data} />
        </TabsContent>
        <TabsContent value="activities">
          <StudentActivitiesTab studentId={studentId} />
        </TabsContent>
        <TabsContent value="timeline">
          <StudentTimeline studentId={studentId} />
        </TabsContent>
        <TabsContent value="enrollment">
          <EnrollmentTab data={data} />
        </TabsContent>
        <TabsContent value="risk">
          <RiskTab data={data} />
        </TabsContent>
      </Tabs>
    </div>
  );
}

export default function Student360Page({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  return (
    <RequireAuth capability={Capability.studentViewAny}>
      <Suspense fallback={<LoadingState label="Loading student…" rows={6} />}>
        <Student360Content studentId={id} />
      </Suspense>
    </RequireAuth>
  );
}
