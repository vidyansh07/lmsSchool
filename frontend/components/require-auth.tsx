'use client';

/**
 * Client-side gate for authenticated pages.
 *
 * This is a *navigation* aid: it avoids rendering a page that would only show
 * permission errors, and sends a signed-out visitor to the login form. It is
 * not a security control. Every protected resource is checked again by the
 * backend, so bypassing this component gains an attacker nothing but an empty
 * screen.
 */

import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useEffect, type ReactNode } from 'react';

import { useAuth } from '@/components/auth-provider';
import { EmptyState, LoadingState } from '@/components/states';
import { Button } from '@/components/ui/button';
import type { CapabilityName } from '@/lib/capabilities';

export function RequireAuth({
  children,
  capability,
}: {
  children: ReactNode;
  capability?: CapabilityName;
}) {
  const { user, isLoading, can } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (!isLoading && !user) router.replace('/login');
  }, [isLoading, user, router]);

  if (isLoading) return <LoadingState label="Checking your session…" rows={4} />;
  if (!user) return <LoadingState label="Redirecting to sign in…" rows={2} />;

  if (capability && !can(capability)) {
    return (
      <EmptyState
        title="You do not have access to this page"
        description="Your role does not permit this area. If you believe this is wrong, contact an administrator."
        action={
          <Button asChild variant="outline">
            <Link href="/">Back to overview</Link>
          </Button>
        }
      />
    );
  }

  return <>{children}</>;
}
