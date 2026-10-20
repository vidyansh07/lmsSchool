'use client';

/**
 * Where a class-report notification's "Open" lands (`/dsr/<id>`, written by
 * `apps/dsr/services.py` when a report is turned back). A reviewer reads it
 * in the sheet on `/dsr`; the trainer who wrote it corrects it on the class
 * itself, `/teaching/today?session=<class>`, which is the only place a report
 * is edited. Which one is decided by what the reader may do, then forwarded.
 */

import { useRouter } from 'next/navigation';
import { use, useEffect, useState } from 'react';

import { useAuth } from '@/components/auth-provider';
import { RequireAuth } from '@/components/require-auth';
import { ErrorState, LoadingState } from '@/components/states';
import { ApiError } from '@/lib/api';
import { Capability } from '@/lib/capabilities';
import { getDsr } from '@/lib/dsr';

export function DsrLinkForward({ dsrId }: { dsrId: string }) {
  const router = useRouter();
  const { user, can } = useAuth();
  const [error, setError] = useState<ApiError | null>(null);
  const reviewer = can(Capability.dsrViewAny);

  useEffect(() => {
    if (!user) return;
    if (reviewer) {
      router.replace(`/dsr?report=${encodeURIComponent(dsrId)}`);
      return;
    }
    let cancelled = false;
    getDsr(dsrId)
      .then((report) => {
        if (!cancelled) router.replace(`/teaching/today?session=${encodeURIComponent(report.session)}`);
      })
      .catch((cause: unknown) => {
        if (!cancelled) {
          setError(
            cause instanceof ApiError
              ? cause
              : new ApiError(0, 'error', 'Could not open this class report.', ''),
          );
        }
      });
    return () => {
      cancelled = true;
    };
  }, [user, reviewer, router, dsrId]);

  if (error) {
    return (
      <ErrorState
        title={error.status === 404 ? 'This class report is no longer available' : 'Could not open this class report'}
        message={error.status === 404 ? 'It may have been deleted, or it belongs to a class you no longer teach.' : error.message}
        requestId={error.requestId || undefined}
      />
    );
  }
  return <LoadingState label="Opening the class report…" rows={3} />;
}

export default function DsrLinkPage({ params }: { params: Promise<{ dsrId: string }> }) {
  const { dsrId } = use(params);
  return (
    <RequireAuth>
      <DsrLinkForward dsrId={dsrId} />
    </RequireAuth>
  );
}
