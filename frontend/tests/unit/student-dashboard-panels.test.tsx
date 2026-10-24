/**
 * Unit coverage for the student dashboard's pure computations and its
 * presentational panels, each driven directly by props rather than through a
 * page render. Every panel here is a dumb component (no fetching of its
 * own), so these tests need no `lib/*` mocking at all — a prop in, rendered
 * text out — which keeps them fast and keeps a failure pointing at exactly
 * the piece that broke.
 *
 * The null-handling tests below are the ones the brief calls the most
 * valuable in the file: a brand-new student is every list empty and every
 * number absent at once, and this file checks that combination exhaustively
 * rather than trusting each panel's individual empty branch in isolation.
 */
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { CertificatesPanel } from '@/components/student/certificates-panel';
import { FeedbackPanel } from '@/components/student/feedback-panel';
import { FeesPanel } from '@/components/student/fees-panel';
import { NotificationsPanel } from '@/components/student/notifications-panel';
import {
  PendingWorkPanel,
  tallyAssignments,
  tallyProjects,
} from '@/components/student/pending-work-panel';
import { StandingPanel, averageMetric, collectRiskItems } from '@/components/student/standing-panel';
import { UpcomingTimeline } from '@/components/student/upcoming-timeline';
import { ApiError } from '@/lib/api';
import type { StudentPerformanceEntry } from '@/lib/performance';
import type {
  AppNotification,
  CalendarEvent,
  Certificate,
  FeePayment,
  FeePlan,
  StudentAssignment,
  StudentFeeSummary,
  StudentProject,
  Submission,
} from '@/types/api';

// --- Fixture builders --------------------------------------------------

function submission(overrides: Partial<Submission> = {}): Submission {
  return {
    id: 'sub-1',
    assignment: 'assign-1',
    assignment_code: 'GRS-A-001',
    assignment_title: 'Essay',
    attempt: 1,
    status: 'submitted',
    text_answer: '',
    link_url: '',
    submitted_at: '2026-03-01T10:00:00Z',
    is_late: false,
    marks_awarded: null,
    max_marks: '100',
    is_passing: null,
    feedback: '',
    graded_at: null,
    files: [],
    created_at: '2026-03-01T10:00:00Z',
    ...overrides,
  };
}

function assignment(overrides: Partial<StudentAssignment> = {}): StudentAssignment {
  return {
    id: 'assign-1',
    code: 'GRS-A-001',
    course: 'course-1',
    course_title: 'Linux Essentials',
    module: null,
    lesson: null,
    title: 'Shell scripting',
    instructions: '',
    submission_kind: 'file',
    max_marks: '100',
    passing_marks: '40',
    due_at: '2026-04-01T23:59:00Z',
    allow_late: false,
    late_cutoff_at: null,
    allow_resubmission: false,
    max_attempts: 1,
    status: 'published',
    is_open: true,
    attachments: [],
    my_submission: null,
    ...overrides,
  };
}

function project(overrides: Partial<StudentProject> = {}): StudentProject {
  return {
    id: 'proj-1',
    code: 'GRS-P-001',
    course: 'course-1',
    course_title: 'Linux Essentials',
    module: null,
    module_title: null,
    batch: null,
    batch_code: null,
    title: 'Capstone build',
    description: '',
    instructions: '',
    deliverables: '',
    kind: 'major',
    is_required: true,
    start_date: '2026-03-01',
    end_date: '2026-05-01',
    requires_repository_url: false,
    requires_deployment_url: false,
    max_marks: '100',
    passing_marks: '40',
    rubric: [],
    reviewer: null,
    reviewer_name: null,
    status: 'published',
    published_at: '2026-02-01',
    is_open: true,
    assigned_count: 1,
    created_at: '2026-02-01',
    updated_at: '2026-02-01',
    my_work: null,
    ...overrides,
  };
}

function performanceEntry(overrides: Partial<StudentPerformanceEntry> = {}): StudentPerformanceEntry {
  return {
    enrollment_id: 'enrol-1',
    course_title: 'Linux Essentials',
    batch_code: 'GRS-B-001',
    attendance: { percent: null, total_sessions: 0, attended: 0, has_records: false },
    assessment: { average_percent: null, sitting_percent: null, recorded: 0, total: 0 },
    assignments: { percent: null, total: 0, submitted: 0, graded: 0, passed: 0, missed: 0 },
    projects: { percent: null, required: 0, finished: 0 },
    progress: { percent: null, expected_percent: null, variance: null },
    overall_score: null,
    risk: { at_risk: false, outcomes: [], triggered: [], triggered_count: 0 },
    counts: { components_measured: 0, risk_flags: 0 },
    ...overrides,
  };
}

const apiError = new ApiError(500, 'server_error', 'The server exploded.', 'req-42');

// --- tallyAssignments / tallyProjects -----------------------------------

describe('tallyAssignments', () => {
  it('counts an open assignment with no submission as outstanding', () => {
    expect(tallyAssignments([assignment({ my_submission: null })]).count).toBe(1);
  });

  it('counts a returned submission as outstanding (needs rework)', () => {
    const tally = tallyAssignments([assignment({ my_submission: submission({ status: 'returned' }) })]);
    expect(tally.count).toBe(1);
  });

  it('does not count a graded submission as outstanding', () => {
    const tally = tallyAssignments([assignment({ my_submission: submission({ status: 'graded' }) })]);
    expect(tally.count).toBe(0);
  });

  it('does not count a closed assignment even with no submission', () => {
    const tally = tallyAssignments([assignment({ is_open: false, my_submission: null })]);
    expect(tally.count).toBe(0);
  });

  it('counts a resubmittable submitted attempt under the attempt limit', () => {
    const tally = tallyAssignments([
      assignment({
        allow_resubmission: true,
        max_attempts: 3,
        my_submission: submission({ status: 'submitted', attempt: 1 }),
      }),
    ]);
    expect(tally.count).toBe(1);
  });

  it('marks an outstanding assignment overdue once its due date has passed', () => {
    const tally = tallyAssignments([assignment({ due_at: '2020-01-01T00:00:00Z', my_submission: null })]);
    expect(tally.overdueCount).toBe(1);
  });

  it('never crashes or miscounts overdue on a null due date', () => {
    const tally = tallyAssignments([assignment({ due_at: null, my_submission: null })]);
    expect(tally.count).toBe(1);
    expect(tally.overdueCount).toBe(0);
  });
});

describe('tallyProjects', () => {
  it('counts an open project with no work at all as outstanding', () => {
    expect(tallyProjects([project({ my_work: null })]).count).toBe(1);
  });

  it('does not count work already submitted', () => {
    const tally = tallyProjects([
      project({ my_work: { id: 'w1', project: 'proj-1', project_code: 'GRS-P-001', project_title: 'x', status: 'submitted', repository_url: '', deployment_url: '', notes: '', submitted_at: '2026-03-01', submission_count: 1, is_late: false, marks_awarded: null, max_marks: '100', rubric_scores: {}, is_passing: null, is_open_to_student: true, feedback: '', reviewed_at: null, files: [], created_at: '2026-03-01' } }),
    ]);
    expect(tally.count).toBe(0);
  });

  it('does not count work the reviewer has closed to further changes', () => {
    const tally = tallyProjects([
      project({ my_work: { id: 'w1', project: 'proj-1', project_code: 'GRS-P-001', project_title: 'x', status: 'rework', repository_url: '', deployment_url: '', notes: '', submitted_at: '2026-03-01', submission_count: 1, is_late: false, marks_awarded: null, max_marks: '100', rubric_scores: {}, is_passing: null, is_open_to_student: false, feedback: '', reviewed_at: null, files: [], created_at: '2026-03-01' } }),
    ]);
    expect(tally.count).toBe(0);
  });

  it('flags overdue once the end date has passed', () => {
    const tally = tallyProjects([project({ end_date: '2020-01-01', my_work: null })]);
    expect(tally.overdueCount).toBe(1);
  });

  it('never crashes on a null end date', () => {
    const tally = tallyProjects([project({ end_date: null, my_work: null })]);
    expect(tally.overdueCount).toBe(0);
  });
});

// --- averageMetric / collectRiskItems -----------------------------------

describe('averageMetric', () => {
  it('averages only entries carrying a value', () => {
    const entries = [
      performanceEntry({ overall_score: 80 }),
      performanceEntry({ overall_score: null }),
      performanceEntry({ overall_score: 60 }),
    ];
    expect(averageMetric(entries, (e) => e.overall_score)).toBe(70);
  });

  it('is null when nothing has a value', () => {
    expect(averageMetric([performanceEntry()], (e) => e.overall_score)).toBeNull();
  });

  it('is null for an empty list', () => {
    expect(averageMetric([], (e) => e.overall_score)).toBeNull();
  });
});

describe('collectRiskItems', () => {
  it('includes only triggered outcomes', () => {
    const entries = [
      performanceEntry({
        risk: {
          at_risk: true,
          triggered: ['attendance'],
          triggered_count: 1,
          outcomes: [
            { key: 'attendance', label: 'Attendance', triggered: true, severity: 'critical', detail: '40% attended.', numbers: {} },
            { key: 'academic', label: 'Assessment average', triggered: false, severity: 'none', detail: 'Fine.', numbers: {} },
          ],
        },
      }),
    ];
    const items = collectRiskItems(entries);
    expect(items).toHaveLength(1);
    expect(items[0]?.title).toContain('Attendance');
  });

  it('never carries backend "critical" through as anything but warning severity', () => {
    const entries = [
      performanceEntry({
        risk: {
          at_risk: true,
          triggered: ['attendance'],
          triggered_count: 1,
          outcomes: [
            { key: 'attendance', label: 'Attendance', triggered: true, severity: 'critical', detail: 'Low.', numbers: {} },
          ],
        },
      }),
    ];
    expect(collectRiskItems(entries)[0]?.severity).toBe('warning');
  });

  it('is empty when nothing is triggered anywhere', () => {
    expect(collectRiskItems([performanceEntry(), performanceEntry()])).toHaveLength(0);
  });

  it('treats an enrolment the risk engine has never evaluated (risk null) as having nothing to flag', () => {
    const never = performanceEntry({ risk: null });
    const noOutcomes = performanceEntry({
      risk: { at_risk: false, triggered: [], triggered_count: 0 } as unknown as StudentPerformanceEntry['risk'],
    });
    expect(collectRiskItems([never, noOutcomes])).toHaveLength(0);
  });
});

// --- PendingWorkPanel ----------------------------------------------------

describe('PendingWorkPanel', () => {
  it('shows a loading skeleton', () => {
    render(<PendingWorkPanel assignments={[]} projects={[]} isLoading />);
    expect(screen.getByRole('status')).toBeInTheDocument();
  });

  it('shows an error with a working retry', async () => {
    const onRetry = vi.fn();
    render(<PendingWorkPanel assignments={[]} projects={[]} error={apiError} onRetry={onRetry} />);
    await userEvent.click(screen.getByRole('button', { name: /try again/i }));
    expect(onRetry).toHaveBeenCalledOnce();
  });

  it('renders an encouraging empty state when nothing is outstanding', () => {
    render(<PendingWorkPanel assignments={[]} projects={[]} />);
    expect(screen.getByText(/nothing outstanding/i)).toBeInTheDocument();
    expect(screen.queryByText(/undefined/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/NaN/i)).not.toBeInTheDocument();
  });

  it('renders counts and an urgent marker for overdue work', () => {
    render(
      <PendingWorkPanel
        assignments={[assignment({ due_at: '2020-01-01T00:00:00Z', my_submission: null })]}
        projects={[]}
      />,
    );
    expect(screen.getByText(/1 assignment/i)).toBeInTheDocument();
    expect(screen.getByText(/urgent/i)).toBeInTheDocument();
  });
});

// --- StandingPanel ---------------------------------------------------------

describe('StandingPanel', () => {
  it('shows a loading skeleton', () => {
    render(<StandingPanel performance={[]} isLoading />);
    expect(screen.getByRole('status')).toBeInTheDocument();
  });

  it('shows an error with a working retry', async () => {
    const onRetry = vi.fn();
    render(<StandingPanel performance={[]} error={apiError} onRetry={onRetry} />);
    await userEvent.click(screen.getByRole('button', { name: /try again/i }));
    expect(onRetry).toHaveBeenCalledOnce();
  });

  it('never renders NaN or undefined when every metric is null (brand-new student)', () => {
    render(<StandingPanel performance={[]} />);
    const text = document.body.textContent ?? '';
    expect(text).not.toMatch(/NaN/);
    expect(text).not.toMatch(/undefined/);
    expect(text).not.toMatch(/Invalid Date/);
    // KpiTile's own fallback for an absent value.
    expect(screen.getAllByText('Not available').length).toBeGreaterThan(0);
  });

  it('says plainly that everything is on track when nothing is triggered', () => {
    render(
      <StandingPanel
        performance={[
          performanceEntry({
            attendance: { percent: 92, total_sessions: 10, attended: 9, has_records: true },
          }),
        ]}
      />,
    );
    expect(screen.getByText(/on track/i)).toBeInTheDocument();
  });

  it('renders a partial-data course (attendance known, assessment unknown) without a fabricated score', async () => {
    render(
      <StandingPanel
        performance={[
          performanceEntry({
            attendance: { percent: 88, total_sessions: 5, attended: 4, has_records: true },
            assessment: { average_percent: null, sitting_percent: null, recorded: 0, total: 0 },
          }),
        ]}
      />,
    );
    // Counts up from zero on mount, so wait for the value rather than
    // catching a frame of the animation.
    expect(await screen.findByText('88%')).toBeInTheDocument();
    // Assessment, progress and overall standing are all genuinely unmeasured
    // here — three tiles legitimately say "Not available" at once.
    expect(screen.getAllByText('Not available')).toHaveLength(3);
  });

  it('shows a triggered flag as a calm, factual line rather than an alarm', () => {
    render(
      <StandingPanel
        performance={[
          performanceEntry({
            risk: {
              at_risk: true,
              triggered: ['attendance'],
              triggered_count: 1,
              outcomes: [
                {
                  key: 'attendance',
                  label: 'Attendance',
                  triggered: true,
                  severity: 'critical',
                  detail: '40% attended, below the 75% risk threshold.',
                  numbers: {},
                },
              ],
            },
          }),
        ]}
      />,
    );
    expect(screen.getByText(/40% attended/)).toBeInTheDocument();
    expect(screen.getByText(/worth a look/i)).toBeInTheDocument();
  });

  it('renders the four standing metrics as a real, already-computed comparison chart', () => {
    vi.spyOn(window, 'matchMedia').mockImplementation(
      (query: string) =>
        ({
          matches: true,
          media: query,
          onchange: null,
          addEventListener: () => {},
          removeEventListener: () => {},
          addListener: () => {},
          removeListener: () => {},
          dispatchEvent: () => false,
        }) as unknown as MediaQueryList,
    );

    const { container } = render(
      <StandingPanel
        performance={[
          performanceEntry({
            attendance: { percent: 90, total_sessions: 10, attended: 9, has_records: true },
            assessment: { average_percent: 75, sitting_percent: 75, recorded: 2, total: 2 },
          }),
        ]}
      />,
    );

    expect(container.querySelector('.recharts-bar-rectangle')).toBeInTheDocument();
    // The chart's own precision (one decimal) deliberately differs from the
    // tile above it ("90%") so the two never collide as identical text —
    // both are the same real figure, not two different ones.
    const table = within(screen.getByRole('table', { hidden: true }));
    expect(table.getByText('90.0%')).toBeInTheDocument();
    expect(table.getByText('75.0%')).toBeInTheDocument();
  });

  it('shows the chart empty state rather than a broken plot when nothing is measured', () => {
    render(<StandingPanel performance={[]} />);
    expect(screen.getByText('Nothing measured yet.')).toBeInTheDocument();
  });
});

// --- UpcomingTimeline ------------------------------------------------------

describe('UpcomingTimeline', () => {
  function event(overrides: Partial<CalendarEvent> = {}): CalendarEvent {
    return {
      kind: 'class',
      title: 'Linux Essentials — Morning batch',
      start: '2026-04-02T09:00:00Z',
      end: '2026-04-02T11:00:00Z',
      all_day: false,
      location: 'Room 4',
      batch_id: 'batch-1',
      batch_code: 'GRS-B-001',
      course_id: 'course-1',
      course_title: 'Linux Essentials',
      trainer_name: 'Tina Trainer',
      metadata: {},
      ...overrides,
    };
  }

  it('renders an encouraging empty state for a clear week', () => {
    render(<UpcomingTimeline events={[]} />);
    expect(screen.getByText(/nothing on your calendar/i)).toBeInTheDocument();
  });

  it('labels a class event', () => {
    render(<UpcomingTimeline events={[event()]} />);
    expect(screen.getByText(/Linux Essentials — Morning batch/)).toBeInTheDocument();
  });

  it('labels "project_due" correctly despite it being missing from the CalendarEventKind union', () => {
    // A real backend event kind (`EventKind.PROJECT_DUE` in
    // `apps/dashboards/calendar.py`) that `CalendarEventKind` in
    // `types/api.ts` does not declare — see the module docstring. The panel
    // still recognises it by value rather than trusting that union is complete.
    render(<UpcomingTimeline events={[event({ kind: 'project_due' as CalendarEvent['kind'], title: '' })]} />);
    expect(screen.getByText('Project due')).toBeInTheDocument();
    expect(screen.queryByText(/undefined/i)).not.toBeInTheDocument();
  });

  it('falls back to a generic label and icon for a kind nothing recognises', () => {
    render(<UpcomingTimeline events={[event({ kind: 'mystery_event' as CalendarEvent['kind'], title: '' })]} />);
    expect(screen.getByText('Event')).toBeInTheDocument();
    expect(screen.queryByText(/undefined/i)).not.toBeInTheDocument();
  });
});

// --- CertificatesPanel -------------------------------------------------

describe('CertificatesPanel', () => {
  function certificate(overrides: Partial<Certificate> = {}): Certificate {
    return {
      id: 'cert-1',
      number: 'GRS-CERT-0001',
      verification_code: 'abc123',
      course_title: 'Linux Essentials',
      batch_code: 'GRS-B-001',
      completion_date: '2026-03-01',
      status: 'issued',
      is_live: true,
      issued_at: '2026-03-02T10:00:00Z',
      ...overrides,
    };
  }

  it('renders an encouraging empty state', () => {
    render(<CertificatesPanel certificates={[]} />);
    expect(screen.getByText(/no certificates yet/i)).toBeInTheDocument();
  });

  it('renders an issued certificate with download and verify links', () => {
    render(<CertificatesPanel certificates={[certificate()]} />);
    expect(screen.getByText('Linux Essentials')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /download/i })).toHaveAttribute(
      'href',
      expect.stringContaining('cert-1'),
    );
    expect(screen.getByRole('link', { name: /verify/i })).toHaveAttribute('href', '/verify/abc123');
  });

  it('shows an error with a working retry', async () => {
    const onRetry = vi.fn();
    render(<CertificatesPanel certificates={[]} error={apiError} onRetry={onRetry} />);
    await userEvent.click(screen.getByRole('button', { name: /try again/i }));
    expect(onRetry).toHaveBeenCalledOnce();
  });

  it('shows only the newest few and links to the rest', () => {
    // A student on their third course can hold dozens of these. Rendering all
    // of them stretched the dashboard into one six-thousand-pixel column.
    const many = Array.from({ length: 9 }, (_, index) =>
      certificate({ id: `cert-${index}`, course_title: `Course ${index}` }),
    );

    render(<CertificatesPanel certificates={many} />);

    expect(screen.getByText('Course 0')).toBeInTheDocument();
    expect(screen.queryByText('Course 8')).not.toBeInTheDocument();
    expect(screen.getByRole('link', { name: '5 more certificates' })).toHaveAttribute(
      'href',
      '/my-progress',
    );
  });

  it('counts the one hidden certificate in the singular', () => {
    const five = Array.from({ length: 5 }, (_, index) =>
      certificate({ id: `cert-${index}`, course_title: `Course ${index}` }),
    );

    render(<CertificatesPanel certificates={five} />);

    expect(screen.getByRole('link', { name: 'One more certificate' })).toBeInTheDocument();
  });

  it('links to nothing when they all fit', () => {
    render(<CertificatesPanel certificates={[certificate()]} />);

    expect(screen.queryByRole('link', { name: /more certificate/i })).not.toBeInTheDocument();
  });
});

// --- FeedbackPanel -------------------------------------------------------

describe('FeedbackPanel', () => {
  it('renders an encouraging empty state', () => {
    render(<FeedbackPanel feedback={[]} />);
    expect(screen.getByText(/no feedback/i)).toBeInTheDocument();
  });

  it('renders a note with a missing author name as "Unknown", never blank or undefined', () => {
    render(
      <FeedbackPanel
        feedback={[
          {
            id: 'fb-1',
            subject_type: 'student',
            student: 's1',
            student_code: 'GRS-S-1',
            student_name: 'Me',
            trainer: null,
            trainer_code: null,
            trainer_name: null,
            batch: null,
            batch_code: '',
            body: 'Great progress this week.',
            visible_to_subject: true,
            author: null,
            author_name: null,
            created_at: '2026-03-01T10:00:00Z',
          },
        ]}
      />,
    );
    expect(screen.getByText('Great progress this week.')).toBeInTheDocument();
    expect(screen.getByText(/Unknown/)).toBeInTheDocument();
    expect(screen.queryByText(/undefined/i)).not.toBeInTheDocument();
  });
});

// --- NotificationsPanel --------------------------------------------------

describe('NotificationsPanel', () => {
  function notification(overrides: Partial<AppNotification> = {}): AppNotification {
    return {
      id: 'n1',
      kind: 'assignment_graded',
      category: 'academic',
      title: 'Your assignment was graded',
      body: '',
      link_path: '/my-assignments',
      resource_type: 'assignment',
      resource_id: 'a1',
      is_read: false,
      read_at: null,
      created_at: '2026-03-01T10:00:00Z',
      ...overrides,
    };
  }

  it('says "all caught up" with zero unread', () => {
    render(<NotificationsPanel notifications={[]} unreadCount={0} />);
    expect(screen.getByText(/all caught up/i)).toBeInTheDocument();
  });

  it('announces the unread count on an aria-live region', () => {
    render(<NotificationsPanel notifications={[notification()]} unreadCount={3} />);
    const live = document.querySelector('[aria-live="polite"]');
    expect(live).toHaveTextContent('3');
  });

  it('renders a notification without a link_path as plain text, not a broken link', () => {
    render(
      <NotificationsPanel
        notifications={[notification({ link_path: '', title: '' })]}
        unreadCount={1}
      />,
    );
    expect(screen.getByText('Notification')).toBeInTheDocument();
  });
});

// --- FeesPanel -----------------------------------------------------------

describe('FeesPanel', () => {
  function payment(overrides: Partial<FeePayment> = {}): FeePayment {
    return {
      kind: 'instalment',
      is_refundable: false,
      is_refunded: false,
      refunded_at: null,
      refunded_by: null,
      refund_reason: '',
      id: 'pay-1',
      receipt_number: 'GRS-R-0001',
      amount: '5000.00',
      paid_on: '2026-03-01',
      method: 'cash',
      reference: '',
      reference_name: '',
      note: '',
      recorded_by: 'Cara Counsellor',
      created_at: '2026-03-01T10:00:00Z',
      is_voided: false,
      voided_at: null,
      voided_by: null,
      void_reason: '',
    clearing_status: 'cleared',
    cleared_on: null,
    bank: null,
    bank_name: null,
    category: null,
    category_name: null,
    apply_tax: false,
    tax_group: null,
    tax_group_name: null,
    instalment: null,
      ...overrides,
    };
  }

  function plan(overrides: Partial<FeePlan> = {}): FeePlan {
    return {
      id: 'plan-1',
      course_id: 'course-1',
      gross_payable: '20000.00',
      written_off: '0.00',
      refund_due: '0.00',
      is_cancelled: false,
      settled_amount: null,
      cancelled_at: null,
      cancellation_reason: '',
      enrollment_id: 'enrol-1',
      enrollment_code: 'GRS-E-001',
      enrollment_status: 'active',
      course_title: 'Red Hat System Administration I',
      batch_code: 'GRS-B-001',
      batch_name: 'Morning Linux batch',
      agreed_amount: '20000.00',
      discount_amount: '0.00',
      discount_percent: null,
      discount_reason: '',
      payable: '20000.00',
      paid: '5000.00',
      balance: '15000.00',
      status: 'partial',
      next_due_amount: '5000.00',
      next_due_on: '2026-04-01',
      is_overdue: false,
      notes: '',
      created_by: null,
      updated_by: null,
      created_at: '2026-02-01T10:00:00Z',
      updated_at: '2026-03-01T10:00:00Z',
      installments: [],
      payments: [payment()],
      ...overrides,
    };
  }

  function summary(overrides: Partial<StudentFeeSummary> = {}): StudentFeeSummary {
    return {
      payable_total: '20000.00',
      paid_total: '5000.00',
      balance_total: '15000.00',
      next_due_amount: '5000.00',
      next_due_on: '2026-04-01',
      is_overdue: false,
      enrollments_without_plan: 0,
      plans: [plan()],
      ...overrides,
    };
  }

  it('shows the backend totals, what falls due next, and each receipt', () => {
    render(<FeesPanel summary={summary()} />);

    // Scoped to the totals row: ₹15,000 is deliberately also the course's own
    // outstanding line below it, and an unscoped query cannot tell which one
    // it found.
    const totals = screen.getByText('Agreed').closest('dl') as HTMLElement;
    expect(within(totals).getByText('₹20,000')).toBeInTheDocument();
    expect(within(totals).getByText('₹5,000')).toBeInTheDocument();
    expect(within(totals).getByText('₹15,000')).toBeInTheDocument();
    // The course that still owes it, and the receipt for what has been paid.
    expect(screen.getByText('Red Hat System Administration I')).toBeInTheDocument();
    expect(screen.getByText('GRS-R-0001')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'My fees in full' })).toHaveAttribute(
      'href',
      '/my-fees',
    );
  });

  it('marks an overdue instalment rather than letting it read as merely upcoming', () => {
    render(<FeesPanel summary={summary({ is_overdue: true })} />);
    expect(screen.getByText('Overdue')).toBeInTheDocument();
  });

  it('leaves a voided or refunded payment out of the receipts — it is no longer money paid', () => {
    render(
      <FeesPanel
        summary={summary({
          plans: [
            plan({
              payments: [
                payment({ id: 'void', receipt_number: 'GRS-R-VOID', is_voided: true }),
                payment({ id: 'ref', receipt_number: 'GRS-R-REF', is_refunded: true }),
                payment({ id: 'good', receipt_number: 'GRS-R-GOOD' }),
              ],
            }),
          ],
        })}
      />,
    );

    expect(screen.getByText('GRS-R-GOOD')).toBeInTheDocument();
    expect(screen.queryByText('GRS-R-VOID')).not.toBeInTheDocument();
    expect(screen.queryByText('GRS-R-REF')).not.toBeInTheDocument();
  });

  it('shows the newest receipts first and links out for the rest', () => {
    render(
      <FeesPanel
        summary={summary({
          plans: [
            plan({
              payments: [
                payment({ id: 'p1', receipt_number: 'R-1', paid_on: '2026-01-01' }),
                payment({ id: 'p2', receipt_number: 'R-2', paid_on: '2026-02-01' }),
                payment({ id: 'p3', receipt_number: 'R-3', paid_on: '2026-03-01' }),
                payment({ id: 'p4', receipt_number: 'R-4', paid_on: '2026-04-01' }),
              ],
            }),
          ],
        })}
      />,
    );

    expect(screen.getByText('R-4')).toBeInTheDocument();
    expect(screen.queryByText('R-1')).not.toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Every payment and receipt' })).toBeInTheDocument();
  });

  it('names a course whose fee has not been set instead of showing it as owing nothing', () => {
    render(<FeesPanel summary={summary({ plans: [], enrollments_without_plan: 2 })} />);
    expect(screen.getByText(/2 courses with no fee set yet/)).toBeInTheDocument();
  });

  it('says there are no fees yet for a student with neither a plan nor an enrolment', () => {
    render(<FeesPanel summary={summary({ plans: [], enrollments_without_plan: 0 })} />);
    expect(screen.getByText(/No fees on record yet/)).toBeInTheDocument();
  });

  it('renders the loading state rather than a fabricated zero balance', () => {
    render(<FeesPanel summary={null} isLoading />);
    expect(screen.getByRole('status')).toBeInTheDocument();
    expect(screen.queryByText('₹0')).not.toBeInTheDocument();
  });

  it('offers a retry when the fee summary fails to load', async () => {
    const onRetry = vi.fn();
    render(<FeesPanel summary={null} error={apiError} onRetry={onRetry} />);
    await userEvent.click(screen.getByRole('button', { name: /try again/i }));
    expect(onRetry).toHaveBeenCalled();
  });
});
