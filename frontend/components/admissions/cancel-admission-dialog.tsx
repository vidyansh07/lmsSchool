'use client';

/**
 * Cancel Admission.
 *
 * The original is its own page with one sentence at the top — "Rs. 1,000 paid
 * by student and Rs. 0 is refunded." — then "Do You want add refund?", a date,
 * an amount, and Submit. This is that, as a dialog, because it is opened from
 * a row in a list and sending somebody to another page to type two fields
 * loses their place.
 *
 * The sentence is the important part: it is the only thing on the screen that
 * says what has already happened, and somebody about to cancel an admission
 * with ₹20,000 against it needs to read that before they decide.
 *
 * The refund is optional and separate on purpose. Cancelling settles the fee
 * — what was not paid stops being chased — and giving money back is a second
 * decision somebody takes deliberately. A single button that did both would
 * make every cancellation a refund by default.
 */

import { useState, type FormEvent } from 'react';

import { Alert } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Field } from '@/components/ui/field';
import { Input } from '@/components/ui/input';
import { fieldErrors, unshownError } from '@/lib/api';
import { cancelAdmission, type Admission } from '@/lib/admissions-api';
import { formatRupees } from '@/lib/format';

const SHOWN = ['reason', 'refund_amount', 'refund_on'] as const;

export function CancelAdmissionDialog({
  admission,
  open,
  onClose,
  onCancelled,
}: {
  admission: Admission;
  open: boolean;
  onClose: () => void;
  onCancelled: () => void;
}) {
  const [reason, setReason] = useState('');
  const [wantsRefund, setWantsRefund] = useState(false);
  const [refundOn, setRefundOn] = useState(() => new Date().toISOString().slice(0, 10));
  const [refundAmount, setRefundAmount] = useState('');
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState(false);

  const paid = Number(admission.money.paid);
  const alreadyRefunded = Number(admission.money.refund);

  async function submit(event: FormEvent) {
    event.preventDefault();
    const found: Record<string, string> = {};
    if (!reason.trim()) found.reason = 'Say why it was cancelled.';
    if (wantsRefund) {
      const amount = Number(refundAmount);
      if (!refundAmount || !Number.isFinite(amount) || amount <= 0) {
        found.refund_amount = 'Give the amount to refund.';
      } else if (amount > paid) {
        // Refunding more than was taken is not a refund.
        found.refund_amount = `More than the ${formatRupees(paid)} paid.`;
      }
      if (!refundOn) found.refund_on = 'Say when it was refunded.';
    }
    if (Object.keys(found).length > 0) {
      setErrors(found);
      return;
    }

    setSaving(true);
    setErrors({});
    try {
      await cancelAdmission(admission.id, reason.trim());
      onCancelled();
      onClose();
    } catch (cause) {
      setErrors(fieldErrors(cause));
    } finally {
      setSaving(false);
    }
  }

  const stray = unshownError(errors, SHOWN);

  return (
    <Dialog open={open} onOpenChange={(next) => (next ? undefined : onClose())}>
      <DialogContent>
        {/*
          `noValidate`: the amount field carries `max={paid}`, which is right
          for the stepper and wrong for submission — a browser refuses to
          submit a form holding a value outside its own constraints, so the
          handler below never ran and the person saw *nothing at all* rather
          than "more than the amount paid". Our checks produce a message
          beside the field; the native ones produce silence.
        */}
        <form onSubmit={submit} noValidate>
          <DialogHeader>
            <DialogTitle>Cancel Admission</DialogTitle>
            <DialogDescription>
              What is still owed stops being chased. What was paid stays on the record.
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-4 py-4">
            <Alert variant="info">
              {formatRupees(paid)} paid by student and {formatRupees(alreadyRefunded)} is refunded.
            </Alert>
            {stray ? <Alert variant="error">{stray}</Alert> : null}

            <Field label="Reason" htmlFor="cancel-reason" error={errors.reason}>
              <Input
                id="cancel-reason"
                value={reason}
                onChange={(event) => setReason(event.target.value)}
                placeholder="Moved city, changed course, stopped attending"
              />
            </Field>

            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={wantsRefund}
                onChange={(event) => setWantsRefund(event.target.checked)}
                disabled={paid <= 0}
                className="size-4 accent-[var(--color-action)]"
              />
              Do You want add refund?
              {paid <= 0 ? (
                <span className="text-xs text-ink-muted">(nothing has been paid)</span>
              ) : null}
            </label>

            {wantsRefund ? (
              <div className="grid gap-3 sm:grid-cols-2">
                <Field label="Refunded on" htmlFor="refund-on" error={errors.refund_on}>
                  <Input
                    id="refund-on"
                    type="date"
                    value={refundOn}
                    onChange={(event) => setRefundOn(event.target.value)}
                  />
                </Field>
                <Field label="Amount" htmlFor="refund-amount" error={errors.refund_amount}>
                  <Input
                    id="refund-amount"
                    type="number"
                    min={0}
                    max={paid}
                    value={refundAmount}
                    onChange={(event) => setRefundAmount(event.target.value)}
                    placeholder="amount"
                  />
                </Field>
                <p className="text-xs text-ink-muted sm:col-span-2">
                  The refund is recorded against the payment it came from, on the fee tab, so the
                  receipt it reverses is named. This cancels the admission first.
                </p>
              </div>
            ) : null}
          </div>

          <DialogFooter>
            <Button type="button" variant="ghost" onClick={onClose} disabled={saving}>
              Cancel
            </Button>
            <Button type="submit" disabled={saving}>
              {saving ? 'Submitting…' : 'Submit'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
