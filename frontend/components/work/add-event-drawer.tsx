'use client';

/**
 * Add Event: the drawer the reference CRM opens from a lead or a student —
 * the event type, a subject line, the From/To it runs between, a reminder,
 * who owns it, who organised it, whatever extra fields that event type asks
 * for, and a description.
 *
 * Three decisions worth stating:
 *
 * **The subject is prefilled and editable.** "Technical Talk with Trainer:
 * Himanshu Verma" is what the original writes, and it is right nine times in
 * ten; typing it out every time is the tenth.
 *
 * **To follows From by the type's own default duration.** A five-minute call
 * and a ninety-minute mock interview are both "an event", and the type is
 * where that difference already lives. Touching the To time stops it
 * following, because at that point the person is telling us the length.
 *
 * **Organiser is whoever is adding it, and cannot be changed.** The server
 * sets `created_by` from the session; a box offering to change it would be a
 * lie. Owner is the one that *is* a choice — it is who the work is assigned
 * to — and the server still re-checks that the person may hold it.
 *
 * The extra fields come from the event type's pinned form, so Calendar Pro's
 * "Manage Fields" is what decides them. They are sent as `form_prefill`:
 * suggested answers for whoever completes the event, not a completed form.
 */

import { useId, useMemo, useState } from 'react';

import { useAuth } from '@/components/auth-provider';
import { usePublishedFields } from '@/components/automation/use-published-fields';
import { FieldRenderer, type FormValues } from '@/components/forms/field-renderer';
import { Alert } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import { Field } from '@/components/ui/field';
import { Input, Select, Textarea } from '@/components/ui/input';
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetFooter,
  SheetHeader,
  SheetTitle,
} from '@/components/ui/sheet';
import { Switch } from '@/components/ui/switch';
import { useApi } from '@/hooks/use-api';
import { fieldErrors } from '@/lib/api';
import { createActivity, type ActivityTypeListResponse } from '@/lib/work';
import type { ActivityType, User } from '@/types/api';

/** The reminder offsets the original offers, in minutes. */
const REMINDERS = [5, 10, 15, 30, 60, 24 * 60] as const;

function reminderLabel(minutes: number): string {
  if (minutes < 60) return `${minutes} minutes before`;
  if (minutes === 60) return '1 hour before';
  if (minutes < 24 * 60) return `${minutes / 60} hours before`;
  return '1 day before';
}

/** `<input type="datetime-local">` takes local time, not UTC. */
function toLocalInput(date: Date): string {
  const offset = date.getTimezoneOffset() * 60_000;
  return new Date(date.getTime() - offset).toISOString().slice(0, 16);
}

function plusMinutes(value: string, minutes: number): string {
  const start = new Date(value);
  if (Number.isNaN(start.getTime())) return '';
  return toLocalInput(new Date(start.getTime() + minutes * 60_000));
}

/** The timezone this browser is in, named the way a calendar names it. */
function zoneLabel(): string {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || 'Local time';
  } catch {
    return 'Local time';
  }
}

export function AddEventDrawer({
  open,
  onClose,
  onCreated,
  subject,
  owners = [],
}: {
  open: boolean;
  onClose: () => void;
  onCreated: () => void;
  /** Who the event is about: a lead, or a student with their enrolment. */
  subject:
    | { kind: 'enquiry'; id: string; name: string }
    | { kind: 'student'; id: string; name: string; enrollment?: string };
  /** People the event may be assigned to. Empty means "assign it to me". */
  owners?: Pick<User, 'id' | 'full_name' | 'email'>[];
}) {
  const uid = useId();
  const { user } = useAuth();
  const { data } = useApi<ActivityTypeListResponse>('/api/v1/activity-types/');

  const types = useMemo(
    () =>
      (data?.results ?? []).filter(
        (type) => type.status === 'active' && type.subject === subject.kind,
      ),
    [data, subject.kind],
  );

  const [slug, setSlug] = useState('');
  const [title, setTitle] = useState('');
  const [titleTouched, setTitleTouched] = useState(false);
  const [from, setFrom] = useState(() => toLocalInput(new Date()));
  const [to, setTo] = useState('');
  const [toTouched, setToTouched] = useState(false);
  const [reminderOn, setReminderOn] = useState(true);
  const [reminder, setReminder] = useState(5);
  const [owner, setOwner] = useState('');
  const [answers, setAnswers] = useState<FormValues>({});
  const [description, setDescription] = useState('');
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState(false);

  const chosen: ActivityType | undefined =
    types.find((type) => type.slug === slug) ?? types[0];
  const extraFields = usePublishedFields(chosen?.form ?? null);

  // The subject line and the To time follow the chosen event type until the
  // person edits them, at which point what they typed wins. Derived from the
  // type rather than written into state by an effect.
  const suggestedTitle = chosen ? `${chosen.name}: ${subject.name}` : '';
  const shownTitle = titleTouched ? title : suggestedTitle;
  const suggestedTo = chosen?.default_duration_minutes
    ? plusMinutes(from, chosen.default_duration_minutes)
    : from;
  const shownTo = toTouched ? to : suggestedTo;
  const suggestedReminder = chosen?.reminder_minutes_before ?? 5;

  // Opening the drawer again is a fresh event, not the last one's leftovers.
  // Reset during render against a key rather than from an effect — the same
  // convention `app/admin/activity-types/page.tsx` uses, and for the same
  // reason: typing inside the drawer is then never clobbered by an unrelated
  // re-render.
  const resetKey = `${open}#${subject.id}`;
  const [openedFor, setOpenedFor] = useState(resetKey);
  if (openedFor !== resetKey) {
    setTitleTouched(false);
    setToTouched(false);
    setAnswers({});
    setDescription('');
    setErrors({});
    setFrom(toLocalInput(new Date()));
    setOpenedFor(resetKey);
  }

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    const problems: Record<string, string> = {};
    if (!chosen) problems.activity_type = 'Pick what kind of event this is.';
    if (!shownTitle.trim()) problems.title = 'Give the event a subject.';
    if (!from) problems.planned_at = 'Say when it starts.';
    if (from && shownTo && new Date(shownTo) < new Date(from)) {
      problems.due_at = 'It cannot end before it starts.';
    }
    if (Object.keys(problems).length > 0) {
      setErrors(problems);
      return;
    }

    const start = new Date(from);
    const end = shownTo ? new Date(shownTo) : start;
    setSaving(true);
    setErrors({});
    try {
      await createActivity({
        activity_type: chosen!.slug,
        ...(subject.kind === 'enquiry'
          ? { enquiry: subject.id }
          : { student: subject.id, enrollment: subject.enrollment }),
        title: shownTitle.trim(),
        summary: description.trim(),
        assigned_to: owner || user?.id,
        planned_at: start.toISOString(),
        due_at: end.toISOString(),
        duration_minutes: Math.max(0, Math.round((end.getTime() - start.getTime()) / 60_000)),
        // 0 is "no reminder for this one", which the type's default cannot say.
        reminder_minutes_before: reminderOn ? reminder : 0,
        form_prefill: Object.keys(answers).length > 0 ? answers : undefined,
      });
      onCreated();
    } catch (cause) {
      setErrors(fieldErrors(cause));
    } finally {
      setSaving(false);
    }
  }

  return (
    <Sheet open={open} onOpenChange={(next) => (next ? undefined : onClose())}>
      <SheetContent size="lg">
        {/* No browser validation: a rule the browser enforces refuses the
            submit with nothing on screen saying why. */}
        <form className="flex h-full flex-col" onSubmit={(event) => void submit(event)} noValidate>
          <SheetHeader>
            <SheetTitle>Events{chosen ? ` — ${chosen.name}` : ''}</SheetTitle>
            <SheetDescription>
              For {subject.name}. Assigned to its owner, who is told about it.
            </SheetDescription>
          </SheetHeader>

          <div className="flex-1 space-y-4 overflow-y-auto px-1 py-4">
            {errors.__all__ ? <Alert variant="error">{errors.__all__}</Alert> : null}

            <Field label="Event" htmlFor={`${uid}-type`} error={errors.activity_type} required>
              <Select
                id={`${uid}-type`}
                value={chosen?.slug ?? ''}
                onChange={(event) => setSlug(event.target.value)}
              >
                {types.length === 0 ? <option value="">No events set up yet</option> : null}
                {types.map((type) => (
                  <option key={type.slug} value={type.slug}>
                    {type.name}
                  </option>
                ))}
              </Select>
            </Field>

            <Field label="Subject" htmlFor={`${uid}-title`} error={errors.title} required>
              <Input
                id={`${uid}-title`}
                value={shownTitle}
                onChange={(event) => {
                  setTitleTouched(true);
                  setTitle(event.target.value);
                }}
              />
            </Field>

            <fieldset className="space-y-3 rounded-card border border-line p-3">
              <legend className="px-1 text-sm font-medium">Event Duration</legend>
              <div className="grid gap-3 sm:grid-cols-2">
                <Field label="From" htmlFor={`${uid}-from`} error={errors.planned_at} required>
                  <Input
                    id={`${uid}-from`}
                    type="datetime-local"
                    value={from}
                    onChange={(event) => setFrom(event.target.value)}
                  />
                </Field>
                <Field label="To" htmlFor={`${uid}-to`} error={errors.due_at}>
                  <Input
                    id={`${uid}-to`}
                    type="datetime-local"
                    value={shownTo}
                    onChange={(event) => {
                      setToTouched(true);
                      setTo(event.target.value);
                    }}
                  />
                </Field>
              </div>
              <p className="text-xs text-ink-muted">
                {zoneLabel()}
                {chosen?.default_duration_minutes && !toTouched
                  ? ` · ${chosen.default_duration_minutes} minutes, from this event's settings`
                  : ''}
              </p>
            </fieldset>

            <div className="space-y-3 rounded-card border border-line p-3">
              <div className="flex items-center justify-between gap-3">
                <div>
                  <p className="text-sm font-medium">Reminder</p>
                  <p className="text-xs text-ink-muted">
                    Notifies the owner in the app. Off means no reminder for this one, whatever
                    the event type says.
                  </p>
                </div>
                <Switch
                  aria-label="Reminder"
                  checked={reminderOn}
                  onCheckedChange={setReminderOn}
                />
              </div>
              {reminderOn ? (
                <Field label="When" htmlFor={`${uid}-reminder`} error={errors.reminder_minutes_before}>
                  <Select
                    id={`${uid}-reminder`}
                    value={String(reminder || suggestedReminder)}
                    onChange={(event) => setReminder(Number(event.target.value))}
                  >
                    {REMINDERS.map((minutes) => (
                      <option key={minutes} value={minutes}>
                        {reminderLabel(minutes)}
                      </option>
                    ))}
                  </Select>
                </Field>
              ) : null}
            </div>

            <div className="grid gap-3 sm:grid-cols-2">
              <Field label="Owner" htmlFor={`${uid}-owner`} error={errors.assigned_to} required>
                <Select
                  id={`${uid}-owner`}
                  value={owner || user?.id || ''}
                  onChange={(event) => setOwner(event.target.value)}
                >
                  <option value={user?.id ?? ''}>{user?.full_name || 'Me'}</option>
                  {owners
                    .filter((person) => person.id !== user?.id)
                    .map((person) => (
                      <option key={person.id} value={person.id}>
                        {person.full_name || person.email}
                      </option>
                    ))}
                </Select>
              </Field>
              <Field
                label="Organiser"
                htmlFor={`${uid}-organiser`}
                hint="Whoever is adding it. The server records this from the session."
              >
                <Input id={`${uid}-organiser`} value={user?.full_name || ''} disabled />
              </Field>
            </div>

            {extraFields.length > 0 ? (
              <fieldset className="space-y-3 rounded-card border border-line p-3">
                <legend className="px-1 text-sm font-medium">
                  {chosen?.name} fields
                </legend>
                <p className="text-xs text-ink-muted">
                  Suggested answers for whoever completes this event. They can change them.
                </p>
                <FieldRenderer
                  fields={extraFields}
                  values={answers}
                  onChange={(key, value) =>
                    setAnswers((current: FormValues) => ({ ...current, [key]: value }))
                  }
                  errors={errors}
                />
              </fieldset>
            ) : null}

            <Field label="Description" htmlFor={`${uid}-description`} error={errors.summary}>
              <Textarea
                id={`${uid}-description`}
                rows={4}
                value={description}
                placeholder="What this is about, and anything the owner should know first."
                onChange={(event) => setDescription(event.target.value)}
              />
            </Field>
          </div>

          <SheetFooter>
            <Button type="button" variant="ghost" onClick={onClose}>
              Cancel
            </Button>
            <Button type="submit" disabled={saving || types.length === 0}>
              {saving ? 'Submitting…' : 'Submit'}
            </Button>
          </SheetFooter>
        </form>
      </SheetContent>
    </Sheet>
  );
}
