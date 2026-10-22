/**
 * A student's own money, on their dashboard: what is still owed across every
 * course, what falls due next, and the receipt for each payment already made.
 *
 * Read-only, and deliberately so — the counsellor's desk is where money
 * changes hands (`components/fees/fee-ledger.tsx` is the writable version of
 * the same figures). This panel exists because the dashboard used to answer
 * every question a student had *except* the one they ask first, with the
 * answer a click away on `/my-fees` and nothing on the dashboard saying so.
 *
 * Every figure comes from `GET /fees/mine/` (`StudentFeeSummary`) — the
 * caller's own plans and nobody else's, scoped by the endpoint rather than
 * filtered here. The panel never computes a total of its own: `payable_total`,
 * `paid_total` and `balance_total` are the backend's, so this card and the
 * fee ledger can never disagree about what somebody owes.
 *
 * `enrollments_without_plan` is shown rather than hidden: "no fee has been
 * set for this course yet" is a real state a student may need to ask about,
 * and showing a balance of zero for it would be a lie.
 */
import Link from 'next/link';
import { AlertTriangle, ReceiptText } from 'lucide-react';

import { ErrorState, LoadingState } from '@/components/states';
import { money } from '@/components/fees/fee-ledger';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { formatCount, formatDate } from '@/lib/format';
import type { FeePayment, StudentFeeSummary } from '@/types/api';

/** Enough to recognise the last payment or two; the rest is on `/my-fees`. */
const RECEIPT_LIMIT = 3;

/** One receipt, with the course it was paid against. */
interface ReceiptRow {
  payment: FeePayment;
  courseTitle: string;
}

/**
 * Every payment that still counts, newest first, carrying the course it was
 * for. A voided or refunded payment is left out: its receipt number is no
 * longer money this student has paid, and showing it here — with no room for
 * the explanation the full ledger gives it — would read as a payment that
 * still stands.
 */
export function receiptsFrom(summary: StudentFeeSummary): ReceiptRow[] {
  return summary.plans
    .flatMap((plan) =>
      plan.payments
        .filter((payment) => !payment.is_voided && !payment.is_refunded)
        .map((payment) => ({ payment, courseTitle: plan.course_title })),
    )
    .sort((a, b) => b.payment.paid_on.localeCompare(a.payment.paid_on));
}

/** The courses with something still to pay — a plan's own `balance`, not a
 *  figure worked out here. */
export function unpaidFrom(summary: StudentFeeSummary) {
  return summary.plans.filter((plan) => Number(plan.balance) > 0);
}

export function FeesPanel({
  summary,
  isLoading,
  error,
  onRetry,
}: {
  summary: StudentFeeSummary | null;
  isLoading?: boolean;
  error?: { message: string; requestId?: string } | null;
  onRetry?: () => void;
}) {
  if (isLoading) return <LoadingState label="Loading your fees…" rows={3} />;
  if (error) {
    return <ErrorState message={error.message} requestId={error.requestId} onRetry={onRetry} />;
  }

  if (!summary || (summary.plans.length === 0 && summary.enrollments_without_plan === 0)) {
    return (
      <p className="rounded-card border border-dashed border-line px-4 py-6 text-center text-sm text-ink-muted">
        No fees on record yet. One appears here as soon as the admissions desk sets it.
      </p>
    );
  }

  const unpaid = unpaidFrom(summary);
  const receipts = receiptsFrom(summary);
  const shownReceipts = receipts.slice(0, RECEIPT_LIMIT);

  return (
    <div className="space-y-4">
      <dl className="grid grid-cols-3 gap-3 text-sm">
        <div>
          <dt className="text-xs text-ink-muted">Agreed</dt>
          <dd className="tabular-nums font-medium">{money(summary.payable_total)}</dd>
        </div>
        <div>
          <dt className="text-xs text-ink-muted">Paid</dt>
          <dd className="tabular-nums font-medium">{money(summary.paid_total)}</dd>
        </div>
        <div>
          <dt className="text-xs text-ink-muted">Still owed</dt>
          <dd className="tabular-nums font-medium">{money(summary.balance_total)}</dd>
        </div>
      </dl>

      {summary.next_due_amount ? (
        <p
          className={`flex flex-wrap items-center gap-2 rounded-card border px-3 py-2 text-sm ${
            summary.is_overdue ? 'border-danger/40 bg-danger/5' : 'border-line'
          }`}
        >
          {summary.is_overdue ? (
            <AlertTriangle className="size-4 shrink-0 text-danger" aria-hidden="true" />
          ) : null}
          <span>
            <span className="tabular-nums font-medium">{money(summary.next_due_amount)}</span>
            {summary.next_due_on ? ` due ${formatDate(summary.next_due_on)}` : ' due'}
          </span>
          {summary.is_overdue ? <Badge variant="error">Overdue</Badge> : null}
        </p>
      ) : null}

      {unpaid.length > 0 ? (
        <div className="space-y-1.5">
          <p className="text-xs font-medium text-ink-muted">Still to pay</p>
          <ul className="divide-y divide-line text-sm">
            {unpaid.map((plan) => (
              <li key={plan.id} className="flex items-center justify-between gap-3 py-1.5">
                <span className="min-w-0 truncate">{plan.course_title}</span>
                <span className="shrink-0 tabular-nums">{money(plan.balance)}</span>
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      {shownReceipts.length > 0 ? (
        <div className="space-y-1.5">
          <p className="text-xs font-medium text-ink-muted">Receipts</p>
          <ul className="divide-y divide-line text-sm">
            {shownReceipts.map(({ payment, courseTitle }) => (
              <li key={payment.id} className="flex items-start justify-between gap-3 py-1.5">
                <span className="flex min-w-0 items-start gap-2">
                  <ReceiptText className="mt-0.5 size-4 shrink-0 text-action" aria-hidden="true" />
                  <span className="min-w-0">
                    <span className="block truncate">{payment.receipt_number}</span>
                    <span className="block truncate text-xs text-ink-muted">
                      {courseTitle} · {formatDate(payment.paid_on)}
                    </span>
                  </span>
                </span>
                <span className="shrink-0 tabular-nums">{money(payment.amount)}</span>
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      {summary.enrollments_without_plan > 0 ? (
        <p className="text-xs text-ink-muted">
          {formatCount(summary.enrollments_without_plan, 'course')} with no fee set yet. Ask the
          admissions desk if that looks wrong.
        </p>
      ) : null}

      <Button asChild variant="ghost" size="sm">
        <Link href="/my-fees">
          {receipts.length > shownReceipts.length ? 'Every payment and receipt' : 'My fees in full'}
        </Link>
      </Button>
    </div>
  );
}
