'use client';

import { useEffect, useState } from 'react';
import { Trash2, Upload } from 'lucide-react';

import { Alert } from '@/components/ui/alert';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Field } from '@/components/ui/field';
import { Input, Select, Textarea } from '@/components/ui/input';
import { ApiError, fieldErrors } from '@/lib/api';
import {
  addLessonResourceLink,
  createLesson,
  deleteLesson,
  deleteResource,
  getLesson,
  setLessonStatus,
  updateLesson,
  uploadLessonResource,
} from '@/lib/courses';
import { CONTENT_TYPE_OPTIONS, formatBytes } from '@/lib/course-labels';
import type { LessonContent, LessonContentType, LessonSummary } from '@/types/api';

interface LessonFormState {
  title: string;
  description: string;
  content_type: LessonContentType;
  text_content: string;
  external_url: string;
  duration_minutes: string;
  is_preview: boolean;
  is_required: boolean;
  video_source_url: string;
  video_duration_seconds: string;
}

const EMPTY: LessonFormState = {
  title: '',
  description: '',
  content_type: 'text',
  text_content: '',
  external_url: '',
  duration_minutes: '',
  is_preview: false,
  is_required: true,
  video_source_url: '',
  video_duration_seconds: '',
};

function toPayload(form: LessonFormState): Record<string, unknown> {
  const payload: Record<string, unknown> = {
    title: form.title,
    description: form.description,
    content_type: form.content_type,
    duration_minutes: form.duration_minutes === '' ? null : Number(form.duration_minutes),
    is_preview: form.is_preview,
    is_required: form.is_required,
  };

  // Only send the field the chosen content type actually uses. The API
  // validates the pairing too, so this is convenience, not enforcement.
  if (form.content_type === 'text') payload.text_content = form.text_content;
  if (form.content_type === 'external_link') payload.external_url = form.external_url;
  if (form.content_type === 'video') {
    payload.video = {
      provider: 'external_url',
      source_url: form.video_source_url,
      status: 'ready',
      duration_seconds:
        form.video_duration_seconds === '' ? null : Number(form.video_duration_seconds),
    };
  }
  return payload;
}

/** Create or edit one lesson, including its resources. */
export function LessonEditor({
  moduleId,
  lesson,
  onSaved,
  onCancel,
}: {
  moduleId: string;
  lesson?: LessonSummary;
  onSaved: () => void;
  onCancel: () => void;
}) {
  const [form, setForm] = useState<LessonFormState>(
    lesson
      ? {
          ...EMPTY,
          title: lesson.title,
          description: lesson.description,
          content_type: lesson.content_type,
          duration_minutes: lesson.duration_minutes ? String(lesson.duration_minutes) : '',
          is_preview: lesson.is_preview,
          is_required: lesson.is_required,
        }
      : EMPTY,
  );
  const [loaded, setLoaded] = useState<LessonContent | null>(null);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [isSaving, setIsSaving] = useState(false);

  // Load the full body when editing: the outline summary deliberately does not
  // include it, so the editor has to ask for it separately.
  const lessonId = lesson?.id;
  useEffect(() => {
    if (!lessonId) return;
    let cancelled = false;

    getLesson(lessonId)
      .then((full) => {
        if (cancelled) return;
        setLoaded(full);
        setForm((current) => ({
          ...current,
          text_content: full.text_content,
          external_url: full.external_url,
          video_duration_seconds: full.video?.duration_seconds
            ? String(full.video.duration_seconds)
            : '',
        }));
      })
      .catch(() => {
        if (!cancelled) setErrors({ __all__: 'Could not load the lesson body.' });
      });

    return () => {
      cancelled = true;
    };
  }, [lessonId]);

  function set<K extends keyof LessonFormState>(key: K, value: LessonFormState[K]) {
    setForm((current) => ({ ...current, [key]: value }));
  }

  async function onSubmit(event: React.FormEvent) {
    event.preventDefault();
    setIsSaving(true);
    setErrors({});
    try {
      if (lesson) {
        await updateLesson(lesson.id, toPayload(form));
      } else {
        await createLesson(moduleId, toPayload(form));
      }
      onSaved();
    } catch (cause) {
      setErrors(fieldErrors(cause));
    } finally {
      setIsSaving(false);
    }
  }

  async function onToggleStatus() {
    if (!lesson) return;
    try {
      await setLessonStatus(lesson.id, lesson.status === 'published' ? 'draft' : 'published');
      onSaved();
    } catch (cause) {
      setErrors(fieldErrors(cause));
    }
  }

  async function onDelete() {
    if (!lesson) return;
    try {
      await deleteLesson(lesson.id);
      onSaved();
    } catch (cause) {
      setErrors(fieldErrors(cause));
    }
  }

  return (
    <form
      onSubmit={onSubmit}
      className="space-y-4 rounded-[var(--radius-card)] border border-border p-4"
      noValidate
    >
      {errors.__all__ ? <Alert variant="error">{errors.__all__}</Alert> : null}

      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="Lesson title" htmlFor="lesson-title" error={errors.title} required>
          <Input value={form.title} onChange={(event) => set('title', event.target.value)} />
        </Field>
        <Field label="Content type" htmlFor="lesson-type" error={errors.content_type}>
          <Select
            value={form.content_type}
            onChange={(event) => set('content_type', event.target.value as LessonContentType)}
          >
            {CONTENT_TYPE_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </Select>
        </Field>
      </div>

      <Field label="Description" htmlFor="lesson-description" error={errors.description}>
        <Textarea
          rows={2}
          value={form.description}
          onChange={(event) => set('description', event.target.value)}
        />
      </Field>

      {form.content_type === 'text' ? (
        <Field
          label="Lesson body"
          htmlFor="lesson-body"
          error={errors.text_content}
          hint="Plain text. Rendered as written, never as HTML."
        >
          <Textarea
            rows={8}
            value={form.text_content}
            onChange={(event) => set('text_content', event.target.value)}
          />
        </Field>
      ) : null}

      {form.content_type === 'external_link' ? (
        <Field
          label="External URL"
          htmlFor="lesson-url"
          error={errors.external_url}
          hint="Must be an https:// URL."
        >
          <Input
            type="url"
            value={form.external_url}
            onChange={(event) => set('external_url', event.target.value)}
          />
        </Field>
      ) : null}

      {form.content_type === 'video' ? (
        <div className="grid gap-4 sm:grid-cols-2">
          <Field
            label="Video URL"
            htmlFor="lesson-video"
            error={errors.video}
            hint="https:// only. Stored as metadata; never served from this app."
          >
            <Input
              type="url"
              value={form.video_source_url}
              onChange={(event) => set('video_source_url', event.target.value)}
            />
          </Field>
          <Field label="Video length (seconds)" htmlFor="lesson-video-duration">
            <Input
              type="number"
              min={0}
              value={form.video_duration_seconds}
              onChange={(event) => set('video_duration_seconds', event.target.value)}
            />
          </Field>
        </div>
      ) : null}

      <div className="grid gap-4 sm:grid-cols-3">
        <Field label="Duration (minutes)" htmlFor="lesson-duration" error={errors.duration_minutes}>
          <Input
            type="number"
            min={1}
            value={form.duration_minutes}
            onChange={(event) => set('duration_minutes', event.target.value)}
          />
        </Field>
        <label className="flex items-center gap-2 self-end pb-2 text-sm">
          <input
            type="checkbox"
            checked={form.is_preview}
            onChange={(event) => set('is_preview', event.target.checked)}
          />
          Free preview
        </label>
        <label className="flex items-center gap-2 self-end pb-2 text-sm">
          <input
            type="checkbox"
            checked={form.is_required}
            onChange={(event) => set('is_required', event.target.checked)}
          />
          Required
        </label>
      </div>

      <div className="flex flex-wrap gap-2">
        <Button type="submit" size="sm" disabled={isSaving}>
          {isSaving ? 'Saving…' : lesson ? 'Save lesson' : 'Add lesson'}
        </Button>
        <Button type="button" size="sm" variant="ghost" onClick={onCancel}>
          Cancel
        </Button>
        {lesson ? (
          <>
            <Button type="button" size="sm" variant="outline" onClick={() => void onToggleStatus()}>
              {lesson.status === 'published' ? 'Unpublish' : 'Publish'}
            </Button>
            <Button
              type="button"
              size="sm"
              variant="destructive"
              onClick={() => void onDelete()}
              className="ml-auto"
            >
              <Trash2 className="size-3.5" aria-hidden="true" />
              Delete
            </Button>
          </>
        ) : null}
      </div>

      {lesson && loaded ? <ResourceManager lesson={loaded} onChanged={onSaved} /> : null}
    </form>
  );
}

/** Attach files and links to a lesson. */
function ResourceManager({ lesson, onChanged }: { lesson: LessonContent; onChanged: () => void }) {
  const [resources, setResources] = useState(lesson.resources);
  const [title, setTitle] = useState('');
  const [linkUrl, setLinkUrl] = useState('');
  const [message, setMessage] = useState('');
  const [isBusy, setIsBusy] = useState(false);

  async function onUpload(event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) return;
    setIsBusy(true);
    setMessage('');
    try {
      const created = await uploadLessonResource(lesson.id, title || file.name, file);
      setResources((current) => [...current, created]);
      setTitle('');
      onChanged();
    } catch (cause) {
      setMessage(cause instanceof ApiError ? cause.message : 'The file could not be uploaded.');
    } finally {
      setIsBusy(false);
      event.target.value = '';
    }
  }

  async function onAddLink() {
    if (!linkUrl) return;
    setIsBusy(true);
    setMessage('');
    try {
      const created = await addLessonResourceLink(lesson.id, {
        title: title || linkUrl,
        external_url: linkUrl,
      });
      setResources((current) => [...current, created]);
      setTitle('');
      setLinkUrl('');
      onChanged();
    } catch (cause) {
      setMessage(cause instanceof ApiError ? cause.message : 'The link could not be added.');
    } finally {
      setIsBusy(false);
    }
  }

  async function onDelete(resourceId: string) {
    try {
      await deleteResource(resourceId);
      setResources((current) => current.filter((item) => item.id !== resourceId));
      onChanged();
    } catch (cause) {
      setMessage(cause instanceof ApiError ? cause.message : 'The resource could not be removed.');
    }
  }

  return (
    <div className="space-y-3 border-t border-border pt-4">
      <p className="text-sm font-medium">Resources</p>
      {message ? <Alert variant="error">{message}</Alert> : null}

      {resources.length > 0 ? (
        <ul className="divide-y divide-border rounded-md border border-border">
          {resources.map((resource) => (
            <li key={resource.id} className="flex items-center gap-3 px-3 py-2 text-sm">
              <span className="min-w-0 flex-1 truncate">{resource.title}</span>
              <Badge>{resource.kind}</Badge>
              {resource.size_bytes ? (
                <span className="text-xs text-muted-foreground">
                  {formatBytes(resource.size_bytes)}
                </span>
              ) : null}
              <Button
                type="button"
                size="sm"
                variant="ghost"
                onClick={() => void onDelete(resource.id)}
                aria-label={`Remove ${resource.title}`}
              >
                <Trash2 className="size-3.5" aria-hidden="true" />
              </Button>
            </li>
          ))}
        </ul>
      ) : (
        <p className="text-xs text-muted-foreground">No resources attached yet.</p>
      )}

      <div className="grid gap-3 sm:grid-cols-2">
        <Field label="Resource title" htmlFor="resource-title" hint="Optional — defaults to the filename.">
          <Input value={title} onChange={(event) => setTitle(event.target.value)} />
        </Field>
        <Field
          label="Upload a file"
          htmlFor="resource-file"
          hint="PDF, Office documents, images, text or ZIP. Up to 25 MB."
        >
          <Input
            type="file"
            disabled={isBusy}
            onChange={onUpload}
            accept=".pdf,.docx,.pptx,.xlsx,.doc,.ppt,.xls,.zip,.png,.jpg,.jpeg,.webp,.txt,.csv,.md"
          />
        </Field>
      </div>

      <div className="flex flex-wrap items-end gap-2">
        <Field label="Or add a link" htmlFor="resource-link" className="min-w-[16rem] flex-1">
          <Input
            type="url"
            placeholder="https://…"
            value={linkUrl}
            onChange={(event) => setLinkUrl(event.target.value)}
          />
        </Field>
        <Button type="button" size="sm" variant="outline" disabled={isBusy} onClick={() => void onAddLink()}>
          <Upload className="size-3.5" aria-hidden="true" />
          Add link
        </Button>
      </div>
    </div>
  );
}
