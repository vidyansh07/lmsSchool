'use client';

import Link from 'next/link';
import { useEffect, useState } from 'react';

import { RequireAuth } from '@/components/require-auth';
import { EmptyState, ErrorState, LoadingState } from '@/components/states';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { ApiError } from '@/lib/api';
import {
  SESSION_STATUS_LABEL,
  SESSION_STATUS_VARIANT,
  formatTime,
} from '@/lib/academic-labels';
import { listTodaySessions } from '@/lib/academics';
import type { ClassSession } from '@/types/api';

/**
 * The trainer's home screen: today's classes, each one click from its register.
 *
 * Deliberately narrow. A trainer arriving after a lecture wants one thing, and
 * a dashboard that makes them hunt for it is a dashboard that ends with
 * attendance marked tomorrow, or not at all.
 */
function Teaching() {
  const [sessions, setSessions] = useState<ClassSession[]>([]);
  const [error, setError] = useState<ApiError | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    listTodaySessions()
      .then((rows) => {
        if (!cancelled) setSessions(rows);
      })
      .catch((cause: unknown) => {
        if (!cancelled) setError(cause instanceof ApiError ? cause : null);
      })
      .finally(() => {
        if (!cancelled) setIsLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  if (isLoading) return <LoadingState label="Loading today's classes…" rows={3} />;
  if (error) {
    return (
      <ErrorState
        title="Could not load today's classes"
        message={error.message}
        requestId={error.requestId || undefined}
      />
    );
  }

  return (
    <div className="space-y-6">
      <div className="space-y-1">
        <h1 className="text-2xl font-semibold tracking-tight">Teaching today</h1>
        <p className="text-sm text-muted-foreground">
          Your classes for today. Open a class to take its register.
        </p>
      </div>

      <div className="flex flex-wrap gap-2">
        <Button asChild variant="outline" size="sm">
          <Link href="/teaching/assignments">Assignments</Link>
        </Button>
        <Button asChild variant="outline" size="sm">
          <Link href="/teaching/assessments">Weekly tests</Link>
        </Button>
        <Button asChild variant="outline" size="sm">
          <Link href="/teaching/projects">Projects</Link>
        </Button>
        <Button asChild variant="outline" size="sm">
          <Link href="/teaching/exams">Examinations</Link>
        </Button>
      </div>

      {sessions.length === 0 ? (
        <EmptyState
          title="No classes today"
          description="Nothing is scheduled for today on the batches you teach."
        />
      ) : (
        <div className="space-y-4">
          {sessions.map((session) => (
            <Card key={session.id} data-testid="today-class">
              <CardHeader className="gap-2">
                <div className="flex flex-wrap items-center gap-2">
                  <Badge variant={SESSION_STATUS_VARIANT[session.status]}>
                    {SESSION_STATUS_LABEL[session.status]}
                  </Badge>
                  {session.attendance_taken_at ? (
                    <Badge variant="success">Register taken</Badge>
                  ) : null}
                  <span className="font-mono text-xs text-muted-foreground">
                    {session.batch_code}
                  </span>
                </div>
                <CardTitle>{session.topic || session.course_title}</CardTitle>
                <CardDescription>
                  {formatTime(session.start_time)} – {formatTime(session.end_time)}
                  {session.location ? ` · ${session.location}` : ''} · {session.batch_name}
                </CardDescription>
              </CardHeader>
              <CardContent>
                <Button asChild size="sm" disabled={!session.can_take_attendance}>
                  <Link href={`/teaching/sessions/${session.id}`}>
                    {session.attendance_taken_at ? 'Review register' : 'Take register'}
                  </Link>
                </Button>
                {!session.can_take_attendance ? (
                  <p className="mt-2 text-sm text-muted-foreground">
                    The register opens once the class has started.
                  </p>
                ) : null}
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}

export default function TeachingPage() {
  return (
    <RequireAuth>
      <Teaching />
    </RequireAuth>
  );
}
