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
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { CertificatesPanel } from '@/components/student/certificates-panel';
import { FeedbackPanel } from '@/components/student/feedback-panel';
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
  StudentAssignment,
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

  it('renders a partial-data course (attendance known, assessment unknown) without a fabricated score', () => {
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
    expect(screen.getByText('88%')).toBeInTheDocument();
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
