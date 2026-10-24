'use client';

/**
 * The instalment schedule, two ways.
 *
 * `InstallmentEditor` is the counsellor shaping a schedule *before* it is
 * saved: how many instalments, each amount, each due date, with a running
 * total that must come to the fee after discount. It starts on the server's
 * own default (six, thirty days apart, first due today — `defaultInstallments`
 * reproduces that arithmetic exactly) and only ever sends the rows the
 * counsellor can see, so what is saved is what was on screen.
 *
 * `InstallmentTable` is the saved schedule read back, each row carrying the
 * state the server derived from the ledger: paid, pending, overdue, upcoming,
 * and — when the caller passes `onOpenComments` — the size of the row's
 * comment thread. A student's own fee screen passes neither, so the column is
 * simply absent there rather than rendering an affordance that would 403.
 */
import { Plus, Trash2 } from 'lucide-react';

import { CommentCountButton } from '@/components/fees/comment-thread';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Checkbox } from '@/components/ui/checkbox';
import { Input } from '@/components/ui/input';
import { Table, TableWrapper, Td, Th, Tr } from '@/components/ui/table';
import { defaultInstallments, installmentsTotal } from '@/lib/fees';
import { formatCurrency, formatDate } from '@/lib/format';
import { INSTALLMENT_STATUS_LABEL, INSTALLMENT_STATUS_VARIANT } from '@/lib/labels';
import { cn } from '@/lib/utils';
import type { FeeInstallment, InstallmentInput } from '@/types/api';

export const DEFAULT_INSTALLMENT_COUNT = 6;
export const MAX_INSTALLMENTS = 36;

function localIso(date: Date): string {
  const yyyy = date.getFullYear();
  const mm = String(date.getMonth() + 1).padStart(2, '0');
  const dd = String(date.getDate()).padStart(2, '0');
  return `${yyyy}-${mm}-${dd}`;
}

function rupees(value: number): string {
  return formatCurrency(value, { decimals: value % 1 === 0 ? 0 : 2 });
}

export interface InstallmentEditorProps {
  /** The fee after discount the rows must add up to. */
  payable: number;
  rows: InstallmentInput[];
  onChange: (rows: InstallmentInput[]) => void;
  /** Shown when the server refused the schedule. */
  error?: string;
  /** What has already been received against this plan, so the rows can say
   *  which of them that money already covers. */
  received?: number;
  /** A compact variant for the wizard, where the table sits inside a form. */
  idPrefix?: string;
}

/** True when the rows are complete and add up to the fee, to the paisa. */
export function installmentsAddUp(rows: InstallmentInput[], payable: number): boolean {
  if (rows.length === 0) return true;
  if (rows.some((row) => !row.due_on || !(Number(row.amount) > 0))) return false;
  return Math.round(installmentsTotal(rows) * 100) === Math.round(payable * 100);
}

/**
 * What the schedule being typed would mean for a student who has already
 * paid something: the ledger covers instalments in order with whatever has
 * been received, so the first rows are already settled and one is partly so.
 *
 * Shown while editing rather than discovered after saving — the reference
 * product calls this an instalments preview, and it is the difference
 * between "four instalments of 5,000" and "the first two are already paid".
 */
export function coverageOf(
  rows: InstallmentInput[],
  received: number,
): ('paid' | 'part' | 'pending')[] {
  let left = received;
  return rows.map((row) => {
    const amount = Number(row.amount) || 0;
    if (left >= amount && amount > 0) {
      left -= amount;
      return 'paid';
    }
    if (left > 0) {
      left = 0;
      return 'part';
    }
    return 'pending';
  });
}

const COVERAGE_LABEL: Record<'paid' | 'part' | 'pending', string> = {
  paid: 'Already paid',
  part: 'Partly paid',
  pending: 'Pending',
};

export function InstallmentEditor({
  payable,
  rows,
  onChange,
  error,
  received = 0,
  idPrefix = 'inst',
}: InstallmentEditorProps) {
  const enabled = rows.length > 0;
  const total = installmentsTotal(rows);
  const difference = Math.round((payable - total) * 100) / 100;
  const addsUp = installmentsAddUp(rows, payable);
  const coverage = coverageOf(rows, received);

  function regenerate(count: number) {
    const start = rows[0]?.due_on ? new Date(`${rows[0].due_on}T00:00:00`) : new Date();
    onChange(defaultInstallments(payable, count, start));
  }

  function update(index: number, patch: Partial<InstallmentInput>) {
    onChange(rows.map((row, at) => (at === index ? { ...row, ...patch } : row)));
  }

  function remove(index: number) {
    onChange(rows.filter((_, at) => at !== index));
  }

  function add() {
    const last = rows[rows.length - 1];
    const due = last?.due_on ? new Date(`${last.due_on}T00:00:00`) : new Date();
    due.setDate(due.getDate() + 30);
    const remaining = Math.max(0, difference);
    onChange([...rows, { amount: remaining > 0 ? remaining.toFixed(2) : '', due_on: localIso(due) }]);
  }

  return (
    <div className="space-y-3" data-testid="installment-editor">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
        <label className="inline-flex items-center gap-2 text-sm">
          <Checkbox
            id={`${idPrefix}-enabled`}
            checked={enabled}
            onCheckedChange={(checked) =>
              onChange(checked ? defaultInstallments(payable, DEFAULT_INSTALLMENT_COUNT) : [])
            }
          />
          <span>Collect in instalments</span>
        </label>
        {enabled ? (
          <label className="inline-flex items-center gap-2 text-sm" htmlFor={`${idPrefix}-count`}>
            <span className="text-ink-muted">Number of instalments</span>
            <Input
              id={`${idPrefix}-count`}
              type="number"
              inputMode="numeric"
              min={1}
              max={MAX_INSTALLMENTS}
              step="1"
              className="w-20"
              value={rows.length}
              onChange={(event) => {
                const count = Math.max(1, Math.min(MAX_INSTALLMENTS, Number(event.target.value) || 1));
                regenerate(count);
              }}
            />
          </label>
        ) : (
          <span className="text-sm text-ink-muted">
            No schedule: payments are taken as they come, any amount, any day.
          </span>
        )}
      </div>

      {enabled ? (
        <>
          <TableWrapper>
            <Table>
              <thead>
                <tr>
                  <Th className="w-10">#</Th>
                  <Th>Due on</Th>
                  <Th className="text-right">Amount (₹)</Th>
                  {received > 0 ? <Th>Covered by what is paid</Th> : null}
                  <Th className="w-12">
                    <span className="sr-only">Remove</span>
                  </Th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row, index) => (
                  <Tr key={index}>
                    <Td className="tabular-nums text-ink-muted">{index + 1}</Td>
                    <Td>
                      <Input
                        type="date"
                        aria-label={`Instalment ${index + 1} due on`}
                        value={row.due_on}
                        onChange={(event) => update(index, { due_on: event.target.value })}
                      />
                    </Td>
                    <Td className="text-right">
                      <Input
                        type="number"
                        inputMode="decimal"
                        min={1}
                        step="1"
                        className="text-right"
                        aria-label={`Instalment ${index + 1} amount`}
                        value={row.amount}
                        onChange={(event) => update(index, { amount: event.target.value })}
                      />
                    </Td>
                    {received > 0 ? (
                      <Td>
                        <Badge
                          variant={
                            coverage[index] === 'paid'
                              ? 'success'
                              : coverage[index] === 'part'
                                ? 'warning'
                                : 'neutral'
                          }
                        >
                          {COVERAGE_LABEL[coverage[index] ?? 'pending']}
                        </Badge>
                      </Td>
                    ) : null}
                    <Td className="text-right">
                      <Button
                        type="button"
                        size="sm"
                        variant="ghost"
                        aria-label={`Remove instalment ${index + 1}`}
                        onClick={() => remove(index)}
                        disabled={rows.length <= 1}
                      >
                        <Trash2 className="size-4" aria-hidden="true" />
                      </Button>
                    </Td>
                  </Tr>
                ))}
              </tbody>
            </Table>
          </TableWrapper>
          <div className="flex flex-wrap items-center justify-between gap-2 text-sm">
            <Button
              type="button"
              size="sm"
              variant="outline"
              onClick={add}
              disabled={rows.length >= MAX_INSTALLMENTS}
            >
              <Plus className="size-4" aria-hidden="true" />
              Add instalment
            </Button>
            <p
              className={cn('tabular-nums', addsUp ? 'text-ink-muted' : 'text-danger')}
              role={addsUp ? undefined : 'alert'}
            >
              {addsUp
                ? `Adds up to ${rupees(payable)}.`
                : difference > 0
                  ? `${rupees(difference)} still to place; the instalments must add up to ${rupees(payable)}.`
                  : `${rupees(-difference)} too much; the instalments must add up to ${rupees(payable)}.`}
            </p>
          </div>
        </>
      ) : null}
      {error ? (
        <p className="text-sm text-danger" role="alert">
          {error}
        </p>
      ) : null}
    </div>
  );
}

export function InstallmentTable({
  installments,
  onOpenComments,
}: {
  installments: FeeInstallment[];
  onOpenComments?: (installment: FeeInstallment) => void;
}) {
  if (installments.length === 0) {
    return (
      <p className="text-sm text-ink-muted">
        No instalment schedule: payments are taken as they come.
      </p>
    );
  }
  return (
    <TableWrapper>
      <Table>
        <thead>
          <tr>
            <Th className="w-10">#</Th>
            <Th>Due on</Th>
            <Th className="text-right">Amount</Th>
            <Th className="text-right">Paid</Th>
            <Th>Status</Th>
            {onOpenComments ? <Th className="text-right">Comments</Th> : null}
          </tr>
        </thead>
        <tbody>
          {installments.map((row) => (
            <Tr key={row.id} data-testid={`installment-${row.sequence}`}>
              <Td className="tabular-nums text-ink-muted">{row.sequence}</Td>
              <Td className="whitespace-nowrap">{formatDate(row.due_on)}</Td>
              <Td className="text-right tabular-nums">{rupees(Number(row.amount))}</Td>
              <Td className="text-right tabular-nums">{rupees(Number(row.paid_amount))}</Td>
              <Td>
                <Badge variant={INSTALLMENT_STATUS_VARIANT[row.status]} dot>
                  {INSTALLMENT_STATUS_LABEL[row.status]}
                </Badge>
              </Td>
              {onOpenComments ? (
                <Td className="text-right">
                  <CommentCountButton
                    count={row.comment_count}
                    label={`instalment ${row.sequence}`}
                    onClick={() => onOpenComments(row)}
                  />
                </Td>
              ) : null}
            </Tr>
          ))}
        </tbody>
      </Table>
    </TableWrapper>
  );
}
