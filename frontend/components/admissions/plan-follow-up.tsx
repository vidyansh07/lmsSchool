'use client';

/**
 * "Plan a follow-up" on the student record — `USER_JOURNEYS.md` §4.3.
 *
 * `POST /api/v1/students/{id}/follow-ups/` (ERP Phase 17) is another front
 * door onto the same activity engine Phase 9 built and Phase 15's DSR
 * follow-on already reuses (`components/teaching/dsr-create-activity.tsx`):
 * the server routes this through the real `apps.work.services.create_activity`
 * rather than a direct model write, so the response is the same
 * `ActivityDetail` shape `POST /activities/` returns, and the success link
 * below reuses that same component's `/activities?id=` deep link — still
 * inert per Phase 11's own noted limitation, not fixed here.
 */
import { useState, type FormEvent } from 'react';

import { Alert } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Field } from '@/components/ui/field';
import { Input, Select } from '@/components/ui/input';
import { isoToday } from '@/lib/batch-labels';
import { fieldErrors } from '@/lib/api';
import { ACTIVITY_PRIORITY_LABEL } from '@/lib/labels';
import { createFollowUp } from '@/lib/people';
import type { ActivityDetail, ActivityPriority } from '@/types/api';

function defaultDueAt(): string {
  // Tomorrow, 09:00 — a reasonable default for "sometime soon", never blank:
  // `due_at` is required by the endpoint's contract, and starting the field
  // empty would just move that requirement onto whoever opens the dialog.
  const tomorrow = new Date();
  tomorrow.setDate(tomorrow.getDate() + 1);
  const yyyy = tomorrow.getFullYear();
  const mm = String(tomorrow.getMonth() + 1).padStart(2, '0');
  const dd = String(tomorrow.getDate()).padStart(2, '0');
  return `${yyyy}-${mm}-${dd}T09:00`;
}

function PlanFollowUpForm({
  studentId,
  onOpenChange,
  onCreated,
}: {
  studentId: string;
  onOpenChange: (open: boolean) => void;
  onCreated: (activity: ActivityDetail) => void;
}) {
  const [dueAt, setDueAt] = useState(defaultDueAt());
  const [priority, setPriority] = useState<ActivityPriority>('normal');
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [isSaving, setIsSaving] = useState(false);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    if (!dueAt) {
      setErrors({ due_at: 'A due date is required.' });
      return;
    }
    setErrors({});
    setIsSaving(true);
    try {
      const activity = await createFollowUp(studentId, {
        due_at: new Date(dueAt).toISOString(),
        priority,
      });
      onCreated(activity);
    } catch (cause) {
      setErrors(fieldErrors(cause));
    } finally {
      setIsSaving(false);
    }
  }

  return (
    <form onSubmit={(event) => void onSubmit(event)} noValidate>
      <DialogHeader>
        <DialogTitle>Plan a follow-up</DialogTitle>
      </DialogHeader>
      <div className="space-y-4">
        {errors.__all__ ? <Alert variant="error">{errors.__all__}</Alert> : null}
        <Field label="Due" htmlFor="follow-up-due-at" error={errors.due_at} required>
          <Input
            id="follow-up-due-at"
            type="datetime-local"
            min={`${isoToday()}T00:00`}
            autoFocus
            value={dueAt}
            onChange={(event) => setDueAt(event.target.value)}
          />
        </Field>
        <Field label="Priority" htmlFor="follow-up-priority" error={errors.priority}>
          <Select
            id="follow-up-priority"
            value={priority}
            onChange={(event) => setPriority(event.target.value as ActivityPriority)}
          >
            {(Object.keys(ACTIVITY_PRIORITY_LABEL) as ActivityPriority[]).map((value) => (
              <option key={value} value={value}>
                {ACTIVITY_PRIORITY_LABEL[value]}
              </option>
            ))}
          </Select>
        </Field>
      </div>
      <DialogFooter>
        <Button type="button" variant="ghost" disabled={isSaving} onClick={() => onOpenChange(false)}>
          Cancel
        </Button>
        <Button type="submit" disabled={isSaving || !dueAt}>
          {isSaving ? 'Creating…' : 'Create follow-up'}
        </Button>
      </DialogFooter>
    </form>
  );
}

function PlanFollowUpSuccess({
  activity,
  onClose,
}: {
  activity: ActivityDetail;
  onClose: () => void;
}) {
  return (
    <div className="space-y-3">
      <DialogHeader>
        <DialogTitle>Follow-up created</DialogTitle>
      </DialogHeader>
      <Alert variant="success" role="status">
        <a href={`/activities?id=${activity.id}`} className="underline underline-offset-2">
          {activity.title}
        </a>
      </Alert>
      <DialogFooter>
        <Button type="button" onClick={onClose}>
          Done
        </Button>
      </DialogFooter>
    </div>
  );
}

export function PlanFollowUp({
  studentId,
  onCreated,
}: {
  studentId: string;
  /** Called after a successful create, so the caller can refresh whatever
   *  activity/timeline list it shows — this dialog does not know of one. */
  onCreated?: () => void;
}) {
  const [isOpen, setIsOpen] = useState(false);
  const [created, setCreated] = useState<ActivityDetail | null>(null);

  function openChange(open: boolean) {
    setIsOpen(open);
    if (!open) setCreated(null);
  }

  return (
    <>
      <Button type="button" variant="outline" size="sm" onClick={() => openChange(true)}>
        Plan a follow-up
      </Button>
      <Dialog open={isOpen} onOpenChange={openChange}>
        <DialogContent>
          {!isOpen ? null : created ? (
            <PlanFollowUpSuccess activity={created} onClose={() => openChange(false)} />
          ) : (
            <PlanFollowUpForm
              studentId={studentId}
              onOpenChange={openChange}
              onCreated={(activity) => {
                setCreated(activity);
                onCreated?.();
              }}
            />
          )}
        </DialogContent>
      </Dialog>
    </>
  );
}
