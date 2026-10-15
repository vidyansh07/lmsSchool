/**
 * `RosterPanel` (`app/admin/batches/[batchId]/page.tsx`) — Suspend/
 * Reactivate/Remove had no busy guard (R11 double-submission audit gap),
 * unlike the identical pattern on `app/admissions/[studentId]/page.tsx`.
 * Covers that a fast double-click on a row action only fires the mutation
 * once.
 */
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { RosterPanel } from '@/app/admin/batches/[batchId]/page';
import { Capability } from '@/lib/capabilities';
import type { BatchDetail, RosterEntry } from '@/types/api';

const getBatchRoster = vi.hoisted(() => vi.fn());
const setEnrollmentStatus = vi.hoisted(() => vi.fn());
const listStudents = vi.hoisted(() => vi.fn());
vi.mock('@/lib/batches', async () => {
  const actual = await vi.importActual<typeof import('@/lib/batches')>('@/lib/batches');
  return { ...actual, getBatchRoster, setEnrollmentStatus };
});
vi.mock('@/lib/people', async () => {
  const actual = await vi.importActual<typeof import('@/lib/people')>('@/lib/people');
  return { ...actual, listStudents };
});

const useAuth = vi.hoisted(() => vi.fn());
vi.mock('@/components/auth-provider', () => ({ useAuth }));

function batch(overrides: Partial<BatchDetail> = {}): BatchDetail {
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
    schedules: [],
    updated_at: '2026-01-01',
    can_manage: true,
    can_view_roster: true,
    ...overrides,
  };
}

function entry(overrides: Partial<RosterEntry> = {}): RosterEntry {
  return {
    id: 'roster-1',
    code: 'RC-1',
    student_id: 'student-1',
    student_code: 'GRS-S-001',
    full_name: 'Amit Kumar',
    email: 'amit@example.com',
    status: 'active',
    enrolled_at: '2026-04-02',
    ...overrides,
  };
}

beforeEach(() => {
  getBatchRoster.mockReset();
  setEnrollmentStatus.mockReset();
  listStudents.mockReset();
  listStudents.mockResolvedValue({ count: 0, page: 1, page_size: 100, total_pages: 1, next: null, previous: null, results: [] });
  useAuth.mockReturnValue({
    can: (capability: string) =>
      [Capability.enrolmentCreate, Capability.enrolmentUpdateAny].includes(capability as never),
  });
});

describe('RosterPanel — double-submission protection', () => {
  it('asks before suspending, then disables the confirm button and calls the server once', async () => {
    getBatchRoster.mockResolvedValue([entry()]);
    let resolve!: () => void;
    setEnrollmentStatus.mockReturnValue(
      new Promise<void>((r) => {
        resolve = r;
      }),
    );

    render(<RosterPanel batch={batch()} onChanged={() => {}} />);

    fireEvent.click(await screen.findByRole('button', { name: 'Suspend' }));
    expect(setEnrollmentStatus).not.toHaveBeenCalled();
    const dialog = await screen.findByRole('dialog', { name: /suspend this enrolment/i });
    const confirm = within(dialog).getByRole('button', { name: 'Suspend' });
    fireEvent.click(confirm);
    fireEvent.click(confirm);

    await waitFor(() => expect(within(dialog).getByRole('button', { name: /suspending/i })).toBeDisabled());
    expect(setEnrollmentStatus).toHaveBeenCalledOnce();
    expect(setEnrollmentStatus).toHaveBeenCalledWith('roster-1', 'suspended', '');

    resolve();
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
  });
});

describe('RosterPanel — withdrawing is never one click', () => {
  it('needs a reason before the enrolment is ended, and sends it with the change', async () => {
    getBatchRoster.mockResolvedValue([entry()]);
    setEnrollmentStatus.mockResolvedValue(undefined);

    render(<RosterPanel batch={batch()} onChanged={() => {}} />);

    fireEvent.click(await screen.findByRole('button', { name: 'Remove' }));
    const dialog = await screen.findByRole('dialog', { name: /withdraw from this batch/i });
    expect(dialog).toHaveTextContent(/cannot be reopened/i);
    const withdraw = within(dialog).getByRole('button', { name: 'Withdraw' });
    expect(withdraw).toBeDisabled();

    fireEvent.change(within(dialog).getByLabelText(/^Reason/), {
      target: { value: 'Moved to another city.' },
    });
    fireEvent.click(withdraw);

    await waitFor(() =>
      expect(setEnrollmentStatus).toHaveBeenCalledWith('roster-1', 'cancelled', 'Moved to another city.'),
    );
  });
});
