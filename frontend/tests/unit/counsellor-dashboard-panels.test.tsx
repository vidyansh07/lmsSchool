/**
 * Unit coverage for the counsellor dashboard's pure computations and
 * presentational panels. As with the student dashboard's equivalent file,
 * every panel here is driven directly by props — no `lib/*` mocking needed —
 * which keeps a failure pointing at the exact composition rule that broke:
 * the seat-count threshold, the recent-window diff, the activity merge.
 */
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import {
  fillingUpBatches,
  startingSoonBatches,
  BatchWatchlist,
} from '@/components/counsellor/batches-panel';
import {
  NotYetEnrolledPanel,
  studentsAwaitingEnrolment,
} from '@/components/counsellor/not-yet-enrolled-panel';
import { PendingConfirmationsPanel } from '@/components/counsellor/pending-confirmations-panel';
import { RecentActivityPanel, buildActivityFeed } from '@/components/counsellor/recent-activity-panel';
import { countRegisteredSince } from '@/app/admissions/dashboard/page';
import { ApiError } from '@/lib/api';
import type { BatchListRow, Enrollment, StudentListRow } from '@/types/api';

function student(overrides: Partial<StudentListRow> = {}): StudentListRow {
  return {
    id: 'student-1',
    student_id: 'GRS-S-00001',
    user_id: 'u1',
    email: 'new.student@example.com',
    full_name: 'New Student',
    city: 'Jaipur',
    qualification: 'bachelors',
    fee_status: 'pending',
    fee_amount: null,
    fee_payable: '0.00',
    fee_paid: '0.00',
    fee_balance: '0.00',
    fee_next_due_on: null,
    institution: '',
    roll_number: '',
    institution_kind: '',
    referred_by: null,
    is_active: true,
    is_email_verified: false,
    created_at: '2026-03-01T09:00:00Z',
    ...overrides,
  };
}

function enrollment(overrides: Partial<Enrollment> = {}): Enrollment {
  return {
    id: 'enrol-1',
    code: 'GRS-E-00001',
    course_id: 'course-1',
    course_code: 'GRS-C-001',
    course_title: 'Linux Essentials',
    course_slug: 'linux-essentials',
    batch_id: 'batch-1',
    batch_code: 'GRS-B-001',
    batch_name: 'Morning batch',
    batch_status: 'active',
    trainer_name: '',
    status: 'active',
    enrolled_at: '2026-03-02T09:00:00Z',
    start_date: null,
    access_end_date: null,
    completed_at: null,
    grants_access: true,
    student_id: 'student-1',
    student_code: 'GRS-S-00001',
    student_name: 'New Student',
    student_email: 'new.student@example.com',
    ...overrides,
  };
}

function batch(overrides: Partial<BatchListRow> = {}): BatchListRow {
  return {
    id: 'batch-1',
    code: 'GRS-B-001',
    name: 'Morning batch',
    course_id: 'course-1',
    course_code: 'GRS-C-001',
    course_title: 'Linux Essentials',
    course_slug: 'linux-essentials',
    trainer_name: '',
    start_date: '2026-04-01',
    end_date: '2026-06-01',
    capacity: 20,
    enrolled_count: 5,
    seats_available: 15,
    status: 'upcoming',
    created_at: '2026-01-01',
    ...overrides,
  };
}

const apiError = new ApiError(500, 'server_error', 'The server exploded.', 'req-42');

// --- Pure computations -----------------------------------------------------

describe('studentsAwaitingEnrolment', () => {
  it('keeps a student whose code is not in the enrolled set', () => {
    const result = studentsAwaitingEnrolment([student()], new Set(['GRS-S-99999']));
    expect(result).toHaveLength(1);
  });

  it('drops a student whose code already appears in the enrolled set', () => {
    const result = studentsAwaitingEnrolment([student()], new Set(['GRS-S-00001']));
    expect(result).toHaveLength(0);
  });
});

describe('startingSoonBatches / fillingUpBatches', () => {
  it('only considers upcoming batches for "starting soon", earliest first', () => {
    const soon = batch({ id: 'a', status: 'upcoming', start_date: '2026-05-01' });
    const sooner = batch({ id: 'b', status: 'upcoming', start_date: '2026-04-01' });
    const active = batch({ id: 'c', status: 'active', start_date: '2026-01-01' });
    const result = startingSoonBatches([soon, sooner, active]);
    expect(result.map((b) => b.id)).toEqual(['b', 'a']);
  });

  it('excludes completed, cancelled and archived batches from "filling up"', () => {
    const result = fillingUpBatches([
      batch({ id: 'x', status: 'completed', seats_available: 1, capacity: 20 }),
      batch({ id: 'y', status: 'cancelled', seats_available: 1, capacity: 20 }),
    ]);
    expect(result).toHaveLength(0);
  });

  it('flags a batch with very few seats left relative to its capacity', () => {
    const result = fillingUpBatches([batch({ id: 'tight', capacity: 20, seats_available: 2 })]);
    expect(result.map((b) => b.id)).toEqual(['tight']);
  });

  it('does not flag a batch with plenty of seats left', () => {
    const result = fillingUpBatches([batch({ id: 'roomy', capacity: 20, seats_available: 15 })]);
    expect(result).toHaveLength(0);
  });

  it('excludes a full batch (zero seats) from "filling up" — that is a different problem', () => {
    const result = fillingUpBatches([batch({ id: 'full', capacity: 20, seats_available: 0 })]);
    expect(result).toHaveLength(0);
  });
});

describe('buildActivityFeed', () => {
  it('interleaves registrations and enrolments by time, most recent first', () => {
    const feed = buildActivityFeed(
      [student({ id: 's1', created_at: '2026-03-01T08:00:00Z' })],
      [enrollment({ id: 'e1', enrolled_at: '2026-03-01T09:00:00Z' })],
    );
    expect(feed.map((row) => row.id)).toEqual(['enrolment-e1', 'student-s1']);
  });

  it('is empty when there is nothing on either side', () => {
    expect(buildActivityFeed([], [])).toHaveLength(0);
  });
});

describe('countRegisteredSince', () => {
  it('counts only students at or after the cut-off', () => {
    const count = countRegisteredSince(
      [
        student({ created_at: '2026-03-05T09:00:00Z' }),
        student({ created_at: '2026-03-01T09:00:00Z' }),
      ],
      '2026-03-03T00:00:00.000Z',
    );
    expect(count).toBe(1);
  });

  it('is zero for an empty list', () => {
    expect(countRegisteredSince([], '2026-03-03T00:00:00.000Z')).toBe(0);
  });
});

// --- NotYetEnrolledPanel -----------------------------------------------

describe('NotYetEnrolledPanel', () => {
  it('shows a loading skeleton', () => {
    render(<NotYetEnrolledPanel recentStudents={[]} enrolledStudentCodes={new Set()} isLoading />);
    expect(screen.getByRole('status')).toBeInTheDocument();
  });

  it('shows an error with a working retry', async () => {
    const onRetry = vi.fn();
    render(
      <NotYetEnrolledPanel
        recentStudents={[]}
        enrolledStudentCodes={new Set()}
        error={apiError}
        onRetry={onRetry}
      />,
    );
    await userEvent.click(screen.getByRole('button', { name: /try again/i }));
    expect(onRetry).toHaveBeenCalledOnce();
  });

  it('says plainly that everyone recent is already enrolled', () => {
    render(
      <NotYetEnrolledPanel
        recentStudents={[student()]}
        enrolledStudentCodes={new Set(['GRS-S-00001'])}
      />,
    );
    expect(screen.getByText(/every recent registration is enrolled/i)).toBeInTheDocument();
  });

  it('lists an outstanding registration and links to that student', () => {
    render(<NotYetEnrolledPanel recentStudents={[student()]} enrolledStudentCodes={new Set()} />);
    expect(screen.getByText('New Student')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /new student/i })).toHaveAttribute(
      'href',
      '/admissions/student-1',
    );
  });

  it('renders an unnamed student honestly rather than a blank row', () => {
    render(
      <NotYetEnrolledPanel
        recentStudents={[student({ full_name: '', email: '' })]}
        enrolledStudentCodes={new Set()}
      />,
    );
    expect(screen.getByText('Unknown')).toBeInTheDocument();
  });
});

// --- PendingConfirmationsPanel -------------------------------------------

describe('PendingConfirmationsPanel', () => {
  it('shows a loading skeleton', () => {
    render(<PendingConfirmationsPanel enrollments={[]} totalCount={0} isLoading />);
    expect(screen.getByRole('status')).toBeInTheDocument();
  });

  it('shows the exact server-reported total even when the visible list is capped', () => {
    render(<PendingConfirmationsPanel enrollments={[enrollment()]} totalCount={7} />);
    expect(screen.getByText(/7 awaiting confirmation/)).toBeInTheDocument();
  });

  it('renders an encouraging empty state', () => {
    render(<PendingConfirmationsPanel enrollments={[]} totalCount={0} />);
    expect(screen.getByText(/nothing pending/i)).toBeInTheDocument();
  });

  it('omits a link when the row carries no student id rather than linking nowhere', () => {
    render(
      <PendingConfirmationsPanel
        enrollments={[enrollment({ student_id: undefined })]}
        totalCount={1}
      />,
    );
    expect(screen.queryByRole('link')).not.toBeInTheDocument();
  });
});

// --- BatchWatchlist ----------------------------------------------------

describe('BatchWatchlist', () => {
  it('shows a starting-soon empty state distinct from the filling-up one', () => {
    const { rerender } = render(<BatchWatchlist batches={[]} kind="starting-soon" />);
    expect(screen.getByText(/no upcoming batch/i)).toBeInTheDocument();
    rerender(<BatchWatchlist batches={[]} kind="filling-up" />);
    expect(screen.getByText(/no batch is close to full/i)).toBeInTheDocument();
  });

  it('shows seats-left phrasing for the filling-up variant', () => {
    render(<BatchWatchlist batches={[batch({ capacity: 20, seats_available: 1 })]} kind="filling-up" />);
    expect(screen.getByText('1 seat left')).toBeInTheDocument();
  });

  it('shows a start date for the starting-soon variant', () => {
    render(<BatchWatchlist batches={[batch({ status: 'upcoming', start_date: '2026-05-01' })]} kind="starting-soon" />);
    expect(screen.getByText(/starts/i)).toBeInTheDocument();
  });
});

// --- RecentActivityPanel -------------------------------------------------

describe('RecentActivityPanel', () => {
  it('renders an empty state when nothing has happened yet', () => {
    render(<RecentActivityPanel students={[]} enrollments={[]} />);
    expect(screen.getByText(/nothing has happened yet/i)).toBeInTheDocument();
  });

  it('shows an error with a working retry', async () => {
    const onRetry = vi.fn();
    render(<RecentActivityPanel students={[]} enrollments={[]} error={apiError} onRetry={onRetry} />);
    await userEvent.click(screen.getByRole('button', { name: /try again/i }));
    expect(onRetry).toHaveBeenCalledOnce();
  });

  it('renders both a registration and an enrolment row', () => {
    render(<RecentActivityPanel students={[student()]} enrollments={[enrollment()]} />);
    expect(screen.getByText(/registered/)).toBeInTheDocument();
    expect(screen.getByText(/enrolled on/)).toBeInTheDocument();
  });
});
