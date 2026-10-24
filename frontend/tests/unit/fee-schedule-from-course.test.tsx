/**
 * "Use the course's structure" on a student's instalment schedule.
 *
 * The course keeps percentages, so the rupees are worked out against what
 * *this* student has to pay — fee less their discount — with the leftover
 * paisa on the first instalment, which is what the server does when it
 * applies a structure itself. Nothing is saved until Save schedule: the
 * button fills the rows in, so a date the student asked about can still be
 * moved.
 */
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { InstallmentsDialog } from '@/components/fees/fee-ledger';
import { ApiError } from '@/lib/api';
import type { FeePlan } from '@/types/api';

const listCourseInstalments = vi.hoisted(() => vi.fn());
vi.mock('@/lib/course-fees', async () => {
  const actual = await vi.importActual<typeof import('@/lib/course-fees')>('@/lib/course-fees');
  return { ...actual, listCourseInstalments };
});

const setInstallments = vi.hoisted(() => vi.fn());
vi.mock('@/lib/fees', async () => {
  const actual = await vi.importActual<typeof import('@/lib/fees')>('@/lib/fees');
  return { ...actual, setInstallments };
});

vi.mock('@/components/auth-provider', () => ({
  useAuth: () => ({ user: { id: 'u1', capabilities: [] }, can: () => true }),
}));

function plan(overrides: Partial<FeePlan> = {}): FeePlan {
  return {
    id: 'plan-1',
    gross_payable: '10000.00',
    written_off: '0.00',
    refund_due: '0.00',
    is_cancelled: false,
    settled_amount: null,
    cancelled_at: null,
    cancellation_reason: '',
    enrollment_id: 'enrol-1',
    enrollment_code: 'GRS-E-1',
    enrollment_status: 'active',
    course_title: 'Linux Essentials',
    course_id: 'course-1',
    batch_code: 'GRS-B-1',
    batch_name: 'Morning',
    agreed_amount: '10000.00',
    discount_amount: '0.00',
    discount_percent: null,
    discount_reason: '',
    payable: '9999.00',
    paid: '0.00',
    balance: '9999.00',
    status: 'pending',
    next_due_amount: null,
    next_due_on: null,
    is_overdue: false,
    notes: '',
    created_by: null,
    updated_by: null,
    created_at: '2026-10-01T00:00:00Z',
    updated_at: '2026-10-01T00:00:00Z',
    installments: [],
    payments: [],
    ...overrides,
  };
}

function renderDialog(overrides: Partial<FeePlan> = {}) {
  return render(
    <InstallmentsDialog
      open
      plan={plan(overrides)}
      onOpenChange={vi.fn()}
      onSaved={vi.fn()}
    />,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe("Use the course's structure", () => {
  it('fills the rows from the percentages, with the odd paisa on the first', async () => {
    listCourseInstalments.mockResolvedValue([
      { id: 'i1', sequence: 1, label: 'Admission', percent: '33.33', due_after_days: 0 },
      { id: 'i2', sequence: 2, label: '', percent: '33.33', due_after_days: 30 },
      { id: 'i3', sequence: 3, label: '', percent: '33.34', due_after_days: 60 },
    ]);
    renderDialog();

    fireEvent.click(screen.getByRole('button', { name: /Use the course's structure/ }));

    await waitFor(() => expect(listCourseInstalments).toHaveBeenCalledWith('course-1'));
    const amounts = await screen.findAllByLabelText(/Instalment \d amount/);
    const values = amounts.map((input) => Number((input as HTMLInputElement).value));
    // 9,999 does not divide into thirds; the schedule still sums to it.
    expect(values.reduce((sum, value) => sum + value, 0)).toBeCloseTo(9999, 2);
    expect(values[0]!).toBeGreaterThan(values[1]!);
  });

  it('says so when the course has no structure, rather than emptying the rows', async () => {
    listCourseInstalments.mockResolvedValue([]);
    renderDialog({
      installments: [
        {
          id: 'x',
          sequence: 1,
          amount: '9999.00',
          due_on: '2026-11-01',
          status: 'pending',
          paid_amount: '0.00',
        },
      ],
    });

    fireEvent.click(screen.getByRole('button', { name: /Use the course's structure/ }));

    expect(
      await screen.findByText('This course has no default instalment structure yet.'),
    ).toBeInTheDocument();
    expect(screen.getAllByLabelText(/Instalment \d amount/)).toHaveLength(1);
  });

  it('reports a failure to read it rather than silently doing nothing', async () => {
    listCourseInstalments.mockRejectedValue(
      new ApiError(500, 'internal_error', 'Boom', 'req-1'),
    );
    renderDialog();

    fireEvent.click(screen.getByRole('button', { name: /Use the course's structure/ }));
    expect(await screen.findByText('Boom')).toBeInTheDocument();
  });

  it('saves nothing by itself — the schedule is still saved by hand', async () => {
    listCourseInstalments.mockResolvedValue([
      { id: 'i1', sequence: 1, label: '', percent: '100', due_after_days: 0 },
    ]);
    renderDialog();

    fireEvent.click(screen.getByRole('button', { name: /Use the course's structure/ }));
    await waitFor(() => expect(listCourseInstalments).toHaveBeenCalled());
    expect(setInstallments).not.toHaveBeenCalled();

    const dialog = within(screen.getByRole('dialog'));
    fireEvent.click(dialog.getByRole('button', { name: 'Save schedule' }));
    await waitFor(() => expect(setInstallments).toHaveBeenCalledWith('enrol-1', expect.any(Array)));
  });
});
