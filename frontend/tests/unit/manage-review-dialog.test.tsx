import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { ReviewDialog } from '@/components/manage/review-dialog';
import { ReviewsPanel } from '@/components/manage/reviews-panel';
import { ApiError } from '@/lib/api';
import type { PerformanceReview } from '@/types/api';

const createReview = vi.hoisted(() => vi.fn());
const updateReview = vi.hoisted(() => vi.fn());
const listReviews = vi.hoisted(() => vi.fn());
vi.mock('@/lib/performance', async () => {
  const actual = await vi.importActual<typeof import('@/lib/performance')>('@/lib/performance');
  return { ...actual, createReview, updateReview, listReviews };
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
    trainer_code: 'TR-001',
    trainer_name: 'Trainer One',
    period_start: '2026-08-01',
    period_end: '2026-08-31',
    rating: 4,
    score: '82.0',
    summary: 'Solid month.',
    strengths: 'Consistent classes.',
    concerns: 'None.',
    weaknesses: 'None.',
    actions: 'Keep it up.',
    recommendations: 'Consider a lead role.',
    next_review_at: '2026-09-30',
    status: 'shared',
    snapshot: {},
    reviewer: 'user-1',
    reviewer_name: 'Manager One',
    created_at: '2026-09-01T00:00:00Z',
    updated_at: '2026-09-01T00:00:00Z',
    ...overrides,
  };
}

beforeEach(() => {
  createReview.mockReset();
  updateReview.mockReset();
  listReviews.mockReset();
});

describe('ReviewDialog', () => {
  it('renders nothing while closed', () => {
    render(
      <ReviewDialog
        open={false}
        onOpenChange={vi.fn()}
        subjectType="trainer"
        subjectId="trainer-1"
        review={null}
        onSaved={vi.fn()}
      />,
    );
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('opens as "New review" with an empty form when there is no review to edit', () => {
    render(
      <ReviewDialog
        open
        onOpenChange={vi.fn()}
        subjectType="trainer"
        subjectId="trainer-1"
        review={null}
        onSaved={vi.fn()}
      />,
    );
    expect(screen.getByRole('heading', { name: 'New review' })).toBeInTheDocument();
    expect(screen.getByLabelText('Period start', { exact: false })).toHaveValue('');
    // Create mode has no status field yet — `ReviewWriteSerializer` does not
    // accept one; a review always starts in draft.
    expect(screen.queryByLabelText('Status')).not.toBeInTheDocument();
  });

  it('opens pre-filled for edit, including the status field', () => {
    render(
      <ReviewDialog
        open
        onOpenChange={vi.fn()}
        subjectType="trainer"
        subjectId="trainer-1"
        review={review()}
        onSaved={vi.fn()}
      />,
    );
    expect(screen.getByRole('heading', { name: 'Edit review' })).toBeInTheDocument();
    expect(screen.getByLabelText('Period start', { exact: false })).toHaveValue('2026-08-01');
    expect(screen.getByLabelText('Status', { exact: false })).toHaveValue('shared');
  });

  it('refuses to submit without the required period dates', () => {
    render(
      <ReviewDialog
        open
        onOpenChange={vi.fn()}
        subjectType="trainer"
        subjectId="trainer-1"
        review={null}
        onSaved={vi.fn()}
      />,
    );
    expect(screen.getByRole('button', { name: /save review/i })).toBeDisabled();
  });

  it('creates a review against the given subject with the entered fields', async () => {
    const onSaved = vi.fn();
    const onOpenChange = vi.fn();
    createReview.mockResolvedValue(review());
    const user = userEvent.setup();
    render(
      <ReviewDialog
        open
        onOpenChange={onOpenChange}
        subjectType="trainer"
        subjectId="trainer-1"
        review={null}
        onSaved={onSaved}
      />,
    );

    fireEvent.change(screen.getByLabelText('Period start', { exact: false }), {
      target: { value: '2026-08-01' },
    });
    fireEvent.change(screen.getByLabelText('Period end', { exact: false }), {
      target: { value: '2026-08-31' },
    });
    await user.click(screen.getByRole('radio', { name: '4' }));
    await user.type(screen.getByLabelText('Weaknesses', { exact: false }), 'Runs late sometimes.');

    await user.click(screen.getByRole('button', { name: /save review/i }));

    await waitFor(() => expect(createReview).toHaveBeenCalledOnce());
    expect(createReview).toHaveBeenCalledWith(
      expect.objectContaining({
        trainer: 'trainer-1',
        period_start: '2026-08-01',
        period_end: '2026-08-31',
        rating: 4,
        weaknesses: 'Runs late sometimes.',
      }),
    );
    await waitFor(() => expect(onSaved).toHaveBeenCalledOnce());
    expect(onOpenChange).toHaveBeenCalledWith(false);
  });

  it('edits an existing review, including its status, without re-sending the subject', async () => {
    updateReview.mockResolvedValue(review({ status: 'acknowledged' }));
    const user = userEvent.setup();
    const onSaved = vi.fn();
    render(
      <ReviewDialog
        open
        onOpenChange={vi.fn()}
        subjectType="trainer"
        subjectId="trainer-1"
        review={review()}
        onSaved={onSaved}
      />,
    );

    await user.selectOptions(screen.getByLabelText('Status', { exact: false }), 'acknowledged');
    await user.click(screen.getByRole('button', { name: /save review/i }));

    await waitFor(() => expect(updateReview).toHaveBeenCalledOnce());
    expect(updateReview).toHaveBeenCalledWith(
      'review-1',
      expect.objectContaining({ status: 'acknowledged' }),
    );
    expect(updateReview.mock.calls[0]?.[1]).not.toHaveProperty('trainer');
    await waitFor(() => expect(onSaved).toHaveBeenCalledOnce());
  });

  it('shows field errors and stays open when the save is rejected', async () => {
    createReview.mockRejectedValue(
      new ApiError(400, 'validation_error', 'The submitted data is invalid.', 'req-1', {
        period_end: ['The period cannot end before it starts.'],
      }),
    );
    const user = userEvent.setup();
    render(
      <ReviewDialog
        open
        onOpenChange={vi.fn()}
        subjectType="trainer"
        subjectId="trainer-1"
        review={null}
        onSaved={vi.fn()}
      />,
    );
    fireEvent.change(screen.getByLabelText('Period start', { exact: false }), {
      target: { value: '2026-08-31' },
    });
    fireEvent.change(screen.getByLabelText('Period end', { exact: false }), {
      target: { value: '2026-08-01' },
    });
    await user.click(screen.getByRole('button', { name: /save review/i }));

    await waitFor(() =>
      expect(screen.getByText('The period cannot end before it starts.')).toBeInTheDocument(),
    );
    expect(screen.getByLabelText('Period start', { exact: false })).toHaveValue('2026-08-31');
  });
});

describe('ReviewsPanel', () => {
  it('shows a loading state, then the reviews scoped to this subject only', async () => {
    listReviews.mockResolvedValue([
      review({ id: 'review-1', trainer: 'trainer-1' }),
      review({ id: 'review-2', trainer: 'trainer-2' }),
    ]);
    render(<ReviewsPanel subjectType="trainer" subjectId="trainer-1" canManage={false} />);
    expect(screen.getByText(/Loading reviews/)).toBeInTheDocument();
    expect(await screen.findAllByTestId('performance-review-row')).toHaveLength(1);
  });

  it('reads no reviews as a real empty state, not a blank screen', async () => {
    listReviews.mockResolvedValue([]);
    render(<ReviewsPanel subjectType="trainer" subjectId="trainer-1" canManage={false} />);
    expect(await screen.findByText('No reviews yet')).toBeInTheDocument();
  });

  it('hides New review and Edit from a caller without review.manage_any', async () => {
    listReviews.mockResolvedValue([review()]);
    render(<ReviewsPanel subjectType="trainer" subjectId="trainer-1" canManage={false} />);
    await screen.findAllByTestId('performance-review-row');
    expect(screen.queryByRole('button', { name: /new review/i })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /edit/i })).not.toBeInTheDocument();
  });

  it('opens the dialog pre-filled from Edit, and fresh from New review', async () => {
    listReviews.mockResolvedValue([review()]);
    const user = userEvent.setup();
    render(<ReviewsPanel subjectType="trainer" subjectId="trainer-1" canManage />);
    await screen.findAllByTestId('performance-review-row');

    await user.click(screen.getByRole('button', { name: 'Edit' }));
    expect(screen.getByRole('heading', { name: 'Edit review' })).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: /cancel/i }));

    await user.click(screen.getByRole('button', { name: /new review/i }));
    expect(screen.getByRole('heading', { name: 'New review' })).toBeInTheDocument();
  });
});
