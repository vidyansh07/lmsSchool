/**
 * The fee ledger on a student's record: the figures come from the server and
 * are laid out, not recomputed; the three actions open dialogs that write
 * through `lib/fees`; a voided payment stays visible, crossed out; and a
 * reader without `fee.manage_any` sees numbers, not buttons.
 */
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { FeeLedger, FeePlanCard, describeHistory, money } from '@/components/fees/fee-ledger';
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
const setInstallments = vi.hoisted(() => vi.fn());
const voidPayment = vi.hoisted(() => vi.fn());
const refundPayment = vi.hoisted(() => vi.fn());
const cancelAdmission = vi.hoisted(() => vi.fn());
const getFeeHistory = vi.hoisted(() => vi.fn());
const emailReceipt = vi.hoisted(() => vi.fn());
const emailStatement = vi.hoisted(() => vi.fn());
const listFeeEmails = vi.hoisted(() => vi.fn());

vi.mock('@/lib/fees', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/lib/fees')>()),
  recordPayment,
  setEnrollmentFee,
  setNextDue,
  setInstallments,
  voidPayment,
  refundPayment,
  cancelAdmission,
  getFeeHistory,
  emailReceipt,
  emailStatement,
  listFeeEmails,
}));

function payment(overrides: Partial<FeePayment> = {}): FeePayment {
  return {
    id: 'pay-1',
    receipt_number: 'GRS-R-00001',
    amount: '1000.00',
    paid_on: '2026-09-01',
    method: 'upi',
    reference: 'UPI-77',
    reference_name: '',
    note: '',
    recorded_by: 'Kiran Counsellor',
    created_at: '2026-09-01T10:00:00Z',
    is_voided: false,
    voided_at: null,
    voided_by: null,
    void_reason: '',
    clearing_status: 'cleared',
    cleared_on: null,
    bank: null,
    bank_name: null,
    category: null,
    category_name: null,
    apply_tax: false,
    tax_group: null,
    tax_group_name: null,
    instalment: null,
    kind: 'instalment',
    is_refundable: false,
    is_refunded: false,
    refunded_at: null,
    refunded_by: null,
    refund_reason: '',
    ...overrides,
  };
}

function plan(overrides: Partial<FeePlan> = {}): FeePlan {
  return {
    installments: [],
    id: 'plan-1',
    gross_payable: '20000.00',
    written_off: '0.00',
    refund_due: '0.00',
    is_cancelled: false,
    settled_amount: null,
    cancelled_at: null,
    cancellation_reason: '',
    enrollment_id: 'enrol-1',
    enrollment_code: 'GRS-E-00001',
    enrollment_status: 'active',
    course_title: 'Linux Essentials',
    batch_code: 'GRS-B-00001',
    batch_name: 'Morning batch',
    agreed_amount: '12000.00',
    discount_amount: '2000.00',
    discount_percent: null,
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
        entry('fee.plan.set', {
          agreed_amount: '12000.00',
          discount_amount: '1200.00',
          discount_percent: '10.00',
          discount_reason: 'Referral',
        }),
      ),
    ).toBe('Agreed ₹12,000, less 10% (₹1,200) (Referral).');
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
    // Nothing to click for a reader, but the statement is theirs to download.
    expect(screen.queryByRole('button', { name: /record payment/i })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /email statement/i })).not.toBeInTheDocument();
    expect(screen.getByRole('link', { name: /fee statement \(pdf\)/i })).toBeInTheDocument();
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
    // The fourteen ways the desk is actually paid, in the order the dialog
    // lists them. `other` is deliberately absent: it says nothing, and every
    // real way of paying has its own name.
    const method = within(dialog).getByLabelText(/payment method/i) as HTMLSelectElement;
    expect(Array.from(method.options).map((option) => option.value)).toEqual([
      'cash',
      'cash_deposit',
      'cheque',
      'demand_draft',
      'swipe_card',
      'net_banking',
      'payment_gateway',
      'emi_card',
      'google_pay',
      'paytm',
      'upi',
      'paypal',
      'phonepe',
      'credit_card',
    ]);
    expect(Array.from(method.options).map((option) => option.value)).not.toContain('other');
    fireEvent.change(method, { target: { value: 'upi' } });
    fireEvent.change(within(dialog).getByLabelText(/reference number/i), {
      target: { value: 'UPI-99' },
    });
    fireEvent.change(within(dialog).getByLabelText(/reference name/i), {
      target: { value: 'Father (Ramesh)' },
    });
    fireEvent.click(within(dialog).getByRole('button', { name: /record payment/i }));
    await waitFor(() => expect(recordPayment).toHaveBeenCalledOnce());
    expect(recordPayment).toHaveBeenCalledWith(
      'enrol-1',
      expect.objectContaining({
        amount: '4000',
        method: 'upi',
        reference: 'UPI-99',
        reference_name: 'Father (Ramesh)',
      }),
    );
    await waitFor(() => expect(onChanged).toHaveBeenCalled());
  });

  it('shows who handed over each payment in the history', () => {
    render(
      <FeeLedger
        summary={summary([plan({ payments: [payment({ reference_name: 'Mother' })] })])}
        enrollments={[]}
        mayManage={false}
        isLoading={false}
        error={null}
        onChanged={() => {}}
      />,
    );
    expect(screen.getByText('Mother')).toBeInTheDocument();
  });

  it('lists the instalments with their state and opens the schedule editor', async () => {
    setInstallments.mockResolvedValue(plan());
    const scheduled = plan({
      installments: [
        {
          id: 'i1',
          sequence: 1,
          amount: '5000.00',
          due_on: '2026-09-01',
          paid_amount: '5000.00',
          balance: '0.00',
          status: 'paid',
        },
        {
          id: 'i2',
          sequence: 2,
          amount: '5000.00',
          due_on: '2026-10-01',
          paid_amount: '0.00',
          balance: '5000.00',
          status: 'overdue',
        },
        {
          id: 'i3',
          sequence: 3,
          amount: '5000.00',
          due_on: '2026-11-01',
          paid_amount: '0.00',
          balance: '5000.00',
          status: 'pending',
        },
      ],
      payable: '15000.00',
      balance: '10000.00',
    });
    render(
      <FeeLedger
        summary={summary([scheduled])}
        enrollments={[]}
        mayManage
        isLoading={false}
        error={null}
        onChanged={() => {}}
      />,
    );
    expect(screen.getByText('Instalments')).toBeInTheDocument();
    expect(screen.getByTestId('installment-2')).toHaveTextContent('Overdue');
    expect(screen.getByTestId('installment-3')).toHaveTextContent('Pending');
    expect(screen.getByTestId('installment-1')).toHaveTextContent('Paid');

    fireEvent.click(screen.getByRole('button', { name: /edit instalments/i }));
    const dialog = await screen.findByRole('dialog');
    const amounts = within(dialog).getAllByLabelText(/instalment \d+ amount/i);
    expect(amounts).toHaveLength(3);
    // Changing one amount so the rows no longer add up blocks saving...
    fireEvent.change(amounts[2]!, { target: { value: '4000' } });
    expect(within(dialog).getByRole('alert')).toHaveTextContent(/must add up to/i);
    expect(within(dialog).getByRole('button', { name: /save schedule/i })).toBeDisabled();
    // ...and putting it right lets the schedule be saved.
    fireEvent.change(amounts[2]!, { target: { value: '5000' } });
    fireEvent.click(within(dialog).getByRole('button', { name: /save schedule/i }));
    await waitFor(() => expect(setInstallments).toHaveBeenCalledOnce());
    expect(setInstallments).toHaveBeenCalledWith('enrol-1', [
      { amount: '5000.00', due_on: '2026-09-01' },
      { amount: '5000.00', due_on: '2026-10-01' },
      { amount: '5000', due_on: '2026-11-01' },
    ]);
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

  it('says why a payment was refused when the reason is not about a field', async () => {
    const { ApiError } = await import('@/lib/api');
    recordPayment.mockRejectedValue(
      new ApiError(403, 'permission_denied', 'You cannot record payments for this centre.', 'r'),
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
    fireEvent.change(within(dialog).getByLabelText(/amount/i), { target: { value: '500' } });
    fireEvent.click(within(dialog).getByRole('button', { name: /record payment/i }));
    expect(
      await within(dialog).findByText('You cannot record payments for this centre.'),
    ).toBeInTheDocument();
  });

  it('warns that a timed-out payment may already be saved and refreshes the ledger', async () => {
    const { ApiError } = await import('@/lib/api');
    recordPayment.mockRejectedValue(
      new ApiError(0, 'timeout', 'The request timed out.', ''),
    );
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
    fireEvent.change(within(dialog).getByLabelText(/amount/i), { target: { value: '500' } });
    fireEvent.click(within(dialog).getByRole('button', { name: /record payment/i }));
    expect(await within(dialog).findByText(/may already be saved/i)).toBeInTheDocument();
    expect(onChanged).toHaveBeenCalled();
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

  it('mails the statement, resends a receipt and lists what was sent', async () => {
    emailStatement.mockResolvedValue({ id: 'm1', to_email: 'sam@example.test', status: 'pending' });
    emailReceipt.mockResolvedValue({ id: 'm2', to_email: 'sam@example.test', status: 'pending' });
    listFeeEmails.mockResolvedValue([
      {
        id: 'm2',
        kind: 'fee_receipt',
        receipt_number: 'GRS-R-00001',
        to_email: 'sam@example.test',
        subject: 'Receipt GRS-R-00001',
        status: 'sent',
        attempts: 1,
        last_error: '',
        sent_at: '2026-10-17T10:00:00Z',
        created_at: '2026-10-17T10:00:00Z',
      },
      {
        id: 'm1',
        kind: 'fee_statement',
        receipt_number: null,
        to_email: 'sam@example.test',
        subject: 'Your fee',
        status: 'failed',
        attempts: 1,
        last_error: 'Recipient not verified',
        sent_at: null,
        created_at: '2026-10-17T09:00:00Z',
      },
    ]);
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
    expect(screen.getByRole('link', { name: /fee statement \(pdf\)/i })).toHaveAttribute(
      'href',
      expect.stringContaining('/api/v1/fees/enrollments/enrol-1/statement/'),
    );

    fireEvent.click(screen.getByRole('button', { name: /email statement/i }));
    expect(await screen.findByText(/statement is on its way to sam@example.test/i)).toBeInTheDocument();
    expect(emailStatement).toHaveBeenCalledWith('enrol-1');

    fireEvent.click(screen.getByRole('button', { name: 'Email receipt GRS-R-00001 to the student' }));
    expect(await screen.findByText(/Receipt GRS-R-00001 is on its way/)).toBeInTheDocument();
    expect(emailReceipt).toHaveBeenCalledWith('pay-1');

    fireEvent.click(screen.getByRole('button', { name: /mails sent to the student/i }));
    const log = await screen.findByRole('list', { name: 'Fee mails' });
    expect(within(log).getByText('Receipt GRS-R-00001')).toBeInTheDocument();
    expect(within(log).getByText('Sent')).toBeInTheDocument();
    expect(within(log).getByText('Not delivered yet')).toBeInTheDocument();
    expect(within(log).getByText(/Recipient not verified/)).toBeInTheDocument();
  });

  it('says why a statement could not be mailed', async () => {
    const { ApiError } = await import('@/lib/api');
    emailStatement.mockRejectedValue(
      new ApiError(400, 'invalid', 'This student has no active email address to send to.', ''),
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
    fireEvent.click(screen.getByRole('button', { name: /email statement/i }));
    expect(await screen.findByText(/no active email address/i)).toBeInTheDocument();
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
        discount_percent: null,
      }),
    );
  });

  it('takes a discount as a percentage by default and shows the rupees', async () => {
    setEnrollmentFee.mockClear();
    setEnrollmentFee.mockResolvedValue({});
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
    fireEvent.click(screen.getByRole('button', { name: /set the fee/i }));
    const dialog = await screen.findByRole('dialog');
    fireEvent.change(within(dialog).getByLabelText(/course fee/i), { target: { value: '20000' } });
    fireEvent.change(within(dialog).getByLabelText('Discount (%)'), { target: { value: '15' } });
    expect(within(dialog).getByText('₹3,000 off the fee.')).toBeInTheDocument();
    expect(within(dialog).getByText('₹17,000')).toBeInTheDocument();
    fireEvent.change(within(dialog).getByLabelText(/reason for the discount/i), {
      target: { value: 'Scholarship' },
    });

    // Switching to rupees carries the figure across.
    fireEvent.click(within(dialog).getByRole('button', { name: 'Rupees' }));
    expect(within(dialog).getByLabelText('Discount (₹)')).toHaveValue(3000);
    fireEvent.click(within(dialog).getByRole('button', { name: 'Percentage of the fee' }));
    expect(within(dialog).getByLabelText('Discount (%)')).toHaveValue(15);

    fireEvent.click(within(dialog).getByRole('button', { name: /save fee/i }));
    await waitFor(() => expect(setEnrollmentFee).toHaveBeenCalledOnce());
    expect(setEnrollmentFee).toHaveBeenCalledWith(
      'enrol-2',
      expect.objectContaining({
        agreed_amount: '20000',
        discount_percent: '15',
        discount_amount: 0,
        discount_reason: 'Scholarship',
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


describe('ending an admission and giving money back', () => {
  /**
   * Both acts are destructive and both are offered only to somebody who may
   * manage fees — the server enforces that, and a button nobody may press is
   * a puzzle, so the screen does not draw one.
   */
  beforeEach(() => {
    refundPayment.mockReset().mockResolvedValue({});
    cancelAdmission.mockReset().mockResolvedValue({});
  });

  it('offers no cancel button to somebody who may not manage fees', () => {
    render(<FeePlanCard plan={plan()} mayManage={false} onChanged={() => {}} />);

    expect(screen.queryByRole('button', { name: /cancel admission/i })).not.toBeInTheDocument();
  });

  it('offers it to somebody who may', () => {
    render(<FeePlanCard plan={plan()} mayManage onChanged={() => {}} />);

    expect(screen.getByRole('button', { name: /cancel admission/i })).toBeInTheDocument();
  });

  it('will not cancel without a reason', async () => {
    // Money written off is a decision somebody has to account for later.
    const user = userEvent.setup();
    render(<FeePlanCard plan={plan()} mayManage onChanged={() => {}} />);

    await user.click(screen.getByRole('button', { name: /cancel admission/i }));

    expect(screen.getByRole('button', { name: /cancel the admission/i })).toBeDisabled();
    expect(cancelAdmission).not.toHaveBeenCalled();
  });

  it('says what cancelling will do before it does it', async () => {
    // Cancelling moves money in three directions at once, and somebody is
    // about to read one of these numbers down the phone.
    const user = userEvent.setup();
    render(
      <FeePlanCard
        plan={plan({ payable: '20000.00', paid: '8000.00' })}
        mayManage
        onChanged={() => {}}
      />,
    );

    await user.click(screen.getByRole('button', { name: /cancel admission/i }));
    await user.clear(screen.getByLabelText(/cancellation charge/i));
    await user.type(screen.getByLabelText(/cancellation charge/i), '3000');

    expect(screen.getByText('₹17,000')).toBeInTheDocument();
    expect(screen.getByText('To refund')).toBeInTheDocument();
    expect(screen.getByText('₹5,000')).toBeInTheDocument();
  });

  it('sends the charge and the reason', async () => {
    const user = userEvent.setup();
    render(<FeePlanCard plan={plan()} mayManage onChanged={() => {}} />);

    await user.click(screen.getByRole('button', { name: /cancel admission/i }));
    await user.clear(screen.getByLabelText(/cancellation charge/i));
    await user.type(screen.getByLabelText(/cancellation charge/i), '3000');
    await user.type(screen.getByLabelText(/why it is being cancelled/i), 'Four weeks attended');
    await user.click(screen.getByRole('button', { name: /cancel the admission/i }));

    await waitFor(() =>
      expect(cancelAdmission).toHaveBeenCalledWith('enrol-1', {
        cancellation_charge: '3000',
        reason: 'Four weeks attended',
      }),
    );
  });

  it('does not offer to cancel an admission that is already cancelled', () => {
    // The way back is a new admission, not an undo.
    render(
      <FeePlanCard
        plan={plan({ is_cancelled: true, settled_amount: '3000.00' })}
        mayManage
        onChanged={() => {}}
      />,
    );

    expect(screen.queryByRole('button', { name: /cancel admission/i })).not.toBeInTheDocument();
  });

  it('explains a cancelled plan, because its numbers changed meaning', () => {
    // Without this, a plan reading "₹3,000" looks like a cheap course rather
    // than a settled cancellation.
    render(
      <FeePlanCard
        plan={plan({
          is_cancelled: true,
          settled_amount: '3000.00',
          gross_payable: '20000.00',
          written_off: '17000.00',
          cancellation_reason: 'Four weeks attended',
        })}
        mayManage
        onChanged={() => {}}
      />,
    );

    expect(screen.getByText('Admission cancelled')).toBeInTheDocument();
    expect(screen.getByText('Four weeks attended')).toBeInTheDocument();
  });
});

describe('Cancelling an admission — the charge that silently did nothing', () => {
  it('says the charge is too big instead of a button that does nothing', async () => {
    // The amount input carries `max`, and a browser refuses to submit a form
    // holding a value outside its own constraints — so this dialog's confirm
    // button did nothing at all, with no message anywhere. The form is now
    // `noValidate` and the check is ours.
    const user = userEvent.setup();
    render(
      <FeePlanCard
        plan={plan({ payable: '20000.00', paid: '5000.00' })}
        mayManage
        onChanged={() => {}}
      />,
    );

    await user.click(screen.getByRole('button', { name: /cancel admission/i }));
    await user.clear(screen.getByLabelText(/cancellation charge/i));
    await user.type(screen.getByLabelText(/cancellation charge/i), '99999');
    await user.type(screen.getByLabelText(/why it is being cancelled/i), 'Moved city.');
    await user.click(screen.getByRole('button', { name: /cancel the admission/i }));

    expect(await screen.findByText(/cannot be more than the .* owed/i)).toBeInTheDocument();
    expect(cancelAdmission).not.toHaveBeenCalled();
  });
});
