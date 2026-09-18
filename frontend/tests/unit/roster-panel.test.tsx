/**
 * `RosterPanel` (`app/admin/batches/[batchId]/page.tsx`) — Suspend/
 * Reactivate/Remove had no busy guard (R11 double-submission audit gap),
 * unlike the identical pattern on `app/admissions/[studentId]/page.tsx`.
 * Covers that a fast double-click on a row action only fires the mutation
 * once.
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
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
  it('disables Suspend while the request is in flight and only calls it once on a fast double-click', async () => {
    getBatchRoster.mockResolvedValue([entry()]);
    let resolve!: () => void;
    setEnrollmentStatus.mockReturnValue(
      new Promise<void>((r) => {
        resolve = r;
      }),
    );

    render(<RosterPanel batch={batch()} onChanged={() => {}} />);

    const suspendButton = await screen.findByRole('button', { name: 'Suspend' });
    fireEvent.click(suspendButton);
    fireEvent.click(suspendButton);

    await waitFor(() => expect(suspendButton).toBeDisabled());
    expect(setEnrollmentStatus).toHaveBeenCalledOnce();
    expect(setEnrollmentStatus).toHaveBeenCalledWith('roster-1', 'suspended');

    resolve();
    await waitFor(() => expect(suspendButton).not.toBeDisabled());
  });
});
