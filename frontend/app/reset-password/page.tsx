'use client';

import Link from 'next/link';
import { useSearchParams } from 'next/navigation';
import { Suspense, useState } from 'react';

import { AuthSplitShell } from '@/components/auth/auth-split-shell';
import { LoadingState } from '@/components/states';
import { Alert, AlertTitle } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import { Field } from '@/components/ui/field';
import { Input } from '@/components/ui/input';
import { fieldErrors } from '@/lib/api';
import { confirmPasswordReset } from '@/lib/auth';

function ResetPasswordForm() {
  const params = useSearchParams();
  const token = params.get('token') ?? '';
  const [newPassword, setNewPassword] = useState('');
  const [confirmation, setConfirmation] = useState('');
  const [done, setDone] = useState(false);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [isSubmitting, setIsSubmitting] = useState(false);

  async function onSubmit(event: React.FormEvent) {
    event.preventDefault();
    if (newPassword !== confirmation) {
      setErrors({ confirmation: 'The two passwords do not match.' });
      return;
    }
    setIsSubmitting(true);
    setErrors({});
    try {
      await confirmPasswordReset(token, newPassword);
      setDone(true);
    } catch (cause) {
      setErrors(fieldErrors(cause));
    } finally {
      setIsSubmitting(false);
    }
  }

  if (!token) {
    return (
      <Alert variant="error">
        <AlertTitle>This link is incomplete</AlertTitle>
        <p className="text-muted-foreground">
          Request a new password reset link and open it directly from your email.
        </p>
      </Alert>
    );
  }

  if (done) {
    return (
      <div className="space-y-4">
        <Alert variant="success">
          <AlertTitle>Password updated</AlertTitle>
          <p className="text-muted-foreground">
            You have been signed out everywhere. Sign in with your new password.
          </p>
        </Alert>
        <Button asChild className="w-full">
          <Link href="/login">Go to sign in</Link>
        </Button>
      </div>
    );
  }

  return (
    <form onSubmit={onSubmit} className="space-y-4" noValidate>
      {/* Expired, already-used and unknown tokens all arrive here with the same
          message: the API does not distinguish them. */}
      {errors.__all__ || errors.token ? (
        <Alert variant="error">{errors.token ?? errors.__all__}</Alert>
      ) : null}

      <Field
        label="New password"
        htmlFor="new-password"
        error={errors.new_password}
        hint="At least 12 characters, and not a common password."
        required
      >
        <Input
          type="password"
          autoComplete="new-password"
          value={newPassword}
          onChange={(event) => setNewPassword(event.target.value)}
        />
      </Field>

      <Field label="Confirm new password" htmlFor="confirmation" error={errors.confirmation} required>
        <Input
          type="password"
          autoComplete="new-password"
          value={confirmation}
          onChange={(event) => setConfirmation(event.target.value)}
        />
      </Field>

      <Button type="submit" disabled={isSubmitting} className="w-full">
        {isSubmitting ? 'Saving…' : 'Set new password'}
      </Button>
    </form>
  );
}

export default function ResetPasswordPage() {
  return (
    <AuthSplitShell heading="Choose a new password" tagline="Almost there — set a fresh password to continue.">
      <div className="mb-6 space-y-1.5">
        <h2 className="text-xl font-semibold tracking-tight">Choose a new password</h2>
        <p className="text-sm text-muted-foreground">This link can be used once.</p>
      </div>
      <Suspense fallback={<LoadingState label="Loading…" rows={3} />}>
        <ResetPasswordForm />
      </Suspense>
    </AuthSplitShell>
  );
}
