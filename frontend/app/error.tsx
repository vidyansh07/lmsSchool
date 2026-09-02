'use client';

import { useEffect } from 'react';

import { ErrorState } from '@/components/states';

/**
 * Route-level error boundary.
 *
 * `error.message` is deliberately not rendered: in production it may contain
 * internal detail. The digest is a server-side correlation id and is safe.
 */
export default function RouteError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error('Route error', error.digest ?? error.name);
  }, [error]);

  return (
    <ErrorState
      title="This page could not be displayed"
      message="An unexpected error occurred. Try again, and contact support if it keeps happening."
      requestId={error.digest}
      onRetry={reset}
    />
  );
}
