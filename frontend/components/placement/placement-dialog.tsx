'use client';

/**
 * Recording an offer, or changing one already recorded.
 *
 * The house dialog pattern (`ReviewDialog`, `SetFeeDialog`): a controlled
 * `open`, the record being edited or `null` to record a new one, and the form
 * mounted only while open so every opening starts from that record as it now
 * is.
 *
 * Two rules the form states because the server enforces them, and a message
 * beside the field beats a 400 somebody has to decipher:
 *
 * * an offer marked "joined" needs the date they joined;
 * * an offer that was declined or withdrawn has no joining date.
 *
 * The student is chosen only when recording. An offer filed against the wrong
 * person is withdrawn and recorded again, so the first student's record keeps
 * the history of what was done about them — the API has no field for moving
 * one, and neither does this.
 */
import { useState, type FormEvent } from 'react';

import { StudentPicker } from '@/components/placement/student-picker';
import { Alert } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Field } from '@/components/ui/field';
import { Input, Select, Textarea } from '@/components/ui/input';
import { fieldErrors, unshownError } from '@/lib/api';
import { PLACEMENT_STATUS_OPTIONS } from '@/lib/placement-labels';
import { recordPlacement, updatePlacement } from '@/lib/placements';
import type { Placement, PlacementStatus } from '@/types/api';

const SHOWN_FIELDS = [
  'student',
  'company',
  'role_title',
  'location',
  'status',
  'annual_package',
  'offered_on',
  'joined_on',
  'notes',
] as const;

interface FormState {
  student: string;
  studentLabel: string;
  company: string;
  role_title: string;
  location: string;
  status: PlacementStatus;
  annual_package: string;
  offered_on: string;
  joined_on: string;
  notes: string;
}

function formFrom(placement: Placement | null): FormState {
  if (!placement) {
    return {
      student: '',
      studentLabel: '',
      company: '',
      role_title: '',
      location: '',
      status: 'offered',
      annual_package: '',
      offered_on: '',
      joined_on: '',
      notes: '',
    };
  }
  return {
    student: placement.student_id,
    studentLabel: placement.student_name,
    company: placement.company,
    role_title: placement.role_title,
    location: placement.location,
    status: placement.status,
    annual_package: placement.annual_package ?? '',
    offered_on: placement.offered_on,
    joined_on: placement.joined_on ?? '',
    notes: placement.notes,
  };
}

/** The rules the server enforces, so nobody has to meet them as a 400. */
export function placementErrors(form: FormState, isNew: boolean): Record<string, string> {
  const errors: Record<string, string> = {};
  if (isNew && !form.student) errors.student = 'Choose the student this offer is for.';
  if (!form.company.trim()) errors.company = 'Name the company.';
  if (!form.role_title.trim()) errors.role_title = 'Name the role.';
  if (!form.offered_on) errors.offered_on = 'Say when the offer was made.';
  if (form.status === 'joined' && !form.joined_on) {
    errors.joined_on = 'Say when they joined.';
  }
  if (form.joined_on && (form.status === 'declined' || form.status === 'withdrawn')) {
    errors.joined_on = 'An offer that was declined or withdrawn has no joining date.';
  }
  return errors;
}

export function PlacementDialog({
  placement,
  open,
  onClose,
  onSaved,
}: {
  /** `null` records a new offer; a row edits that one. */
  placement: Placement | null;
  open: boolean;
  onClose: () => void;
  onSaved: () => void;
}) {
  const isNew = placement === null;
  const [form, setForm] = useState<FormState>(() => formFrom(placement));
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState(false);

  function set<K extends keyof FormState>(key: K, value: FormState[K]) {
    setForm((current) => ({ ...current, [key]: value }));
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    const found = placementErrors(form, isNew);
    if (Object.keys(found).length > 0) {
      setErrors(found);
      return;
    }
    setSaving(true);
    setErrors({});
    const body = {
      company: form.company.trim(),
      role_title: form.role_title.trim(),
      location: form.location.trim(),
      status: form.status,
      annual_package: form.annual_package ? form.annual_package : null,
      offered_on: form.offered_on,
      joined_on: form.joined_on ? form.joined_on : null,
      notes: form.notes,
    };
    try {
      if (isNew) {
        await recordPlacement({ student: form.student, ...body });
      } else {
        await updatePlacement(placement.id, body);
      }
      onSaved();
      onClose();
    } catch (cause) {
      setErrors(fieldErrors(cause));
    } finally {
      setSaving(false);
    }
  }

  const stray = unshownError(errors, SHOWN_FIELDS);

  return (
    <Dialog open={open} onOpenChange={(next) => (next ? undefined : onClose())}>
      <DialogContent>
        <form onSubmit={submit}>
          <DialogHeader>
            <DialogTitle>{isNew ? 'Record an offer' : `${placement.company} offer`}</DialogTitle>
            <DialogDescription>
              {isNew
                ? 'One row per offer — four interviews and one job is four of these.'
                : `For ${placement.student_name}.`}
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-4 py-4">
            {stray ? <Alert variant="error">{stray}</Alert> : null}

            {isNew ? (
              <Field label="Student" htmlFor="placement-student" error={errors.student}>
                <StudentPicker
                  id="placement-student"
                  value={form.student}
                  label={form.studentLabel}
                  onChange={(id, name) => {
                    setForm((current) => ({ ...current, student: id, studentLabel: name }));
                  }}
                />
              </Field>
            ) : null}

            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="Company" htmlFor="placement-company" error={errors.company}>
                <Input
                  id="placement-company"
                  value={form.company}
                  onChange={(event) => set('company', event.target.value)}
                />
              </Field>
              <Field label="Role" htmlFor="placement-role" error={errors.role_title}>
                <Input
                  id="placement-role"
                  value={form.role_title}
                  onChange={(event) => set('role_title', event.target.value)}
                />
              </Field>
              <Field label="Location" htmlFor="placement-location" error={errors.location}>
                <Input
                  id="placement-location"
                  value={form.location}
                  onChange={(event) => set('location', event.target.value)}
                />
              </Field>
              <Field
                label="Annual package"
                htmlFor="placement-package"
                hint="In rupees. Blank if it has not been stated."
                error={errors.annual_package}
              >
                <Input
                  id="placement-package"
                  type="number"
                  min={0}
                  step="1000"
                  value={form.annual_package}
                  onChange={(event) => set('annual_package', event.target.value)}
                />
              </Field>
              <Field label="Status" htmlFor="placement-status" error={errors.status}>
                <Select
                  id="placement-status"
                  value={form.status}
                  onChange={(event) => set('status', event.target.value as PlacementStatus)}
                >
                  {PLACEMENT_STATUS_OPTIONS.map((option) => (
                    <option key={option.value} value={option.value}>
                      {option.label}
                    </option>
                  ))}
                </Select>
              </Field>
              <Field label="Offered on" htmlFor="placement-offered" error={errors.offered_on}>
                <Input
                  id="placement-offered"
                  type="date"
                  value={form.offered_on}
                  onChange={(event) => set('offered_on', event.target.value)}
                />
              </Field>
              <Field label="Joined on" htmlFor="placement-joined" error={errors.joined_on}>
                <Input
                  id="placement-joined"
                  type="date"
                  value={form.joined_on}
                  onChange={(event) => set('joined_on', event.target.value)}
                />
              </Field>
            </div>

            <Field
              label="Notes"
              htmlFor="placement-notes"
              hint="Why it was declined, who the contact was — anything worth keeping."
              error={errors.notes}
            >
              <Textarea
                id="placement-notes"
                rows={3}
                value={form.notes}
                onChange={(event) => set('notes', event.target.value)}
              />
            </Field>
          </div>

          <DialogFooter>
            <Button type="button" variant="ghost" onClick={onClose} disabled={saving}>
              Cancel
            </Button>
            <Button type="submit" disabled={saving}>
              {saving ? 'Saving…' : isNew ? 'Record offer' : 'Save changes'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
