/**
 * Comment threads on a payment and on an instalment.
 *
 * What is worth pinning is the behaviour the thread exists for: it reads
 * downwards, nothing in it can be edited, and the composer is absent for
 * somebody who may only look. The column itself is absent for a student,
 * because a desk writes "chasing is pointless until the exam" in one of these
 * and that is not a sentence to render on the student's own fee screen.
 */
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import {
  CommentCountButton,
  CommentThreadDialog,
} from '@/components/fees/comment-thread';
import { FeePlanCard } from '@/components/fees/fee-ledger';
import { ApiError } from '@/lib/api';
import type { FeeComment, FeeInstallment, FeePayment, FeePlan } from '@/types/api';

const listPaymentComments = vi.hoisted(() => vi.fn());
const addPaymentComment = vi.hoisted(() => vi.fn());
const listInstalmentComments = vi.hoisted(() => vi.fn());
const addInstalmentComment = vi.hoisted(() => vi.fn());

vi.mock('@/lib/fees', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/lib/fees')>()),
  listPaymentComments,
  addPaymentComment,
  listInstalmentComments,
  addInstalmentComment,
  getFeeHistory: vi.fn().mockResolvedValue([]),
  listFeeEmails: vi.fn().mockResolvedValue([]),
}));

function comment(overrides: Partial<FeeComment> = {}): FeeComment {
  return {
    id: 'c-1',
    body: 'Cheque with the bank since Tuesday.',
    author: 'Kiran Counsellor',
    created_at: '2026-10-20T09:00:00Z',
    ...overrides,
  };
}

function instalment(overrides: Partial<FeeInstallment> = {}): FeeInstallment {
  return {
    id: 'i-1',
    sequence: 1,
    amount: '5000.00',
    due_on: '2026-11-01',
    paid_amount: '0.00',
    balance: '5000.00',
    status: 'pending',
    comment_count: 0,
    ...overrides,
  };
}

function payment(overrides: Partial<FeePayment> = {}): FeePayment {
  return {
    id: 'pay-1',
    receipt_number: 'GRS-R-00001',
    amount: '5000.00',
    paid_on: '2026-10-20',
    method: 'cheque',
    reference: 'CHQ-9931',
    reference_name: '',
    note: '',
    recorded_by: 'Kiran Counsellor',
    created_at: '2026-10-20T09:00:00Z',
    is_voided: false,
    voided_at: null,
    voided_by: null,
    void_reason: '',
    kind: 'instalment',
    is_refundable: false,
    is_refunded: false,
    refunded_at: null,
    refunded_by: null,
    refund_reason: '',
    clearing_status: 'uncleared',
    cleared_on: null,
    bank: null,
    bank_name: null,
    category: null,
    category_name: null,
    apply_tax: false,
    tax_group: null,
    tax_group_name: null,
    instalment: null,
    comment_count: 0,
    ...overrides,
  };
}

function plan(overrides: Partial<FeePlan> = {}): FeePlan {
  return {
    id: 'plan-1',
    enrollment_id: 'enrol-1',
    course_id: 'course-1',
    enrollment_code: 'GRS-E-00001',
    enrollment_status: 'active',
    course_title: 'Linux Essentials',
    batch_code: 'GRS-B-00001',
    batch_name: 'Morning batch',
    agreed_amount: '20000.00',
    gross_payable: '20000.00',
    discount_amount: '0.00',
    discount_percent: null,
    discount_reason: '',
    written_off: '0.00',
    refund_due: '0.00',
    is_cancelled: false,
    settled_amount: null,
    cancelled_at: null,
    cancellation_reason: '',
    payable: '20000.00',
    paid: '5000.00',
    balance: '15000.00',
    status: 'partial',
    is_overdue: false,
    next_due_on: null,
    next_due_amount: null,
    notes: '',
    created_by: null,
    updated_by: null,
    created_at: '2026-10-20T09:00:00Z',
    updated_at: '2026-10-20T09:00:00Z',
    installments: [instalment()],
    payments: [payment()],
    ...overrides,
  };
}

beforeEach(() => {
  vi.clearAllMocks();
  listPaymentComments.mockResolvedValue([]);
  listInstalmentComments.mockResolvedValue([]);
});

// ---------------------------------------------------------------------------
// The dialog
// ---------------------------------------------------------------------------

describe('CommentThreadDialog', () => {
  function open(props: Partial<React.ComponentProps<typeof CommentThreadDialog>> = {}) {
    return render(
      <CommentThreadDialog
        open
        target={{ kind: 'payment', id: 'pay-1' }}
        title="Comments on receipt GRS-R-00001"
        description="What the desk has said about this row."
        canWrite
        onClose={vi.fn()}
        {...props}
      />,
    );
  }

  it('reads the thread downwards, oldest first as the server sends it', async () => {
    listPaymentComments.mockResolvedValue([
      comment({ id: 'c-1', body: 'Rang the father.' }),
      comment({ id: 'c-2', body: 'He asked for the 15th.' }),
    ]);
    open();

    await waitFor(() => expect(listPaymentComments).toHaveBeenCalledWith('pay-1'));
    const items = await screen.findAllByRole('listitem');
    expect(items.map((item) => item.textContent)).toEqual([
      expect.stringContaining('Rang the father.'),
      expect.stringContaining('He asked for the 15th.'),
    ]);
  });

  it('says so plainly when nothing has been written yet', async () => {
    open();
    expect(await screen.findByText('Nothing written about this one yet.')).toBeInTheDocument();
  });

  it('adds a comment and shows it without re-reading the thread', async () => {
    addPaymentComment.mockResolvedValue(comment({ id: 'c-9', body: 'Bank honoured it today.' }));
    const onAdded = vi.fn();
    open({ onAdded });

    await screen.findByText('Nothing written about this one yet.');
    fireEvent.change(screen.getByLabelText('Add a comment'), {
      target: { value: 'Bank honoured it today.' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Add comment' }));

    await waitFor(() =>
      expect(addPaymentComment).toHaveBeenCalledWith('pay-1', 'Bank honoured it today.'),
    );
    expect(await screen.findByText('Bank honoured it today.')).toBeInTheDocument();
    // The count beside the row has to move too, which is the caller's job.
    expect(onAdded).toHaveBeenCalledWith({ kind: 'payment', id: 'pay-1' });
    // One read, for opening — the new message came back from the write.
    expect(listPaymentComments).toHaveBeenCalledTimes(1);
  });

  it('will not post an empty comment', async () => {
    open();
    await screen.findByText('Nothing written about this one yet.');
    expect(screen.getByRole('button', { name: 'Add comment' })).toBeDisabled();
    expect(addPaymentComment).not.toHaveBeenCalled();
  });

  it('says what the server refused rather than looking as though it saved', async () => {
    addPaymentComment.mockRejectedValue(
      new ApiError(400, 'validation_error', 'Keep a comment under 1000 characters.', 'r1', {
        body: ['Keep a comment under 1000 characters.'],
      }),
    );
    open();
    await screen.findByText('Nothing written about this one yet.');

    fireEvent.change(screen.getByLabelText('Add a comment'), { target: { value: 'x' } });
    fireEvent.click(screen.getByRole('button', { name: 'Add comment' }));
    expect(await screen.findByText('Keep a comment under 1000 characters.')).toBeInTheDocument();
  });

  it('offers no composer to somebody who may only read', async () => {
    listPaymentComments.mockResolvedValue([comment()]);
    open({ canWrite: false });

    await screen.findByText('Cheque with the bank since Tuesday.');
    expect(screen.queryByLabelText('Add a comment')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Add comment' })).not.toBeInTheDocument();
  });

  it('reads an instalment thread from the instalment endpoint', async () => {
    listInstalmentComments.mockResolvedValue([comment({ body: 'Pushed to the 15th.' })]);
    open({ target: { kind: 'instalment', id: 'i-1' } });

    await waitFor(() => expect(listInstalmentComments).toHaveBeenCalledWith('i-1'));
    expect(await screen.findByText('Pushed to the 15th.')).toBeInTheDocument();
    expect(listPaymentComments).not.toHaveBeenCalled();
  });

  it('names a message whose author has since left rather than showing a blank', async () => {
    listPaymentComments.mockResolvedValue([comment({ author: null })]);
    open();
    expect(await screen.findByText(/A former colleague/)).toBeInTheDocument();
  });

  it('offers nothing that would edit or delete a message', async () => {
    listPaymentComments.mockResolvedValue([comment()]);
    open();

    await screen.findByText('Cheque with the bank since Tuesday.');
    expect(screen.queryByRole('button', { name: /edit/i })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /delete/i })).not.toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// The affordance in a row
// ---------------------------------------------------------------------------

describe('CommentCountButton', () => {
  it('reads as an invitation when the row has no thread', () => {
    render(<CommentCountButton count={0} label="receipt GRS-R-00001" onClick={vi.fn()} />);
    expect(
      screen.getByRole('button', { name: 'Comment on receipt GRS-R-00001' }),
    ).toBeInTheDocument();
  });

  it('carries the count and the row in its name, so a column is not all alike', () => {
    render(<CommentCountButton count={3} label="instalment 2" onClick={vi.fn()} />);
    expect(screen.getByRole('button', { name: 'Comments on instalment 2 (3)' })).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// In the fee card
// ---------------------------------------------------------------------------

describe('FeePlanCard comments', () => {
  it('shows a comments column on the payments and the schedule', () => {
    render(
      <FeePlanCard
        plan={plan({ payments: [payment({ comment_count: 2 })] })}
        mayManage
        mayReadComments
        onChanged={vi.fn()}
      />,
    );

    expect(
      screen.getByRole('button', { name: 'Comments on receipt GRS-R-00001 (2)' }),
    ).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Comment on instalment 1' })).toBeInTheDocument();
  });

  it('opens the thread for the row that was clicked', async () => {
    listPaymentComments.mockResolvedValue([comment({ body: 'Cheque still with the bank.' })]);
    render(<FeePlanCard plan={plan()} mayManage mayReadComments onChanged={vi.fn()} />);

    fireEvent.click(screen.getByRole('button', { name: 'Comment on receipt GRS-R-00001' }));
    const dialog = await screen.findByRole('dialog');
    expect(within(dialog).getByText(/Comments on receipt GRS-R-00001/)).toBeInTheDocument();
    expect(await within(dialog).findByText('Cheque still with the bank.')).toBeInTheDocument();
  });

  it('lets a reader open a thread but not write in it', async () => {
    listInstalmentComments.mockResolvedValue([comment({ body: 'Agreed to wait.' })]);
    render(<FeePlanCard plan={plan()} mayManage={false} mayReadComments onChanged={vi.fn()} />);

    fireEvent.click(screen.getByRole('button', { name: 'Comment on instalment 1' }));
    const dialog = await screen.findByRole('dialog');
    expect(await within(dialog).findByText('Agreed to wait.')).toBeInTheDocument();
    expect(within(dialog).queryByLabelText('Add a comment')).not.toBeInTheDocument();
  });

  it('shows no comments at all to somebody without fee.view_any', () => {
    // A student looking at their own fees. The column is absent rather than
    // present-and-403, because these are notes about the student.
    render(<FeePlanCard plan={plan()} mayManage={false} onChanged={vi.fn()} />);

    expect(screen.queryByRole('button', { name: /Comment/ })).not.toBeInTheDocument();
    expect(screen.queryByText('Comments')).not.toBeInTheDocument();
  });
});
