/**
 * Removing a weekly class slot is a hard delete on the server. The trash
 * icon used to do it on one click; it now names the slot and asks first.
 */
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { SchedulePanel } from '@/app/admin/batches/[batchId]/batch-detail-view';
import type { BatchDetail } from '@/types/api';

const deleteSchedule = vi.hoisted(() => vi.fn());
vi.mock('@/lib/batches', async () => {
  const actual = await vi.importActual<typeof import('@/lib/batches')>('@/lib/batches');
  return { ...actual, deleteSchedule };
});
vi.mock('@/components/auth-provider', () => ({
  useAuth: () => ({ can: () => true, user: { id: 'admin-1', role: 'admin' } }),
}));

function batch(): BatchDetail {
  return {
    id: 'batch-1',
    code: 'GRS-B-001',
    name: 'Morning Linux batch',
    course_id: 'course-1',
    course_code: 'GRS-C-001',
    course_title: 'Linux Essentials',
    course_slug: 'linux-essentials',
    trainer_name: 'Tina Trainer',
    start_date: '2026-04-01',
    end_date: '2026-06-01',
    capacity: 20,
    enrolled_count: 1,
    seats_available: 19,
    status: 'active',
    created_at: '2026-01-01',
    description: '',
    trainer_id: null,
    trainer_code: '',
    schedules: [
      {
        id: 'slot-1',
        weekday: 0,
        weekday_label: 'Monday',
        start_time: '09:00:00',
        end_time: '10:30:00',
        timezone_name: 'Asia/Kolkata',
        location: 'Lab 2',
        trainer_name: '',
        is_active: true,
        note: '',
        duration_minutes: 90,
      },
    ],
    updated_at: '2026-01-01',
    can_manage: true,
    can_view_roster: true,
  } as BatchDetail;
}

beforeEach(() => deleteSchedule.mockReset());

describe('SchedulePanel — removing a weekly slot', () => {
  it('asks first, naming the slot, and only then deletes it', async () => {
    deleteSchedule.mockResolvedValue(undefined);
    const onChanged = vi.fn();
    render(<SchedulePanel batch={batch()} onChanged={onChanged} />);

    fireEvent.click(screen.getByRole('button', { name: 'Remove the Monday class' }));
    expect(deleteSchedule).not.toHaveBeenCalled();
    const dialog = screen.getByRole('alertdialog');
    expect(dialog).toHaveTextContent('Monday 09:00–10:30 stops repeating');

    fireEvent.click(within(dialog).getByRole('button', { name: 'Remove' }));
    await waitFor(() => expect(deleteSchedule).toHaveBeenCalledWith('slot-1'));
    await waitFor(() => expect(onChanged).toHaveBeenCalled());
  });
});
