import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { ClassPicker } from '@/components/teaching/class-picker';
import { ApiError } from '@/lib/api';
import type { ClassSession } from '@/types/api';

const listSessions = vi.hoisted(() => vi.fn());
vi.mock('@/lib/academics', () => ({ listSessions }));

const TODAY = '2026-09-07';

function classSession(overrides: Partial<ClassSession> = {}): ClassSession {
  return {
    id: 'session-1',
    batch_id: 'batch-1',
    batch_code: 'GRS-B-001',
    batch_name: 'Morning batch',
    course_title: 'Linux Essentials',
    session_date: TODAY,
    start_time: '09:00:00',
    end_time: '11:00:00',
    timezone_name: 'Asia/Kolkata',
    starts_at: `${TODAY}T09:00:00+05:30`,
    ends_at: `${TODAY}T11:00:00+05:30`,
    duration_minutes: 120,
    trainer_name: 'Tina Trainer',
    topic: 'Shell basics',
    location: 'Room 4',
    status: 'in_progress',
    cancellation_reason: '',
    attendance_taken_at: null,
    can_take_attendance: true,
    planned_lesson_id: null,
    planned_lesson_title: null,
    actual_lesson_id: null,
    actual_lesson_title: null,
    topic_status: 'planned',
    ...overrides,
  };
}

function emptyPage(): { count: number; page: number; page_size: number; total_pages: number; next: null; previous: null; results: ClassSession[] } {
  return { count: 0, page: 1, page_size: 20, total_pages: 0, next: null, previous: null, results: [] };
}

beforeEach(() => {
  listSessions.mockReset().mockResolvedValue(emptyPage());
});

describe('ClassPicker', () => {
  it('shows the sessions handed in for today without calling listSessions', () => {
    render(
      <ClassPicker
        todayIso={TODAY}
        todaySessions={[classSession()]}
        isLoadingToday={false}
        todayError={null}
        onRetryToday={vi.fn()}
        onSelect={vi.fn()}
      />,
    );
    // The card prefers the class's own topic over the course title, matching
    // the convention `/teaching/page.tsx` already uses for the same card.
    expect(screen.getByText('Shell basics')).toBeInTheDocument();
    expect(listSessions).not.toHaveBeenCalled();
  });

  it('shows a loading state for today', () => {
    render(
      <ClassPicker
        todayIso={TODAY}
        todaySessions={[]}
        isLoadingToday
        todayError={null}
        onRetryToday={vi.fn()}
        onSelect={vi.fn()}
      />,
    );
    expect(screen.getByRole('status')).toBeInTheDocument();
  });

  it('shows today’s error with a working retry', async () => {
    const user = userEvent.setup();
    const onRetryToday = vi.fn();
    render(
      <ClassPicker
        todayIso={TODAY}
        todaySessions={[]}
        isLoadingToday={false}
        todayError={new ApiError(500, 'error', 'Server exploded.', 'req-1')}
        onRetryToday={onRetryToday}
        onSelect={vi.fn()}
      />,
    );
    expect(screen.getByText('Server exploded.')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: /try again/i }));
    expect(onRetryToday).toHaveBeenCalledOnce();
  });

  it('says "No classes today" for an empty today, and a different message for another date', async () => {
    render(
      <ClassPicker
        todayIso={TODAY}
        todaySessions={[]}
        isLoadingToday={false}
        todayError={null}
        onRetryToday={vi.fn()}
        onSelect={vi.fn()}
      />,
    );
    expect(screen.getByText('No classes today')).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText('Date', { exact: false }), { target: { value: '2026-09-01' } });
    await waitFor(() => expect(screen.getByText('No classes on this date')).toBeInTheDocument());
  });

  it('fetches and shows sessions for a chosen backdated date, and lets one be selected', async () => {
    const user = userEvent.setup();
    const onSelect = vi.fn();
    const pastSession = classSession({ id: 'session-past', session_date: '2026-09-01', topic: 'Old class' });
    listSessions.mockResolvedValue({ ...emptyPage(), results: [pastSession] });

    render(
      <ClassPicker
        todayIso={TODAY}
        todaySessions={[]}
        isLoadingToday={false}
        todayError={null}
        onRetryToday={vi.fn()}
        onSelect={onSelect}
      />,
    );

    fireEvent.change(screen.getByLabelText('Date', { exact: false }), { target: { value: '2026-09-01' } });
    await waitFor(() => expect(listSessions).toHaveBeenCalledWith({
      date_from: '2026-09-01',
      date_to: '2026-09-01',
      ordering: 'start_time',
    }));
    await waitFor(() => expect(screen.getByText('Old class')).toBeInTheDocument());

    await user.click(screen.getByText('Old class'));
    expect(onSelect).toHaveBeenCalledWith(pastSession);
  });

  it('does not let the date field go past today', () => {
    render(
      <ClassPicker
        todayIso={TODAY}
        todaySessions={[]}
        isLoadingToday={false}
        todayError={null}
        onRetryToday={vi.fn()}
        onSelect={vi.fn()}
      />,
    );
    expect(screen.getByLabelText('Date', { exact: false })).toHaveAttribute('max', TODAY);
  });
});
