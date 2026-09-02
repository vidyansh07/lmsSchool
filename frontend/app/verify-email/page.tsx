'use client';

import Link from 'next/link';
import { useSearchParams } from 'next/navigation';
import { Suspense, useEffect, useRef, useState } from 'react';

import { LoadingState } from '@/components/states';
import { Alert, AlertTitle } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { ApiError } from '@/lib/api';
import { confirmEmailVerification } from '@/lib/auth';

type State = 'verifying' | 'verified' | 'failed';

function VerifyEmail() {
  const params = useSearchParams();
  const token = params.get('token') ?? '';
  const [state, setState] = useState<State>('verifying');
  const [message, setMessage] = useState('');
  // Guards against React strict mode running the effect twice, which would
  // consume the single-use token and then report it as already used.
  const attempted = useRef(false);

  useEffect(() => {
    if (attempted.current) return;
    attempted.current = true;

    if (!token) {
      // Deferred to a microtask so no state is set synchronously in the effect.
      void Promise.resolve().then(() => {
        setState('failed');
        setMessage('This link is incomplete. Open the link directly from your email.');
      });
      return;
    }

    confirmEmailVerification(token)
      .then(() => setState('verified'))
      .catch((cause: unknown) => {
        setState('failed');
        setMessage(
          cause instanceof ApiError
            ? cause.message
            : 'This link is invalid or has expired. Request a new one from your account settings.',
        );
      });
  }, [token]);

  if (state === 'verifying') return <LoadingState label="Verifying your email address…" rows={2} />;

  return (
    <div className="space-y-4">
      <Alert variant={state === 'verified' ? 'success' : 'error'}>
        <AlertTitle>
          {state === 'verified' ? 'Email address verified' : 'Could not verify this link'}
        </AlertTitle>
        <p className="text-muted-foreground">
          {state === 'verified'
            ? 'Thank you. Your email address is confirmed.'
            : message}
        </p>
      </Alert>
      <Button asChild variant="outline" className="w-full">
        <Link href={state === 'verified' ? '/' : '/settings/account'}>
          {state === 'verified' ? 'Continue' : 'Go to account settings'}
        </Link>
      </Button>
    </div>
  );
}

export default function VerifyEmailPage() {
  return (
    <div className="mx-auto max-w-md">
      <Card>
        <CardHeader>
          <CardTitle>Email verification</CardTitle>
        </CardHeader>
        <CardContent>
          <Suspense fallback={<LoadingState label="Loading…" rows={2} />}>
            <VerifyEmail />
          </Suspense>
        </CardContent>
      </Card>
    </div>
  );
}
