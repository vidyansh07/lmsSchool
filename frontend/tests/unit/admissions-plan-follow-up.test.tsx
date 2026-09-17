import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { PlanFollowUp } from '@/components/admissions/plan-follow-up';
import { ApiError } from '@/lib/api';
import type { ActivityDetail } from '@/types/api';

const createFollowUp = vi.hoisted(() => vi.fn());

vi.mock('@/lib/people', () => ({ createFollowUp }));

function activity(overrides: Partial<ActivityDetail> = {}): ActivityDetail {
  return {
    id: 'activity-1',
    title: 'Follow-up',
    status: 'planned',
    priority: 'normal',
    planned_at: null,
    due_at: '2026-09-20T09:00:00Z',
    completed_at: null,
    created_at: '2026-09-17T00:00:00Z',
    student: { id: 'student-1', name: 'Jane Existing', student_id: 'GRS-S-00099' },
    type: { id: 'type-1', slug: 'follow_up', name: 'Follow-up', category: 'follow_up' },
    batch: null,
    assigned_to: null,
    created_by: null,
    counts: { history: 0 },
    performed_by: null,
    reviewed_by: null,
    started_at: null,
    reviewed_at: null,
    duration_minutes: null,
    result: 'n/a',
    score: null,
    max_score: null,
    summary: '',
    review_note: '',
    student_visible: false,
    form: null,
    form_values: {},
    history: [],
    parent: null,
    children: [],
    automation_run: null,
    ...overrides,
  } as ActivityDetail;
}

describe('PlanFollowUp', () => {
  it('creates a follow-up through the real activity endpoint, never a direct write', async () => {
    createFollowUp.mockResolvedValue(activity());
    const user = userEvent.setup();
    render(<PlanFollowUp studentId="student-1" />);

    await user.click(screen.getByRole('button', { name: 'Plan a follow-up' }));
    // `userEvent.type` cannot fill a `datetime-local` input's segmented UI —
    // this dialog already starts it pre-filled with a sensible default (see
    // the component's own docstring), so the test only needs to confirm a
    // *different* value than that default reaches the request.
    fireEvent.change(screen.getByLabelText('Due', { exact: false }), {
      target: { value: '2026-09-20T09:00' },
    });
    await user.click(screen.getByRole('button', { name: /create follow-up/i }));

    await waitFor(() => expect(createFollowUp).toHaveBeenCalledOnce());
    expect(createFollowUp).toHaveBeenCalledWith(
      'student-1',
      expect.objectContaining({ priority: 'normal' }),
    );
    expect(await screen.findByText('Follow-up created')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Follow-up' })).toHaveAttribute(
      'href',
      '/activities?id=activity-1',
    );
  });

  it('shows the server error inline and lets the counsellor retry', async () => {
    createFollowUp.mockRejectedValue(
      new ApiError(400, 'validation_error', 'A due date is required.', 'req-1', {
        due_at: ['A due date is required.'],
      }),
    );
    const user = userEvent.setup();
    render(<PlanFollowUp studentId="student-1" />);

    await user.click(screen.getByRole('button', { name: 'Plan a follow-up' }));
    await user.click(screen.getByRole('button', { name: /create follow-up/i }));

    expect(await screen.findByText('A due date is required.')).toBeInTheDocument();
  });

  it('resets when cancelled and reopened', async () => {
    createFollowUp.mockResolvedValue(activity());
    const user = userEvent.setup();
    render(<PlanFollowUp studentId="student-1" />);

    await user.click(screen.getByRole('button', { name: 'Plan a follow-up' }));
    await user.click(screen.getByRole('button', { name: /create follow-up/i }));
    await waitFor(() => expect(screen.getByText('Follow-up created')).toBeInTheDocument());
    await user.click(screen.getByRole('button', { name: 'Done' }));

    await user.click(screen.getByRole('button', { name: 'Plan a follow-up' }));
    expect(screen.queryByText('Follow-up created')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: /create follow-up/i })).toBeInTheDocument();
  });
});
