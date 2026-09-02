'use client';

import Link from 'next/link';
import { useEffect, useState } from 'react';
import { BookOpen, CalendarClock, GraduationCap, PlayCircle, Users } from 'lucide-react';

import { useAuth } from '@/components/auth-provider';
import { ProgressBar } from '@/components/progress-bar';
import { RequireAuth } from '@/components/require-auth';
import { EmptyState, ErrorState, LoadingState } from '@/components/states';
import { Alert } from '@/components/ui/alert';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { ApiError } from '@/lib/api';
import { getStudentDashboard, getTrainerDashboard } from '@/lib/batches';
import {
  BATCH_STATUS_LABEL,
  BATCH_STATUS_VARIANT,
  ENROLLMENT_STATUS_LABEL,
  ENROLLMENT_STATUS_VARIANT,
  formatDate,
  formatEventDay,
  formatEventTime,
} from '@/lib/batch-labels';
import type { CalendarEvent, StudentDashboard, TrainerDashboard } from '@/types/api';

function ClassList({ events, empty }: { events: CalendarEvent[]; empty: string }) {
  if (events.length === 0) return <p className="text-sm text-muted-foreground">{empty}</p>;
  return (
    <ul className="divide-y divide-border">
      {events.map((event, index) => (
        <li key={`${event.start}-${index}`} className="flex flex-wrap items-center gap-3 py-2 text-sm">
          <span className="w-24 shrink-0 text-muted-foreground">
            {formatEventDay(event.start)}
          </span>
          {!event.all_day ? (
            <span className="w-16 shrink-0 text-muted-foreground">
              {formatEventTime(event.start)}
            </span>
          ) : null}
          <span className="min-w-0 flex-1 truncate">{event.title}</span>
          {event.location ? (
            <span className="text-xs text-muted-foreground">{event.location}</span>
          ) : null}
        </li>
      ))}
    </ul>
  );
}

function StudentView({ data }: { data: StudentDashboard }) {
  return (
    <div className="space-y-6">
      {data.continue_learning?.last_lesson_id ? (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <PlayCircle className="size-5 text-primary" aria-hidden="true" />
              Continue learning
            </CardTitle>
            <CardDescription>{data.continue_learning.course_title}</CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            <p className="text-sm font-medium">{data.continue_learning.last_lesson_title}</p>
            <ProgressBar
              percent={data.continue_learning.progress_percent}
              label={`${data.continue_learning.completed_lessons} of ${data.continue_learning.total_lessons} lessons complete`}
            />
            <Button asChild size="sm">
              <Link
                href={`/courses/${data.continue_learning.course_slug}/learn/${data.continue_learning.last_lesson_id}`}
              >
                Resume
              </Link>
            </Button>
          </CardContent>
        </Card>
      ) : null}

      <div className="grid gap-6 lg:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]">
        <section className="space-y-3">
          <h2 className="text-lg font-semibold tracking-tight">My courses</h2>
          {data.courses.length === 0 ? (
            <EmptyState
              title="No active courses"
              description="You are not currently enrolled on a course. Browse the catalogue to see what is available."
              action={
                <Button asChild variant="outline">
                  <Link href="/courses">Browse courses</Link>
                </Button>
              }
            />
          ) : (
            <div className="grid gap-4 sm:grid-cols-2">
              {data.courses.map((course) => (
                <Card key={course.enrollment_id}>
                  <CardHeader className="gap-1">
                    <CardTitle>
                      <Link
                        href={`/courses/${course.course_slug}`}
                        className="hover:text-primary"
                      >
                        {course.course_title}
                      </Link>
                    </CardTitle>
                    <CardDescription className="font-mono text-xs">
                      {course.batch_code} · {course.batch_name}
                    </CardDescription>
                  </CardHeader>
                  <CardContent className="space-y-3">
                    <ProgressBar
                      percent={course.progress_percent}
                      label={`${course.completed_lessons} of ${course.total_lessons} lessons`}
                    />
                    {course.last_lesson_id ? (
                      <Button asChild variant="outline" size="sm">
                        <Link
                          href={`/courses/${course.course_slug}/learn/${course.last_lesson_id}`}
                        >
                          Continue
                        </Link>
                      </Button>
                    ) : (
                      <Button asChild variant="outline" size="sm">
                        <Link href={`/courses/${course.course_slug}`}>Open course</Link>
                      </Button>
                    )}
                  </CardContent>
                </Card>
              ))}
            </div>
          )}
        </section>

        <aside className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <CalendarClock className="size-5 text-primary" aria-hidden="true" />
                Upcoming classes
              </CardTitle>
            </CardHeader>
            <CardContent>
              <ClassList events={data.upcoming_classes} empty="Nothing in the next week." />
              <Button asChild variant="ghost" size="sm" className="mt-2">
                <Link href="/calendar">Open the calendar</Link>
              </Button>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <GraduationCap className="size-5 text-primary" aria-hidden="true" />
                My batches
              </CardTitle>
            </CardHeader>
            <CardContent>
              {data.batches.length === 0 ? (
                <p className="text-sm text-muted-foreground">No batches yet.</p>
              ) : (
                <ul className="divide-y divide-border text-sm">
                  {data.batches.map((batch) => (
                    <li key={batch.id} className="flex flex-wrap items-center gap-2 py-2">
                      <span className="min-w-0 flex-1 truncate">{batch.name}</span>
                      {batch.enrollment_status ? (
                        <Badge variant={ENROLLMENT_STATUS_VARIANT[batch.enrollment_status]}>
                          {ENROLLMENT_STATUS_LABEL[batch.enrollment_status]}
                        </Badge>
                      ) : null}
                    </li>
                  ))}
                </ul>
              )}
              <Button asChild variant="ghost" size="sm" className="mt-2">
                <Link href="/my-batches">All my batches</Link>
              </Button>
            </CardContent>
          </Card>

          {/* Placeholder, as the brief asks. The shape is fixed now so the
              notifications feature fills it rather than redesigning the page. */}
          <Card>
            <CardHeader>
              <CardTitle>Notifications</CardTitle>
            </CardHeader>
            <CardContent>
              <p className="text-sm text-muted-foreground">
                Nothing to show. Notifications arrive in a later phase.
              </p>
            </CardContent>
          </Card>
        </aside>
      </div>
    </div>
  );
}

function TrainerView({ data }: { data: TrainerDashboard }) {
  return (
    <div className="space-y-6">
      <div className="grid gap-4 sm:grid-cols-3">
        <Card>
          <CardHeader className="gap-1">
            <CardDescription>Assigned batches</CardDescription>
            <CardTitle className="text-2xl">{data.batches.length}</CardTitle>
          </CardHeader>
        </Card>
        <Card>
          <CardHeader className="gap-1">
            <CardDescription>Students</CardDescription>
            <CardTitle className="text-2xl">{data.student_count}</CardTitle>
          </CardHeader>
        </Card>
        <Card>
          <CardHeader className="gap-1">
            <CardDescription>Courses taught</CardDescription>
            <CardTitle className="text-2xl">{data.courses.length}</CardTitle>
          </CardHeader>
        </Card>
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <CalendarClock className="size-5 text-primary" aria-hidden="true" />
              Today
            </CardTitle>
          </CardHeader>
          <CardContent>
            <ClassList events={data.today_classes} empty="No classes today." />
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>This week</CardTitle>
          </CardHeader>
          <CardContent>
            <ClassList events={data.upcoming_classes} empty="Nothing in the next week." />
          </CardContent>
        </Card>
      </div>

      <section className="space-y-3">
        <h2 className="flex items-center gap-2 text-lg font-semibold tracking-tight">
          <Users className="size-5 text-primary" aria-hidden="true" />
          My batches
        </h2>
        {data.batches.length === 0 ? (
          <EmptyState
            title="No batches assigned"
            description="An administrator assigns the batches you teach."
          />
        ) : (
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {data.batches.map((batch) => (
              <Card key={batch.id}>
                <CardHeader className="gap-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <Badge variant={BATCH_STATUS_VARIANT[batch.status]}>
                      {BATCH_STATUS_LABEL[batch.status]}
                    </Badge>
                    <span className="font-mono text-xs text-muted-foreground">{batch.code}</span>
                  </div>
                  <CardTitle>
                    <Link href={`/admin/batches/${batch.id}`} className="hover:text-primary">
                      {batch.name}
                    </Link>
                  </CardTitle>
                  <CardDescription>{batch.course_title}</CardDescription>
                </CardHeader>
                <CardContent className="space-y-1 text-sm text-muted-foreground">
                  <p>
                    {formatDate(batch.start_date)} – {formatDate(batch.end_date)}
                  </p>
                  <p>
                    {batch.enrolled_count ?? 0} of {batch.capacity ?? 0} seats taken
                  </p>
                </CardContent>
              </Card>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}

function Dashboard() {
  const { user } = useAuth();
  const isTrainer = user?.role === 'trainer';

  const [student, setStudent] = useState<StudentDashboard | null>(null);
  const [trainer, setTrainer] = useState<TrainerDashboard | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    const load = isTrainer ? getTrainerDashboard() : getStudentDashboard();

    load
      .then((result) => {
        if (cancelled) return;
        if (isTrainer) setTrainer(result as TrainerDashboard);
        else setStudent(result as StudentDashboard);
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
  }, [isTrainer]);

  if (isLoading) return <LoadingState label="Loading your dashboard…" rows={6} />;
  if (error) {
    return (
      <ErrorState
        title="Could not load your dashboard"
        message={error.message}
        requestId={error.requestId || undefined}
      />
    );
  }

  return (
    <div className="space-y-6">
      <div className="space-y-1">
        <h1 className="text-2xl font-semibold tracking-tight">
          Welcome back, {user?.first_name || user?.email}
        </h1>
        <p className="text-sm text-muted-foreground">
          {isTrainer ? 'Your batches, classes and students.' : 'Your courses, classes and progress.'}
        </p>
      </div>

      {isTrainer && trainer ? (
        trainer.is_trainer ? (
          <TrainerView data={trainer} />
        ) : (
          <Alert variant="info">Your trainer profile is not set up yet.</Alert>
        )
      ) : null}

      {!isTrainer && student ? (
        student.is_student ? (
          <StudentView data={student} />
        ) : (
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <BookOpen className="size-5 text-primary" aria-hidden="true" />
                Nothing to show here
              </CardTitle>
              <CardDescription>
                This dashboard is for students. Administrators manage the platform from the
                sections in the navigation.
              </CardDescription>
            </CardHeader>
            <CardContent>
              <Button asChild variant="outline">
                <Link href="/admin/batches">Go to batches</Link>
              </Button>
            </CardContent>
          </Card>
        )
      ) : null}
    </div>
  );
}

export default function DashboardPage() {
  return (
    <RequireAuth>
      <Dashboard />
    </RequireAuth>
  );
}
