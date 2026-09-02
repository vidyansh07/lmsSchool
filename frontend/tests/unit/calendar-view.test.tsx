import { render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { CalendarView } from '@/components/calendar-view';
import type { CalendarEvent } from '@/types/api';

const getCalendar = vi.hoisted(() => vi.fn());

vi.mock('@/lib/batches', () => ({ getCalendar }));

function event(overrides: Partial<CalendarEvent> = {}): CalendarEvent {
  return {
    kind: 'class',
    title: 'Linux Essentials — Morning',
    start: '2026-03-02T09:00:00+05:30',
    end: '2026-03-02T11:00:00+05:30',
    all_day: false,
    location: 'Lab 1',
    batch_id: 'b1',
    batch_code: 'GRS-B-00001',
    course_id: 'c1',
    course_title: 'Linux Essentials',
    trainer_name: 'Tina Trainer',
    metadata: {},
    ...overrides,
  };
}

describe('CalendarView', () => {
  it('groups events by day and shows what a timetable needs', async () => {
    getCalendar.mockResolvedValue({ start: '2026-03-01', end: '2026-03-28', count: 1, events: [event()] });
    render(<CalendarView />);

    await waitFor(() => expect(screen.getByText('Linux Essentials — Morning')).toBeInTheDocument());
    expect(screen.getByText('Class')).toBeInTheDocument();
    expect(screen.getByText('Lab 1')).toBeInTheDocument();
    expect(screen.getByText('GRS-B-00001')).toBeInTheDocument();
  });

  it('renders an all-day milestone without a time', async () => {
    getCalendar.mockResolvedValue({
      start: '2026-03-01',
      end: '2026-03-28',
      count: 1,
      events: [event({ kind: 'batch_end', title: 'Morning cohort ends', all_day: true, end: null })],
    });
    render(<CalendarView />);

    await waitFor(() => expect(screen.getByText('Morning cohort ends')).toBeInTheDocument());
    expect(screen.getByText('All day')).toBeInTheDocument();
    expect(screen.getByText('Batch ends')).toBeInTheDocument();
  });

  it('shows an empty state when nothing is scheduled', async () => {
    getCalendar.mockResolvedValue({ start: '2026-03-01', end: '2026-03-28', count: 0, events: [] });
    render(<CalendarView />);
    await waitFor(() => expect(screen.getByText(/nothing scheduled/i)).toBeInTheDocument());
  });

  it('renders an unknown event kind rather than breaking', async () => {
    // A source registered in a later phase must not blank the calendar.
    getCalendar.mockResolvedValue({
      start: '2026-03-01',
      end: '2026-03-28',
      count: 1,
      events: [event({ kind: 'assignment_due' as CalendarEvent['kind'], title: 'Essay due' })],
    });
    render(<CalendarView />);
    await waitFor(() => expect(screen.getByText('Essay due')).toBeInTheDocument());
    expect(screen.getByText('Assignment due')).toBeInTheDocument();
  });
});
