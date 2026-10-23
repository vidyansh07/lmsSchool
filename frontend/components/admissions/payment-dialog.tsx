'use client';

/**
 * The Payment dialog: "How Vipul is paying?".
 *
 * Opened from an unpaid instalment, so the amount and the instalment date
 * arrive fixed — the counsellor is recording *this* instalment, not deciding
 * what to collect. Both are shown read-only rather than hidden, because the
 * person at the counter is about to say the figure out loud.
 *
 * Bank Name appears only for the methods that go through one. A cheque needs
 * it; cash does not, and a field that is never filled is a field that gets
 * filled wrongly.
 *
 * `Apply Tax?` and its group are recorded, never computed (owner's decision,
 * 23 October 2026). The amount is the amount; these say under what heading it
 * was taken so the receipt and an accountant's export can repeat it.
 */

import { useEffect, useState, type FormEvent } from 'react';

import { Alert } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Field } from '@/components/ui/field';
import { Input, Select } from '@/components/ui/input';
import { fieldErrors, unshownError } from '@/lib/api';
import { listBanks, listPaymentCategories, listTaxGroups, type NamedRow } from '@/lib/fee-settings';
import { recordPayment } from '@/lib/fees';
import { formatDate, formatRupees, localIsoDate } from '@/lib/format';
import { PAYMENT_METHODS_OFFERED, PAYMENT_METHODS_UNCLEARED } from '@/types/api';
import { PAYMENT_METHOD_LABEL } from '@/lib/labels';
import type { FeeInstallment, PaymentMethod } from '@/types/api';

const SHOWN = [
  'amount',
  'paid_on',
  'method',
  'reference',
  'bank',
  'category',
  'tax_group',
  'apply_tax',
] as const;

export function PaymentDialog({
  enrollmentId,
  instalment,
  firstName,
  open,
  onClose,
  onPaid,
}: {
  enrollmentId: string;
  /** The instalment being settled. Its amount and date are what the dialog
   *  opens with and neither is editable here. */
  instalment: FeeInstallment;
  /** "How Vipul is paying?" — the student's own first name, as the original
   *  asks it. */
  firstName: string;
  open: boolean;
  onClose: () => void;
  onPaid: () => void;
}) {
  const [paidOn, setPaidOn] = useState(() => localIsoDate());
  const [method, setMethod] = useState<PaymentMethod>('cash');
  const [reference, setReference] = useState('');
  const [bank, setBank] = useState('');
  const [category, setCategory] = useState('');
  const [applyTax, setApplyTax] = useState(false);
  const [taxGroup, setTaxGroup] = useState('');
  const [banks, setBanks] = useState<NamedRow[]>([]);
  const [categories, setCategories] = useState<NamedRow[]>([]);
  const [taxGroups, setTaxGroups] = useState<NamedRow[]>([]);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    let cancelled = false;
    Promise.all([listBanks(), listPaymentCategories(), listTaxGroups()])
      .then(([bankRows, categoryRows, taxRows]) => {
        if (cancelled) return;
        setBanks(bankRows);
        setCategories(categoryRows);
        setTaxGroups(taxRows);
        setCategory(categoryRows.find((row) => row.is_default)?.id ?? '');
        setTaxGroup(taxRows.find((row) => row.is_default)?.id ?? '');
      })
      // The lists are a convenience. A payment can be recorded without
      // naming a bank or a category, and a counter that cannot reach the
      // settings endpoints should still be able to take money.
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, []);

  const needsBank = PAYMENT_METHODS_UNCLEARED.includes(method);

  async function submit(event: FormEvent) {
    event.preventDefault();
    const found: Record<string, string> = {};
    if (!paidOn) found.paid_on = 'Say when it was paid.';
    if (applyTax && !taxGroup) found.tax_group = 'Choose the tax group.';
    if (Object.keys(found).length > 0) {
      setErrors(found);
      return;
    }
    setSaving(true);
    setErrors({});
    try {
      await recordPayment(enrollmentId, {
        amount: instalment.balance,
        paid_on: paidOn,
        method,
        reference: reference.trim(),
        instalment: instalment.id,
        ...(bank ? { bank } : {}),
        ...(category ? { category } : {}),
        apply_tax: applyTax,
        ...(applyTax && taxGroup ? { tax_group: taxGroup } : {}),
      });
      onPaid();
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
        <form onSubmit={submit} noValidate>
          <DialogHeader>
            <DialogTitle>Payment</DialogTitle>
          </DialogHeader>

          <div className="grid gap-4 py-4 sm:grid-cols-2">
            {stray ? (
              <div className="sm:col-span-2">
                <Alert variant="error">{stray}</Alert>
              </div>
            ) : null}

            <Field label="Amount" htmlFor="pay-amount">
              <Input id="pay-amount" value={instalment.balance} readOnly disabled />
            </Field>
            <Field label="Instalment Date" htmlFor="pay-instalment-date">
              <Input
                id="pay-instalment-date"
                value={formatDate(instalment.due_on)}
                readOnly
                disabled
              />
            </Field>

            <Field label="When it is Paid?" htmlFor="pay-when" error={errors.paid_on}>
              <Input
                id="pay-when"
                type="date"
                value={paidOn}
                onChange={(event) => setPaidOn(event.target.value)}
              />
            </Field>
            <Field
              label={`How ${firstName || 'the student'} is paying?`}
              htmlFor="pay-method"
              error={errors.method}
            >
              <Select
                id="pay-method"
                value={method}
                onChange={(event) => setMethod(event.target.value as PaymentMethod)}
              >
                {PAYMENT_METHODS_OFFERED.map((value) => (
                  <option key={value} value={value}>
                    {PAYMENT_METHOD_LABEL[value]}
                  </option>
                ))}
              </Select>
            </Field>

            {needsBank ? (
              <Field label="Bank Name" htmlFor="pay-bank" error={errors.bank}>
                <Select
                  id="pay-bank"
                  value={bank}
                  onChange={(event) => setBank(event.target.value)}
                >
                  <option value="">Select Bank</option>
                  {banks.map((row) => (
                    <option key={row.id} value={row.id}>
                      {row.name}
                    </option>
                  ))}
                </Select>
              </Field>
            ) : null}

            <Field
              label="Reference Number"
              htmlFor="pay-reference"
              error={errors.reference}
              hint={needsBank ? 'The cheque or draft number.' : undefined}
            >
              <Input
                id="pay-reference"
                value={reference}
                onChange={(event) => setReference(event.target.value)}
              />
            </Field>

            <div className="space-y-1.5">
              <span className="block text-xs font-medium text-ink">Apply Tax?</span>
              <label className="flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  checked={applyTax}
                  onChange={(event) => setApplyTax(event.target.checked)}
                  className="size-4 accent-[var(--color-action)]"
                />
                <span className="sr-only">Apply tax</span>
              </label>
            </div>
            <Field label="Tax Group" htmlFor="pay-tax-group" error={errors.tax_group}>
              <Select
                id="pay-tax-group"
                value={taxGroup}
                onChange={(event) => setTaxGroup(event.target.value)}
                disabled={!applyTax}
              >
                <option value="">None</option>
                {taxGroups.map((row) => (
                  <option key={row.id} value={row.id}>
                    {row.name}
                  </option>
                ))}
              </Select>
            </Field>

            <Field label="Payment Category" htmlFor="pay-category" error={errors.category}>
              <Select
                id="pay-category"
                value={category}
                onChange={(event) => setCategory(event.target.value)}
              >
                <option value="">None</option>
                {categories.map((row) => (
                  <option key={row.id} value={row.id}>
                    {row.name}
                  </option>
                ))}
              </Select>
            </Field>

            {needsBank ? (
              <p className="text-xs text-ink-muted sm:col-span-2">
                Taken by {PAYMENT_METHOD_LABEL[method].toLowerCase()}, so it counts as received
                now and stays <strong>uncleared</strong> until the bank honours it. The receipt
                says so too.
              </p>
            ) : null}
          </div>

          <DialogFooter>
            <Button
              type="submit"
              disabled={saving}
              className="bg-success hover:bg-success/90"
            >
              {saving ? 'Saving…' : 'Save'}
            </Button>
            <Button type="button" variant="outline" onClick={onClose} disabled={saving}>
              Cancel
            </Button>
          </DialogFooter>
          <p className="pt-2 text-xs text-ink-muted">
            {formatRupees(instalment.balance)} against the instalment due{' '}
            {formatDate(instalment.due_on)}.
          </p>
        </form>
      </DialogContent>
    </Dialog>
  );
}
