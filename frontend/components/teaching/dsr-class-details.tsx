'use client';

/**
 * The class report's after-class sections: what was covered against the
 * course, the homework, notes about individual students, attached files,
 * and the institution's own extra questions. Edited here and saved with the
 * rest of the draft; `DsrClassDetailsSummary` is the read-only view once
 * the report is submitted.
 */
import { useId, useState } from 'react';
import { Download, Paperclip, Plus, Trash2 } from 'lucide-react';

import { FieldRenderer } from '@/components/forms/field-renderer';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Checkbox } from '@/components/ui/checkbox';
import { Field } from '@/components/ui/field';
import { Input, Select, Textarea } from '@/components/ui/input';
import { RadioGroup, RadioGroupItem } from '@/components/ui/radio-group';
import { errorMessage } from '@/lib/api';
import type {
  DSR,
  DSRStudentFlag,
  DSRTopicStatus,
  DSRWritePayload,
} from '@/lib/dsr';
import { formUploadUrl, uploadFormFile } from '@/lib/forms';
import { formatDate } from '@/lib/format';
import type { Module, RegisterEntry } from '@/types/api';

export const STUDENT_FLAG_LABEL: Record<DSRStudentFlag, string> = {
  doubt: 'Had a doubt',
  needs_attention: 'Needs attention',
  did_well: 'Did well',
  absent_reason: 'Reason for absence',
  other: 'Other',
};

const TOPIC_STATUS_OPTIONS: { value: DSRTopicStatus; label: string; hint: string }[] = [
  { value: 'completed', label: 'Finished', hint: 'The planned lesson is done' },
  { value: 'in_progress', label: 'Partly', hint: 'Carries over to the next class' },
  { value: 'skipped', label: 'Not covered', hint: 'Revision, a test, or something else' },
];

function Section({ title, hint, children }: { title: string; hint?: string; children: React.ReactNode }) {
  return (
    <section className="space-y-2 border-t border-line pt-4">
      <div>
        <h3 className="text-sm font-semibold text-ink">{title}</h3>
        {hint ? <p className="text-xs text-ink-muted">{hint}</p> : null}
      </div>
      {children}
    </section>
  );
}

export function DsrClassDetails({
  dsr,
  draft,
  onChange,
  modules,
  roster,
  fieldErrors,
}: {
  dsr: DSR;
  draft: DSRWritePayload;
  onChange: (patch: DSRWritePayload) => void;
  modules: Module[];
  roster: RegisterEntry[];
  fieldErrors: Record<string, string>;
}) {
  const uid = useId();
  const lessons = new Set(draft.lessons_covered ?? []);
  const notes = draft.student_notes ?? [];
  const attachments = draft.attachments ?? [];
  const [filenames, setFilenames] = useState<Record<string, string>>(() =>
    Object.fromEntries((dsr.attachments ?? []).map((row) => [row.upload, row.filename ?? 'File'])),
  );
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [noteStudent, setNoteStudent] = useState('');
  const [noteFlag, setNoteFlag] = useState<DSRStudentFlag>('needs_attention');
  const [noteText, setNoteText] = useState('');
  const nameOf = (enrollmentId: string) =>
    roster.find((entry) => entry.enrollment_id === enrollmentId)?.full_name ??
    dsr.student_notes?.find((note) => note.enrollment === enrollmentId)?.student_name ??
    'Student';

  const groups = modules
    .map((module) => ({
      module,
      lessons: module.lessons.filter((lesson) => lesson.status === 'published'),
    }))
    .filter((group) => group.lessons.length > 0);

  function toggleLesson(id: string, checked: boolean) {
    const next = new Set(lessons);
    if (checked) next.add(id);
    else next.delete(id);
    onChange({ lessons_covered: Array.from(next) });
  }

  function addNote() {
    if (!noteStudent) return;
    const others = notes.filter(
      (note) => !(note.enrollment === noteStudent && note.flag === noteFlag),
    );
    onChange({
      student_notes: [...others, { enrollment: noteStudent, flag: noteFlag, note: noteText.trim() }],
    });
    setNoteText('');
  }

  async function attach(file: File) {
    setUploading(true);
    setUploadError(null);
    try {
      const upload = await uploadFormFile(file);
      setFilenames((current) => ({ ...current, [upload.id]: upload.filename }));
      onChange({ attachments: [...attachments, { upload: upload.id, caption: '' }] });
    } catch (cause) {
      setUploadError(errorMessage(cause));
    } finally {
      setUploading(false);
    }
  }

  const extraFields = dsr.extra_form?.fields ?? [];

  return (
    <div className="space-y-4">
      <Section
        title="What was covered"
        hint={
          dsr.planned_lesson
            ? `Planned: ${dsr.planned_lesson.title}`
            : 'Tick the lessons this class got through.'
        }
      >
        <RadioGroup
          value={draft.topic_status ?? 'completed'}
          onValueChange={(value) => onChange({ topic_status: value as DSRTopicStatus })}
          aria-label="Was the planned lesson finished?"
          className="flex flex-wrap gap-x-5 gap-y-2"
        >
          {TOPIC_STATUS_OPTIONS.map((option) => (
            <label key={option.value} className="flex items-center gap-2 text-sm" title={option.hint}>
              <RadioGroupItem value={option.value} />
              {option.label}
            </label>
          ))}
        </RadioGroup>
        {groups.length === 0 ? (
          <p className="text-xs text-ink-muted">This batch&rsquo;s course has no published lessons.</p>
        ) : (
          <fieldset className="rounded-control border border-line p-2">
            <legend className="px-1 text-sm text-ink">
              Lessons covered{lessons.size > 0 ? ` (${lessons.size})` : ''}
            </legend>
            <div className="max-h-64 space-y-3 overflow-y-auto pr-1">
              {groups.map(({ module, lessons: moduleLessons }) => (
                <div key={module.id} className="space-y-1">
                  <p className="text-2xs font-semibold uppercase tracking-wide text-ink-faint">
                    {module.title}
                  </p>
                  {moduleLessons.map((lesson) => (
                    <div key={lesson.id} className="flex items-center gap-2 text-sm">
                      <Checkbox
                        id={`${uid}-lesson-${lesson.id}`}
                        checked={lessons.has(lesson.id)}
                        onCheckedChange={(checked) => toggleLesson(lesson.id, checked)}
                      />
                      <label htmlFor={`${uid}-lesson-${lesson.id}`}>{lesson.title}</label>
                    </div>
                  ))}
                </div>
              ))}
            </div>
          </fieldset>
        )}
        {fieldErrors.lessons_covered ? (
          <p className="text-2xs font-medium text-danger">{fieldErrors.lessons_covered}</p>
        ) : null}
      </Section>

      <Section title="Homework" hint="Students see this, with what was covered.">
        <div className="grid gap-3 sm:grid-cols-[minmax(0,1fr)_11rem]">
          <Field label="What to do" htmlFor={`${uid}-homework`} error={fieldErrors.homework}>
            <Textarea
              rows={2}
              maxLength={2000}
              value={draft.homework ?? ''}
              onChange={(event) => onChange({ homework: event.target.value })}
            />
          </Field>
          <Field label="Due" htmlFor={`${uid}-homework-due`} error={fieldErrors.homework_due_on}>
            <Input
              type="date"
              value={draft.homework_due_on ?? ''}
              onChange={(event) => onChange({ homework_due_on: event.target.value || null })}
            />
          </Field>
        </div>
      </Section>

      <Section title="Notes about students" hint="Shown on each student's timeline. Staff only.">
        {notes.length > 0 ? (
          <ul className="space-y-1.5">
            {notes.map((note) => (
              <li
                key={`${note.enrollment}-${note.flag}`}
                className="flex items-start justify-between gap-2 rounded-control bg-sunken/60 px-2 py-1.5 text-sm"
              >
                <span className="min-w-0">
                  <span className="font-medium text-ink">{nameOf(note.enrollment)}</span>{' '}
                  <Badge variant={note.flag === 'needs_attention' ? 'warning' : 'neutral'} dot={false}>
                    {STUDENT_FLAG_LABEL[note.flag]}
                  </Badge>
                  {note.note ? <span className="block text-xs text-ink-muted">{note.note}</span> : null}
                </span>
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  aria-label={`Remove the note about ${nameOf(note.enrollment)}`}
                  onClick={() =>
                    onChange({
                      student_notes: notes.filter(
                        (other) => !(other.enrollment === note.enrollment && other.flag === note.flag),
                      ),
                    })
                  }
                >
                  <Trash2 className="size-3.5" aria-hidden="true" />
                </Button>
              </li>
            ))}
          </ul>
        ) : null}
        <div className="grid gap-2 sm:grid-cols-[minmax(0,1fr)_10rem]">
          <Field label="Student" htmlFor={`${uid}-note-student`}>
            <Select value={noteStudent} onChange={(event) => setNoteStudent(event.target.value)}>
              <option value="">Choose a student…</option>
              {roster.map((entry) => (
                <option key={entry.enrollment_id} value={entry.enrollment_id}>
                  {entry.full_name}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Note" htmlFor={`${uid}-note-flag`}>
            <Select
              value={noteFlag}
              onChange={(event) => setNoteFlag(event.target.value as DSRStudentFlag)}
            >
              {(Object.keys(STUDENT_FLAG_LABEL) as DSRStudentFlag[]).map((flag) => (
                <option key={flag} value={flag}>
                  {STUDENT_FLAG_LABEL[flag]}
                </option>
              ))}
            </Select>
          </Field>
        </div>
        <div className="flex gap-2">
          <Input
            aria-label="Details (optional)"
            placeholder="Details (optional)"
            maxLength={500}
            value={noteText}
            onChange={(event) => setNoteText(event.target.value)}
          />
          <Button type="button" variant="outline" disabled={!noteStudent} onClick={addNote}>
            <Plus className="size-4" aria-hidden="true" />
            Add
          </Button>
        </div>
        {fieldErrors.student_notes ? (
          <p className="text-2xs font-medium text-danger">{fieldErrors.student_notes}</p>
        ) : null}
      </Section>

      <Section title="Files" hint="Class notes, a whiteboard photo. PDF, Office or image files.">
        {attachments.length > 0 ? (
          <ul className="space-y-1.5">
            {attachments.map((row, index) => (
              <li key={row.upload} className="flex items-center gap-2">
                <Paperclip className="size-4 shrink-0 text-ink-faint" aria-hidden="true" />
                <span className="min-w-0 flex-1 truncate text-sm">{filenames[row.upload] ?? 'File'}</span>
                <Input
                  aria-label={`Caption for ${filenames[row.upload] ?? 'file'}`}
                  placeholder="Caption"
                  className="max-w-[12rem]"
                  maxLength={150}
                  value={row.caption}
                  onChange={(event) => {
                    const next = attachments.slice();
                    next[index] = { ...row, caption: event.target.value };
                    onChange({ attachments: next });
                  }}
                />
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  aria-label={`Remove ${filenames[row.upload] ?? 'file'}`}
                  onClick={() => onChange({ attachments: attachments.filter((_, i) => i !== index) })}
                >
                  <Trash2 className="size-3.5" aria-hidden="true" />
                </Button>
              </li>
            ))}
          </ul>
        ) : null}
        <Input
          type="file"
          aria-label="Attach a file"
          disabled={uploading}
          onChange={(event) => {
            const file = event.target.files?.[0];
            if (file) void attach(file);
            event.target.value = '';
          }}
        />
        {uploading ? <p className="text-2xs text-ink-faint">Uploading…</p> : null}
        {uploadError ? <p className="text-2xs font-medium text-danger">{uploadError}</p> : null}
        {fieldErrors.attachments ? (
          <p className="text-2xs font-medium text-danger">{fieldErrors.attachments}</p>
        ) : null}
      </Section>

      {extraFields.length > 0 ? (
        <Section title="More questions" hint="Your institute's own questions.">
          <FieldRenderer
            fields={extraFields}
            values={draft.extra_answers ?? {}}
            errors={fieldErrors}
            onChange={(key, value) =>
              onChange({ extra_answers: { ...(draft.extra_answers ?? {}), [key]: value } })
            }
          />
        </Section>
      ) : null}
    </div>
  );
}

/** The same sections, read-only, for a submitted report. */
export function DsrClassDetailsSummary({ dsr }: { dsr: DSR }) {
  const lessons = dsr.lessons_covered ?? [];
  const notes = dsr.student_notes ?? [];
  const files = dsr.attachments ?? [];
  const extraFields = dsr.extra_form?.fields ?? [];
  return (
    <div className="space-y-3 text-sm">
      {lessons.length > 0 ? (
        <p>
          <span className="text-ink-muted">Covered: </span>
          {lessons.map((lesson) => lesson.title).join(', ')}
        </p>
      ) : null}
      {dsr.homework ? (
        <p>
          <span className="text-ink-muted">Homework: </span>
          {dsr.homework}
          {dsr.homework_due_on ? ` (due ${formatDate(dsr.homework_due_on)})` : ''}
        </p>
      ) : null}
      {notes.length > 0 ? (
        <ul className="space-y-1">
          {notes.map((note) => (
            <li key={`${note.enrollment}-${note.flag}`}>
              <span className="font-medium">{note.student_name ?? 'Student'}</span> ·{' '}
              {STUDENT_FLAG_LABEL[note.flag]}
              {note.note ? ` — ${note.note}` : ''}
            </li>
          ))}
        </ul>
      ) : null}
      {files.length > 0 ? (
        <ul className="space-y-1">
          {files.map((row) => (
            <li key={row.upload}>
              <a
                href={formUploadUrl(row.upload)}
                className="inline-flex items-center gap-1.5 text-action hover:underline"
              >
                <Download className="size-3.5" aria-hidden="true" />
                {row.caption || row.filename || 'File'}
              </a>
            </li>
          ))}
        </ul>
      ) : null}
      {extraFields.length > 0 && dsr.extra_answers ? (
        <FieldRenderer fields={extraFields} values={dsr.extra_answers} readOnly />
      ) : null}
    </div>
  );
}
