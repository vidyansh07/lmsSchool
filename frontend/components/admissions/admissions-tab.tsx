'use client';

/**
 * The Admissions card on a student's record: every admission they have, what
 * each one costs, and what is left to pay.
 *
 * One row per admission, with the five figures the desk reads across —
 * Total, Paid, Uncleared, Refund, Balance — and the four things it does:
 * Pay, edit, Cancel Admission, Delete.
 *
 * The figures are the server's, read from the fee ledger. Nothing is summed
 * here: an admission's money lives in its courses' fee plans, and a screen
 * that adds them up again can disagree with the ledger it is reporting on.
 *
 * `Delete` is not offered for an admission with money against it. Cancelling
 * settles what was paid and writes off what will not be; deleting would make
 * a receipt point at nothing, which is the one thing a ledger must never
 * allow.
 */

import Link from 'next/link';
import { useCallback, useEffect, useState } from 'react';
import { Pencil, Plus, Receipt, Trash2, XCircle } from 'lucide-react';

import { CancelAdmissionDialog } from '@/components/admissions/cancel-admission-dialog';
import { EmptyState, ErrorState, LoadingState } from '@/components/states';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { ApiError } from '@/lib/api';
import { listAdmissions, type Admission } from '@/lib/admissions-api';
import { formatDate, formatRupees } from '@/lib/format';

const FIGURES = [
  { key: 'total', label: 'Total', tone: 'text-action' },
  { key: 'paid', label: 'Paid', tone: 'text-success' },
  { key: 'uncleared', label: 'Uncleared', tone: 'text-warning' },
  { key: 'refund', label: 'Refund', tone: 'text-danger' },
  { key: 'balance', label: 'Balance', tone: 'text-danger' },
] as const;

export function AdmissionsTab({
  studentId,
  canManage,
}: {
  studentId: string;
  /** `enrolment.create` — a caller without it reads the same list. */
  canManage: boolean;
}) {
  const [admissions, setAdmissions] = useState<Admission[] | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [cancelling, setCancelling] = useState<Admission | null>(null);

  const load = useCallback(() => {
    let cancelled = false;
    listAdmissions({ student: studentId })
      .then((page) => {
        if (!cancelled) {
          setAdmissions(page.results);
          setError(null);
        }
      })
      .catch((cause: unknown) => {
        if (!cancelled) setError(cause instanceof ApiError ? cause : null);
      });
    return () => {
      cancelled = true;
    };
  }, [studentId]);

  useEffect(() => load(), [load]);

  if (error) {
    return (
      <ErrorState
        title="Could not load admissions"
        message={error.message}
        requestId={error.requestId || undefined}
        onRetry={load}
      />
    );
  }
  if (admissions === null) return <LoadingState label="Loading admissions…" rows={2} />;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 className="text-xl font-normal text-ink">Admissions</h2>
        {canManage ? (
          <Button asChild>
            <Link href={`/students/${studentId}/admissions/new`}>
              <Plus className="size-4" aria-hidden="true" />
              New Admission
            </Link>
          </Button>
        ) : null}
      </div>

      {admissions.length === 0 ? (
        <EmptyState
          title="No admissions yet"
          description="Record one when the student signs up for a course."
        />
      ) : (
        <ul className="divide-y divide-line rounded-card border border-line">
          {admissions.map((admission) => (
            <li key={admission.id} className="flex flex-col gap-4 p-4 lg:flex-row lg:items-start">
              <div className="min-w-0 flex-1 space-y-1">
                <p className="text-xs text-ink-muted">{formatDate(admission.admission_date)}</p>
                <p className="flex flex-wrap items-center gap-2">
                  <Link
                    href={`/students/${studentId}/admissions/${admission.id}`}
                    className="text-base font-medium text-action underline-offset-4 hover:underline"
                  >
                    {admission.lines
                      .filter((line) => line.kind === 'course')
                      .map((line) => line.name)
                      .join(', ') || 'Admission'}
                  </Link>
                  {admission.academic_year ? (
                    <span className="text-ink-muted">({admission.academic_year})</span>
                  ) : null}
                  {admission.is_cancelled ? <Badge variant="error">Cancelled</Badge> : null}
                </p>

                {canManage && !admission.is_cancelled ? (
                  <div className="flex flex-wrap items-center gap-3 pt-1 text-sm">
                    <Link
                      href={`/students/${studentId}/admissions/${admission.id}/payment`}
                      className="inline-flex items-center gap-1 text-action hover:underline"
                    >
                      <Receipt className="size-3.5" aria-hidden="true" />
                      Pay
                    </Link>
                    <Link
                      href={`/students/${studentId}/admissions/${admission.id}/edit`}
                      className="inline-flex items-center gap-1 text-action hover:underline"
                    >
                      <Pencil className="size-3.5" aria-hidden="true" />
                      edit
                    </Link>
                    <button
                      type="button"
                      onClick={() => setCancelling(admission)}
                      className="inline-flex items-center gap-1 text-danger hover:underline"
                    >
                      <XCircle className="size-3.5" aria-hidden="true" />
                      Cancel Admission
                    </button>
                    {Number(admission.money.paid) === 0 ? (
                      <button
                        type="button"
                        disabled
                        title="Deleting is not available while an admission has a fee plan against it. Cancel it instead."
                        className="inline-flex items-center gap-1 text-ink-faint"
                      >
                        <Trash2 className="size-3.5" aria-hidden="true" />
                        Delete
                      </button>
                    ) : null}
                  </div>
                ) : null}

                {admission.is_cancelled && admission.cancellation_reason ? (
                  <p className="text-sm text-ink-muted">
                    Cancelled: {admission.cancellation_reason}
                  </p>
                ) : null}
              </div>

              <dl className="grid shrink-0 grid-cols-2 gap-x-6 gap-y-2 sm:grid-cols-5 sm:text-right">
                {FIGURES.map((figure) => (
                  <div key={figure.key}>
                    <dt className={`text-xs font-semibold ${figure.tone}`}>{figure.label}</dt>
                    <dd className={`tabular-nums ${figure.tone}`}>
                      {formatRupees(admission.money[figure.key])}
                    </dd>
                  </div>
                ))}
              </dl>
            </li>
          ))}
        </ul>
      )}

      {cancelling ? (
        <CancelAdmissionDialog
          admission={cancelling}
          open
          onClose={() => setCancelling(null)}
          onCancelled={load}
        />
      ) : null}
    </div>
  );
}
