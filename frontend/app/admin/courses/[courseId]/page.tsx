'use client';

import Link from 'next/link';
import { use, useCallback, useEffect, useState } from 'react';
import { ChevronDown, ChevronUp, Plus, Trash2 } from 'lucide-react';

import { RequireAuth } from '@/components/require-auth';
import { EmptyState, ErrorState, LoadingState } from '@/components/states';
import { Alert } from '@/components/ui/alert';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { ApiError } from '@/lib/api';
import {
  createModule,
  deleteModule,
  getCourse,
  reorderLessons,
  reorderModules,
  setModuleStatus,
} from '@/lib/courses';
import { CONTENT_TYPE_LABEL, STATUS_LABEL, STATUS_VARIANT } from '@/lib/course-labels';
import type { CourseDetail, LessonSummary, Module } from '@/types/api';
import { CourseSettingsForm } from './course-settings-form';
import { LessonEditor } from './lesson-editor';
import { PublishPanel } from './publish-panel';

/** Move an item within an array, returning the new id order. */
function moved<T extends { id: string }>(items: T[], index: number, delta: number): string[] {
  const next = [...items];
  const target = index + delta;
  if (target < 0 || target >= next.length) return next.map((item) => item.id);
  [next[index], next[target]] = [next[target]!, next[index]!];
  return next.map((item) => item.id);
}

function ModulePanel({
  module,
  index,
  total,
  onChanged,
  onMove,
}: {
  module: Module;
  index: number;
  total: number;
  onChanged: () => void;
  onMove: (delta: number) => void;
}) {
  const [editingLesson, setEditingLesson] = useState<LessonSummary | null>(null);
  const [isAdding, setIsAdding] = useState(false);
  const [message, setMessage] = useState('');

  async function onToggleStatus() {
    try {
      await setModuleStatus(module.id, module.status === 'published' ? 'draft' : 'published');
      onChanged();
    } catch (cause) {
      setMessage(cause instanceof ApiError ? cause.message : 'Could not change the status.');
    }
  }

  async function onDelete() {
    try {
      await deleteModule(module.id);
      onChanged();
    } catch (cause) {
      setMessage(cause instanceof ApiError ? cause.message : 'Could not delete the module.');
    }
  }

  async function onMoveLesson(lessonIndex: number, delta: number) {
    try {
      await reorderLessons(module.id, moved(module.lessons, lessonIndex, delta));
      onChanged();
    } catch (cause) {
      setMessage(cause instanceof ApiError ? cause.message : 'Could not reorder the lessons.');
    }
  }

  return (
    <Card>
      <CardHeader className="gap-2">
        <div className="flex flex-wrap items-center gap-2">
          <CardTitle className="flex-1">{module.title}</CardTitle>
          <Badge variant={STATUS_VARIANT[module.status]}>{STATUS_LABEL[module.status]}</Badge>
          <Button
            size="sm"
            variant="ghost"
            onClick={() => onMove(-1)}
            disabled={index === 0}
            aria-label={`Move ${module.title} up`}
          >
            <ChevronUp className="size-4" aria-hidden="true" />
          </Button>
          <Button
            size="sm"
            variant="ghost"
            onClick={() => onMove(1)}
            disabled={index === total - 1}
            aria-label={`Move ${module.title} down`}
          >
            <ChevronDown className="size-4" aria-hidden="true" />
          </Button>
          <Button size="sm" variant="outline" onClick={() => void onToggleStatus()}>
            {module.status === 'published' ? 'Unpublish' : 'Publish'}
          </Button>
          <Button
            size="sm"
            variant="ghost"
            onClick={() => void onDelete()}
            aria-label={`Delete ${module.title}`}
          >
            <Trash2 className="size-4" aria-hidden="true" />
          </Button>
        </div>
        {module.description ? (
          <p className="text-sm text-muted-foreground">{module.description}</p>
        ) : null}
      </CardHeader>

      <CardContent className="space-y-3">
        {message ? <Alert variant="error">{message}</Alert> : null}

        {module.lessons.length === 0 ? (
          <p className="text-sm text-muted-foreground">No lessons in this module yet.</p>
        ) : (
          <ul className="divide-y divide-border rounded-md border border-border">
            {module.lessons.map((lesson, lessonIndex) => (
              <li key={lesson.id} className="space-y-3 px-3 py-2">
                <div className="flex flex-wrap items-center gap-2 text-sm">
                  <span className="min-w-0 flex-1 truncate font-medium">{lesson.title}</span>
                  <Badge>{CONTENT_TYPE_LABEL[lesson.content_type]}</Badge>
                  {lesson.is_preview ? <Badge variant="success">Preview</Badge> : null}
                  <Badge variant={STATUS_VARIANT[lesson.status]}>
                    {STATUS_LABEL[lesson.status]}
                  </Badge>
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={() => void onMoveLesson(lessonIndex, -1)}
                    disabled={lessonIndex === 0}
                    aria-label={`Move ${lesson.title} up`}
                  >
                    <ChevronUp className="size-3.5" aria-hidden="true" />
                  </Button>
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={() => void onMoveLesson(lessonIndex, 1)}
                    disabled={lessonIndex === module.lessons.length - 1}
                    aria-label={`Move ${lesson.title} down`}
                  >
                    <ChevronDown className="size-3.5" aria-hidden="true" />
                  </Button>
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() =>
                      setEditingLesson((current) => (current?.id === lesson.id ? null : lesson))
                    }
                  >
                    {editingLesson?.id === lesson.id ? 'Close' : 'Edit'}
                  </Button>
                </div>

                {editingLesson?.id === lesson.id ? (
                  <LessonEditor
                    moduleId={module.id}
                    lesson={lesson}
                    onSaved={() => {
                      setEditingLesson(null);
                      onChanged();
                    }}
                    onCancel={() => setEditingLesson(null)}
                  />
                ) : null}
              </li>
            ))}
          </ul>
        )}

        {isAdding ? (
          <LessonEditor
            moduleId={module.id}
            onSaved={() => {
              setIsAdding(false);
              onChanged();
            }}
            onCancel={() => setIsAdding(false)}
          />
        ) : (
          <Button size="sm" variant="outline" onClick={() => setIsAdding(true)}>
            <Plus className="size-3.5" aria-hidden="true" />
            Add lesson
          </Button>
        )}
      </CardContent>
    </Card>
  );
}

function CourseEditor({ courseId }: { courseId: string }) {
  const [course, setCourse] = useState<CourseDetail | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [newModuleTitle, setNewModuleTitle] = useState('');
  const [message, setMessage] = useState('');

  const load = useCallback(async () => {
    try {
      setCourse(await getCourse(courseId));
      setError(null);
    } catch (cause) {
      setError(cause instanceof ApiError ? cause : null);
    } finally {
      setIsLoading(false);
    }
  }, [courseId]);

  useEffect(() => {
    let cancelled = false;
    getCourse(courseId)
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
  }, [courseId]);

  async function onAddModule(event: React.FormEvent) {
    event.preventDefault();
    if (!newModuleTitle.trim()) return;
    try {
      await createModule(courseId, { title: newModuleTitle.trim() });
      setNewModuleTitle('');
      await load();
    } catch (cause) {
      setMessage(cause instanceof ApiError ? cause.message : 'Could not add the module.');
    }
  }

  async function onMoveModule(index: number, delta: number) {
    if (!course) return;
    try {
      await reorderModules(courseId, moved(course.modules, index, delta));
      await load();
    } catch (cause) {
      setMessage(cause instanceof ApiError ? cause.message : 'Could not reorder the modules.');
    }
  }

  if (isLoading) return <LoadingState label="Loading course…" rows={6} />;

  if (error) {
    if (error.status === 404) {
      return (
        <EmptyState
          title="Course not found"
          description="This course does not exist, or you are not assigned to it."
          action={
            <Button asChild variant="outline">
              <Link href="/admin/courses">Back to courses</Link>
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

  if (!course.can_manage) {
    // The API would refuse every write anyway; this avoids showing a form that
    // could only fail.
    return (
      <EmptyState
        title="You cannot edit this course"
        description="You have read access, but no authoring rights on it."
        action={
          <Button asChild variant="outline">
            <Link href={`/courses/${course.slug}`}>View the course page</Link>
          </Button>
        }
      />
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="space-y-1">
          <div className="flex flex-wrap items-center gap-2">
            <h1 className="text-2xl font-semibold tracking-tight">{course.title}</h1>
            <Badge variant={STATUS_VARIANT[course.status]}>{STATUS_LABEL[course.status]}</Badge>
          </div>
          <p className="font-mono text-xs text-muted-foreground">{course.code}</p>
        </div>
        <Button asChild variant="outline">
          <Link href={`/courses/${course.slug}`}>View as a student</Link>
        </Button>
      </div>

      {message ? <Alert variant="error">{message}</Alert> : null}

      <PublishPanel course={course} onChanged={load} />
      <CourseSettingsForm course={course} onSaved={load} />

      <section className="space-y-3">
        <h2 className="text-lg font-semibold tracking-tight">Modules and lessons</h2>

        {course.modules.length === 0 ? (
          <EmptyState
            title="No modules yet"
            description="Add the first module to start building the course."
          />
        ) : (
          <div className="space-y-4">
            {course.modules.map((module, index) => (
              <ModulePanel
                key={module.id}
                module={module}
                index={index}
                total={course.modules.length}
                onChanged={load}
                onMove={(delta) => void onMoveModule(index, delta)}
              />
            ))}
          </div>
        )}

        <form onSubmit={onAddModule} className="flex flex-wrap items-end gap-2">
          <div className="min-w-[16rem] flex-1">
            <label htmlFor="new-module" className="mb-1.5 block text-sm font-medium">
              New module title
            </label>
            <input
              id="new-module"
              className="h-10 w-full rounded-md border border-border bg-background px-3 text-sm"
              value={newModuleTitle}
              onChange={(event) => setNewModuleTitle(event.target.value)}
            />
          </div>
          <Button type="submit">
            <Plus className="size-4" aria-hidden="true" />
            Add module
          </Button>
        </form>
      </section>
    </div>
  );
}

export default function AdminCoursePage({ params }: { params: Promise<{ courseId: string }> }) {
  const { courseId } = use(params);
  return (
    <RequireAuth>
      <CourseEditor courseId={courseId} />
    </RequireAuth>
  );
}
