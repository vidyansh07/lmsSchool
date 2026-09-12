/**
 * The fee ledger on a student's record: the figures come from the server and
 * are laid out, not recomputed; the three actions open dialogs that write
 * through `lib/fees`; a voided payment stays visible, crossed out; and a
 * reader without `fee.manage_any` sees numbers, not buttons.
 */
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { FeeLedger, describeHistory, money } from '@/components/fees/fee-ledger';
import type {
  Enrollment,
  FeeHistoryEntry,
  FeePayment,
  FeePlan,
  StudentFeeSummary,
} from '@/types/api';

const recordPayment = vi.hoisted(() => vi.fn());
const setEnrollmentFee = vi.hoisted(() => vi.fn());
const setNextDue = vi.hoisted(() => vi.fn());
const voidPayment = vi.hoisted(() => vi.fn());
const getFeeHistory = vi.hoisted(() => vi.fn());

vi.mock('@/lib/fees', () => ({
  recordPayment,
  setEnrollmentFee,
  setNextDue,
  voidPayment,
  getFeeHistory,
}));

function payment(overrides: Partial<FeePayment> = {}): FeePayment {
  return {
    id: 'pay-1',
    receipt_number: 'GRS-R-00001',
    amount: '1000.00',
    paid_on: '2026-09-01',
    method: 'upi',
    reference: 'UPI-77',
    note: '',
    recorded_by: 'Kiran Counsellor',
    created_at: '2026-09-01T10:00:00Z',
    is_voided: false,
    voided_at: null,
    voided_by: null,
    void_reason: '',
    ...overrides,
  };
}

function plan(overrides: Partial<FeePlan> = {}): FeePlan {
  return {
    id: 'plan-1',
    enrollment_id: 'enrol-1',
    enrollment_code: 'GRS-E-00001',
    enrollment_status: 'active',
    course_title: 'Linux Essentials',
    batch_code: 'GRS-B-00001',
    batch_name: 'Morning batch',
    agreed_amount: '12000.00',
    discount_amount: '2000.00',
    discount_reason: 'Referral',
    payable: '10000.00',
    paid: '1000.00',
    balance: '9000.00',
    status: 'partial',
    next_due_amount: '4000.00',
    next_due_on: '2026-08-30',
    is_overdue: true,
    notes: '',
    created_by: 'Kiran Counsellor',
    updated_by: 'Kiran Counsellor',
    created_at: '2026-09-01T10:00:00Z',
    updated_at: '2026-09-01T10:00:00Z',
    payments: [
      payment(),
      payment({
        id: 'pay-2',
        receipt_number: 'GRS-R-00002',
        amount: '500.00',
        is_voided: true,
        voided_at: '2026-09-02T10:00:00Z',
        voided_by: 'Mira Manager',
        void_reason: 'Entered twice',
      }),
    ],
    ...overrides,
  };
}

function summary(plans: FeePlan[]): StudentFeeSummary {
  return {
    payable_total: '10000.00',
    paid_total: '1000.00',
    balance_total: '9000.00',
    next_due_amount: '4000.00',
    next_due_on: '2026-08-30',
    is_overdue: true,
    enrollments_without_plan: 0,
    plans,
  };
}

function enrollment(overrides: Partial<Enrollment> = {}): Enrollment {
  return {
    id: 'enrol-2',
    code: 'GRS-E-00002',
    course_id: 'course-2',
    course_code: 'GRS-C-002',
    course_title: 'Python Foundations',
    course_slug: 'python',
    batch_id: 'batch-2',
    batch_code: 'GRS-B-00002',
    batch_name: 'Evening batch',
    batch_status: 'active',
    trainer_name: '',
    status: 'active',
    enrolled_at: '2026-09-01T10:00:00Z',
    start_date: null,
    access_end_date: null,
    completed_at: null,
    grants_access: true,
    ...overrides,
  };
}

describe('money', () => {
  it('shows whole rupees unless there are paise', () => {
    expect(money('12000.00')).toBe('₹12,000');
    expect(money('3500.50')).toBe('₹3,500.50');
    expect(money(null)).toBe('Not available');
  });
});

describe('describeHistory', () => {
  const entry = (action: string, context: Record<string, unknown>): FeeHistoryEntry => ({
    id: '1',
    action,
    action_label: action,
    actor_label: 'kiran@example.test',
    created_at: '2026-09-01T10:00:00Z',
    context,
  });

  it('reads each audit row back as a sentence', () => {
    expect(
      describeHistory(
        entry('fee.plan.set', {
          agreed_amount: '12000.00',
          discount_amount: '2000.00',
          discount_reason: 'Referral',
        }),
      ),
    ).toBe('Agreed ₹12,000, less ₹2,000 (Referral).');
    expect(
      describeHistory(
        entry('fee.plan.updated', {
          changes: { agreed_amount: { from: '12000.00', to: '11000.00' } },
        }),
      ),
    ).toBe('Changed fee ₹12,000 → ₹11,000.');
    expect(
      describeHistory(
        entry('fee.payment.recorded', {
          amount: '1000.00',
          method: 'upi',
          paid_on: '2026-09-01',
          receipt_number: 'GRS-R-00001',
          balance_after: '9000.00',
        }),
      ),
    ).toContain('Received ₹1,000 by UPI');
    expect(
      describeHistory(
        entry('fee.payment.voided', {
          amount: '500.00',
          receipt_number: 'GRS-R-00002',
          reason: 'Entered twice',
        }),
      ),
    ).toBe('Voided ₹500 (receipt GRS-R-00002): Entered twice.');
  });
});

describe('FeeLedger', () => {
  it('lays out the figures, the payments and the overdue flag', () => {
    render(
      <FeeLedger
        summary={summary([plan()])}
        enrollments={[]}
        mayManage={false}
        isLoading={false}
        error={null}
        onChanged={vi.fn()}
      />,
    );
    expect(screen.getByText('Linux Essentials')).toBeInTheDocument();
    expect(screen.getAllByText('₹9,000').length).toBeGreaterThan(0);
    expect(screen.getByText('Less ₹2,000 · Referral')).toBeInTheDocument();
    expect(screen.getAllByText('Overdue').length).toBeGreaterThan(0);
    expect(screen.getByText('GRS-R-00001')).toBeInTheDocument();
    // The voided payment is still there, marked.
    expect(screen.getByText('GRS-R-00002')).toBeInTheDocument();
    expect(screen.getByText('Voided')).toBeInTheDocument();
    expect(screen.getByText(/Entered twice/)).toBeInTheDocument();
    // Nothing to click for a reader.
    expect(screen.queryByRole('button', { name: /record payment/i })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /^void$/i })).not.toBeInTheDocument();
  });

  it('records a payment through the dialog and reloads', async () => {
    recordPayment.mockResolvedValue(payment({ id: 'pay-3', amount: '4000.00' }));
    const onChanged = vi.fn();
    render(
      <FeeLedger
        summary={summary([plan()])}
        enrollments={[]}
        mayManage
        isLoading={false}
        error={null}
        onChanged={onChanged}
      />,
    );
    fireEvent.click(screen.getByRole('button', { name: /record payment/i }));
    const dialog = await screen.findByRole('dialog');
    fireEvent.change(within(dialog).getByLabelText(/amount/i), { target: { value: '4000' } });
    fireEvent.change(within(dialog).getByLabelText(/reference/i), { target: { value: 'UPI-99' } });
    fireEvent.click(within(dialog).getByRole('button', { name: /record payment/i }));
    await waitFor(() => expect(recordPayment).toHaveBeenCalledOnce());
    expect(recordPayment).toHaveBeenCalledWith(
      'enrol-1',
      expect.objectContaining({
        amount: '4000',
        method: 'cash',
        reference: 'UPI-99',
      }),
    );
    await waitFor(() => expect(onChanged).toHaveBeenCalled());
  });

  it('shows the field error the server sent back', async () => {
    const { ApiError } = await import('@/lib/api');
    recordPayment.mockRejectedValue(
      new ApiError(400, 'validation_error', 'Invalid.', 'req-1', {
        amount: ['Only ₹9,000 is still owed.'],
      }),
    );
    render(
      <FeeLedger
        summary={summary([plan()])}
        enrollments={[]}
        mayManage
        isLoading={false}
        error={null}
        onChanged={vi.fn()}
      />,
    );
    fireEvent.click(screen.getByRole('button', { name: /record payment/i }));
    const dialog = await screen.findByRole('dialog');
    fireEvent.change(within(dialog).getByLabelText(/amount/i), { target: { value: '99999' } });
    fireEvent.click(within(dialog).getByRole('button', { name: /record payment/i }));
    expect(await within(dialog).findByText('Only ₹9,000 is still owed.')).toBeInTheDocument();
  });

  it('voids a payment with a reason, never without one', async () => {
    voidPayment.mockResolvedValue(payment({ is_voided: true }));
    render(
      <FeeLedger
        summary={summary([plan()])}
        enrollments={[]}
        mayManage
        isLoading={false}
        error={null}
        onChanged={vi.fn()}
      />,
    );
    fireEvent.click(screen.getByRole('button', { name: /^void$/i }));
    const confirm = screen.getByRole('button', { name: /^void$/i });
    expect(confirm).toBeDisabled();
    fireEvent.change(screen.getByLabelText(/why this payment is being voided/i), {
      target: { value: 'Wrong student' },
    });
    fireEvent.click(confirm);
    await waitFor(() => expect(voidPayment).toHaveBeenCalledWith('pay-1', 'Wrong student'));
  });

  it('offers to set the fee on an enrolment that has none', async () => {
    setEnrollmentFee.mockResolvedValue(plan({ enrollment_id: 'enrol-2' }));
    render(
      <FeeLedger
        summary={{ ...summary([]), plans: [] }}
        enrollments={[enrollment()]}
        mayManage
        isLoading={false}
        error={null}
        onChanged={vi.fn()}
      />,
    );
    expect(screen.getByText(/No fee agreed yet/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /set the fee/i }));
    const dialog = await screen.findByRole('dialog');
    fireEvent.change(within(dialog).getByLabelText(/course fee/i), { target: { value: '15000' } });
    fireEvent.click(within(dialog).getByRole('button', { name: /save fee/i }));
    await waitFor(() => expect(setEnrollmentFee).toHaveBeenCalledOnce());
    expect(setEnrollmentFee).toHaveBeenCalledWith(
      'enrol-2',
      expect.objectContaining({
        agreed_amount: '15000',
        discount_amount: 0,
      }),
    );
  });

  it('opens the history on demand', async () => {
    getFeeHistory.mockResolvedValue([
      {
        id: 'h1',
        action: 'fee.plan.set',
        action_label: 'Fee agreed',
        actor_label: 'kiran@example.test',
        created_at: '2026-09-01T10:00:00Z',
        context: { agreed_amount: '12000.00', discount_amount: '0' },
      },
    ]);
    render(
      <FeeLedger
        summary={summary([plan()])}
        enrollments={[]}
        mayManage={false}
        isLoading={false}
        error={null}
        onChanged={vi.fn()}
      />,
    );
    fireEvent.click(screen.getByRole('button', { name: /who changed what/i }));
    expect(await screen.findByText('Agreed ₹12,000.')).toBeInTheDocument();
    expect(screen.getByText(/kiran@example.test/)).toBeInTheDocument();
  });
});
