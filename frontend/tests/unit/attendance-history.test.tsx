import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { AttendanceHistory } from '@/components/academics/attendance-history';
import { ApiError } from '@/lib/api';
import type { AttendanceCorrection } from '@/types/api';

const getAttendanceHistory = vi.hoisted(() => vi.fn());
vi.mock('@/lib/academics', async () => {
  const actual = await vi.importActual<typeof import('@/lib/academics')>('@/lib/academics');
  return { ...actual, getAttendanceHistory };
});

function correction(overrides: Partial<AttendanceCorrection> = {}): AttendanceCorrection {
  return {
    id: 'corr-1',
    from_status: 'absent',
    to_status: 'present',
    corrected_by_name: 'A. Trainer',
    reason: 'Marked absent by mistake.',
    created_at: '2026-09-10T10:00:00Z',
    ...overrides,
  };
}

beforeEach(() => {
  getAttendanceHistory.mockReset();
});

describe('AttendanceHistory', () => {
  it('does not fetch until opened', () => {
    render(<AttendanceHistory recordId="rec-1" />);
    expect(getAttendanceHistory).not.toHaveBeenCalled();
  });

  it('fetches and shows corrections newest-first order as returned by the server', async () => {
    getAttendanceHistory.mockResolvedValue([correction()]);
    const user = userEvent.setup();
    render(<AttendanceHistory recordId="rec-1" />);

    await user.click(screen.getByRole('button', { name: /view history/i }));

    expect(getAttendanceHistory).toHaveBeenCalledWith('rec-1');
    await waitFor(() => expect(screen.getByText(/A\. Trainer/)).toBeInTheDocument());
    expect(screen.getByText('Marked absent by mistake.')).toBeInTheDocument();
  });

  it('does not refetch on a second toggle', async () => {
    getAttendanceHistory.mockResolvedValue([correction()]);
    const user = userEvent.setup();
    render(<AttendanceHistory recordId="rec-1" />);

    await user.click(screen.getByRole('button', { name: /view history/i }));
    await waitFor(() => expect(screen.getByText(/A\. Trainer/)).toBeInTheDocument());
    await user.click(screen.getByRole('button', { name: /hide history/i }));
    await user.click(screen.getByRole('button', { name: /view history/i }));

    expect(getAttendanceHistory).toHaveBeenCalledTimes(1);
  });

  it('shows an inline error when the fetch fails, another centre reading as not found', async () => {
    getAttendanceHistory.mockRejectedValue(new ApiError(404, 'not_found', 'Not found.', 'req-1'));
    const user = userEvent.setup();
    render(<AttendanceHistory recordId="rec-1" />);

    await user.click(screen.getByRole('button', { name: /view history/i }));

    await waitFor(() => expect(screen.getByText('Not found.')).toBeInTheDocument());
  });
});
