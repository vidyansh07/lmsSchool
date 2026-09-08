'use client';

import Link from 'next/link';
import { useState } from 'react';

import { AuthSplitShell } from '@/components/auth/auth-split-shell';
import { Alert, AlertTitle } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import { Field } from '@/components/ui/field';
import { Input } from '@/components/ui/input';
import { fieldErrors } from '@/lib/api';
import { requestPasswordReset } from '@/lib/auth';

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState('');
  const [submitted, setSubmitted] = useState(false);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [isSubmitting, setIsSubmitting] = useState(false);

  async function onSubmit(event: React.FormEvent) {
    event.preventDefault();
    setIsSubmitting(true);
    setErrors({});
    try {
      await requestPasswordReset(email);
      setSubmitted(true);
    } catch (cause) {
      setErrors(fieldErrors(cause));
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <AuthSplitShell heading="Forgot your password?" tagline="No problem — we'll get you back in.">
      <div className="mb-6 space-y-1.5">
        <h2 className="text-xl font-semibold tracking-tight">Reset your password</h2>
        <p className="text-sm text-muted-foreground">
          Enter your email address and we will send a link to set a new password.
        </p>
      </div>
      <div className="space-y-4">
        {submitted ? (
          <>
            {/* Worded so it reveals nothing about whether the address exists —
                the API answers identically either way. */}
            <Alert variant="success">
              <AlertTitle>Check your inbox</AlertTitle>
              <p className="text-muted-foreground">
                If an account exists for that address, a password reset link has been sent. The
                link can be used once and expires shortly.
              </p>
            </Alert>
            <Button asChild variant="outline" className="w-full">
              <Link href="/login">Back to sign in</Link>
            </Button>
          </>
        ) : (
          <form onSubmit={onSubmit} className="space-y-4" noValidate>
            {errors.__all__ ? <Alert variant="error">{errors.__all__}</Alert> : null}
            <Field label="Email" htmlFor="email" error={errors.email} required>
              <Input
                type="email"
                autoComplete="email"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
              />
            </Field>
            <Button type="submit" disabled={isSubmitting} className="w-full">
              {isSubmitting ? 'Sending…' : 'Send reset link'}
            </Button>
            <p className="text-center text-sm text-muted-foreground">
              <Link href="/login" className="underline hover:text-foreground">
                Back to sign in
              </Link>
            </p>
          </form>
        )}
      </div>
    </AuthSplitShell>
  );
}
