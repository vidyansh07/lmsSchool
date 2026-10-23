'use client';

/**
 * One admission's money (`/students/{id}/admissions/{admissionId}/payment`).
 *
 * Behind `fee.view_any` rather than the admission's own right: this screen is
 * about receipts and balances, and somebody who may read an admission but not
 * its money should not meet a page of figures with the numbers taken out.
 */

import { use } from 'react';

import { useAuth } from '@/components/auth-provider';
import { PaymentDetails } from '@/components/admissions/payment-details';
import { RequireAuth } from '@/components/require-auth';
import { Capability } from '@/lib/capabilities';

function Screen({ studentId, admissionId }: { studentId: string; admissionId: string }) {
  const { can } = useAuth();
  return (
    <PaymentDetails
      studentId={studentId}
      admissionId={admissionId}
      canManage={can(Capability.feeManageAny)}
    />
  );
}

export default function AdmissionPaymentPage({
  params,
}: {
  params: Promise<{ id: string; admissionId: string }>;
}) {
  const { id, admissionId } = use(params);
  return (
    <RequireAuth capability={Capability.feeViewAny}>
      <Screen studentId={id} admissionId={admissionId} />
    </RequireAuth>
  );
}
