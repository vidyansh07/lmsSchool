/**
 * What one staff member has been doing.
 *
 * The owner's decision (26 October 2026): a counsellor's record of work is
 * for administrators, and for the counsellor themselves. A manager does not
 * see it. The card going missing is a courtesy — the server enforces the same
 * pair — but a card that renders for the wrong person is a card somebody will
 * screenshot, so it is worth pinning on this side too.
 *
 * The other thing worth pinning is what a record *omits*. Lines that counted
 * nothing are dropped by the server, so a counsellor's record never lists "0
 * class reports" beside a trainer's "0 receipts": what a record contains says
 * what the job was.
 */
import { render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { StaffRecordCard, readableAction } from '@/components/people/staff-record-card';
import { ApiError } from '@/lib/api';
import { Capability } from '@/lib/capabilities';
import type { StaffRecord } from '@/types/api';

const getStaffRecord = vi.hoisted(() => vi.fn());
vi.mock('@/lib/people', async () => {
  const actual = await vi.importActual<typeof import('@/lib/people')>('@/lib/people');
  return { ...actual, getStaffRecord };
});

const useAuth = vi.hoisted(() => vi.fn());
vi.mock('@/components/auth-provider', () => ({ useAuth }));

function asRole(...capabilities: string[]) {
  useAuth.mockReturnValue({
    can: (capability: string) => capabilities.includes(capability),
  });
}

function record(overrides: Partial<StaffRecord> = {}): StaffRecord {
  return {
    person: {
      id: 'u1',
      name: 'Kiran Counsellor',
      email: 'kiran@example.test',
      role: 'counsellor',
      is_active: true,
    },
    start: '2026-09-26',
    end: '2026-10-26',
    counters: [
      { key: 'admissions', label: 'Admissions taken', count: 18, amount: null },
      { key: 'collected', label: 'Collected', count: 31, amount: '840000.00' },
    ],
    timeline: [
      {
        id: 'e1',
        action: 'fee.payment.recorded',
        resource_type: 'fee_payment',
        resource_id: 'p1',
        result: 'success',
        at: '2026-10-20T09:00:00Z',
      },
    ],
    timeline_truncated: false,
    ...overrides,
  };
}

beforeEach(() => {
  vi.clearAllMocks();
  getStaffRecord.mockResolvedValue(record());
});

describe('StaffRecordCard', () => {
  it('shows an administrator anybody’s record', async () => {
    asRole(Capability.staffViewRecord);
    render(<StaffRecordCard userId="u1" />);

    expect(await screen.findByText('Admissions taken')).toBeInTheDocument();
    expect(screen.getByText('18')).toBeInTheDocument();
  });

  it('shows a person their own without any capability at all', async () => {
    asRole();
    render(<StaffRecordCard userId="u1" isSelf />);

    expect(await screen.findByText('What you have done')).toBeInTheDocument();
    expect(getStaffRecord).toHaveBeenCalled();
  });

  it('shows a manager nothing, and asks the server for nothing', () => {
    // A manager holds neither `staff.view_record` nor ownership here.
    asRole(Capability.userViewAny, Capability.trainerViewAny);
    const { container } = render(<StaffRecordCard userId="u1" />);

    expect(container).toBeEmptyDOMElement();
    expect(getStaffRecord).not.toHaveBeenCalled();
  });

  it('reads money as money and everything else as a count', async () => {
    asRole(Capability.staffViewRecord);
    render(<StaffRecordCard userId="u1" />);

    await screen.findByText('Collected');
    // The amount, not the row count, is the headline on a money line — and
    // the count is still there, named.
    expect(screen.getByText(/8,40,000/)).toBeInTheDocument();
    expect(screen.getByText('31 receipts')).toBeInTheDocument();
  });

  it('says the timeline was cut rather than letting the length imply it', async () => {
    getStaffRecord.mockResolvedValue(record({ timeline_truncated: true }));
    asRole(Capability.staffViewRecord);
    render(<StaffRecordCard userId="u1" />);

    expect(await screen.findByText(/the most recent 1/)).toBeInTheDocument();
  });

  it('says plainly when a span holds nothing', async () => {
    getStaffRecord.mockResolvedValue(record({ counters: [], timeline: [] }));
    asRole(Capability.staffViewRecord);
    render(<StaffRecordCard userId="u1" />);

    expect(await screen.findByText('Nothing recorded between these dates.')).toBeInTheDocument();
  });

  it('asks again when the dates change', async () => {
    asRole(Capability.staffViewRecord);
    render(<StaffRecordCard userId="u1" />);

    await waitFor(() => expect(getStaffRecord).toHaveBeenCalledTimes(1));
    const [, range] = getStaffRecord.mock.calls[0]!;
    expect(range).toHaveProperty('start');
    expect(range).toHaveProperty('end');
  });

  it('says what went wrong instead of an empty card', async () => {
    getStaffRecord.mockRejectedValue(
      new ApiError(403, 'forbidden', 'You do not have authority to read this record.', 'r1'),
    );
    asRole(Capability.staffViewRecord);
    render(<StaffRecordCard userId="u1" />);

    expect(
      await screen.findByText('You do not have authority to read this record.'),
    ).toBeInTheDocument();
  });
});

describe('readableAction', () => {
  it('reuses the audit action’s own words rather than a second vocabulary', () => {
    // A hand-written label per action is a list that drifts from the enum it
    // describes the moment somebody adds one.
    expect(readableAction('fee.payment.recorded')).toBe('Fee payment recorded');
    expect(readableAction('activity.released')).toBe('Activity released');
    expect(readableAction('student.created')).toBe('Student created');
  });
});
