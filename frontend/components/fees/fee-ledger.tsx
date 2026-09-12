'use client';

/**
 * A student's fees, course by course.
 *
 * One card per enrolment: what was agreed, what has come in, what is still
 * owed, and every payment underneath with its receipt number and who took it.
 * The arithmetic is the server's (`FeePlan.payable/paid/balance`); this file
 * only lays it out.
 *
 * Three actions, each a small dialog rather than an inline form, because each
 * one writes a number that ends up on a receipt and deserves a deliberate
 * "Save": set or change the agreed fee (with a discount and its reason),
 * record a payment (any amount, any past date, any method), and note what is
 * expected next and by when. A payment is never edited or deleted — the
 * "Void" control keeps it, crossed out, with the reason beside it.
 *
 * Read-only for anybody without `fee.manage_any` — a student looking at their
 * own fees, an administrator who prefers to look rather than touch. The
 * server checks the capability again on every write.
 */

import { useCallback, useEffect, useState } from 'react';
import {
  BadgeIndianRupee,
  CalendarClock,
  ChevronDown,
  ChevronUp,
  History,
  Receipt,
  Wallet,
} from 'lucide-react';

import { EmptyState, ErrorState, LoadingState } from '@/components/states';
import { Alert } from '@/components/ui/alert';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Field } from '@/components/ui/field';
import { Input, Select, Textarea } from '@/components/ui/input';
import { Table, TableWrapper, Td, Th, Tr } from '@/components/ui/table';
import { ApiError, errorMessage, fieldErrors } from '@/lib/api';
import { ENROLLMENT_STATUS_LABEL, ENROLLMENT_STATUS_VARIANT } from '@/lib/batch-labels';
import {
  getFeeHistory,
  recordPayment,
  setEnrollmentFee,
  setNextDue,
  voidPayment,
} from '@/lib/fees';
import { formatCurrency, formatDate, formatDateTime } from '@/lib/format';
import {
  FEE_PLAN_STATUS_LABEL,
  FEE_PLAN_STATUS_VARIANT,
  PAYMENT_METHOD_LABEL,
  PAYMENT_METHOD_OPTIONS,
} from '@/lib/labels';
import { cn } from '@/lib/utils';
import type {
  Enrollment,
  FeeHistoryEntry,
  FeePayment,
  FeePlan,
  PaymentMethod,
  StudentFeeSummary,
} from '@/types/api';

/** Whole rupees unless there are paise to show — ₹3,500.50 must not round. */
export function money(value: string | number | null | undefined): string {
  const number = typeof value === 'string' ? Number(value) : value;
  const hasPaise = typeof number === 'number' && Number.isFinite(number) && number % 1 !== 0;
  return formatCurrency(value, { decimals: hasPaise ? 2 : 0 });
}

function isoToday(): string {
  const now = new Date();
  const offset = now.getTimezoneOffset() * 60_000;
  return new Date(now.getTime() - offset).toISOString().slice(0, 10);
}

// ---------------------------------------------------------------------------
// The summary strip
// ---------------------------------------------------------------------------

const FIGURE_TONES = {
  neutral: 'bg-muted/60',
  green: 'bg-green-tint',
  amber: 'bg-amber-tint',
  rose: 'bg-rose-tint',
  blue: 'bg-blue-tint',
} as const;

function Figure({
  label,
  value,
  sub,
  tone = 'neutral',
}: {
  label: string;
  value: string;
  sub?: string;
  tone?: keyof typeof FIGURE_TONES;
}) {
  return (
    <div className={cn('rounded-lg px-3 py-2.5', FIGURE_TONES[tone])}>
      <p className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
        {label}
      </p>
      <p className="mt-0.5 text-lg font-semibold tabular-nums text-foreground">{value}</p>
      {sub ? <p className="text-xs text-muted-foreground">{sub}</p> : null}
    </div>
  );
}

export function FeeSummaryStrip({ summary }: { summary: StudentFeeSummary }) {
  const balance = Number(summary.balance_total);
  return (
    <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
      <Figure label="Agreed" value={money(summary.payable_total)} tone="blue" />
      <Figure label="Paid" value={money(summary.paid_total)} tone="green" />
      <Figure
        label="Balance"
        value={money(summary.balance_total)}
        tone={balance > 0 ? (summary.is_overdue ? 'rose' : 'amber') : 'neutral'}
      />
      <Figure
        label="Next expected"
        value={summary.next_due_on ? money(summary.next_due_amount) : 'Not set'}
        sub={
          summary.next_due_on
            ? `${summary.is_overdue ? 'Was due' : 'By'} ${formatDate(summary.next_due_on)}`
            : undefined
        }
        tone={summary.is_overdue ? 'rose' : 'neutral'}
      />
    </div>
  );
}

// ---------------------------------------------------------------------------
// Dialogs
// ---------------------------------------------------------------------------

function DialogError({ message }: { message: string }) {
  return message ? <Alert variant="error">{message}</Alert> : null;
}

interface SetFeeProps {
  onOpenChange: (open: boolean) => void;
  enrollmentId: string;
  plan: FeePlan | null;
  onSaved: () => void;
}

/**
 * The form is its own component, mounted only while the dialog is open, so
 * every opening starts from the plan as it is now — no effect that resets
 * fields, no stale draft from last time.
 */
function SetFeeForm({ onOpenChange, enrollmentId, plan, onSaved }: SetFeeProps) {
  const [agreed, setAgreed] = useState(plan?.agreed_amount ?? '');
  const [discount, setDiscount] = useState(
    plan && Number(plan.discount_amount) > 0 ? plan.discount_amount : '',
  );
  const [reason, setReason] = useState(plan?.discount_reason ?? '');
  const [notes, setNotes] = useState(plan?.notes ?? '');
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [message, setMessage] = useState('');
  const [saving, setSaving] = useState(false);

  async function save(event: React.FormEvent) {
    event.preventDefault();
    setSaving(true);
    setErrors({});
    setMessage('');
    try {
      await setEnrollmentFee(enrollmentId, {
        agreed_amount: agreed.trim(),
        discount_amount: discount.trim() === '' ? 0 : discount.trim(),
        discount_reason: reason.trim(),
        notes: notes.trim(),
      });
      onOpenChange(false);
      onSaved();
    } catch (cause) {
      const fields = fieldErrors(cause);
      setErrors(fields);
      if (Object.keys(fields).length === 0)
        setMessage(errorMessage(cause, 'The fee could not be saved.'));
    } finally {
      setSaving(false);
    }
  }

  const payable = Math.max(0, Number(agreed || 0) - Number(discount || 0));

  return (
    <form onSubmit={(event) => void save(event)} noValidate>
      <DialogHeader>
        <DialogTitle>{plan ? 'Change the agreed fee' : 'Set the fee for this course'}</DialogTitle>
        <DialogDescription>
          What the student pays for this course. A discount needs a reason; both are kept with the
          record.
        </DialogDescription>
      </DialogHeader>
      <div className="space-y-3">
        <DialogError message={message} />
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <Field label="Course fee (₹)" htmlFor="fee-agreed" error={errors.agreed_amount} required>
            <Input
              id="fee-agreed"
              type="number"
              inputMode="decimal"
              min={0}
              step="1"
              autoFocus
              value={agreed}
              onChange={(event) => setAgreed(event.target.value)}
              placeholder="e.g. 25000"
            />
          </Field>
          <Field label="Discount (₹)" htmlFor="fee-discount" error={errors.discount_amount}>
            <Input
              id="fee-discount"
              type="number"
              inputMode="decimal"
              min={0}
              step="1"
              value={discount}
              onChange={(event) => setDiscount(event.target.value)}
              placeholder="0"
            />
          </Field>
        </div>
        {Number(discount) > 0 ? (
          <Field
            label="Reason for the discount"
            htmlFor="fee-reason"
            error={errors.discount_reason}
            required
          >
            <Input
              id="fee-reason"
              value={reason}
              onChange={(event) => setReason(event.target.value)}
              placeholder="e.g. Referral, early bird"
            />
          </Field>
        ) : null}
        <Field
          label="Notes"
          htmlFor="fee-notes"
          error={errors.notes}
          hint="Anything agreed that the numbers do not say."
        >
          <Textarea
            id="fee-notes"
            rows={2}
            value={notes}
            onChange={(event) => setNotes(event.target.value)}
          />
        </Field>
        <p className="rounded-md bg-muted/60 px-3 py-2 text-sm">
          Payable after discount:{' '}
          <span className="font-semibold tabular-nums">{money(payable)}</span>
        </p>
      </div>
      <DialogFooter>
        <Button type="button" variant="ghost" disabled={saving} onClick={() => onOpenChange(false)}>
          Cancel
        </Button>
        <Button type="submit" disabled={saving || agreed.trim() === ''}>
          {saving ? 'Saving…' : 'Save fee'}
        </Button>
      </DialogFooter>
    </form>
  );
}

export function SetFeeDialog({ open, ...props }: SetFeeProps & { open: boolean }) {
  return (
    <Dialog open={open} onOpenChange={props.onOpenChange}>
      <DialogContent>{open ? <SetFeeForm {...props} /> : null}</DialogContent>
    </Dialog>
  );
}

interface PlanDialogProps {
  onOpenChange: (open: boolean) => void;
  plan: FeePlan;
  onSaved: () => void;
}

function RecordPaymentForm({ onOpenChange, plan, onSaved }: PlanDialogProps) {
  const firstPayment = plan.payments.every((payment) => payment.is_voided);
  // The registration payment is the usual first amount; after that the
  // amount is whatever the student brought, so the field starts empty.
  const [amount, setAmount] = useState(firstPayment && Number(plan.balance) >= 1000 ? '1000' : '');
  const [paidOn, setPaidOn] = useState(isoToday());
  const [method, setMethod] = useState<PaymentMethod>('cash');
  const [reference, setReference] = useState('');
  const [note, setNote] = useState('');
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [message, setMessage] = useState('');
  const [saving, setSaving] = useState(false);

  async function save(event: React.FormEvent) {
    event.preventDefault();
    setSaving(true);
    setErrors({});
    setMessage('');
    try {
      await recordPayment(plan.enrollment_id, {
        amount: amount.trim(),
        paid_on: paidOn,
        method,
        reference: reference.trim(),
        note: note.trim(),
      });
      onOpenChange(false);
      onSaved();
    } catch (cause) {
      const fields = fieldErrors(cause);
      setErrors(fields);
      if (Object.keys(fields).length === 0)
        setMessage(errorMessage(cause, 'The payment could not be recorded.'));
    } finally {
      setSaving(false);
    }
  }

  return (
    <form onSubmit={(event) => void save(event)} noValidate>
      <DialogHeader>
        <DialogTitle>Record a payment</DialogTitle>
        <DialogDescription>
          {plan.course_title} · {money(plan.balance)} still owed. A receipt number is issued when
          you save.
        </DialogDescription>
      </DialogHeader>
      <div className="space-y-3">
        <DialogError message={message} />
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <Field
            label="Amount (₹)"
            htmlFor="pay-amount"
            error={errors.amount}
            required
            hint={
              firstPayment ? 'First payment: at least ₹1,000.' : 'Any amount up to the balance.'
            }
          >
            <Input
              id="pay-amount"
              type="number"
              inputMode="decimal"
              min={1}
              step="1"
              autoFocus
              value={amount}
              onChange={(event) => setAmount(event.target.value)}
            />
          </Field>
          <Field label="Paid on" htmlFor="pay-date" error={errors.paid_on} required>
            <Input
              id="pay-date"
              type="date"
              max={isoToday()}
              value={paidOn}
              onChange={(event) => setPaidOn(event.target.value)}
            />
          </Field>
          <Field label="How" htmlFor="pay-method" error={errors.method} required>
            <Select
              id="pay-method"
              value={method}
              onChange={(event) => setMethod(event.target.value as PaymentMethod)}
            >
              {PAYMENT_METHOD_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </Select>
          </Field>
          <Field
            label="Reference"
            htmlFor="pay-reference"
            error={errors.reference}
            hint="UPI or bank transaction id, cheque number."
          >
            <Input
              id="pay-reference"
              value={reference}
              onChange={(event) => setReference(event.target.value)}
            />
          </Field>
        </div>
        <Field label="Note" htmlFor="pay-note" error={errors.note}>
          <Input id="pay-note" value={note} onChange={(event) => setNote(event.target.value)} />
        </Field>
      </div>
      <DialogFooter>
        <Button type="button" variant="ghost" disabled={saving} onClick={() => onOpenChange(false)}>
          Cancel
        </Button>
        <Button type="submit" disabled={saving || amount.trim() === ''}>
          {saving ? 'Recording…' : 'Record payment'}
        </Button>
      </DialogFooter>
    </form>
  );
}

export function RecordPaymentDialog({ open, ...props }: PlanDialogProps & { open: boolean }) {
  return (
    <Dialog open={open} onOpenChange={props.onOpenChange}>
      <DialogContent>{open ? <RecordPaymentForm {...props} /> : null}</DialogContent>
    </Dialog>
  );
}

function NextDueForm({ onOpenChange, plan, onSaved }: PlanDialogProps) {
  const [amount, setAmount] = useState(plan.next_due_amount ?? '');
  const [on, setOn] = useState(plan.next_due_on ?? '');
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [message, setMessage] = useState('');
  const [saving, setSaving] = useState(false);

  async function save(clear: boolean) {
    setSaving(true);
    setErrors({});
    setMessage('');
    try {
      await setNextDue(
        plan.enrollment_id,
        clear
          ? { next_due_amount: null, next_due_on: null }
          : { next_due_amount: amount.trim(), next_due_on: on },
      );
      onOpenChange(false);
      onSaved();
    } catch (cause) {
      const fields = fieldErrors(cause);
      setErrors(fields);
      if (Object.keys(fields).length === 0) setMessage(errorMessage(cause, 'Could not save this.'));
    } finally {
      setSaving(false);
    }
  }

  return (
    <form
      onSubmit={(event) => {
        event.preventDefault();
        void save(false);
      }}
      noValidate
    >
      <DialogHeader>
        <DialogTitle>What is expected next</DialogTitle>
        <DialogDescription>
          Not a schedule — just the amount the student said they would bring, and when. It shows as
          overdue once the date passes, and clears itself when the money arrives.
        </DialogDescription>
      </DialogHeader>
      <div className="space-y-3">
        <DialogError message={message} />
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <Field label="Amount (₹)" htmlFor="due-amount" error={errors.next_due_amount} required>
            <Input
              id="due-amount"
              type="number"
              inputMode="decimal"
              min={1}
              step="1"
              autoFocus
              value={amount}
              onChange={(event) => setAmount(event.target.value)}
              placeholder={`up to ${money(plan.balance)}`}
            />
          </Field>
          <Field label="Expected by" htmlFor="due-on" error={errors.next_due_on} required>
            <Input
              id="due-on"
              type="date"
              value={on}
              onChange={(event) => setOn(event.target.value)}
            />
          </Field>
        </div>
      </div>
      <DialogFooter className="justify-between">
        <div>
          {plan.next_due_on ? (
            <Button type="button" variant="ghost" disabled={saving} onClick={() => void save(true)}>
              Clear
            </Button>
          ) : null}
        </div>
        <div className="flex gap-2">
          <Button
            type="button"
            variant="ghost"
            disabled={saving}
            onClick={() => onOpenChange(false)}
          >
            Cancel
          </Button>
          <Button type="submit" disabled={saving || amount.trim() === '' || on === ''}>
            {saving ? 'Saving…' : 'Save'}
          </Button>
        </div>
      </DialogFooter>
    </form>
  );
}

export function NextDueDialog({ open, ...props }: PlanDialogProps & { open: boolean }) {
  return (
    <Dialog open={open} onOpenChange={props.onOpenChange}>
      <DialogContent>{open ? <NextDueForm {...props} /> : null}</DialogContent>
    </Dialog>
  );
}

// ---------------------------------------------------------------------------
// History
// ---------------------------------------------------------------------------

function text(value: unknown): string {
  return typeof value === 'string' || typeof value === 'number' ? String(value) : '';
}

/** One sentence per audit row, from the context the service wrote. */
export function describeHistory(entry: FeeHistoryEntry): string {
  const context = entry.context ?? {};
  switch (entry.action) {
    case 'fee.plan.set': {
      const discount = Number(text(context.discount_amount) || 0);
      return `Agreed ${money(text(context.agreed_amount))}${
        discount > 0
          ? `, less ${money(discount)} (${text(context.discount_reason) || 'no reason given'})`
          : ''
      }.`;
    }
    case 'fee.plan.updated': {
      const changes = (context.changes ?? {}) as Record<string, { from?: string; to?: string }>;
      const parts = Object.entries(changes).map(([field, change]) => {
        const label =
          field === 'agreed_amount'
            ? 'fee'
            : field === 'discount_amount'
              ? 'discount'
              : field === 'discount_reason'
                ? 'discount reason'
                : field;
        const isMoney = field === 'agreed_amount' || field === 'discount_amount';
        const from = isMoney ? money(change.from) : change.from || 'nothing';
        const to = isMoney ? money(change.to) : change.to || 'nothing';
        return `${label} ${from} → ${to}`;
      });
      return parts.length ? `Changed ${parts.join('; ')}.` : 'Changed.';
    }
    case 'fee.next_due.set': {
      const to = (context.to ?? {}) as { amount?: string | null; on?: string | null };
      return to.on
        ? `Next ${money(to.amount)} expected by ${formatDate(to.on)}.`
        : 'Expected payment cleared.';
    }
    case 'fee.payment.recorded':
      return `Received ${money(text(context.amount))} by ${
        PAYMENT_METHOD_LABEL[text(context.method) as PaymentMethod] ?? text(context.method)
      } on ${formatDate(text(context.paid_on))}. Receipt ${text(context.receipt_number)}. Balance ${money(
        text(context.balance_after),
      )}.`;
    case 'fee.payment.voided':
      return `Voided ${money(text(context.amount))} (receipt ${text(context.receipt_number)}): ${
        text(context.reason) || 'no reason given'
      }.`;
    default:
      return entry.action_label;
  }
}

function FeeHistory({ enrollmentId }: { enrollmentId: string }) {
  const [rows, setRows] = useState<FeeHistoryEntry[] | null>(null);
  const [error, setError] = useState<ApiError | null>(null);

  useEffect(() => {
    let cancelled = false;
    getFeeHistory(enrollmentId)
      .then((result) => {
        if (!cancelled) setRows(result);
      })
      .catch((cause: unknown) => {
        if (!cancelled)
          setError(
            cause instanceof ApiError
              ? cause
              : new ApiError(0, 'network_error', 'Could not load the history.', ''),
          );
      });
    return () => {
      cancelled = true;
    };
  }, [enrollmentId]);

  if (error) return <ErrorState title="Could not load the history" message={error.message} />;
  if (rows === null) return <LoadingState label="Loading history…" rows={2} />;
  if (rows.length === 0)
    return <p className="text-sm text-muted-foreground">Nothing recorded yet.</p>;

  return (
    <ol className="relative space-y-3 border-l border-border pl-4" aria-label="Fee history">
      {rows.map((entry) => (
        <li key={entry.id} className="relative text-sm">
          <span
            aria-hidden="true"
            className="absolute -left-[21px] top-1.5 size-2.5 rounded-full border-2 border-surface bg-primary"
          />
          <p className="font-medium text-foreground">{entry.action_label}</p>
          <p className="text-muted-foreground">{describeHistory(entry)}</p>
          <p className="text-xs text-muted-foreground">
            {formatDateTime(entry.created_at)} · {entry.actor_label}
          </p>
        </li>
      ))}
    </ol>
  );
}

// ---------------------------------------------------------------------------
// One enrolment's fee
// ---------------------------------------------------------------------------

function PaymentsTable({
  payments,
  mayManage,
  onVoided,
}: {
  payments: FeePayment[];
  mayManage: boolean;
  onVoided: () => void;
}) {
  const [voidingId, setVoidingId] = useState('');
  const [reason, setReason] = useState('');
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');

  async function confirmVoid(payment: FeePayment) {
    setBusy(true);
    setMessage('');
    try {
      await voidPayment(payment.id, reason.trim());
      setVoidingId('');
      setReason('');
      onVoided();
    } catch (cause) {
      setMessage(errorMessage(cause, 'Could not void this payment.'));
    } finally {
      setBusy(false);
    }
  }

  if (payments.length === 0) {
    return <p className="text-sm text-muted-foreground">No payments recorded yet.</p>;
  }

  return (
    <div className="space-y-2">
      {message ? <Alert variant="error">{message}</Alert> : null}
      <TableWrapper>
        <Table>
          <thead>
            <tr>
              <Th>Receipt</Th>
              <Th>Date</Th>
              <Th className="text-right">Amount</Th>
              <Th>How</Th>
              <Th>Taken by</Th>
              {mayManage ? <Th className="text-right">Actions</Th> : null}
            </tr>
          </thead>
          <tbody>
            {payments.map((payment) => (
              <Tr
                key={payment.id}
                className={payment.is_voided ? 'text-muted-foreground' : undefined}
              >
                <Td className="font-mono text-xs">
                  {payment.receipt_number}
                  {payment.is_voided ? (
                    <Badge variant="error" className="ml-2">
                      Voided
                    </Badge>
                  ) : null}
                </Td>
                <Td className="whitespace-nowrap">{formatDate(payment.paid_on)}</Td>
                <Td
                  className={cn(
                    'text-right tabular-nums',
                    payment.is_voided ? 'line-through' : 'font-medium',
                  )}
                >
                  {money(payment.amount)}
                </Td>
                <Td>
                  {PAYMENT_METHOD_LABEL[payment.method]}
                  {payment.reference ? (
                    <span className="block font-mono text-xs text-muted-foreground">
                      {payment.reference}
                    </span>
                  ) : null}
                  {payment.is_voided ? (
                    <span className="block text-xs">
                      Voided {formatDate(payment.voided_at)} by {payment.voided_by || 'unknown'}:{' '}
                      {payment.void_reason}
                    </span>
                  ) : payment.note ? (
                    <span className="block text-xs text-muted-foreground">{payment.note}</span>
                  ) : null}
                </Td>
                <Td>{payment.recorded_by || 'Unknown'}</Td>
                {mayManage ? (
                  <Td className="text-right">
                    {payment.is_voided ? null : voidingId === payment.id ? (
                      <form
                        className="flex flex-wrap items-center justify-end gap-2"
                        onSubmit={(event) => {
                          event.preventDefault();
                          void confirmVoid(payment);
                        }}
                      >
                        <Input
                          aria-label="Why this payment is being voided"
                          className="h-8 w-44 text-xs"
                          placeholder="Reason (kept on record)"
                          autoFocus
                          value={reason}
                          onChange={(event) => setReason(event.target.value)}
                        />
                        <Button
                          type="submit"
                          size="sm"
                          variant="destructive"
                          disabled={busy || reason.trim() === ''}
                        >
                          Void
                        </Button>
                        <Button
                          type="button"
                          size="sm"
                          variant="ghost"
                          disabled={busy}
                          onClick={() => setVoidingId('')}
                        >
                          Keep
                        </Button>
                      </form>
                    ) : (
                      <Button
                        type="button"
                        size="sm"
                        variant="ghost"
                        className="text-muted-foreground"
                        onClick={() => {
                          setVoidingId(payment.id);
                          setReason('');
                        }}
                      >
                        Void
                      </Button>
                    )}
                  </Td>
                ) : null}
              </Tr>
            ))}
          </tbody>
        </Table>
      </TableWrapper>
    </div>
  );
}

export function FeePlanCard({
  plan,
  mayManage,
  onChanged,
}: {
  plan: FeePlan;
  mayManage: boolean;
  onChanged: () => void;
}) {
  const [dialog, setDialog] = useState<'fee' | 'payment' | 'due' | null>(null);
  const [showHistory, setShowHistory] = useState(false);
  const payable = Number(plan.payable);
  const paid = Number(plan.paid);
  const percent = payable > 0 ? Math.min(100, Math.round((paid / payable) * 100)) : 100;
  const balance = Number(plan.balance);

  return (
    <div className="rounded-xl border border-border bg-surface p-4 shadow-[var(--shadow-card)]">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="font-semibold text-foreground">
            {plan.course_title || 'Course not available'}
          </p>
          <p className="text-sm text-muted-foreground">
            {plan.batch_name || 'Batch not available'}
            <span className="ml-1 font-mono text-xs">{plan.batch_code}</span>
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Badge variant={ENROLLMENT_STATUS_VARIANT[plan.enrollment_status]}>
            {ENROLLMENT_STATUS_LABEL[plan.enrollment_status]}
          </Badge>
          <Badge variant={FEE_PLAN_STATUS_VARIANT[plan.status]} dot>
            {FEE_PLAN_STATUS_LABEL[plan.status]}
          </Badge>
          {plan.is_overdue ? (
            <Badge variant="error" dot>
              Overdue
            </Badge>
          ) : null}
        </div>
      </div>

      <div className="mt-4 grid grid-cols-2 gap-2 sm:grid-cols-4">
        <Figure
          label="Course fee"
          value={money(plan.agreed_amount)}
          sub={
            Number(plan.discount_amount) > 0
              ? `Less ${money(plan.discount_amount)} · ${plan.discount_reason || 'discount'}`
              : undefined
          }
        />
        <Figure label="Payable" value={money(plan.payable)} tone="blue" />
        <Figure label="Paid" value={money(plan.paid)} tone="green" />
        <Figure
          label="Balance"
          value={money(plan.balance)}
          tone={balance > 0 ? (plan.is_overdue ? 'rose' : 'amber') : 'neutral'}
        />
      </div>

      <div className="mt-3">
        <div
          className="h-2 w-full overflow-hidden rounded-full bg-muted"
          role="progressbar"
          aria-valuemin={0}
          aria-valuemax={100}
          aria-valuenow={percent}
          aria-label="Paid so far"
        >
          <div
            className={cn(
              'h-full rounded-full transition-[width] duration-500',
              percent >= 100 ? 'bg-green' : 'bg-primary',
            )}
            style={{ width: `${percent}%` }}
          />
        </div>
        <div className="mt-2 flex flex-wrap items-center justify-between gap-2 text-sm">
          <p className="text-muted-foreground">
            {percent}% paid
            {plan.updated_by
              ? ` · fee last changed ${formatDate(plan.updated_at)} by ${plan.updated_by}`
              : ''}
          </p>
          <p
            className={cn(
              'flex items-center gap-1.5',
              plan.is_overdue ? 'text-rose' : 'text-muted-foreground',
            )}
          >
            <CalendarClock className="size-4" aria-hidden="true" />
            {plan.next_due_on
              ? `${money(plan.next_due_amount)} ${plan.is_overdue ? 'was due' : 'expected by'} ${formatDate(plan.next_due_on)}`
              : balance > 0
                ? 'No date set for the next payment'
                : 'Nothing outstanding'}
          </p>
        </div>
      </div>

      {plan.notes ? (
        <p className="mt-3 rounded-md bg-muted/60 px-3 py-2 text-sm">{plan.notes}</p>
      ) : null}

      {mayManage ? (
        <div className="mt-4 flex flex-wrap gap-2">
          <Button size="sm" onClick={() => setDialog('payment')} disabled={balance <= 0}>
            <Receipt className="size-4" aria-hidden="true" />
            Record payment
          </Button>
          <Button
            size="sm"
            variant="outline"
            onClick={() => setDialog('due')}
            disabled={balance <= 0}
          >
            <CalendarClock className="size-4" aria-hidden="true" />
            Next expected
          </Button>
          <Button size="sm" variant="outline" onClick={() => setDialog('fee')}>
            <BadgeIndianRupee className="size-4" aria-hidden="true" />
            Change fee
          </Button>
        </div>
      ) : null}

      <div className="mt-4">
        <p className="mb-2 text-xs font-medium uppercase tracking-wide text-muted-foreground">
          Payments
        </p>
        <PaymentsTable payments={plan.payments} mayManage={mayManage} onVoided={onChanged} />
      </div>

      <div className="mt-3">
        <button
          type="button"
          className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
          onClick={() => setShowHistory((value) => !value)}
          aria-expanded={showHistory}
        >
          <History className="size-4" aria-hidden="true" />
          {showHistory ? 'Hide history' : 'Who changed what'}
          {showHistory ? (
            <ChevronUp className="size-4" aria-hidden="true" />
          ) : (
            <ChevronDown className="size-4" aria-hidden="true" />
          )}
        </button>
        {showHistory ? (
          <div className="mt-3">
            <FeeHistory enrollmentId={plan.enrollment_id} />
          </div>
        ) : null}
      </div>

      {mayManage ? (
        <>
          <SetFeeDialog
            open={dialog === 'fee'}
            onOpenChange={(open) => setDialog(open ? 'fee' : null)}
            enrollmentId={plan.enrollment_id}
            plan={plan}
            onSaved={onChanged}
          />
          <RecordPaymentDialog
            open={dialog === 'payment'}
            onOpenChange={(open) => setDialog(open ? 'payment' : null)}
            plan={plan}
            onSaved={onChanged}
          />
          <NextDueDialog
            open={dialog === 'due'}
            onOpenChange={(open) => setDialog(open ? 'due' : null)}
            plan={plan}
            onSaved={onChanged}
          />
        </>
      ) : null}
    </div>
  );
}

// ---------------------------------------------------------------------------
// The whole ledger for one student
// ---------------------------------------------------------------------------

function UnplannedEnrollment({
  enrollment,
  mayManage,
  onChanged,
}: {
  enrollment: Enrollment;
  mayManage: boolean;
  onChanged: () => void;
}) {
  const [open, setOpen] = useState(false);
  return (
    <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-dashed border-border px-4 py-3">
      <div>
        <p className="font-medium text-foreground">
          {enrollment.course_title || 'Course not available'}
        </p>
        <p className="text-sm text-muted-foreground">
          {enrollment.batch_name || 'Batch not available'} · No fee agreed yet
        </p>
      </div>
      {mayManage ? (
        <>
          <Button size="sm" variant="outline" onClick={() => setOpen(true)}>
            Set the fee
          </Button>
          <SetFeeDialog
            open={open}
            onOpenChange={setOpen}
            enrollmentId={enrollment.id}
            plan={null}
            onSaved={onChanged}
          />
        </>
      ) : null}
    </div>
  );
}

export function FeeLedger({
  summary,
  enrollments,
  mayManage,
  isLoading,
  error,
  onChanged,
  title = 'Fees',
  description = 'What was agreed for each course, what has been paid, and what is still owed.',
}: {
  summary: StudentFeeSummary | null;
  /** The student's enrolments, so the ones without a fee can be listed. */
  enrollments: Enrollment[] | null;
  mayManage: boolean;
  isLoading: boolean;
  error: { message: string; requestId?: string } | null;
  onChanged: () => void;
  title?: string;
  description?: string;
}) {
  const planned = new Set((summary?.plans ?? []).map((plan) => plan.enrollment_id));
  const unplanned = (enrollments ?? []).filter(
    (entry) =>
      !planned.has(entry.id) &&
      (entry.status === 'active' || entry.status === 'pending' || entry.status === 'suspended'),
  );

  return (
    <Card className="animate-rise-in">
      <CardHeader className="flex-row items-start justify-between gap-3">
        <div className="space-y-1">
          <CardTitle className="flex items-center gap-2">
            <Wallet className="size-5 text-primary" aria-hidden="true" />
            {title}
          </CardTitle>
          <CardDescription>{description}</CardDescription>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        {error ? (
          <ErrorState
            title="Could not load the fees"
            message={error.message}
            requestId={error.requestId}
            onRetry={onChanged}
          />
        ) : isLoading || summary === null ? (
          <LoadingState label="Loading fees…" rows={3} />
        ) : (
          <>
            {summary.plans.length > 0 ? <FeeSummaryStrip summary={summary} /> : null}
            {summary.plans.length === 0 && unplanned.length === 0 ? (
              <EmptyState
                title="No fees yet"
                description="A fee is agreed per course, once the student is placed on a batch."
              />
            ) : null}
            {summary.plans.map((plan) => (
              <FeePlanCard key={plan.id} plan={plan} mayManage={mayManage} onChanged={onChanged} />
            ))}
            {unplanned.map((entry) => (
              <UnplannedEnrollment
                key={entry.id}
                enrollment={entry}
                mayManage={mayManage}
                onChanged={onChanged}
              />
            ))}
          </>
        )}
      </CardContent>
    </Card>
  );
}

/** Loads a student's fees for a screen; the panel above renders them. */
export function useStudentFees(load: () => Promise<StudentFeeSummary>, deps: readonly unknown[]) {
  const [attempt, setAttempt] = useState(0);
  const requestKey = `${attempt}:${deps.map(String).join('|')}`;
  const [state, setState] = useState<{
    summary: StudentFeeSummary | null;
    error: ApiError | null;
    requestKey: string;
  }>({ summary: null, error: null, requestKey });

  // Reset during render when the request identity moves — the same pattern as
  // `hooks/use-api.ts`, and for the same reason: a synchronous `setState` at
  // the top of the effect is the cascading-render shape the lint refuses. The
  // previous summary is kept on screen while the new one loads.
  if (state.requestKey !== requestKey) {
    setState({ summary: state.summary, error: null, requestKey });
  }

  useEffect(() => {
    let cancelled = false;
    load()
      .then((result) => {
        if (!cancelled) setState({ summary: result, error: null, requestKey });
      })
      .catch((cause: unknown) => {
        if (!cancelled) {
          setState({
            summary: null,
            error:
              cause instanceof ApiError
                ? cause
                : new ApiError(0, 'network_error', 'Could not load the fees.', ''),
            requestKey,
          });
        }
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [requestKey]);

  const reload = useCallback(() => setAttempt((value) => value + 1), []);
  return {
    summary: state.summary,
    error: state.error,
    isLoading: state.summary === null && state.error === null,
    reload,
  };
}
