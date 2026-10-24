'use client';

/**
 * "Add Fee Instalment Structure": how a course's fee is normally collected.
 *
 * Shares are **percentages**, which is the one decision in this screen worth
 * explaining. A structure in rupees would be wrong for every discounted
 * admission — the money a plan has to collect is the fee less that student's
 * discount — so the rows are percentages and the rupees are worked out
 * against each student's own payable amount.
 *
 * The running total is shown against 100 the whole time, because the server
 * refuses anything else and finding that out on submit is how a person loses
 * five rows of typing. "Split evenly" exists for the common case: three equal
 * instalments is three clicks of arithmetic nobody should do by hand, and it
 * puts the odd hundredth on the first row, the same way the fee ledger puts
 * the odd paisa there.
 *
 * An empty structure is a real answer and is the default: no rows means each
 * admission decides how that student pays.
 */
import { Plus, Trash2 } from 'lucide-react';
import { useId } from 'react';

import { Button } from '@/components/ui/button';
import { Field } from '@/components/ui/field';
import { Input } from '@/components/ui/input';
import type { CourseFeeInstalmentInput } from '@/lib/course-fees';
import { cn } from '@/lib/utils';

/** Two decimal places, as a string, the way the API takes them. */
function money(value: number): string {
  return (Math.round(value * 100) / 100).toFixed(2);
}

export function sharesTotal(rows: CourseFeeInstalmentInput[]): number {
  return rows.reduce((sum, row) => sum + (Number(row.percent) || 0), 0);
}

/** `count` shares of 100, the remainder on the first — never 99.99. */
export function evenShares(count: number): string[] {
  if (count < 1) return [];
  const each = Math.floor((100 / count) * 100) / 100;
  const shares = Array.from({ length: count }, () => each);
  shares[0] = Number((100 - each * (count - 1)).toFixed(2));
  return shares.map(money);
}

export function blankInstalment(index: number): CourseFeeInstalmentInput {
  return { label: '', percent: '', due_after_days: index * 30 };
}

export function FeeInstalmentEditor({
  rows,
  onChange,
  errors = {},
  disabled = false,
  className,
}: {
  rows: CourseFeeInstalmentInput[];
  onChange: (rows: CourseFeeInstalmentInput[]) => void;
  errors?: Record<string, string>;
  disabled?: boolean;
  className?: string;
}) {
  const uid = useId();
  const total = sharesTotal(rows);
  const balanced = rows.length === 0 || Math.abs(total - 100) < 0.005;

  function update(index: number, change: Partial<CourseFeeInstalmentInput>) {
    onChange(rows.map((row, i) => (i === index ? { ...row, ...change } : row)));
  }

  function splitEvenly() {
    const shares = evenShares(rows.length);
    onChange(rows.map((row, index) => ({ ...row, percent: shares[index] ?? '' })));
  }

  return (
    <div className={cn('space-y-3', className)}>
      {rows.length === 0 ? (
        <p className="text-sm text-ink-muted">
          No structure. Every admission on this course decides how that student pays.
        </p>
      ) : (
        <ol className="space-y-3">
          {rows.map((row, index) => (
            <li key={index} className="grid gap-3 sm:grid-cols-[1fr_7rem_8rem_auto] sm:items-end">
              <Field label={`Instalment ${index + 1}`} htmlFor={`${uid}-label-${index}`}>
                <Input
                  id={`${uid}-label-${index}`}
                  value={row.label ?? ''}
                  disabled={disabled}
                  placeholder={index === 0 ? 'Admission' : 'Balance'}
                  onChange={(event) => update(index, { label: event.target.value })}
                />
              </Field>
              <Field label="Share (%)" htmlFor={`${uid}-percent-${index}`}>
                <Input
                  id={`${uid}-percent-${index}`}
                  type="number"
                  min={0.01}
                  max={100}
                  step="0.01"
                  value={row.percent}
                  disabled={disabled}
                  onChange={(event) => update(index, { percent: event.target.value })}
                />
              </Field>
              <Field label="Due after (days)" htmlFor={`${uid}-days-${index}`}>
                <Input
                  id={`${uid}-days-${index}`}
                  type="number"
                  min={0}
                  value={row.due_after_days}
                  disabled={disabled}
                  onChange={(event) =>
                    update(index, { due_after_days: Number(event.target.value || 0) })
                  }
                />
              </Field>
              <Button
                type="button"
                variant="ghost"
                size="sm"
                disabled={disabled}
                aria-label={`Remove instalment ${index + 1}`}
                onClick={() => onChange(rows.filter((_, i) => i !== index))}
              >
                <Trash2 className="size-4" aria-hidden="true" />
              </Button>
            </li>
          ))}
        </ol>
      )}

      {errors.instalments ? <p className="text-sm text-danger">{errors.instalments}</p> : null}

      <div className="flex flex-wrap items-center justify-between gap-3 border-t border-line pt-3">
        <p className={cn('text-sm', balanced ? 'text-ink-muted' : 'text-danger')}>
          {rows.length === 0
            ? 'The first instalment is due on the day of admission.'
            : `Shares add up to ${money(total)}% of ${100}%.`}
        </p>
        <div className="flex gap-2">
          {rows.length > 1 ? (
            <Button type="button" variant="outline" size="sm" disabled={disabled} onClick={splitEvenly}>
              Split evenly
            </Button>
          ) : null}
          <Button
            type="button"
            variant="outline"
            size="sm"
            disabled={disabled}
            onClick={() => onChange([...rows, blankInstalment(rows.length)])}
          >
            <Plus className="size-4" aria-hidden="true" />
            Add Fee Instalment
          </Button>
        </div>
      </div>
    </div>
  );
}
