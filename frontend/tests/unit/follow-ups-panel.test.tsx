import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { FollowUpsPanel } from '@/components/students/follow-ups-panel';
import type { Activity } from '@/types/api';

const listStudentActivities = vi.hoisted(() => vi.fn());
const completeActivity = vi.hoisted(() => vi.fn());

vi.mock('@/lib/work', () => ({ listStudentActivities, completeActivity }));

function followUp(overrides: Partial<Activity> = {}): Activity {
  return {
    id: 'act-1',
    title: 'Follow-up: Jane Doe',
    status: 'assigned',
    priority: 'normal',
    planned_at: null,
    due_at: '2026-10-09T09:00:00Z',
    completed_at: null,
    created_at: '2026-10-07T09:00:00Z',
    student: { id: 'student-1', name: 'Jane Doe', student_id: 'GRS-S-00001' },
    type: { id: 'type-1', slug: 'follow-up', name: 'Follow-up', category: 'follow_up', subject: 'student' },
    batch: null,
    assigned_to: { id: 'user-1', name: 'Kiran Counsellor' },
    created_by: { id: 'user-1', name: 'Kiran Counsellor' },
    counts: { history: 1 },
    ...overrides,
  };
}

beforeEach(() => {
  listStudentActivities.mockReset();
  completeActivity.mockReset();
});

describe('FollowUpsPanel', () => {
  it('splits pending from completed and asks for follow-ups only', async () => {
    listStudentActivities.mockResolvedValue({
      count: 3,
      next: null,
      previous: null,
      results: [
        followUp(),
        followUp({ id: 'act-2', status: 'overdue', due_at: '2026-10-01T09:00:00Z' }),
        followUp({ id: 'act-3', status: 'completed', completed_at: '2026-10-02T10:00:00Z' }),
      ],
    });
    render(<FollowUpsPanel studentId="student-1" mayComplete />);
    await screen.findByText('2 pending · 1 completed');
    expect(listStudentActivities).toHaveBeenCalledWith(
      'student-1',
      expect.objectContaining({ category: 'follow_up' }),
    );
    expect(within(screen.getByTestId('follow-up-act-2')).getByText('Overdue')).toBeInTheDocument();
    expect(screen.getByTestId('follow-up-act-3')).toHaveTextContent(/Done/);
    // Only pending rows can be marked done.
    expect(screen.getAllByRole('button', { name: /mark done/i })).toHaveLength(2);
  });

  it('marks a follow-up done through the note form and reloads', async () => {
    listStudentActivities.mockResolvedValue({
      count: 1,
      next: null,
      previous: null,
      results: [followUp()],
    });
    completeActivity.mockResolvedValue({});
    render(<FollowUpsPanel studentId="student-1" mayComplete />);
    fireEvent.click(await screen.findByRole('button', { name: /mark done/i }));
    const dialog = await screen.findByRole('dialog');
    fireEvent.change(within(dialog).getByLabelText(/outcome/i), { target: { value: 'callback' } });
    fireEvent.change(within(dialog).getByLabelText(/what was said/i), {
      target: { value: 'Will decide after the weekend' },
    });
    fireEvent.click(within(dialog).getByRole('button', { name: /^mark done$/i }));
    await waitFor(() => expect(completeActivity).toHaveBeenCalledOnce());
    expect(completeActivity).toHaveBeenCalledWith('act-1', {
      form_values: { channel: 'phone', outcome: 'callback', summary: 'Will decide after the weekend' },
      summary: 'Will decide after the weekend',
    });
    await waitFor(() => expect(listStudentActivities).toHaveBeenCalledTimes(2));
  });

  it('hides the done button from someone who cannot complete', async () => {
    listStudentActivities.mockResolvedValue({
      count: 1,
      next: null,
      previous: null,
      results: [followUp()],
    });
    render(<FollowUpsPanel studentId="student-1" mayComplete={false} />);
    await screen.findByText('1 pending · 0 completed');
    expect(screen.queryByRole('button', { name: /mark done/i })).not.toBeInTheDocument();
  });
});
