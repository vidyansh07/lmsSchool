"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { AuthSplitShell } from "@/components/auth/auth-split-shell";
import { MfaVerifyForm } from "@/components/auth/mfa-verify-form";
import { useAuth } from "@/components/auth-provider";
import { ErrorState } from "@/components/states";
import { Button } from "@/components/ui/button";
import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { fieldErrors } from "@/lib/api";
import { login } from "@/lib/auth";
import type { CurrentUser, MfaMethodName } from "@/types/api";

export default function LoginPage() {
  const router = useRouter();
  const { user, setUser } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [isSubmitting, setIsSubmitting] = useState(false);
  // Set once `POST /auth/login/` answers `{mfa_required: true}` (ADR-05):
  // the credentials form gives way to the MFA-verify step rather than
  // navigating anywhere, since the session is only pending, not signed in.
  const [mfaMethods, setMfaMethods] = useState<MfaMethodName[] | null>(null);

  useEffect(() => {
    if (user) router.replace("/");
  }, [user, router]);

  function finishSignIn(signedIn: CurrentUser) {
    setUser(signedIn);
    router.replace("/");
  }

  async function onSubmit(event: React.FormEvent) {
    event.preventDefault();
    setIsSubmitting(true);
    setErrors({});
    try {
      const result = await login(email, password);
      if ("mfa_required" in result) {
        setMfaMethods(result.methods);
      } else {
        finishSignIn(result);
      }
    } catch (cause) {
      setErrors(fieldErrors(cause));
    } finally {
      setIsSubmitting(false);
    }
  }

  if (mfaMethods) {
    return (
      <AuthSplitShell
        heading="Welcome back"
        tagline="Sign in to keep learning where you left off."
      >
        <MfaVerifyForm
          methods={mfaMethods}
          onVerified={finishSignIn}
          onBack={() => {
            setMfaMethods(null);
            setPassword("");
          }}
        />
      </AuthSplitShell>
    );
  }

  return (
    <AuthSplitShell
      heading="Welcome back"
      tagline="Sign in to keep learning where you left off."
    >
      <div className="mb-6 space-y-1.5">
        <h2 className="text-xl font-semibold tracking-tight">Sign in</h2>
        <p className="text-sm text-ink-muted">
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

        <Field
          label="Password"
          htmlFor="password"
          error={errors.password}
          required
        >
          <Input
            type="password"
            autoComplete="current-password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
          />
        </Field>

        <Button type="submit" disabled={isSubmitting} className="w-full">
          {isSubmitting ? "Signing in…" : "Sign in"}
        </Button>

        <p className="text-center text-sm text-ink-muted">
          <Link
            href="/forgot-password"
            className="underline hover:text-ink"
          >
            Forgot your password?
          </Link>
        </p>
      </form>
    </AuthSplitShell>
  );
}
