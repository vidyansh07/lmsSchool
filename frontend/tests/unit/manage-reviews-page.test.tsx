import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { ReviewsDueWorkspace as ManageReviewsPage } from '@/app/manage/reviews/page';
import { ApiError } from '@/lib/api';
import type { PerformanceReview } from '@/types/api';

const listReviews = vi.hoisted(() => vi.fn());
vi.mock('@/lib/performance', async () => {
  const actual = await vi.importActual<typeof import('@/lib/performance')>('@/lib/performance');
  return { ...actual, listReviews };
});

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
    next_review_at: '2020-01-01',
    status: 'draft',
    snapshot: {},
    reviewer: 'user-1',
    reviewer_name: 'Manager One',
    created_at: '2026-07-01T00:00:00Z',
    updated_at: '2026-07-01T00:00:00Z',
    ...overrides,
  };
}

beforeEach(() => {
  listReviews.mockReset();
});

describe('ManageReviewsPage', () => {
  it('shows a loading state, then a real, past-due review', async () => {
    listReviews.mockResolvedValue([review()]);
    render(<ManageReviewsPage />);
    expect(screen.getByText(/Loading reviews/)).toBeInTheDocument();
    expect(await screen.findByText('Tina Trainer')).toBeInTheDocument();
    expect(screen.getByText('Due')).toBeInTheDocument();
  });

  it('links a trainer review to that trainer’s own page', async () => {
    listReviews.mockResolvedValue([review()]);
    render(<ManageReviewsPage />);
    const link = await screen.findByRole('link');
    expect(link).toHaveAttribute('href', '/manage/trainers/trainer-1');
  });

  it('links a student review to the Student 360 Enrolment tab', async () => {
    listReviews.mockResolvedValue([
      review({
        id: 'review-2',
        subject_type: 'student',
        trainer: null,
        trainer_code: null,
        trainer_name: null,
        student: 'student-1',
        student_code: 'GRS-S-001',
        student_name: 'Jane Student',
      }),
    ]);
    render(<ManageReviewsPage />);
    const link = await screen.findByRole('link');
    expect(link).toHaveAttribute('href', '/students/student-1?tab=enrollment');
  });

  it('reads no due reviews as a real empty state under the default filters', async () => {
    listReviews.mockResolvedValue([review({ next_review_at: '2099-01-01', status: 'shared' })]);
    render(<ManageReviewsPage />);
    expect(await screen.findByText('Nothing due')).toBeInTheDocument();
  });

  it('shows every review, due or not, once "Due only" is cleared', async () => {
    listReviews.mockResolvedValue([review({ next_review_at: '2099-01-01', status: 'shared' })]);
    const user = userEvent.setup();
    render(<ManageReviewsPage />);
    await screen.findByText('Nothing due');
    await user.click(screen.getByRole('checkbox', { name: 'Due only' }));
    expect(await screen.findByText('Tina Trainer')).toBeInTheDocument();
  });

  it('shows a retryable error on failure', async () => {
    listReviews.mockRejectedValue(new ApiError(500, 'server_error', 'Down.', 'req-1'));
    render(<ManageReviewsPage />);
    expect(await screen.findByText('Could not load reviews')).toBeInTheDocument();
  });
});
