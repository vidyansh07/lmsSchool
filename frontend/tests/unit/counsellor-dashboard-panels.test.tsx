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
  hasOverdueStart,
  startingSoonBatches,
  BatchWatchlist,
} from '@/components/counsellor/batches-panel';
import { NotYetEnrolledPanel } from '@/components/counsellor/not-yet-enrolled-panel';
import { PendingConfirmationsPanel } from '@/components/counsellor/pending-confirmations-panel';
import { RecentActivityPanel, buildActivityFeed } from '@/components/counsellor/recent-activity-panel';
import { FigureDefinitions } from '@/app/admissions/dashboard/page';
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

describe('startingSoonBatches / fillingUpBatches', () => {
  const TODAY = '2026-04-15';

  it('only considers upcoming batches for "starting soon", earliest first', () => {
    const soon = batch({ id: 'a', status: 'upcoming', start_date: '2026-05-01' });
    const sooner = batch({ id: 'b', status: 'upcoming', start_date: '2026-04-20' });
    const active = batch({ id: 'c', status: 'active', start_date: '2026-01-01' });
    const result = startingSoonBatches([soon, sooner, active], TODAY);
    expect(result.map((b) => b.id)).toEqual(['b', 'a']);
  });

  it('leads with a batch that was due to start, not with the one starting next', () => {
    // The defect this pins down: `GRS-B-00017` sat at the top of "Upcoming
    // batches, soonest first" fourteen days after its own start date, reading
    // as the next thing to start. It is still first — it is the row to act on —
    // but the list is no longer claiming it starts soon.
    const overdue = batch({ id: 'late', status: 'upcoming', start_date: '2026-04-01' });
    const next = batch({ id: 'next', status: 'upcoming', start_date: '2026-04-20' });
    expect(startingSoonBatches([next, overdue], TODAY).map((b) => b.id)).toEqual(['late', 'next']);
    expect(hasOverdueStart(overdue, TODAY)).toBe(true);
    expect(hasOverdueStart(next, TODAY)).toBe(false);
  });

  it('treats a batch starting today as starting, not as overdue', () => {
    const starting = batch({ id: 'today', status: 'upcoming', start_date: TODAY });
    expect(hasOverdueStart(starting, TODAY)).toBe(false);
  });

  it('puts the longest-overdue start first among several', () => {
    const older = batch({ id: 'older', status: 'upcoming', start_date: '2026-03-01' });
    const newer = batch({ id: 'newer', status: 'upcoming', start_date: '2026-04-10' });
    expect(startingSoonBatches([newer, older], TODAY).map((b) => b.id)).toEqual(['older', 'newer']);
  });

  it('sorts an upcoming batch with no start date last rather than throwing', () => {
    const dated = batch({ id: 'a', status: 'upcoming', start_date: '2026-05-01' });
    const undated = batch({ id: 'b', status: 'upcoming', start_date: null as unknown as string });
    expect(startingSoonBatches([undated, dated], TODAY).map((b) => b.id)).toEqual(['a', 'b']);
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

describe('FigureDefinitions', () => {
  it('renders the definition the server sent, under the tile it belongs to', () => {
    render(
      <FigureDefinitions
        definitions={{
          new_students_this_week: 'A rolling seven days, today included.',
          unassigned_batch: 'Registered students holding no seat on any batch.',
        }}
      />,
    );
    expect(screen.getByText('Registered this week')).toBeInTheDocument();
    expect(screen.getByText('A rolling seven days, today included.')).toBeInTheDocument();
    expect(screen.getByText('Unassigned batch')).toBeInTheDocument();
  });

  it('still explains the one figure this screen computes itself', () => {
    // "Batches starting soon" is filtered in the browser, so the payload
    // carries no definition for it and this file is its only source.
    render(<FigureDefinitions definitions={{}} />);
    expect(screen.getByText('Batches starting soon')).toBeInTheDocument();
    expect(screen.getByText(/start date has already passed/)).toBeInTheDocument();
  });
});

// --- NotYetEnrolledPanel -----------------------------------------------

describe('NotYetEnrolledPanel', () => {
  it('shows a loading skeleton', () => {
    render(<NotYetEnrolledPanel students={[]} totalCount={0} isLoading />);
    expect(screen.getByRole('status')).toBeInTheDocument();
  });

  it('shows an error with a working retry', async () => {
    const onRetry = vi.fn();
    render(<NotYetEnrolledPanel students={[]} totalCount={0} error={apiError} onRetry={onRetry} />);
    await userEvent.click(screen.getByRole('button', { name: /try again/i }));
    expect(onRetry).toHaveBeenCalledOnce();
  });

  it('says plainly that everyone is on a batch', () => {
    render(<NotYetEnrolledPanel students={[]} totalCount={0} />);
    expect(screen.getByText(/every registration is on a batch/i)).toBeInTheDocument();
  });

  it('lists an outstanding registration and links to that student', () => {
    render(<NotYetEnrolledPanel students={[student()]} totalCount={1} />);
    expect(screen.getByText('New Student')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /new student/i })).toHaveAttribute(
      'href',
      '/admissions/student-1',
    );
  });

  it('reports the server total, not the length of the page it was given', () => {
    // The count and the rows come from one request now (`count` and `results`
    // of `?awaiting_enrolment=true`), so a capped list cannot understate the
    // gap — and the panel can no longer invent a count of its own, which is
    // how it came to claim fifteen students who were all enrolled.
    render(<NotYetEnrolledPanel students={[student()]} totalCount={14} />);
    expect(screen.getByText(/14 registered students hold no seat/i)).toBeInTheDocument();
    expect(screen.getByText(/showing the 1 most recent/i)).toBeInTheDocument();
  });

  it('does not say "showing the N most recent" when the page is the whole total', () => {
    render(<NotYetEnrolledPanel students={[student()]} totalCount={1} />);
    expect(screen.getByText(/1 registered student holds no seat/i)).toBeInTheDocument();
    expect(screen.queryByText(/showing the/i)).not.toBeInTheDocument();
  });

  it('renders an unnamed student honestly rather than a blank row', () => {
    render(
      <NotYetEnrolledPanel students={[student({ full_name: '', email: '' })]} totalCount={1} />,
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
    render(
      <BatchWatchlist
        batches={[batch({ status: 'upcoming', start_date: '2026-05-01' })]}
        kind="starting-soon"
        today="2026-04-15"
      />,
    );
    expect(screen.getByText(/starts/i)).toBeInTheDocument();
  });

  it('never says "starts" about a date that has gone', () => {
    render(
      <BatchWatchlist
        batches={[batch({ status: 'upcoming', start_date: '2026-04-01' })]}
        kind="starting-soon"
        today="2026-04-15"
      />,
    );
    expect(screen.getByText(/was due to start .* not marked active/i)).toBeInTheDocument();
    expect(screen.queryByText(/^starts/i)).not.toBeInTheDocument();
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
