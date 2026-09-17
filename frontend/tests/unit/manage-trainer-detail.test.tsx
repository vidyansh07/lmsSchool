import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { TrainerDetail } from '@/app/manage/trainers/[trainerId]/page';
import { ApiError } from '@/lib/api';
import type { TrainerOverview } from '@/lib/manage';
import type { PerformanceReview } from '@/types/api';

const getTrainerOverview = vi.hoisted(() => vi.fn());
vi.mock('@/lib/manage', async () => {
  const actual = await vi.importActual<typeof import('@/lib/manage')>('@/lib/manage');
  return { ...actual, getTrainerOverview };
});

const listReviews = vi.hoisted(() => vi.fn());
const createReview = vi.hoisted(() => vi.fn());
vi.mock('@/lib/performance', async () => {
  const actual = await vi.importActual<typeof import('@/lib/performance')>('@/lib/performance');
  return { ...actual, listReviews, createReview };
});

const mockAuth = vi.hoisted(() => ({ value: { can: () => true } as { can: (capability: string) => boolean } }));
vi.mock('@/components/auth-provider', () => ({ useAuth: () => mockAuth.value }));

function review(overrides: Partial<PerformanceReview> = {}): PerformanceReview {
  return {
    id: 'review-1',
    subject_type: 'trainer',
    review_type: 'monthly',
    student: null,
    student_code: null,
    student_name: null,
    trainer: 'trainer-1',
    trainer_code: 'GRS-T-001',
    trainer_name: 'Tina Trainer',
    period_start: '2026-06-01',
    period_end: '2026-06-30',
    rating: 4,
    score: null,
    summary: 'Consistently strong.',
    strengths: '',
    concerns: '',
    weaknesses: '',
    actions: '',
    recommendations: '',
    next_review_at: null,
    status: 'shared',
    snapshot: {},
    reviewer: 'user-1',
    reviewer_name: 'Manager One',
    created_at: '2026-07-01T00:00:00Z',
    updated_at: '2026-07-01T00:00:00Z',
    ...overrides,
  };
}

function overview(overrides: Partial<TrainerOverview> = {}): TrainerOverview {
  return {
    trainer: { id: 'trainer-1', name: 'Tina Trainer', trainer_id: 'GRS-T-001', email: 'tina@example.com' },
    batches: { total: 3, active: 2 },
    students: { total: 40, at_risk: 2 },
    submission: { attendance_rate: 95, dsr_rate: 90, dsr_approval_rate: 80 },
    completion: { assessments: 88, assignments: 76, projects: 60 },
    outcomes: { student_average_score: 72, student_attendance_percent: 84 },
    pending: { dsr_to_submit: 1, assignments_to_grade: 3, projects_to_review: 1, overdue: 0 },
    reviews: [
      {
        id: 'review-1',
        period_start: '2026-06-01',
        period_end: '2026-06-30',
        rating: 4,
        summary: 'Consistently strong.',
        reviewer: 'Manager One',
        created_at: '2026-07-01T00:00:00Z',
      },
    ],
    student_feedback: [
      { id: 'fb-1', body: 'Explains concepts very clearly.', created_at: '2026-06-15T00:00:00Z', batch_code: 'GRS-B-001' },
    ],
    as_of: '2026-09-07',
    ...overrides,
  };
}

beforeEach(() => {
  getTrainerOverview.mockReset();
  listReviews.mockReset();
  listReviews.mockResolvedValue([review()]);
  createReview.mockReset();
  mockAuth.value = { can: () => true };
});

describe('TrainerDetail', () => {
  it('renders the header and workload figures', async () => {
    getTrainerOverview.mockResolvedValue(overview());
    render(<TrainerDetail trainerId="trainer-1" />);
    await waitFor(() => expect(screen.getByRole('heading', { name: 'Tina Trainer' })).toBeInTheDocument());
    expect(screen.getByText('GRS-T-001')).toBeInTheDocument();
    expect(screen.getByText('95%')).toBeInTheDocument();
  });

  it('renders the reviews written about this trainer, from the real register', async () => {
    getTrainerOverview.mockResolvedValue(overview());
    render(<TrainerDetail trainerId="trainer-1" />);
    await waitFor(() => expect(screen.getByText('Consistently strong.')).toBeInTheDocument());
    expect(screen.getByText('4 / 5')).toBeInTheDocument();
    expect(screen.getByText(/Manager One/)).toBeInTheDocument();
    expect(listReviews).toHaveBeenCalledOnce();
  });

  it('scopes the reviews list to this trainer only, not every visible review', async () => {
    listReviews.mockResolvedValue([review({ id: 'review-1', trainer: 'trainer-1' }), review({ id: 'review-2', trainer: 'trainer-2', summary: 'About someone else.' })]);
    getTrainerOverview.mockResolvedValue(overview());
    render(<TrainerDetail trainerId="trainer-1" />);
    await waitFor(() => expect(screen.getByText('Consistently strong.')).toBeInTheDocument());
    expect(screen.queryByText('About someone else.')).not.toBeInTheDocument();
  });

  it('says plainly when there are no reviews yet', async () => {
    listReviews.mockResolvedValue([]);
    getTrainerOverview.mockResolvedValue(overview());
    render(<TrainerDetail trainerId="trainer-1" />);
    await waitFor(() => expect(screen.getByText('No reviews yet')).toBeInTheDocument());
  });

  it('renders the feedback this trainer’s own students left, by name', async () => {
    getTrainerOverview.mockResolvedValue(overview());
    render(<TrainerDetail trainerId="trainer-1" />);
    await waitFor(() => expect(screen.getByText('Explains concepts very clearly.')).toBeInTheDocument());
  });

  it('says plainly when there is no student feedback yet', async () => {
    getTrainerOverview.mockResolvedValue(overview({ student_feedback: [] }));
    render(<TrainerDetail trainerId="trainer-1" />);
    await waitFor(() => expect(screen.getByText('No feedback yet')).toBeInTheDocument());
  });

  it('hides the review form from someone without review authority', async () => {
    mockAuth.value = { can: () => false };
    getTrainerOverview.mockResolvedValue(overview());
    render(<TrainerDetail trainerId="trainer-1" />);
    await waitFor(() => expect(screen.getByRole('heading', { name: 'Tina Trainer' })).toBeInTheDocument());
    expect(screen.queryByRole('button', { name: /new review/i })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Edit' })).not.toBeInTheDocument();
  });

  it('writes a review inline and reloads the reviews list afterwards', async () => {
    getTrainerOverview.mockResolvedValue(overview());
    createReview.mockResolvedValue(
      review({ id: 'review-2', period_start: '2026-07-01', period_end: '2026-07-31', rating: 5, summary: 'Great month.' }),
    );
    const user = userEvent.setup();
    render(<TrainerDetail trainerId="trainer-1" />);
    await waitFor(() => expect(screen.getByRole('button', { name: /new review/i })).toBeInTheDocument());

    await user.click(screen.getByRole('button', { name: /new review/i }));
    await user.type(screen.getByLabelText('Period start', { exact: false }), '2026-07-01');
    await user.type(screen.getByLabelText('Period end', { exact: false }), '2026-07-31');
    await user.click(screen.getByRole('radio', { name: '5' }));
    await user.click(screen.getByRole('button', { name: /save review/i }));

    await waitFor(() => expect(createReview).toHaveBeenCalledWith(expect.objectContaining({ trainer: 'trainer-1' })));
    await waitFor(() => expect(listReviews).toHaveBeenCalledTimes(2));
  });

  it('shows a not-found state for a trainer that does not exist or is not visible', async () => {
    getTrainerOverview.mockRejectedValue(new ApiError(404, 'not_found', 'Not found.', 'req-1'));
    render(<TrainerDetail trainerId="missing" />);
    await waitFor(() => expect(screen.getByText('Trainer not found')).toBeInTheDocument());
  });

  it('shows a retryable error for anything other than a 404', async () => {
    getTrainerOverview.mockRejectedValue(new ApiError(500, 'server_error', 'Something broke.', 'req-2'));
    render(<TrainerDetail trainerId="trainer-1" />);
    await waitFor(() => expect(screen.getByText('Something broke.')).toBeInTheDocument());
  });

  it('surfaces a "Needs attention" banner when pending work is overdue', async () => {
    getTrainerOverview.mockResolvedValue(
      overview({ pending: { dsr_to_submit: 0, assignments_to_grade: 0, projects_to_review: 0, overdue: 3 } }),
    );
    render(<TrainerDetail trainerId="trainer-1" />);
    await waitFor(() => expect(screen.getByTestId('trainer-attention-banner')).toBeInTheDocument());
  });

  it('shows no attention banner when nothing is overdue and nobody is at risk', async () => {
    getTrainerOverview.mockResolvedValue(
      overview({
        pending: { dsr_to_submit: 1, assignments_to_grade: 1, projects_to_review: 0, overdue: 0 },
        students: { total: 10, at_risk: 0 },
      }),
    );
    render(<TrainerDetail trainerId="trainer-1" />);
    await waitFor(() => expect(screen.getByRole('heading', { name: 'Tina Trainer' })).toBeInTheDocument());
    expect(screen.queryByTestId('trainer-attention-banner')).not.toBeInTheDocument();
  });

  it('renders fallbacks for every nullable figure, never a raw NaN or undefined', async () => {
    getTrainerOverview.mockResolvedValue(
      overview({
        submission: { attendance_rate: null, dsr_rate: null, dsr_approval_rate: null },
        completion: { assessments: null, assignments: null, projects: null },
        outcomes: { student_average_score: null, student_attendance_percent: null },
      }),
    );
    const { container } = render(<TrainerDetail trainerId="trainer-1" />);
    await waitFor(() => expect(screen.getByRole('heading', { name: 'Tina Trainer' })).toBeInTheDocument());
    expect(container.textContent).not.toMatch(/NaN|undefined|Invalid Date/);
    expect(screen.getAllByText('No data').length).toBeGreaterThanOrEqual(8);
  });
});
