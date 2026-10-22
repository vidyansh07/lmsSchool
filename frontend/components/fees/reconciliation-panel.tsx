/**
 * Does the money add up?
 *
 * The fees panel next to this one answers "how are we doing" — collected
 * this month, who is late. It cannot answer "does it add up", because it
 * never states what was charged in the first place and it drops a cancelled
 * admission entirely, so money on a cancellation leaves the screen without
 * ever being accounted for.
 *
 * This states the institute's own identity instead:
 *
 *     charged = received − to refund + written off + still owed
 *
 * and shows what is left over. The backend
 * (`apps.fees.services.ledger_reconciliation`) computes both sides
 * independently rather than deriving the remainder by subtraction, so
 * `unreconciled` is a real finding rather than an arithmetic certainty. Zero
 * is the normal, quiet answer; anything else is shown as the problem it is,
 * never hidden or folded into another figure.
 *
 * Everything here is scoped by the endpoint to the enrolments the caller may
 * already see, so a counsellor at one centre reconciles their own centre and
 * not the institute. No figure is recomputed in this component: a screen that
 * does its own arithmetic can disagree with the ledger it is reporting on.
 */
import { AlertTriangle, CheckCircle2 } from 'lucide-react';

import { money } from '@/components/fees/fee-ledger';
import { ErrorState, LoadingState } from '@/components/states';
import { Alert } from '@/components/ui/alert';
import { Card, CardContent } from '@/components/ui/card';
import { formatCount } from '@/lib/format';
import type { LedgerReconciliation } from '@/types/api';

/** A bucket, named in the words an owner would use rather than the field's.
 *  `deduct` marks the one line that comes *off* the total rather than adding
 *  to it — money the institute is holding but has not earned. */
interface Bucket {
  label: string;
  hint: string;
  amount: string;
  deduct?: boolean;
}

/** The buckets, each straight from the endpoint. Nothing is added, netted or
 *  subtracted here: the arithmetic belongs to the ledger being reported on,
 *  and a screen that redoes it can disagree with it. */
function buckets(data: LedgerReconciliation): Bucket[] {
  return [
    {
      label: 'Received',
      hint: 'Payments neither voided nor refunded',
      amount: data.received,
    },
    {
      label: 'Owed back',
      hint: 'Held, but somebody paid more than they ended up owing',
      amount: data.refund_due,
      deduct: true,
    },
    {
      label: 'Written off',
      hint: 'Decided not to pursue on a cancelled admission',
      amount: data.written_off,
    },
    {
      label: 'Still owed',
      hint: 'Outstanding on a live admission',
      amount: data.outstanding,
    },
  ];
}

export function ReconciliationPanel({
  data,
  isLoading,
  error,
  onRetry,
}: {
  data: LedgerReconciliation | null;
  isLoading?: boolean;
  error?: { message: string; requestId?: string } | null;
  onRetry?: () => void;
}) {
  if (isLoading) return <LoadingState label="Reconciling the ledger…" rows={3} />;
  if (error) {
    return (
      <ErrorState
        title="The reconciliation did not load"
        message={error.message}
        requestId={error.requestId}
        onRetry={onRetry}
      />
    );
  }
  if (!data) return null;

  const unreconciled = Number(data.unreconciled);
  const balances = unreconciled === 0;

  return (
    <div className="space-y-4" data-testid="fee-reconciliation">
      {balances ? (
        <Alert variant="success">
          <CheckCircle2 className="size-4" aria-hidden="true" />
          Every rupee charged is accounted for.
        </Alert>
      ) : (
        <Alert variant="error">
          <AlertTriangle className="size-4" aria-hidden="true" />
          {money(data.unreconciled)} is not accounted for. The buckets below do not add up to what
          was charged — somebody needs to look at this.
        </Alert>
      )}

      <Card>
        <CardContent className="space-y-4 pt-5">
          <div className="flex flex-wrap items-baseline justify-between gap-2">
            <div>
              <p className="text-sm font-medium text-ink">Charged</p>
              <p className="text-xs text-ink-muted">
                Every fee agreed, less its discount, cancelled admissions included
              </p>
            </div>
            <p className="text-xl font-semibold tabular-nums text-ink">{money(data.charged)}</p>
          </div>

          <dl className="divide-y divide-line border-t border-line">
            {buckets(data).map((bucket) => (
              <div
                key={bucket.label}
                className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1 py-3"
              >
                <div className="min-w-0">
                  <dt className="text-sm text-ink">{bucket.label}</dt>
                  <dd className="text-xs text-ink-muted">{bucket.hint}</dd>
                </div>
                <dd className="shrink-0 tabular-nums text-ink">
                  {bucket.deduct ? `− ${money(bucket.amount)}` : money(bucket.amount)}
                </dd>
              </div>
            ))}
            {unreconciled === 0 ? null : (
              <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1 py-3">
                <div className="min-w-0">
                  <dt className="text-sm font-medium text-danger">Not accounted for</dt>
                  <dd className="text-xs text-ink-muted">
                    What the buckets above fail to explain
                  </dd>
                </div>
                <dd className="shrink-0 tabular-nums font-medium text-danger">
                  {money(data.unreconciled)}
                </dd>
              </div>
            )}
          </dl>

          <div className="grid gap-3 border-t border-line pt-4 text-sm sm:grid-cols-2">
            <div>
              <p className="text-xs text-ink-muted">Refunded</p>
              <p className="tabular-nums text-ink">{money(data.refunded)}</p>
              <p className="text-2xs text-ink-faint">Given back; already out of money held</p>
            </div>
            <div>
              <p className="text-xs text-ink-muted">Cancelled admissions</p>
              <p className="tabular-nums text-ink">
                {formatCount(data.cancelled_enrolments, 'admission')}
              </p>
              <p className="text-2xs text-ink-faint">Still counted above, not dropped</p>
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
