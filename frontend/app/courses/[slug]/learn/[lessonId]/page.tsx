'use client';

import Link from 'next/link';
import { use, useEffect, useMemo, useState } from 'react';
import { ChevronLeft, ChevronRight } from 'lucide-react';

import { LessonBody } from '@/components/lesson-content';
import { RequireAuth } from '@/components/require-auth';
import { EmptyState, ErrorState, LoadingState } from '@/components/states';
import { Alert } from '@/components/ui/alert';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { ApiError } from '@/lib/api';
import { setLessonCompletion } from '@/lib/batches';
import { getCourse, getLesson } from '@/lib/courses';
import { CONTENT_TYPE_LABEL, formatDuration } from '@/lib/course-labels';
import { cn } from '@/lib/utils';
import type { CourseDetail, LessonContent, LessonSummary } from '@/types/api';

interface FlatLesson extends LessonSummary {
  moduleTitle: string;
}

/**
 * The course player.
 *
 * Marking a lesson complete lives here because this is where a student is when
 * they finish one. The API and its client have existed since progress was
 * built; the player was written before that and never caught up, which left the
 * odd situation of a system that counts completed lessons and no way for a
 * student to complete one.
 *
 * The control is a toggle rather than a one-way action: a student who marks the
 * wrong lesson should be able to say so, and reopening is a supported operation
 * on the same endpoint.
 */
/** Mark this lesson done, or reopen it. */
function LessonCompletion({ lessonId }: { lessonId: string }) {
  const [completed, setCompleted] = useState<boolean | null>(null);
  const [message, setMessage] = useState('');
  const [isBusy, setIsBusy] = useState(false);

  // Reset when the student moves to another lesson: the component is reused
  // across lessons, and carrying the previous one's state over would show the
  // wrong answer for a moment.
  const [seen, setSeen] = useState(lessonId);
  if (seen !== lessonId) {
    setSeen(lessonId);
    setCompleted(null);
    setMessage('');
  }

  async function onToggle(next: boolean) {
    setIsBusy(true);
    setMessage('');
    try {
      const progress = await setLessonCompletion(lessonId, next);
      setCompleted(progress.status === 'completed');
    } catch (cause) {
      setMessage(
        cause instanceof ApiError
          ? cause.message
          : 'Could not record that. Your progress is unchanged.',
      );
    } finally {
      setIsBusy(false);
    }
  }

  return (
    <div className="space-y-2 rounded-md border border-border p-4">
      {message ? <Alert variant="error">{message}</Alert> : null}
      {completed === true ? (
        <Alert variant="success" role="status" className="animate-rise-in">
          Marked complete.
        </Alert>
      ) : null}
      <Button
        type="button"
        variant={completed ? 'outline' : 'primary'}
        disabled={isBusy}
        onClick={() => void onToggle(!completed)}
        data-testid="lesson-completion"
      >
        {isBusy ? 'Saving…' : completed ? 'Mark as not complete' : 'Mark as complete'}
      </Button>
    </div>
  );
}

function Player({ slug, lessonId }: { slug: string; lessonId: string }) {
  const key = `${slug}#${lessonId}`;
  const [state, setState] = useState<{
    course: CourseDetail | null;
    lesson: LessonContent | null;
    error: ApiError | null;
    isLoading: boolean;
    key: string;
  }>({ course: null, lesson: null, error: null, isLoading: true, key });

  // Reset during render when the lesson changes — the documented alternative to
  // a synchronous setState inside the effect.
  if (state.key !== key) {
    setState({ course: null, lesson: null, error: null, isLoading: true, key });
  }

  useEffect(() => {
    let cancelled = false;

    Promise.all([getCourse(slug), getLesson(lessonId)])
      .then(([courseResult, lessonResult]) => {
        if (!cancelled) {
          setState({
            course: courseResult,
            lesson: lessonResult,
            error: null,
            isLoading: false,
            key,
          });
        }
      })
      .catch((cause: unknown) => {
        if (!cancelled) {
          setState({
            course: null,
            lesson: null,
            error: cause instanceof ApiError ? cause : null,
            isLoading: false,
            key,
          });
        }
      });

    return () => {
      cancelled = true;
    };
  }, [slug, lessonId, key]);

  const { course, lesson, error, isLoading } = state;

  const flat = useMemo<FlatLesson[]>(
    () =>
      (course?.modules ?? []).flatMap((module) =>
        module.lessons.map((item) => ({ ...item, moduleTitle: module.title })),
      ),
    [course],
  );

  const index = flat.findIndex((item) => item.id === lessonId);
  const previous = index > 0 ? flat[index - 1] : undefined;
  const next = index >= 0 && index < flat.length - 1 ? flat[index + 1] : undefined;

  if (isLoading) return <LoadingState label="Loading lesson…" rows={6} />;

  if (error) {
    if (error.status === 403) {
      // The outline stays visible; only the body is withheld.
      return (
        <EmptyState
          title="This lesson is not available to you"
          description={error.message}
          action={
            <Button asChild variant="outline">
              <Link href={`/courses/${slug}`}>Back to the course</Link>
            </Button>
          }
        />
      );
    }
    if (error.status === 404) {
      return (
        <EmptyState
          title="Lesson not found"
          description="This lesson does not exist, or it is not available to you."
          action={
            <Button asChild variant="outline">
              <Link href={`/courses/${slug}`}>Back to the course</Link>
            </Button>
          }
        />
      );
    }
    return (
      <ErrorState
        title="Could not load this lesson"
        message={error.message}
        requestId={error.requestId || undefined}
      />
    );
  }

  if (!course || !lesson) return null;

  return (
    <div className="animate-fade-in space-y-4">
      <div className="flex flex-wrap items-center gap-2 text-sm">
        <Link href={`/courses/${course.slug}`} className="text-muted-foreground hover:text-primary">
          {course.title}
        </Link>
        <span className="text-muted-foreground" aria-hidden="true">
          /
        </span>
        <span className="font-medium">{lesson.title}</span>
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-[minmax(0,1fr)_18rem]">
        <div className="min-w-0 space-y-6">
          <header className="animate-rise-in space-y-2">
            <h1 className="text-2xl font-semibold tracking-tight">{lesson.title}</h1>
            <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
              <Badge>{CONTENT_TYPE_LABEL[lesson.content_type]}</Badge>
              {lesson.duration_minutes ? (
                <span>{formatDuration(lesson.duration_minutes)}</span>
              ) : null}
              {lesson.is_preview ? <Badge variant="success">Free preview</Badge> : null}
              {!lesson.is_required ? <Badge>Optional</Badge> : null}
            </div>
          </header>

          <LessonBody lesson={lesson} />

          <LessonCompletion lessonId={lesson.id} />

          <nav
            aria-label="Lesson navigation"
            className="flex flex-wrap items-center justify-between gap-3 border-t border-border pt-4"
          >
            {previous ? (
              <Button asChild variant="outline">
                <Link href={`/courses/${course.slug}/learn/${previous.id}`}>
                  <ChevronLeft className="size-4" aria-hidden="true" />
                  <span className="max-w-[14rem] truncate">{previous.title}</span>
                </Link>
              </Button>
            ) : (
              <span />
            )}
            {next ? (
              <Button asChild>
                <Link href={`/courses/${course.slug}/learn/${next.id}`}>
                  <span className="max-w-[14rem] truncate">{next.title}</span>
                  <ChevronRight className="size-4" aria-hidden="true" />
                </Link>
              </Button>
            ) : null}
          </nav>
        </div>

        <aside className="lg:sticky lg:top-4 lg:self-start">
          <nav
            aria-label="Course outline"
            className="max-h-[70vh] overflow-y-auto rounded-[var(--radius-card)] border border-border"
          >
            {course.modules.map((module) => (
              <div key={module.id}>
                <p className="border-b border-border bg-muted/60 px-3 py-2 text-xs font-medium">
                  {module.title}
                </p>
                <ul>
                  {module.lessons.map((item) => {
                    const isCurrent = item.id === lessonId;
                    return (
                      <li key={item.id}>
                        <Link
                          href={`/courses/${course.slug}/learn/${item.id}`}
                          aria-current={isCurrent ? 'page' : undefined}
                          className={cn(
                            'block border-b border-border px-3 py-2 text-sm transition-colors last:border-b-0 hover:bg-muted',
                            isCurrent
                              ? 'bg-accent font-medium text-foreground'
                              : 'text-muted-foreground',
                          )}
                        >
                          {item.title}
                        </Link>
                      </li>
                    );
                  })}
                </ul>
              </div>
            ))}
          </nav>
        </aside>
      </div>
    </div>
  );
}

export default function LessonPage({
  params,
}: {
  params: Promise<{ slug: string; lessonId: string }>;
}) {
  const { slug, lessonId } = use(params);
  return (
    <RequireAuth>
      <Player slug={slug} lessonId={lessonId} />
    </RequireAuth>
  );
}
