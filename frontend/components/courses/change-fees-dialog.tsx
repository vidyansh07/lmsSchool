'use client';

/**
 * "Change Fees" from the course row's menu: the new fee, the day it applies
 * from, why, and the history of every previous answer.
 *
 * Separate from editing the course, because it is a different act. Changing a
 * fee is a commercial decision somebody announces for a date, and it is the
 * one course field an accountant is later asked to account for; a PATCH that
 * moved `default_fee` among ten other fields would leave no such record.
 *
 * Two things this screen says out loud, because people ask both every time:
 *
 * * **Nobody already enrolled is affected.** Their plan copied the figure the
 *   day they enrolled and never reads the course again.
 * * **A date in the future is normal.** A fee rise decided in October and
 *   announced for November is exactly what `effective_from` is for; quotes
 *   before that day still use today's fee.
 *
 * The instalment structure is edited here too. It is the other half of "what
 * does this course cost" — how the money arrives — and the two are always
 * changed in the same conversation.
 */
import { useEffect, useState } from 'react';

import { FeeInstalmentEditor, sharesTotal } from '@/components/courses/fee-instalment-editor';
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
import { Table, TableWrapper, Td, Th } from '@/components/ui/table';
import { errorMessage, fieldErrors } from '@/lib/api';
import {
  listCourseInstalments,
  listCoursePrices,
  recordCoursePrice,
  setCourseInstalments,
  type CourseFeeInstalmentInput,
} from '@/lib/course-fees';
import { formatDate, formatRupees, localIsoDate } from '@/lib/format';
import type { CoursePrice } from '@/types/api';

export function ChangeFeesDialog({
  course,
  open,
  onClose,
  onSaved,
}: {
  course: { id: string; title: string; default_fee: string | null };
  open: boolean;
  onClose: () => void;
  onSaved: (message: string) => void;
}) {
  const [amount, setAmount] = useState(course.default_fee ?? '');
  // Today in *local* time. `toISOString().slice(0, 10)` is yesterday in IST
  // before 05:30, which would date a fee change to the wrong day.
  const [effectiveFrom, setEffectiveFrom] = useState(localIsoDate());
  const [note, setNote] = useState('');
  const [rows, setRows] = useState<CourseFeeInstalmentInput[]>([]);
  /** Whether this course had a structure when the dialog opened. A course
   *  with none, left with none, is not written to at all — an empty PUT
   *  would record a change that nobody made. */
  const [hadStructure, setHadStructure] = useState(false);
  const [history, setHistory] = useState<CoursePrice[]>([]);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    void Promise.all([listCoursePrices(course.id), listCourseInstalments(course.id)])
      .then(([prices, instalments]) => {
        if (cancelled) return;
        setHistory(prices);
        setHadStructure(instalments.length > 0);
        setRows(
          instalments.map((row) => ({
            label: row.label,
            percent: row.percent,
            due_after_days: row.due_after_days,
          })),
        );
      })
      .catch((cause) => {
        if (!cancelled) setErrors({ __all__: errorMessage(cause) });
      });
    return () => {
      cancelled = true;
    };
  }, [open, course.id]);

  const total = sharesTotal(rows);
  const balanced = rows.length === 0 || Math.abs(total - 100) < 0.005;

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    const problems: Record<string, string> = {};
    if (!amount.trim()) problems.amount = 'Say what the fee becomes.';
    if (Number(amount) < 0) problems.amount = 'A fee cannot be negative.';
    if (!effectiveFrom) problems.effective_from = 'Say which day it applies from.';
    if (!balanced) problems.instalments = `The shares add up to ${total.toFixed(2)}%, not 100%.`;
    if (Object.keys(problems).length > 0) {
      setErrors(problems);
      return;
    }

    setSaving(true);
    setErrors({});
    try {
      await recordCoursePrice(course.id, {
        amount: amount.trim(),
        effective_from: effectiveFrom,
        note: note.trim(),
      });
      if (rows.length > 0 || hadStructure) {
        await setCourseInstalments(course.id, rows);
      }
      onSaved(`${course.title} now costs ${formatRupees(amount)} from ${formatDate(effectiveFrom)}.`);
    } catch (cause) {
      setErrors(fieldErrors(cause));
    } finally {
      setSaving(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={(next) => (next ? undefined : onClose())}>
      <DialogContent className="max-h-[85vh] overflow-y-auto">
        {/* No browser validation: a `max` or a `required` the browser enforces
            refuses the submit with no message anywhere on screen. Every rule
            here is checked above and reported in the form. */}
        <form className="space-y-4" onSubmit={(event) => void submit(event)} noValidate>
          <DialogHeader>
            <DialogTitle>Change Fees — {course.title}</DialogTitle>
            <DialogDescription>
              Students already enrolled keep the fee they were quoted; their plan copied it the
              day they enrolled. A date in the future is normal — a rise announced now for next
              month leaves today&apos;s quotes alone.
            </DialogDescription>
          </DialogHeader>

          {errors.__all__ ? <Alert variant="error">{errors.__all__}</Alert> : null}

          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Course fee" htmlFor="fee-amount" error={errors.amount} required>
              <Input
                id="fee-amount"
                type="number"
                min={0}
                step="0.01"
                autoFocus
                value={amount}
                onChange={(event) => setAmount(event.target.value)}
              />
            </Field>
            <Field
              label="Effective from"
              htmlFor="fee-from"
              error={errors.effective_from}
              required
              hint="The first day this fee applies."
            >
              <Input
                id="fee-from"
                type="date"
                value={effectiveFrom}
                onChange={(event) => setEffectiveFrom(event.target.value)}
              />
            </Field>
          </div>

          <Field
            label="Why it changed"
            htmlFor="fee-note"
            error={errors.note}
            hint="Kept with the record, for whoever reads this a year from now."
          >
            <Input
              id="fee-note"
              value={note}
              maxLength={200}
              placeholder="Revised rate for the 2026 session"
              onChange={(event) => setNote(event.target.value)}
            />
          </Field>

          <section className="space-y-3 rounded-card border border-line p-3">
            <div>
              <h3 className="text-sm font-medium">Fee Instalment Structure</h3>
              <p className="text-xs text-ink-muted">
                How this fee is normally collected. Shares are of what each student actually
                pays, so a discount scales them rather than breaking them.
              </p>
            </div>
            <FeeInstalmentEditor rows={rows} onChange={setRows} errors={errors} />
          </section>

          {history.length > 0 ? (
            <section className="space-y-2">
              <h3 className="text-sm font-medium">What it has cost</h3>
              <TableWrapper>
                <Table>
                  <thead>
                    <tr>
                      <Th>From</Th>
                      <Th>Fee</Th>
                      <Th>Why</Th>
                      <Th>Recorded by</Th>
                    </tr>
                  </thead>
                  <tbody>
                    {history.map((row) => (
                      <tr key={row.id}>
                        <Td className="whitespace-nowrap tabular-nums">
                          {formatDate(row.effective_from)}
                        </Td>
                        <Td className="tabular-nums">{formatRupees(row.amount)}</Td>
                        <Td>{row.note || '—'}</Td>
                        <Td>{row.recorded_by_name || '—'}</Td>
                      </tr>
                    ))}
                  </tbody>
                </Table>
              </TableWrapper>
            </section>
          ) : null}

          <DialogFooter>
            <Button type="button" variant="ghost" onClick={onClose}>
              Cancel
            </Button>
            <Button type="submit" disabled={saving}>
              {saving ? 'Saving…' : 'Change Fees'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
