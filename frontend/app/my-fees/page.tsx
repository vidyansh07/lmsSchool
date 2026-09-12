'use client';

/**
 * A student's own fees: what was agreed for each course, what they have
 * paid (with receipt numbers), and what is still owed. Read-only — the
 * counsellor's desk is where money changes hands.
 */

import { FeeLedger, useStudentFees } from '@/components/fees/fee-ledger';
import { RequireAuth } from '@/components/require-auth';
import { getMyFees } from '@/lib/fees';

function MyFees() {
  const fees = useStudentFees(getMyFees, []);
  return (
    <div className="space-y-4">
      <div className="space-y-1">
        <h1 className="text-2xl font-semibold tracking-tight">My fees</h1>
        <p className="text-sm text-muted-foreground">
          Every payment has a receipt number. Questions about a figure go to the admissions desk.
        </p>
      </div>
      <FeeLedger
        summary={fees.summary}
        enrollments={[]}
        mayManage={false}
        isLoading={fees.isLoading}
        error={fees.error}
        onChanged={fees.reload}
        title="Fees by course"
        description="What was agreed, what you have paid, and what is still to come."
      />
    </div>
  );
}

export default function MyFeesPage() {
  return (
    <RequireAuth>
      <MyFees />
    </RequireAuth>
  );
}
