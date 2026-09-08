'use client';

import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useEffect, useState } from 'react';

import { AuthSplitShell } from '@/components/auth/auth-split-shell';
import { useAuth } from '@/components/auth-provider';
import { ErrorState } from '@/components/states';
import { Button } from '@/components/ui/button';
import { Field } from '@/components/ui/field';
import { Input } from '@/components/ui/input';
import { fieldErrors } from '@/lib/api';
import { login } from '@/lib/auth';

export default function LoginPage() {
  const router = useRouter();
  const { user, setUser } = useAuth();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [isSubmitting, setIsSubmitting] = useState(false);

  useEffect(() => {
    if (user) router.replace('/');
  }, [user, router]);

  async function onSubmit(event: React.FormEvent) {
    event.preventDefault();
    setIsSubmitting(true);
    setErrors({});
    try {
      const signedIn = await login(email, password);
      setUser(signedIn);
      router.replace('/');
    } catch (cause) {
      setErrors(fieldErrors(cause));
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <AuthSplitShell heading="Welcome back" tagline="Sign in to keep learning where you left off.">
      <div className="mb-6 space-y-1.5">
        <h2 className="text-xl font-semibold tracking-tight">Sign in</h2>
        <p className="text-sm text-muted-foreground">
          Use the email address your account was created with.
        </p>
      </div>
      <form onSubmit={onSubmit} className="space-y-4" noValidate>
        {errors.__all__ ? (
          // The server answers every failed sign-in identically, so this
          // never reveals whether the address exists.
          <ErrorState title="Could not sign in" message={errors.__all__} />
        ) : null}

        <Field label="Email" htmlFor="email" error={errors.email} required>
          <Input
            type="email"
            autoComplete="email"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
          />
        </Field>

        <Field label="Password" htmlFor="password" error={errors.password} required>
          <Input
            type="password"
            autoComplete="current-password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
          />
        </Field>

        <Button type="submit" disabled={isSubmitting} className="w-full">
          {isSubmitting ? 'Signing in…' : 'Sign in'}
        </Button>

        <p className="text-center text-sm text-muted-foreground">
          <Link href="/forgot-password" className="underline hover:text-foreground">
            Forgot your password?
          </Link>
        </p>
      </form>
    </AuthSplitShell>
  );
}
