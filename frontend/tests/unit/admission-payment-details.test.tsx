/**
 * An admission's money screen.
 *
 * The behaviour this pins down is the one that could lose a rupee: an
 * admission can carry two courses and each keeps its own fee plan, so the
 * payments and instalments shown here are *merged*. Every action has to name
 * the plan it acts on — a payment spread over two ledgers could not be
 * refunded, receipted or reconciled.
 */
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { PaymentDetails } from '@/components/admissions/payment-details';
import { ApiError } from '@/lib/api';
import type { Admission } from '@/lib/admissions-api';
import type { FeePlan } from '@/types/api';

const getAdmission = vi.hoisted(() => vi.fn());
vi.mock('@/lib/admissions-api', () => ({ getAdmission }));

const getEnrollmentFee = vi.hoisted(() => vi.fn());
const emailReceipt = vi.hoisted(() => vi.fn());
const recordPayment = vi.hoisted(() => vi.fn());
vi.mock('@/lib/fees', () => ({ getEnrollmentFee, emailReceipt, recordPayment }));

vi.mock('@/lib/fee-settings', () => ({
  listBanks: vi.fn().mockResolvedValue([{ id: 'b1', name: 'HDFC Bank' }]),
  listPaymentCategories: vi.fn().mockResolvedValue([{ id: 'c1', name: 'Fees', is_default: true }]),
  listTaxGroups: vi.fn().mockResolvedValue([{ id: 't1', name: 'GST', is_default: true }]),
}));

function admission(overrides: Partial<Admission> = {}): Admission {
  return {
    id: 'adm-1',
    student_id: 'student-1',
    student_name: 'Vipul Attri',
    branch_id: 'b',
    branch_name: 'Jaipur',
    academic_year_id: 'y',
    academic_year: '2026',
    admission_date: '2026-10-23',
    status: 'active',
    is_cancelled: false,
    discount_kind: 'flat',
    discount_amount: '0.00',
    discount_percent: null,
    gross_total: '30000.00',
    total_fees: '30000.00',
    note: '',
    money: {
      total: '30000.00',
      paid: '1000.00',
      uncleared: '0.00',
      refund: '0.00',
      balance: '29000.00',
    },
    lines: [
      {
        id: 'l1',
        kind: 'course',
        course_id: 'c-1',
        course_title: 'Data Analytics',
        label: '',
        name: 'Data Analytics',
        charged_on_id: null,
        quantity: 1,
        unit_fee: '30000.00',
        line_total: '30000.00',
        discount_share: '0.00',
        enrollment_id: 'enrol-1',
      },
    ],
    created_by: 'Deepti Vyas',
    cancelled_at: null,
    cancellation_reason: '',
    created_at: '2026-10-23T09:00:00Z',
    updated_at: '2026-10-23T09:00:00Z',
    ...overrides,
  };
}

function plan(overrides: Partial<FeePlan> = {}): FeePlan {
  return {
    id: 'plan-1',
    gross_payable: '30000.00',
    written_off: '0.00',
    refund_due: '0.00',
    is_cancelled: false,
    settled_amount: null,
    cancelled_at: null,
    cancellation_reason: '',
    enrollment_id: 'enrol-1',
    course_id: 'course-1',
    enrollment_code: 'E-1',
    enrollment_status: 'active',
    course_title: 'Data Analytics',
    batch_code: 'B-1',
    batch_name: 'Morning',
    agreed_amount: '30000.00',
    discount_amount: '0.00',
    discount_percent: null,
    discount_reason: '',
    payable: '30000.00',
    paid: '1000.00',
    balance: '29000.00',
    status: 'partial',
    next_due_amount: '7250.00',
    next_due_on: '2026-12-24',
    is_overdue: false,
    notes: '',
    created_by: null,
    updated_by: null,
    created_at: '2026-10-23T09:00:00Z',
    updated_at: '2026-10-23T09:00:00Z',
    installments: [
      { id: 'i1', sequence: 1, amount: '1000.00', due_on: '2026-10-23', paid_amount: '1000.00', balance: '0.00', status: 'paid' },
      { id: 'i2', sequence: 2, amount: '7250.00', due_on: '2026-12-24', paid_amount: '0.00', balance: '7250.00', status: 'pending' },
    ],
    payments: [
      {
        kind: 'instalment',
        is_refundable: false,
        is_refunded: false,
        refunded_at: null,
        refunded_by: null,
        refund_reason: '',
        id: 'pay-1',
        receipt_number: 'B1-2026-27-1712',
        amount: '1000.00',
        paid_on: '2026-10-23',
        method: 'upi',
        reference: 'Annu Agarwal',
        reference_name: '',
        note: '',
        recorded_by: 'Deepti Vyas',
        created_at: '2026-10-23T09:11:00Z',
        is_voided: false,
        voided_at: null,
        voided_by: null,
        void_reason: '',
        clearing_status: 'cleared',
        cleared_on: '2026-10-23',
        bank: null,
        bank_name: null,
        category: 'c1',
        category_name: 'Fees',
        apply_tax: false,
        tax_group: null,
        tax_group_name: null,
        instalment: 'i1',
      },
    ],
    ...overrides,
  };
}

describe('PaymentDetails', () => {
  beforeEach(() => {
    getAdmission.mockReset().mockResolvedValue(admission());
    getEnrollmentFee.mockReset().mockResolvedValue(plan());
    emailReceipt.mockReset().mockResolvedValue({});
    recordPayment.mockReset().mockResolvedValue({});
  });

  it('opens with the four figures the desk reads', async () => {
    render(<PaymentDetails studentId="student-1" admissionId="adm-1" canManage />);

    expect(await screen.findByText('Total (Rs.)')).toBeInTheDocument();
    expect(screen.getByText('Received (Rs.)')).toBeInTheDocument();
    expect(screen.getByText('Uncleared (Rs.)')).toBeInTheDocument();
    expect(screen.getByText('Balance (Rs.)')).toBeInTheDocument();
    expect(screen.getByText('30,000')).toBeInTheDocument();
    expect(screen.getByText('29,000')).toBeInTheDocument();
  });

  it('reads a payment back the way the receipt does', async () => {
    render(<PaymentDetails studentId="student-1" admissionId="adm-1" canManage />);

    expect(
      await screen.findByText('Paid on 23 Oct 2026 by UPI with reference number Annu Agarwal.'),
    ).toBeInTheDocument();
    expect(screen.getByText(/created by Deepti Vyas/)).toBeInTheDocument();
    // Scoped: "Fees" is also a row in the admission's own figures down the
    // right, and an unscoped query cannot tell the badge from the label.
    const paidSection = screen.getByText('Paid').closest('div') as HTMLElement;
    expect(within(paidSection).getByText('Fees')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /Print/ })).toHaveAttribute(
      'href',
      expect.stringContaining('/fees/payments/pay-1/receipt/'),
    );
  });

  it('lists only what is still unpaid', async () => {
    render(<PaymentDetails studentId="student-1" admissionId="adm-1" canManage />);

    expect(await screen.findByText('Unpaid')).toBeInTheDocument();
    expect(screen.getByText('Due on 24 Dec 2026.')).toBeInTheDocument();
    // The settled instalment is not repeated under Unpaid.
    expect(screen.queryByText('Due on 23 Oct 2026.')).not.toBeInTheDocument();
  });

  it('pays one instalment of one plan, naming that instalment', async () => {
    render(<PaymentDetails studentId="student-1" admissionId="adm-1" canManage />);
    fireEvent.click(await screen.findByRole('button', { name: /Pay/ }));

    const dialog = await screen.findByRole('dialog');
    expect(within(dialog).getByText('Payment')).toBeInTheDocument();
    // The amount and the instalment date arrive fixed — this is recording
    // *this* instalment, not deciding what to collect.
    expect(within(dialog).getByLabelText('Amount')).toBeDisabled();
    expect(within(dialog).getByLabelText('Instalment Date')).toBeDisabled();
    expect(within(dialog).getByLabelText(/How Vipul is paying/)).toBeInTheDocument();

    fireEvent.click(within(dialog).getByRole('button', { name: 'Save' }));

    await waitFor(() => expect(recordPayment).toHaveBeenCalled());
    const [enrollmentId, payload] = recordPayment.mock.calls[0]!;
    expect(enrollmentId).toBe('enrol-1');
    expect(payload.amount).toBe('7250.00');
    expect(payload.instalment).toBe('i2');
  });

  it('asks which bank only for the methods that go through one', async () => {
    render(<PaymentDetails studentId="student-1" admissionId="adm-1" canManage />);
    fireEvent.click(await screen.findByRole('button', { name: /Pay/ }));
    const dialog = await screen.findByRole('dialog');

    expect(within(dialog).queryByLabelText('Bank Name')).not.toBeInTheDocument();
    fireEvent.change(within(dialog).getByLabelText(/How Vipul is paying/), {
      target: { value: 'cheque' },
    });
    expect(await within(dialog).findByLabelText('Bank Name')).toBeInTheDocument();
    // The sentence carries <strong>uncleared</strong> inside it, so it is
    // matched on the element that holds the whole thing rather than on one
    // broken-up fragment.
    expect(
      within(dialog).getByText(
        (_, element) =>
          element?.tagName === 'P' &&
          (element.textContent ?? '').includes('until the bank honours it'),
      ),
    ).toBeInTheDocument();
  });

  it('will not record a tax group nobody applied tax to', async () => {
    render(<PaymentDetails studentId="student-1" admissionId="adm-1" canManage />);
    fireEvent.click(await screen.findByRole('button', { name: /Pay/ }));
    const dialog = await screen.findByRole('dialog');

    expect(within(dialog).getByLabelText('Tax Group')).toBeDisabled();
    fireEvent.click(within(dialog).getByLabelText('Apply tax'));
    expect(within(dialog).getByLabelText('Tax Group')).not.toBeDisabled();

    fireEvent.click(within(dialog).getByRole('button', { name: 'Save' }));
    await waitFor(() => expect(recordPayment).toHaveBeenCalled());
    expect(recordPayment.mock.calls[0]![1].apply_tax).toBe(true);
    expect(recordPayment.mock.calls[0]![1].tax_group).toBe('t1');
  });

  it('merges two courses and still names the plan each instalment belongs to', async () => {
    getAdmission.mockResolvedValue(
      admission({
        lines: [
          { ...admission().lines[0]!, id: 'l1', enrollment_id: 'enrol-1' },
          {
            ...admission().lines[0]!,
            id: 'l2',
            course_title: 'Linux',
            name: 'Linux',
            enrollment_id: 'enrol-2',
          },
        ],
      }),
    );
    getEnrollmentFee.mockImplementation((id: string) =>
      Promise.resolve(
        id === 'enrol-1'
          ? plan()
          : plan({
              id: 'plan-2',
              enrollment_id: 'enrol-2',
              course_title: 'Linux',
              payments: [],
              installments: [
                { id: 'j1', sequence: 1, amount: '5000.00', due_on: '2026-11-10', paid_amount: '0.00', balance: '5000.00', status: 'pending' },
              ],
            }),
      ),
    );

    render(<PaymentDetails studentId="student-1" admissionId="adm-1" canManage />);

    expect(await screen.findByText('Due on 10 Nov 2026.')).toBeInTheDocument();
    expect(screen.getByText('Due on 24 Dec 2026.')).toBeInTheDocument();
    // With more than one ledger behind the screen, each row says whose it is.
    expect(screen.getByText('Linux')).toBeInTheDocument();
  });

  it('offers nothing that writes to somebody who may only read the figures', async () => {
    render(<PaymentDetails studentId="student-1" admissionId="adm-1" canManage={false} />);

    expect(await screen.findByText('Paid')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /^Pay$/ })).not.toBeInTheDocument();
    expect(screen.queryByRole('link', { name: /Reconfigure instalments/ })).not.toBeInTheDocument();
  });

  it('shows the admission figures and the event note down the side', async () => {
    render(<PaymentDetails studentId="student-1" admissionId="adm-1" canManage />);

    expect(await screen.findByText('Admission Date')).toBeInTheDocument();
    expect(screen.getByText('Cancellation Charges')).toBeInTheDocument();
    expect(screen.getByText(/added new admission/)).toBeInTheDocument();
    expect(screen.getByText(/for the student/)).toBeInTheDocument();
  });

  it('says a course with no batch yet simply has no plan, rather than failing', async () => {
    getAdmission.mockResolvedValue(
      admission({ lines: [{ ...admission().lines[0]!, enrollment_id: null }] }),
    );
    render(<PaymentDetails studentId="student-1" admissionId="adm-1" canManage />);

    expect(await screen.findByText('Nothing outstanding')).toBeInTheDocument();
    expect(getEnrollmentFee).not.toHaveBeenCalled();
  });

  it('offers a retry when the admission will not load', async () => {
    getAdmission.mockRejectedValue(new ApiError(500, 'server_error', 'Down.', 'req-1'));
    render(<PaymentDetails studentId="student-1" admissionId="adm-1" canManage />);

    expect(await screen.findByText('Down.')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /try again/i }));
    await waitFor(() => expect(getAdmission).toHaveBeenCalledTimes(2));
  });
});
