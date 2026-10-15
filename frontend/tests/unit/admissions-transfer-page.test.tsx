/**
 * `/admissions/transfer`: both modes ask why, and both move through the real
 * transfer (the old enrolment becomes Transferred), never enrol-and-cancel.
 * The batch mode moves the ticked students in one request and shows who was
 * skipped and why.
 */
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { TransferContent } from '@/app/admissions/transfer/page';
import type { BatchListRow, Enrollment, RosterEntry } from '@/types/api';

const search = vi.hoisted(() => ({ value: '' }));
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  useSearchParams: () => new URLSearchParams(search.value),
}));

const batches = vi.hoisted(() => ({
  getBatchRoster: vi.fn(),
  getEnrollment: vi.fn(),
  listBatches: vi.fn(),
  listEnrolmentDestinations: vi.fn(),
  listStudentEnrollments: vi.fn(),
  transferEnrollment: vi.fn(),
}));
vi.mock('@/lib/batches', async () => {
  const actual = await vi.importActual<typeof import('@/lib/batches')>('@/lib/batches');
  return { ...actual, ...batches };
});
const people = vi.hoisted(() => ({ getStudent: vi.fn(), listStudents: vi.fn() }));
vi.mock('@/lib/people', async () => {
  const actual = await vi.importActual<typeof import('@/lib/people')>('@/lib/people');
  return { ...actual, ...people };
});
const bulkTransferEnrollments = vi.hoisted(() => vi.fn());
vi.mock('@/lib/bulk', async () => {
  const actual = await vi.importActual<typeof import('@/lib/bulk')>('@/lib/bulk');
  return { ...actual, bulkTransferEnrollments };
});

function batch(overrides: Partial<BatchListRow> = {}): BatchListRow {
  return {
    id: 'b-2',
    code: 'GRS-B-002',
    name: 'Evening',
    course_title: 'Linux',
    seats_available: 5,
    start_date: '2026-11-01',
    ...overrides,
  } as BatchListRow;
}

function entry(id: string, name: string): RosterEntry {
  return {
    id,
    code: `E-${id}`,
    student_id: `s-${id}`,
    student_code: `GRS-S-${id}`,
    full_name: name,
    email: `${id}@x.test`,
    status: 'active',
    enrolled_at: '2026-09-01T00:00:00Z',
  };
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.useRealTimers();
  search.value = '';
  batches.listBatches.mockResolvedValue({ results: [batch({ id: 'b-1', name: 'Morning', code: 'GRS-B-001' })] });
  batches.listEnrolmentDestinations.mockResolvedValue({ batches: [batch()], isComplete: true });
});

describe('Transfer — one student', () => {
  it('asks why, then transfers with the reason and the upgrade flag', async () => {
    search.value = '?student=s-1&enrollment=e-1';
    people.getStudent.mockResolvedValue({
      id: 's-1',
      student_id: 'GRS-S-1',
      user: { full_name: 'Asha Rao', email: 'asha@x.test' },
    });
    const source = {
      id: 'e-1',
      batch_id: 'b-1',
      batch_name: 'Morning',
      course_title: 'Linux',
      status: 'active',
    } as Enrollment;
    batches.getEnrollment.mockResolvedValue(source);
    batches.listStudentEnrollments.mockResolvedValue([source]);
    batches.transferEnrollment.mockResolvedValue({ id: 'e-2' });
    render(<TransferContent />);

    const results = await screen.findByRole('listbox', { name: 'Move to batch results' });
    fireEvent.change(results, { target: { value: 'b-2' } });
    expect(await screen.findByTestId('transfer-preview')).toHaveTextContent('marked Transferred');

    fireEvent.click(screen.getByRole('button', { name: 'Confirm transfer' }));
    expect(await screen.findByText('Say why the student is being moved.')).toBeInTheDocument();
    expect(batches.transferEnrollment).not.toHaveBeenCalled();

    fireEvent.change(screen.getByLabelText(/^Reason/), { target: { value: 'Evening suits' } });
    fireEvent.click(screen.getByRole('checkbox'));
    fireEvent.click(screen.getByRole('button', { name: 'Confirm transfer' }));
    await waitFor(() =>
      expect(batches.transferEnrollment).toHaveBeenCalledWith({
        fromEnrollmentId: 'e-1',
        toBatchId: 'b-2',
        reason: 'Evening suits',
        isUpgrade: true,
      }),
    );
    expect(await screen.findByText(/Asha Rao moved from Morning to Evening/)).toBeInTheDocument();
  });
});

describe('Transfer — a whole batch', () => {
  it('moves the ticked students in one request and says who was skipped', async () => {
    batches.getBatchRoster.mockResolvedValue([
      entry('1', 'Asha'),
      entry('2', 'Bala'),
      entry('3', 'Chitra'),
    ]);
    bulkTransferEnrollments.mockResolvedValue({
      action: 'transfer',
      total: 2,
      done: 1,
      skipped: [{ id: '3', label: 'Chitra', reason: 'This batch is full.' }],
    });
    render(<TransferContent />);
    fireEvent.click(screen.getByRole('button', { name: 'Move a whole batch' }));

    fireEvent.change(await screen.findByRole('listbox', { name: 'Move students out of results' }), {
      target: { value: 'b-1' },
    });
    fireEvent.change(await screen.findByRole('listbox', { name: 'Move them to results' }), {
      target: { value: 'b-2' },
    });
    fireEvent.click(await screen.findByRole('checkbox', { name: 'Move Bala' }));
    expect(screen.getByTestId('batch-transfer-preview')).toHaveTextContent('This moves 2 students');
    fireEvent.change(screen.getByLabelText(/^Reason/), { target: { value: 'Merged' } });
    fireEvent.click(screen.getByRole('button', { name: 'Move 2 students' }));

    await waitFor(() =>
      expect(bulkTransferEnrollments).toHaveBeenCalledWith({
        ids: ['1', '3'],
        batch_id: 'b-2',
        reason: 'Merged',
        is_upgrade: false,
      }),
    );
    const table = screen.getByRole('table');
    expect(await within(table).findByText('Moved')).toBeInTheDocument();
    expect(within(table).getByText('This batch is full.')).toBeInTheDocument();
    expect(within(table).queryByText('Bala')).not.toBeInTheDocument();
  });
});
