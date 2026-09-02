'use client';

import Link from 'next/link';
import { Activity, GraduationCap, KeyRound, ShieldCheck, UserCog, Users } from 'lucide-react';

import { useAuth } from '@/components/auth-provider';
import { LoadingState } from '@/components/states';
import { Alert, AlertTitle } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Capability } from '@/lib/capabilities';

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
  const { user, isLoading, can } = useAuth();

  if (isLoading) return <LoadingState label="Loading…" rows={4} />;

  if (!user) {
    return (
      <div className="space-y-8">
        <section className="space-y-4">
          <h1 className="text-3xl font-semibold tracking-tight">Grras LMS</h1>
          <p className="max-w-prose text-muted-foreground">
            Identity and people management for students, trainers and administrators. Sign in to
            continue.
          </p>
          <Button asChild>
            <Link href="/login">Sign in</Link>
          </Button>
        </section>

        <section className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {foundations.map(({ icon: Icon, title, description }) => (
            <Card key={title}>
              <CardHeader>
                <Icon className="size-5 text-primary" aria-hidden="true" />
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

  return (
    <div className="space-y-6">
      <div className="space-y-1">
        <h1 className="text-2xl font-semibold tracking-tight">
          Welcome back, {user.first_name || user.email}
        </h1>
        <p className="text-sm text-muted-foreground">
          Signed in as {user.role}. Learning features arrive in a later phase.
        </p>
      </div>

      {!user.is_email_verified ? (
        <Alert variant="warning" className="space-y-2">
          <AlertTitle>Your email address is not verified</AlertTitle>
          <p className="text-muted-foreground">
            Verify it so password resets and notifications reach you.
          </p>
          <Button asChild size="sm" variant="outline">
            <Link href="/settings/account">Verify email</Link>
          </Button>
        </Alert>
      ) : null}

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {user.role !== 'admin' ? (
          <Card>
            <CardHeader>
              <GraduationCap className="size-5 text-primary" aria-hidden="true" />
              <CardTitle>My dashboard</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <CardDescription>
                Your courses, classes and progress in one place.
              </CardDescription>
              <Button asChild variant="outline" size="sm">
                <Link href="/dashboard">Open dashboard</Link>
              </Button>
            </CardContent>
          </Card>
        ) : null}

        <Card>
          <CardHeader>
            <UserCog className="size-5 text-primary" aria-hidden="true" />
            <CardTitle>My profile</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <CardDescription>
              Keep your contact details and profile information up to date.
            </CardDescription>
            <Button asChild variant="outline" size="sm">
              <Link href="/profile">Open profile</Link>
            </Button>
          </CardContent>
        </Card>

        {can(Capability.userViewAny) ? (
          <Card>
            <CardHeader>
              <Users className="size-5 text-primary" aria-hidden="true" />
              <CardTitle>People management</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <CardDescription>
                Manage accounts, students and trainers across the platform.
              </CardDescription>
              <div className="flex flex-wrap gap-2">
                <Button asChild variant="outline" size="sm">
                  <Link href="/admin/users">Users</Link>
                </Button>
                <Button asChild variant="outline" size="sm">
                  <Link href="/admin/students">Students</Link>
                </Button>
                <Button asChild variant="outline" size="sm">
                  <Link href="/admin/trainers">Trainers</Link>
                </Button>
                <Button asChild variant="outline" size="sm">
                  <Link href="/admin/batches">Batches</Link>
                </Button>
              </div>
            </CardContent>
          </Card>
        ) : null}

        <Card>
          <CardHeader>
            <KeyRound className="size-5 text-primary" aria-hidden="true" />
            <CardTitle>Security</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <CardDescription>
              Change your password or sign out of every device.
            </CardDescription>
            <Button asChild variant="outline" size="sm">
              <Link href="/settings/security">Security settings</Link>
            </Button>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
