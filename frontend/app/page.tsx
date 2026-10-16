'use client';

import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useEffect } from 'react';
import { Activity, KeyRound, ShieldCheck } from 'lucide-react';

import { useAuth } from '@/components/auth-provider';
import { LoadingState } from '@/components/states';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { workspaceHomeForUser } from '@/lib/workspace';

const foundations = [
  {
    icon: ShieldCheck,
    title: 'Server-side authorization',
    description:
      'Roles map to capabilities in one table, and every endpoint re-checks them. The interface never decides access.',
  },
  {
    icon: KeyRound,
    title: 'Session authentication',
    description:
      'HttpOnly, SameSite session cookies with CSRF protection, password reset, email verification and sign-out everywhere.',
  },
  {
    icon: Activity,
    title: 'Audited by default',
    description:
      'Sign-ins, password changes, role changes and profile edits are recorded in an append-only audit trail.',
  },
];

export default function HomePage() {
  const { user, isLoading } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (user) router.replace(workspaceHomeForUser(user));
  }, [router, user]);

  if (isLoading) return <LoadingState label="Loading…" rows={4} />;

  if (user) return <LoadingState label="Opening your workspace…" rows={4} />;

  return (
    <div className="space-y-8">
      <section className="space-y-4">
        <h1 className="text-3xl font-semibold tracking-tight">Grras LMS</h1>
        <p className="max-w-prose text-ink-muted">
          Run admissions, teaching, fees, student progress and communication from one role-aware
          workspace.
        </p>
        <Button asChild>
          <Link href="/login">Sign in</Link>
        </Button>
      </section>

      <section className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        <h2 className="sr-only">What this platform provides</h2>
        {foundations.map(({ icon: Icon, title, description }) => (
          <Card key={title}>
            <CardHeader>
              <Icon className="size-5 text-action" aria-hidden="true" />
              <CardTitle>{title}</CardTitle>
            </CardHeader>
            <CardContent>
              <CardDescription>{description}</CardDescription>
            </CardContent>
          </Card>
        ))}
      </section>
    </div>
  );
}
