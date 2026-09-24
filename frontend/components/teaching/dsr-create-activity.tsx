'use client';

/**
 * "Create activity from this class" — spins a follow-on activity (mentoring,
 * a warning, a placement call…) straight off one class's report, for a
 * student on this class's own batch roster, without sending the trainer or
 * manager to the activities workspace to find them first.
 *
 * `POST /api/v1/dsr/{id}/create-activity/` (ERP Phase 15) is a second front
 * door onto the same activity engine Phase 9 built (`lib/work.ts`) — the
 * response is the same `ActivityDetail` shape `POST /activities/` returns,
 * and the success link below reuses the `/activities?id=` deep link the
 * global search backend already emits for an activity hit
 * (`apps/search/services.py::_activities`). That link is currently inert —
 * `/activities` opens a row's detail from in-page selection state, not a
 * query param — a limitation Phase 11 already noted and this phase does not
 * fix; the link is still worth showing, since even an inert one names
 * exactly what was created.
 *
 * The student list comes from `getBatchRoster` (`lib/batches.ts`), the same
 * roster the batch-detail screen's own roster view fetches — not from this
 * screen's already-loaded register: a `RegisterEntry` (`register-editor
 * .tsx`) carries an enrollment id and a display code, never the real student
 * id this endpoint needs (see `types/api.ts`'s `RegisterEntry` vs.
 * `RosterEntry`). Activity types come from `lib/work.ts::listActivityTypes`
 * — Phase 9's own list, not a second copy.
 */
import { useRef, useState, type FormEvent } from 'react';

import { Alert } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import { Field } from '@/components/ui/field';
import { Input, Select } from '@/components/ui/input';
import { ApiError, fieldErrors } from '@/lib/api';
import { getBatchRoster } from '@/lib/batches';
import { createActivityFromDsr } from '@/lib/dsr';
import { listActivityTypes } from '@/lib/work';
import type { ActivityDetail, ActivityType, RosterEntry } from '@/types/api';

interface DsrCreateActivityProps {
  dsrId: string;
  batchId: string;
}

interface OptionsState {
  roster: RosterEntry[];
  types: ActivityType[];
  error: string | null;
  isLoading: boolean;
}

function emptyForm() {
  return { student: '', activityType: '', title: '', dueInDays: '' };
}

export function DsrCreateActivity({ dsrId, batchId }: DsrCreateActivityProps) {
  const [isOpen, setIsOpen] = useState(false);
  const [options, setOptions] = useState<OptionsState>({ roster: [], types: [], error: null, isLoading: false });
  const [form, setForm] = useState(emptyForm());
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [isSaving, setIsSaving] = useState(false);
  const [created, setCreated] = useState<ActivityDetail | null>(null);
  // Guards a fetch started by a since-closed-and-reopened form from
  // overwriting state for the form the person is now looking at — the same
  // "own the latest request" pattern `hooks/use-api.ts`'s `requestKey` uses,
  // sized down for a one-shot fetch with no key to compare, just a token.
  const loadToken = useRef(0);

  function loadOptions() {
    const token = ++loadToken.current;
    setOptions({ roster: [], types: [], error: null, isLoading: true });
    Promise.all([getBatchRoster(batchId), listActivityTypes()])
      .then(([roster, typesResponse]) => {
        if (loadToken.current !== token) return;
        setOptions({ roster, types: typesResponse.results, error: null, isLoading: false });
      })
      .catch((cause: unknown) => {
        if (loadToken.current !== token) return;
        const message =
          cause instanceof ApiError ? cause.message : 'Could not load the student list and activity types.';
        setOptions({ roster: [], types: [], error: message, isLoading: false });
      });
  }

  function reset() {
    setForm(emptyForm());
    setErrors({});
    setCreated(null);
  }

  function open() {
    reset();
    setIsOpen(true);
    loadOptions();
  }

  function close() {
    setIsOpen(false);
    reset();
  }

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    const nextErrors: Record<string, string> = {};
    if (!form.student) nextErrors.student = 'Choose a student.';
    if (!form.activityType) nextErrors.activity_type = 'Choose an activity type.';
    if (Object.keys(nextErrors).length > 0) {
      setErrors(nextErrors);
      return;
    }

    setErrors({});
    setIsSaving(true);
    try {
      const activity = await createActivityFromDsr(dsrId, {
        student: form.student,
        activity_type: form.activityType,
        title: form.title.trim() || undefined,
        due_in_days: form.dueInDays.trim() ? Number(form.dueInDays) : undefined,
      });
      setCreated(activity);
    } catch (cause) {
      setErrors(fieldErrors(cause));
    } finally {
      setIsSaving(false);
    }
  }

  if (!isOpen) {
    return (
      <Button type="button" variant="outline" size="sm" onClick={open}>
        Create activity from this class
      </Button>
    );
  }

  if (created) {
    return (
      <Alert variant="success" className="space-y-1.5">
        <p className="font-medium">Activity created.</p>
        <p>
          <a href={`/activities?id=${created.id}`} className="underline underline-offset-2">
            {created.title}
          </a>
        </p>
        <Button type="button" variant="ghost" size="sm" onClick={close}>
          Done
        </Button>
      </Alert>
    );
  }

  return (
    <form
      onSubmit={(event) => void onSubmit(event)}
      aria-label="Create activity from this class"
      className="space-y-4 rounded-[var(--radius-card)] border border-border p-4"
      // The browser's own required-field validation would otherwise block
      // the `submit` event entirely on an empty required `<select>` and show
      // its own bubble instead of this form's inline errors below — the
      // student and activity type fields still carry `required` for the
      // visual asterisk and assistive tech, but this form owns the actual
      // validation message.
      noValidate
    >
      {errors.__all__ ? <Alert variant="error">{errors.__all__}</Alert> : null}
      {options.error ? (
        <Alert variant="error">{options.error}</Alert>
      ) : options.isLoading ? (
        <p className="text-sm text-muted-foreground">Loading students and activity types…</p>
      ) : null}

      <Field label="Student" htmlFor="dsr-activity-student" error={errors.student} required>
        <Select
          disabled={options.isLoading || Boolean(options.error)}
          value={form.student}
          onChange={(event) => setForm((current) => ({ ...current, student: event.target.value }))}
        >
          <option value="">Choose a student…</option>
          {options.roster.map((entry) => (
            <option key={entry.student_id} value={entry.student_id}>
              {entry.full_name} ({entry.student_code})
            </option>
          ))}
        </Select>
      </Field>

      <Field label="Activity type" htmlFor="dsr-activity-type" error={errors.activity_type} required>
        <Select
          disabled={options.isLoading || Boolean(options.error)}
          value={form.activityType}
          onChange={(event) => setForm((current) => ({ ...current, activityType: event.target.value }))}
        >
          <option value="">Choose an activity type…</option>
          {options.types.map((type) => (
            <option key={type.slug} value={type.slug}>
              {type.name}
            </option>
          ))}
        </Select>
      </Field>

      <Field label="Title" htmlFor="dsr-activity-title" error={errors.title} hint="Optional — the activity type suggests one if left blank.">
        <Input
          value={form.title}
          maxLength={200}
          onChange={(event) => setForm((current) => ({ ...current, title: event.target.value }))}
        />
      </Field>

      <Field label="Due in (days)" htmlFor="dsr-activity-due" error={errors.due_in_days} hint="Optional.">
        <Input
          type="number"
          inputMode="numeric"
          min={0}
          value={form.dueInDays}
          onChange={(event) => setForm((current) => ({ ...current, dueInDays: event.target.value }))}
        />
      </Field>

      <div className="flex gap-2">
        <Button type="submit" disabled={isSaving}>
          {isSaving ? 'Creating…' : 'Create activity'}
        </Button>
        <Button type="button" variant="outline" disabled={isSaving} onClick={close}>
          Cancel
        </Button>
      </div>
    </form>
  );
}
