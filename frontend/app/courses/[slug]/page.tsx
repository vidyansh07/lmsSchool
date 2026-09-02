'use client';

import Link from 'next/link';
import { use, useEffect, useState } from 'react';
import { BookOpen, CheckCircle2, Clock, FileText, Layers, Link2, PlayCircle } from 'lucide-react';

import { RequireAuth } from '@/components/require-auth';
import { EmptyState, ErrorState, LoadingState } from '@/components/states';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { ApiError } from '@/lib/api';
import { getCourse } from '@/lib/courses';
import {
  CONTENT_TYPE_LABEL,
  DIFFICULTY_LABEL,
  STATUS_LABEL,
  STATUS_VARIANT,
  formatDuration,
} from '@/lib/course-labels';
import type { CourseDetail, LessonContentType, LessonSummary } from '@/types/api';

const CONTENT_ICON: Record<LessonContentType, typeof FileText> = {
  text: FileText,
  video: PlayCircle,
  document: FileText,
  external_link: Link2,
};

function LessonRow({ lesson, courseSlug }: { lesson: LessonSummary; courseSlug: string }) {
  const Icon = CONTENT_ICON[lesson.content_type];
  return (
    <li className="flex flex-wrap items-center gap-3 border-b border-border px-4 py-2.5 last:border-b-0">
      <Icon className="size-4 shrink-0 text-muted-foreground" aria-hidden="true" />
      <Link
        href={`/courses/${courseSlug}/learn/${lesson.id}`}
        className="min-w-0 flex-1 text-sm hover:text-primary"
      >
        {lesson.title}
      </Link>
      {lesson.is_preview ? <Badge variant="success">Free preview</Badge> : null}
      {!lesson.is_required ? <Badge>Optional</Badge> : null}
      {lesson.status !== 'published' ? (
        <Badge variant={STATUS_VARIANT[lesson.status]}>{STATUS_LABEL[lesson.status]}</Badge>
      ) : null}
      <span className="text-xs text-muted-foreground">
        {CONTENT_TYPE_LABEL[lesson.content_type]}
        {lesson.duration_minutes ? ` · ${formatDuration(lesson.duration_minutes)}` : ''}
      </span>
    </li>
  );
}

function CourseDetailContent({ slug }: { slug: string }) {
  const [course, setCourse] = useState<CourseDetail | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    getCourse(slug)
      .then((result) => {
        if (!cancelled) setCourse(result);
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
  }, [slug]);

  if (isLoading) return <LoadingState label="Loading course…" rows={6} />;

  if (error) {
    // A course the caller may not see returns 404, exactly as one that does not
    // exist — so the message is the same either way.
    if (error.status === 404) {
      return (
        <EmptyState
          title="Course not found"
          description="This course does not exist, or it is not available to you."
          action={
            <Button asChild variant="outline">
              <Link href="/courses">Back to the catalogue</Link>
            </Button>
          }
        />
      );
    }
    return (
      <ErrorState
        title="Could not load this course"
        message={error.message}
        requestId={error.requestId || undefined}
      />
    );
  }

  if (!course) return null;

  const firstLesson = course.modules.flatMap((module) => module.lessons)[0];

  return (
    <div className="space-y-8">
      <header className="space-y-4">
        <div className="flex flex-wrap items-center gap-2">
          <Badge>{course.category_name}</Badge>
          <Badge>{DIFFICULTY_LABEL[course.difficulty]}</Badge>
          {course.status !== 'published' ? (
            <Badge variant={STATUS_VARIANT[course.status]}>{STATUS_LABEL[course.status]}</Badge>
          ) : null}
          <span className="font-mono text-xs text-muted-foreground">{course.code}</span>
        </div>

        <div className="space-y-2">
          <h1 className="text-3xl font-semibold tracking-tight">{course.title}</h1>
          <p className="max-w-prose text-muted-foreground">{course.short_description}</p>
        </div>

        <dl className="flex flex-wrap gap-6 text-sm text-muted-foreground">
          <div className="flex items-center gap-2">
            <Clock className="size-4" aria-hidden="true" />
            <dt className="sr-only">Duration</dt>
            <dd>{formatDuration(course.estimated_duration_minutes)}</dd>
          </div>
          <div className="flex items-center gap-2">
            <Layers className="size-4" aria-hidden="true" />
            <dt className="sr-only">Modules</dt>
            <dd>{course.modules.length} modules</dd>
          </div>
          <div className="flex items-center gap-2">
            <BookOpen className="size-4" aria-hidden="true" />
            <dt className="sr-only">Lessons</dt>
            <dd>{course.modules.reduce((total, m) => total + m.lessons.length, 0)} lessons</dd>
          </div>
        </dl>

        <div className="flex flex-wrap gap-2">
          {firstLesson ? (
            <Button asChild>
              <Link href={`/courses/${course.slug}/learn/${firstLesson.id}`}>Start learning</Link>
            </Button>
          ) : null}
          {course.can_manage ? (
            <Button asChild variant="outline">
              <Link href={`/admin/courses/${course.id}`}>Edit this course</Link>
            </Button>
          ) : null}
        </div>
      </header>

      <div className="grid gap-6 lg:grid-cols-[2fr_1fr]">
        <div className="space-y-6">
          {course.description ? (
            <section className="space-y-2">
              <h2 className="text-lg font-semibold tracking-tight">About this course</h2>
              <p className="whitespace-pre-line text-sm text-muted-foreground">
                {course.description}
              </p>
            </section>
          ) : null}

          <section className="space-y-3">
            <h2 className="text-lg font-semibold tracking-tight">Course content</h2>
            {course.modules.length === 0 ? (
              <EmptyState
                title="No content yet"
                description="This course has no published modules."
              />
            ) : (
              <div className="space-y-3">
                {course.modules.map((module) => (
                  <Card key={module.id}>
                    <CardHeader className="gap-1">
                      <div className="flex flex-wrap items-center gap-2">
                        <CardTitle>{module.title}</CardTitle>
                        {module.status !== 'published' ? (
                          <Badge variant={STATUS_VARIANT[module.status]}>
                            {STATUS_LABEL[module.status]}
                          </Badge>
                        ) : null}
                      </div>
                      {module.description ? (
                        <p className="text-sm text-muted-foreground">{module.description}</p>
                      ) : null}
                    </CardHeader>
                    <CardContent className="px-0 pb-0">
                      {module.lessons.length === 0 ? (
                        <p className="px-5 pb-4 text-sm text-muted-foreground">
                          No lessons in this module yet.
                        </p>
                      ) : (
                        <ul>
                          {module.lessons.map((lesson) => (
                            <LessonRow key={lesson.id} lesson={lesson} courseSlug={course.slug} />
                          ))}
                        </ul>
                      )}
                    </CardContent>
                  </Card>
                ))}
              </div>
            )}
          </section>
        </div>

        <aside className="space-y-4">
          {course.learning_objectives.length > 0 ? (
            <Card>
              <CardHeader>
                <CardTitle>What you will learn</CardTitle>
              </CardHeader>
              <CardContent>
                <ul className="space-y-2 text-sm">
                  {course.learning_objectives.map((objective) => (
                    <li key={objective} className="flex gap-2">
                      <CheckCircle2
                        className="mt-0.5 size-4 shrink-0 text-primary"
                        aria-hidden="true"
                      />
                      <span>{objective}</span>
                    </li>
                  ))}
                </ul>
              </CardContent>
            </Card>
          ) : null}

          {course.prerequisites.length > 0 ? (
            <Card>
              <CardHeader>
                <CardTitle>Prerequisites</CardTitle>
              </CardHeader>
              <CardContent>
                <ul className="list-inside list-disc space-y-1 text-sm text-muted-foreground">
                  {course.prerequisites.map((item) => (
                    <li key={item}>{item}</li>
                  ))}
                </ul>
              </CardContent>
            </Card>
          ) : null}

          {course.instructors.length > 0 ? (
            <Card>
              <CardHeader>
                <CardTitle>Instructors</CardTitle>
              </CardHeader>
              <CardContent>
                <ul className="space-y-1 text-sm">
                  {course.instructors.map((instructor) => (
                    <li key={instructor.full_name}>{instructor.full_name}</li>
                  ))}
                </ul>
              </CardContent>
            </Card>
          ) : null}
        </aside>
      </div>
    </div>
  );
}

export default function CoursePage({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = use(params);
  return (
    <RequireAuth>
      <CourseDetailContent slug={slug} />
    </RequireAuth>
  );
}
