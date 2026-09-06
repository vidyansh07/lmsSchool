import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { TrainerReviewForm } from '@/components/manage/review-form';
import { ApiError } from '@/lib/api';

const createTrainerReview = vi.hoisted(() => vi.fn());
vi.mock('@/lib/manage', async () => {
  const actual = await vi.importActual<typeof import('@/lib/manage')>('@/lib/manage');
  return { ...actual, createTrainerReview };
});

beforeEach(() => {
  createTrainerReview.mockReset();
});

async function expandForm() {
  const user = userEvent.setup();
  render(<TrainerReviewForm trainerId="trainer-1" onSaved={vi.fn()} />);
  await user.click(screen.getByRole('button', { name: /write a review/i }));
  return user;
}

describe('TrainerReviewForm', () => {
  it('starts collapsed, as a single button', () => {
    render(<TrainerReviewForm trainerId="trainer-1" onSaved={vi.fn()} />);
    expect(screen.getByRole('button', { name: /write a review/i })).toBeInTheDocument();
    expect(screen.queryByLabelText('Period start')).not.toBeInTheDocument();
  });

  it('expands into the full form on click', async () => {
    await expandForm();
    expect(screen.getByLabelText('Period start', { exact: false })).toBeInTheDocument();
    expect(screen.getByLabelText('Period end', { exact: false })).toBeInTheDocument();
    expect(screen.getByRole('radiogroup', { name: /rating/i })).toBeInTheDocument();
  });

  it('collapses again on cancel without saving anything', async () => {
    const user = await expandForm();
    await user.click(screen.getByRole('button', { name: /cancel/i }));
    expect(screen.queryByLabelText('Period start')).not.toBeInTheDocument();
    expect(createTrainerReview).not.toHaveBeenCalled();
  });

  it('lets a rating be chosen from 1 to 5', async () => {
    await expandForm();
    const five = screen.getByRole('radio', { name: '5' });
    await userEvent.click(five);
    expect(five).toHaveAttribute('aria-checked', 'true');
  });

  it('submits the review with the trainer id and the entered fields', async () => {
    const onSaved = vi.fn();
    createTrainerReview.mockResolvedValue({
      id: 'review-1',
      period_start: '2026-08-01',
      period_end: '2026-08-31',
      rating: 4,
      summary: 'Solid month.',
      reviewer_name: 'Manager One',
      created_at: '2026-09-01T00:00:00Z',
    });
    const user = userEvent.setup();
    render(<TrainerReviewForm trainerId="trainer-1" onSaved={onSaved} />);
    await user.click(screen.getByRole('button', { name: /write a review/i }));

    fireEvent.change(screen.getByLabelText('Period start', { exact: false }), { target: { value: '2026-08-01' } });
    fireEvent.change(screen.getByLabelText('Period end', { exact: false }), { target: { value: '2026-08-31' } });
    await user.click(screen.getByRole('radio', { name: '4' }));
    await user.type(screen.getByLabelText('Summary'), 'Solid month.');

    await user.click(screen.getByRole('button', { name: /save review/i }));

    await waitFor(() => expect(createTrainerReview).toHaveBeenCalledOnce());
    expect(createTrainerReview).toHaveBeenCalledWith(
      expect.objectContaining({
        trainer: 'trainer-1',
        period_start: '2026-08-01',
        period_end: '2026-08-31',
        rating: 4,
        summary: 'Solid month.',
      }),
    );
    await waitFor(() => expect(onSaved).toHaveBeenCalledOnce());
    // Collapses back to the single button once saved.
    expect(screen.getByRole('button', { name: /write a review/i })).toBeInTheDocument();
  });

  it('shows field errors and stays open when the save is rejected', async () => {
    createTrainerReview.mockRejectedValue(
      new ApiError(400, 'validation_error', 'The submitted data is invalid.', 'req-1', {
        period_end: ['The period cannot end before it starts.'],
      }),
    );
    const user = await expandForm();
    fireEvent.change(screen.getByLabelText('Period start', { exact: false }), { target: { value: '2026-08-31' } });
    fireEvent.change(screen.getByLabelText('Period end', { exact: false }), { target: { value: '2026-08-01' } });
    await user.click(screen.getByRole('button', { name: /save review/i }));

    await waitFor(() =>
      expect(screen.getByText('The period cannot end before it starts.')).toBeInTheDocument(),
    );
    // Still open — a rejected save must not silently discard what was typed.
    expect(screen.getByLabelText('Period start', { exact: false })).toHaveValue('2026-08-31');
  });
});
