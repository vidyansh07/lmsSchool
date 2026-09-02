import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { ScheduleList } from '@/components/schedule-list';
import type { BatchSchedule } from '@/types/api';

function schedule(overrides: Partial<BatchSchedule> = {}): BatchSchedule {
  return {
    id: 's1',
    weekday: 0,
    weekday_label: 'Monday',
    start_time: '09:00:00',
    end_time: '11:00:00',
    timezone_name: 'Asia/Kolkata',
    location: 'Lab 1',
    trainer_name: 'Tina Trainer',
    is_active: true,
    note: '',
    duration_minutes: 120,
    ...overrides,
  };
}

describe('ScheduleList', () => {
  it('renders the day, time, location and trainer', () => {
    render(<ScheduleList schedules={[schedule()]} />);
    expect(screen.getByText('Monday')).toBeInTheDocument();
    expect(screen.getByText(/09:00.*11:00/)).toBeInTheDocument();
    expect(screen.getByText('Lab 1')).toBeInTheDocument();
    expect(screen.getByText('Tina Trainer')).toBeInTheDocument();
    expect(screen.getByText('Asia/Kolkata')).toBeInTheDocument();
  });

  it('marks a suspended slot', () => {
    render(<ScheduleList schedules={[schedule({ is_active: false })]} />);
    expect(screen.getByText('Suspended')).toBeInTheDocument();
  });

  it('shows an empty message when there is no timetable', () => {
    render(<ScheduleList schedules={[]} />);
    expect(screen.getByText(/no classes scheduled/i)).toBeInTheDocument();
  });
});
