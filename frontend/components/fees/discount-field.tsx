'use client';

import { Input } from '@/components/ui/input';
import { formatCurrency } from '@/lib/format';
import { cn } from '@/lib/utils';

/** How the counsellor typed the discount. A percentage is the default: "10"
 *  means 10% of the fee, which is how a scholarship or an offer is quoted. */
export type DiscountMode = 'percent' | 'amount';

/**
 * The rupee discount a typed value comes to, rounded to the paisa half up —
 * the same rule the server applies, so the figure shown before saving is the
 * figure on the ledger and the receipt.
 */
export function discountRupees(agreed: string | number, mode: DiscountMode, value: string): number {
  const fee = Number(agreed || 0);
  const typed = Number(value || 0);
  if (!Number.isFinite(fee) || !Number.isFinite(typed) || typed <= 0 || fee <= 0) return 0;
  if (mode === 'amount') return typed;
  return Math.round(fee * typed) / 100;
}

/** What to send to `PUT /fees/enrollments/<id>/` for this discount. */
export function discountPayload(
  mode: DiscountMode,
  value: string,
): { discount_percent: string | null; discount_amount: string | number } {
  const typed = value.trim();
  if (mode === 'percent') {
    return { discount_percent: typed === '' ? null : typed, discount_amount: 0 };
  }
  return { discount_percent: null, discount_amount: typed === '' ? 0 : typed };
}

/** The mode and value to start an edit from: the plan's percentage when it was
 *  given as one, its rupees when it was flat, and an empty percentage otherwise. */
export function initialDiscount(plan: {
  discount_percent?: string | null;
  discount_amount: string;
} | null): { mode: DiscountMode; value: string } {
  if (plan?.discount_percent != null && Number(plan.discount_percent) > 0) {
    return { mode: 'percent', value: String(Number(plan.discount_percent)) };
  }
  if (plan && Number(plan.discount_amount) > 0) {
    return { mode: 'amount', value: String(Number(plan.discount_amount)) };
  }
  return { mode: 'percent', value: '' };
}

export function DiscountField({
  id,
  agreed,
  mode,
  value,
  onModeChange,
  onValueChange,
  error,
  disabled,
}: {
  id: string;
  agreed: string;
  mode: DiscountMode;
  value: string;
  onModeChange: (mode: DiscountMode) => void;
  onValueChange: (value: string) => void;
  error?: string;
  disabled?: boolean;
}) {
  const rupees = discountRupees(agreed, mode, value);
  const fee = Number(agreed || 0);
  const overLimit = mode === 'percent' ? Number(value) > 100 : fee > 0 && Number(value) > fee;
  let hint: string | undefined;
  if (overLimit) {
    hint = mode === 'percent' ? 'A percentage cannot be more than 100.' : 'More than the fee.';
  } else if (rupees > 0 && mode === 'percent') {
    hint = `${formatCurrency(rupees)} off the fee.`;
  } else if (rupees > 0 && fee > 0) {
    hint = `${(Math.round((rupees / fee) * 10000) / 100).toString()}% of the fee.`;
  }

  const errorId = `${id}-error`;
  const hintId = `${id}-hint`;

  // Laid out like `Field`, by hand: `Field` hands its id to its one child,
  // and here the child is the input *and* its unit switch.
  return (
    <div className="space-y-1.5">
      <label htmlFor={id} className="block text-xs font-medium text-ink">
        {mode === 'percent' ? 'Discount (%)' : 'Discount (₹)'}
      </label>
      <div className="flex gap-2">
        <Input
          id={id}
          type="number"
          inputMode="decimal"
          min={0}
          max={mode === 'percent' ? 100 : undefined}
          step={mode === 'percent' ? '0.01' : '1'}
          value={value}
          disabled={disabled}
          aria-invalid={error || overLimit ? true : undefined}
          aria-describedby={error ? errorId : hint ? hintId : undefined}
          onChange={(event) => onValueChange(event.target.value)}
          placeholder={mode === 'percent' ? 'e.g. 10' : '0'}
          className="min-w-0 flex-1"
        />
        <div
          role="group"
          aria-label="Discount given as"
          className="inline-flex shrink-0 overflow-hidden rounded-control border border-line"
        >
          {(
            [
              ['percent', '%', 'Percentage of the fee'],
              ['amount', '₹', 'Rupees'],
            ] as const
          ).map(([option, symbol, label]) => (
            <button
              key={option}
              type="button"
              aria-pressed={mode === option}
              aria-label={label}
              title={label}
              disabled={disabled}
              onClick={() => {
                if (option === mode) return;
                // Carry the figure across so switching never loses what was typed.
                if (option === 'amount' && rupees > 0) onValueChange(String(rupees));
                if (option === 'percent' && rupees > 0 && fee > 0) {
                  onValueChange(String(Math.round((rupees / fee) * 10000) / 100));
                }
                onModeChange(option);
              }}
              className={cn(
                'min-w-9 px-2.5 text-sm font-medium transition-colors duration-150 disabled:opacity-50',
                mode === option ? 'bg-action text-action-fg' : 'bg-surface text-ink-muted hover:text-ink',
              )}
            >
              {symbol}
            </button>
          ))}
        </div>
      </div>
      {hint && !error ? (
        <p
          id={hintId}
          className={cn('text-2xs', overLimit ? 'font-medium text-danger' : 'text-ink-faint')}
        >
          {hint}
        </p>
      ) : null}
      {error ? (
        <p id={errorId} className="text-2xs font-medium text-danger">
          {error}
        </p>
      ) : null}
    </div>
  );
}
