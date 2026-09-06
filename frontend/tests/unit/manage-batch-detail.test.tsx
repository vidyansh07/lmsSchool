import { render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { BatchDetail } from '@/app/manage/batches/[batchId]/page';
import { ApiError } from '@/lib/api';
import type { BatchOverview } from '@/lib/manage';

const getBatchOverview = vi.hoisted(() => vi.fn());
vi.mock('@/lib/manage', async () => {
  const actual = await vi.importActual<typeof import('@/lib/manage')>('@/lib/manage');
  return { ...actual, getBatchOverview };
});

vi.mock('@/components/manage/dsr-review-queue', () => ({
  DsrReviewQueue: ({ batchId }: { batchId: string }) => <div data-testid="dsr-queue-stub">{batchId}</div>,
}));

function overview(overrides: Partial<BatchOverview> = {}): BatchOverview {
  return {
    batch: {
      id: 'batch-1',
      code: 'GRS-B-001',
      name: 'Morning Linux batch',
      kind: 'regular',
      status: 'active',
      delivery_mode: 'offline',
      start_date: '2026-04-01',
      end_date: '2026-06-01',
      capacity: 20,
      seats_taken: 12,
    },
    course: { id: 'course-1', title: 'Linux Essentials', code: 'GRS-C-001' },
    trainer: { id: 'trainer-1', name: 'Tina Trainer', trainer_id: 'GRS-T-001' },
    attendance: { percentage: 82, present: 90, absent: 20, total_sessions: 12 },
    timeline: {
      percent_complete: 40,
      percent_expected: 45,
      variance_percent: -5,
      status: 'behind',
      lessons_covered: 8,
      course_lessons_total: 20,
      next_lesson: { id: 'lesson-9', title: 'File permissions' },
    },
    sessions: { total: 12, completed: 10, cancelled: 1, upcoming: 1 },
    dsr: { expected: 12, submitted: 10, approved: 8, pending_review: 2, overdue: 0 },
    assessments: { total: 4, completed: 3, average_percent: 71 },
    assignments: { total: 6, submitted: 5, graded: 4 },
    projects: { total: 2, submitted: 1, reviewed: 1 },
    students: { total: 12, active: 11, at_risk: 1 },
    as_of: '2026-09-07',
    ...overrides,
  };
}

beforeEach(() => {
  getBatchOverview.mockReset();
});

describe('BatchDetail', () => {
  it('renders the batch header, attendance and timeline figures', async () => {
    getBatchOverview.mockResolvedValue(overview());
    render(<BatchDetail batchId="batch-1" />);
    await waitFor(() => expect(screen.getByText('Morning Linux batch')).toBeInTheDocument());
    expect(screen.getByText('82%')).toBeInTheDocument();
    expect(screen.getByText('Tina Trainer')).toBeInTheDocument();
    expect(screen.getByText('File permissions')).toBeInTheDocument();
  });

  it('renders "Not assigned" when no trainer is on the batch', async () => {
    getBatchOverview.mockResolvedValue(overview({ trainer: null }));
    render(<BatchDetail batchId="batch-1" />);
    await waitFor(() => expect(screen.getByText(/Not assigned/)).toBeInTheDocument());
  });

  it('surfaces a "Needs attention" banner when the batch is behind schedule', async () => {
    getBatchOverview.mockResolvedValue(overview({ timeline: { ...overview().timeline, status: 'behind' } }));
    render(<BatchDetail batchId="batch-1" />);
    await waitFor(() => expect(screen.getByTestId('batch-attention-banner')).toBeInTheDocument());
  });

  it('surfaces the banner when a report is overdue, even if the schedule is fine', async () => {
    getBatchOverview.mockResolvedValue(
      overview({
        timeline: { ...overview().timeline, status: 'on_track' },
        dsr: { expected: 5, submitted: 5, approved: 5, pending_review: 0, overdue: 2 },
      }),
    );
    render(<BatchDetail batchId="batch-1" />);
    await waitFor(() => expect(screen.getByTestId('batch-attention-banner')).toBeInTheDocument());
    expect(screen.getByText(/2 daily status report\(s\) overdue/)).toBeInTheDocument();
  });

  it('shows no attention banner when nothing is wrong', async () => {
    getBatchOverview.mockResolvedValue(
      overview({
        timeline: { ...overview().timeline, status: 'on_track' },
        dsr: { expected: 5, submitted: 5, approved: 5, pending_review: 0, overdue: 0 },
        students: { total: 10, active: 10, at_risk: 0 },
      }),
    );
    render(<BatchDetail batchId="batch-1" />);
    await waitFor(() => expect(screen.getByText('Morning Linux batch')).toBeInTheDocument());
    expect(screen.queryByTestId('batch-attention-banner')).not.toBeInTheDocument();
  });

  it('renders an empty batch — every zero and null field — without crashing or showing a raw NaN/undefined', async () => {
    getBatchOverview.mockResolvedValue({
      batch: {
        id: 'batch-2',
        code: 'GRS-B-002',
        name: 'Brand new batch',
        kind: 'regular',
        status: 'upcoming',
        delivery_mode: 'offline',
        start_date: '2026-10-01',
        end_date: '2026-12-01',
        capacity: 20,
        seats_taken: 0,
      },
      course: { id: 'course-2', title: 'New Course', code: 'GRS-C-002' },
      trainer: null,
      attendance: { percentage: null, present: 0, absent: 0, total_sessions: 0 },
      timeline: {
        percent_complete: null,
        percent_expected: null,
        variance_percent: null,
        status: 'not_started',
        lessons_covered: 0,
        course_lessons_total: 0,
        next_lesson: null,
      },
      sessions: { total: 0, completed: 0, cancelled: 0, upcoming: 0 },
      dsr: { expected: 0, submitted: 0, approved: 0, pending_review: 0, overdue: 0 },
      assessments: { total: 0, completed: 0, average_percent: null },
      assignments: { total: 0, submitted: 0, graded: 0 },
      projects: { total: 0, submitted: 0, reviewed: 0 },
      students: { total: 0, active: 0, at_risk: 0 },
      as_of: '2026-09-07',
    } satisfies BatchOverview);

    const { container } = render(<BatchDetail batchId="batch-2" />);
    await waitFor(() => expect(screen.getByText('Brand new batch')).toBeInTheDocument());

    expect(container.textContent).not.toMatch(/undefined/i);
    expect(container.textContent).not.toMatch(/NaN/);
    expect(container.textContent).not.toMatch(/Invalid Date/);
    expect(screen.getAllByText('No data').length).toBeGreaterThan(0);
    expect(screen.getByText(/Not assigned/)).toBeInTheDocument();
  });

  it('shows a not-found state for a batch that does not exist or is not visible', async () => {
    getBatchOverview.mockRejectedValue(new ApiError(404, 'not_found', 'Not found.', 'req-1'));
    render(<BatchDetail batchId="missing" />);
    await waitFor(() => expect(screen.getByText('Batch not found')).toBeInTheDocument());
  });

  it('shows a retryable error for anything other than a 404', async () => {
    getBatchOverview.mockRejectedValue(new ApiError(500, 'server_error', 'Something broke.', 'req-2'));
    render(<BatchDetail batchId="batch-1" />);
    await waitFor(() => expect(screen.getByText('Something broke.')).toBeInTheDocument());
    expect(screen.getByRole('button', { name: /try again/i })).toBeInTheDocument();
  });

  it('passes the batch id through to the inline DSR review queue', async () => {
    getBatchOverview.mockResolvedValue(overview());
    render(<BatchDetail batchId="batch-1" />);
    await waitFor(() => expect(screen.getByTestId('dsr-queue-stub')).toHaveTextContent('batch-1'));
  });
});
