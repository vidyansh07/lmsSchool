'use client';

/**
 * An admission's money: what has been paid, what is still due, and what the
 * whole thing was agreed at.
 *
 * Four tiles across the top, then Paid, then Unpaid, then the admission's own
 * figures down the right with the notes under them — the order the desk reads
 * it in when a student is standing at the counter asking "how much is left".
 *
 * **One screen, several ledgers.** An admission can carry two courses, and
 * each course keeps its own fee plan (that is the whole point of the
 * grouping — "which course was that ₹5,000 for" has to stay answerable). So
 * the payments and instalments shown here are *merged* across the plans and
 * sorted by date, and every action names the plan it belongs to: Pay settles
 * one instalment of one plan, never a sum spread over two. A payment that
 * straddled two ledgers could not be refunded, receipted or reconciled.
 *
 * Nothing here is added up by this component. Each plan's own totals are the
 * server's, and the tiles sum those — a screen that recomputes a balance can
 * disagree with the ledger it is reporting on, and the ledger is the one that
 * is right.
 */

import Link from 'next/link';
import { useCallback, useEffect, useState } from 'react';
import { Download, Mail, Pencil, Printer, Receipt } from 'lucide-react';

import { PaymentDialog } from '@/components/admissions/payment-dialog';
import { EmptyState, ErrorState, LoadingState } from '@/components/states';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { Textarea } from '@/components/ui/input';
import { ApiError } from '@/lib/api';
import { getAdmission, type Admission } from '@/lib/admissions-api';
import { receiptUrl } from '@/components/fees/fee-ledger';
import { emailReceipt, getEnrollmentFee } from '@/lib/fees';
import { formatDate, formatDateTime, formatRupees } from '@/lib/format';
import { PAYMENT_METHOD_LABEL } from '@/lib/labels';
import type { FeeInstallment, FeePayment, FeePlan } from '@/types/api';

/** One instalment or payment, with the plan it belongs to. The screen merges
 *  several plans; every action needs to know which one it is acting on. */
interface Owned<T> {
  row: T;
  plan: FeePlan;
}

function byDate<T extends { due_on?: string; paid_on?: string }>(a: Owned<T>, b: Owned<T>) {
  const left = a.row.due_on ?? a.row.paid_on ?? '';
  const right = b.row.due_on ?? b.row.paid_on ?? '';
  return left.localeCompare(right);
}

export function PaymentDetails({
  studentId,
  admissionId,
  canManage,
}: {
  studentId: string;
  admissionId: string;
  /** `fee.manage_any` — a caller without it reads the same figures. */
  canManage: boolean;
}) {
  const [admission, setAdmission] = useState<Admission | null>(null);
  const [plans, setPlans] = useState<FeePlan[]>([]);
  const [error, setError] = useState<ApiError | null>(null);
  const [paying, setPaying] = useState<Owned<FeeInstallment> | null>(null);
  const [note, setNote] = useState('');

  const load = useCallback(() => {
    let cancelled = false;
    getAdmission(admissionId)
      .then(async (found) => {
        if (cancelled) return;
        setAdmission(found);
        const enrolments = found.lines
          .filter((line) => line.kind === 'course' && line.enrollment_id)
          .map((line) => line.enrollment_id as string);
        // A line with no batch chosen yet has no plan, which is a real state
        // and not an error: the agreement exists before the seat does.
        const settled = await Promise.allSettled(enrolments.map(getEnrollmentFee));
        if (cancelled) return;
        setPlans(
          settled
            .filter((result) => result.status === 'fulfilled')
            .map((result) => (result as PromiseFulfilledResult<FeePlan>).value),
        );
        setError(null);
      })
      .catch((cause: unknown) => {
        if (!cancelled) {
          setError(
            cause instanceof ApiError
              ? cause
              : new ApiError(0, 'unknown', 'Could not load this admission.', ''),
          );
        }
      });
    return () => {
      cancelled = true;
    };
  }, [admissionId]);

  useEffect(() => load(), [load]);

  // Derived, not a third piece of state: "still loading" is exactly "nothing
  // has arrived and nothing has failed". A `setLoading(true)` reachable from
  // the effect body is the cascading-render pattern this codebase's lint
  // config refuses, and a reload keeps the figures on screen rather than
  // blanking them.
  if (admission === null && error === null) {
    return <LoadingState label="Loading this admission…" rows={8} />;
  }
  if (error || !admission) {
    return (
      <ErrorState
        title="Could not load this admission"
        message={error?.message ?? 'It may have been removed.'}
        requestId={error?.requestId || undefined}
        onRetry={load}
      />
    );
  }

  const paid: Owned<FeePayment>[] = plans.flatMap((plan) =>
    plan.payments.map((row) => ({ row, plan })),
  );
  const unpaid: Owned<FeeInstallment>[] = plans.flatMap((plan) =>
    plan.installments
      .filter((row) => row.status !== 'paid')
      .map((row) => ({ row, plan })),
  );
  const money = admission.money;
  const firstName = admission.student_name.split(' ')[0] ?? '';

  const tiles = [
    { label: 'Total (Rs.)', value: money.total, tone: 'bg-action/10 text-action' },
    { label: 'Received (Rs.)', value: money.paid, tone: 'bg-success/10 text-success' },
    { label: 'Uncleared (Rs.)', value: money.uncleared, tone: 'bg-warning/10 text-warning' },
    { label: 'Balance (Rs.)', value: money.balance, tone: 'bg-danger/10 text-danger' },
  ];

  return (
    <div className="space-y-5">
      <ul className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {tiles.map((tile) => (
          <li key={tile.label} className={`rounded-card p-4 ${tile.tone}`}>
            <p className="text-sm font-medium">{tile.label}</p>
            <p className="text-2xl font-semibold tabular-nums">
              {Number(tile.value).toLocaleString('en-IN', { maximumFractionDigits: 0 })}
            </p>
          </li>
        ))}
      </ul>

      <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_20rem]">
        <div className="min-w-0 space-y-5">
          <Card>
            <CardContent className="space-y-4 pt-5">
              <h2 className="text-xl font-normal text-success">Paid</h2>
              {paid.length === 0 ? (
                <p className="text-sm text-ink-muted">Nothing has been paid yet.</p>
              ) : (
                <ul className="divide-y divide-line">
                  {paid.sort(byDate).map(({ row, plan }) => (
                    <li key={row.id} className="space-y-1 py-4 first:pt-0">
                      <p className="text-xl font-normal tabular-nums text-ink">
                        {formatRupees(row.amount)}
                      </p>
                      <p className="text-sm text-ink">
                        Paid on {formatDate(row.paid_on)} by {PAYMENT_METHOD_LABEL[row.method]}
                        {row.reference ? ` with reference number ${row.reference}` : ''}.
                      </p>
                      <p className="text-xs text-ink-muted">
                        created by {row.recorded_by ?? 'the system'} on{' '}
                        {formatDateTime(row.created_at)}
                      </p>
                      <div className="flex flex-wrap items-center gap-3 pt-1 text-sm">
                        {row.category_name ? (
                          <Badge variant="info">{row.category_name}</Badge>
                        ) : null}
                        {row.clearing_status === 'uncleared' ? (
                          <Badge variant="warning">Uncleared</Badge>
                        ) : null}
                        {row.is_voided ? <Badge variant="error">Voided</Badge> : null}
                        <a
                          href={receiptUrl(row.id)}
                          className="inline-flex items-center gap-1 text-action hover:underline"
                        >
                          <Printer className="size-3.5" aria-hidden="true" />
                          Print
                        </a>
                        {canManage ? (
                          <button
                            type="button"
                            onClick={() => void emailReceipt(row.id)}
                            className="inline-flex items-center gap-1 text-action hover:underline"
                          >
                            <Mail className="size-3.5" aria-hidden="true" />
                            Email
                          </button>
                        ) : null}
                        <Link
                          href={`/students/${studentId}?tab=fees`}
                          className="inline-flex items-center gap-1 text-action hover:underline"
                          title={`On ${plan.course_title}`}
                        >
                          <Pencil className="size-3.5" aria-hidden="true" />
                          On the fee tab
                        </Link>
                      </div>
                    </li>
                  ))}
                </ul>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardContent className="space-y-4 pt-5">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <h2 className="text-xl font-normal text-danger">Unpaid</h2>
                {canManage && plans.length > 0 ? (
                  <div className="flex gap-2">
                    <Button asChild size="sm">
                      <Link href={`/students/${studentId}?tab=fees`}>Reconfigure instalments</Link>
                    </Button>
                    <Button asChild size="sm" variant="outline">
                      <Link href={`/students/${studentId}?tab=fees`}>Edit existing instalments</Link>
                    </Button>
                  </div>
                ) : null}
              </div>

              {unpaid.length === 0 ? (
                <EmptyState
                  title="Nothing outstanding"
                  description="Every instalment on this admission has been settled."
                />
              ) : (
                <ul className="divide-y divide-line">
                  {unpaid.sort(byDate).map(({ row, plan }) => (
                    <li key={row.id} className="space-y-1 py-4 first:pt-0">
                      <p className="text-xl font-normal tabular-nums text-ink">
                        {formatRupees(row.balance)}
                      </p>
                      <p className="text-sm text-ink">Due on {formatDate(row.due_on)}.</p>
                      {plans.length > 1 ? (
                        <p className="text-xs text-ink-muted">{plan.course_title}</p>
                      ) : null}
                      {canManage ? (
                        <div className="flex flex-wrap items-center gap-3 pt-1 text-sm">
                          <button
                            type="button"
                            onClick={() => setPaying({ row, plan })}
                            className="inline-flex items-center gap-1 text-action hover:underline"
                          >
                            <Receipt className="size-3.5" aria-hidden="true" />
                            Pay
                          </button>
                        </div>
                      ) : null}
                    </li>
                  ))}
                </ul>
              )}
            </CardContent>
          </Card>
        </div>

        <aside className="space-y-5">
          <Card>
            <CardContent className="pt-5">
              <h2 className="mb-3 text-base font-medium text-ink">
                {admission.lines
                  .filter((line) => line.kind === 'course')
                  .map((line) => line.name)
                  .join(', ') || 'Admission'}
              </h2>
              <dl className="divide-y divide-line text-sm">
                {[
                  ['Admission Date', formatDate(admission.admission_date)],
                  ['Fees', formatRupees(admission.gross_total)],
                  ['Discount', formatRupees(admission.discount_amount)],
                  ['Refund', formatRupees(money.refund)],
                  ['Cancellation Charges', formatRupees(0)],
                ].map(([label, value]) => (
                  <div key={label} className="flex items-center justify-between gap-3 py-2">
                    <dt className="text-ink-muted">{label}</dt>
                    <dd className="tabular-nums text-ink">{value}</dd>
                  </div>
                ))}
                <div className="flex items-center justify-between gap-3 py-2 font-semibold">
                  <dt>Total</dt>
                  <dd className="tabular-nums">{formatRupees(admission.total_fees)}</dd>
                </div>
              </dl>
            </CardContent>
          </Card>

          <Card>
            <CardContent className="space-y-3 pt-5">
              <h2 className="text-base font-medium text-ink">Download</h2>
              <Button asChild variant="outline" size="sm">
                <Link href={`/students/${studentId}?tab=fees`}>
                  <Download className="size-4" aria-hidden="true" />
                  Instalment&apos;s schedules
                </Link>
              </Button>
            </CardContent>
          </Card>

          <Card>
            <CardContent className="space-y-3 pt-5">
              <h2 className="text-base font-medium text-ink">Notes</h2>
              <Textarea
                aria-label="Note"
                rows={3}
                value={note}
                onChange={(event) => setNote(event.target.value)}
                placeholder="Note"
              />
              <Button size="sm" disabled className="bg-success hover:bg-success/90">
                Save
              </Button>
              {admission.created_by ? (
                <p className="border-t border-line pt-3 text-sm text-ink">
                  <strong>{admission.created_by}</strong> added new admission (
                  <span className="text-action">
                    {admission.lines
                      .filter((line) => line.kind === 'course')
                      .map((line) => line.name)
                      .join(', ')}
                  </span>
                  ) for the student <strong>{admission.student_name}</strong>.
                  <span className="mt-1 block text-xs text-ink-muted">
                    note added by {admission.created_by} on {formatDate(admission.created_at)}
                  </span>
                </p>
              ) : null}
            </CardContent>
          </Card>
        </aside>
      </div>

      {paying ? (
        <PaymentDialog
          enrollmentId={paying.plan.enrollment_id}
          instalment={paying.row}
          firstName={firstName}
          open
          onClose={() => setPaying(null)}
          onPaid={load}
        />
      ) : null}

      {admission.is_cancelled ? (
        <Card>
          <CardContent className="pt-5">
            <p className="text-sm text-ink">
              This admission was cancelled on {formatDate(admission.cancelled_at ?? '')}.{' '}
              {admission.cancellation_reason}
            </p>
          </CardContent>
        </Card>
      ) : null}
    </div>
  );
}
