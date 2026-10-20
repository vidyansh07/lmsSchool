'use client';

/**
 * Suspending or withdrawing one enrolment, asked before it happens.
 *
 * Withdrawing is terminal on the server (`apps/enrollments/services.py`
 * TRANSITIONS: cancelled → nothing), so a stray click used to end a student's
 * place on a batch for good. Suspending is reversible but takes them off the
 * register, which a counsellor should not do by accident either. Both now say
 * what will happen, and a withdrawal asks why — the reason is stored on the
 * enrolment as its status note and in the audit trail.
 *
 * Reactivating needs none of this: it is the undo, and it is safe to repeat.
 */

import { useState } from 'react';

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
import { Input } from '@/components/ui/input';
import { errorMessage } from '@/lib/api';
import { setEnrollmentStatus } from '@/lib/batches';

export interface EnrollmentStatusChange {
  enrollmentId: string;
  /** Who and where, in the person's own words: "Asha Rao on DEVOPS-JAN". */
  subject: string;
  status: 'suspended' | 'cancelled';
}

const COPY = {
  suspended: {
    title: 'Suspend this enrolment?',
    consequence:
      'They come off the class register and lose access to this batch until somebody reactivates them. You can reactivate at any time.',
    confirm: 'Suspend',
    busy: 'Suspending…',
  },
  cancelled: {
    title: 'Withdraw from this batch?',
    consequence:
      'This ends the enrolment for good. Attendance, progress and fees stay on record, but it cannot be reopened — coming back later means a new enrolment.',
    confirm: 'Withdraw',
    busy: 'Withdrawing…',
  },
} as const;

export function EnrollmentStatusDialog({
  change,
  onClose,
  onChanged,
}: {
  change: EnrollmentStatusChange | null;
  onClose: () => void;
  onChanged: () => void;
}) {
  return (
    <Dialog open={change !== null} onOpenChange={(open) => (open ? undefined : onClose())}>
      <DialogContent size="md">
        {change ? (
          <ChangeForm key={`${change.enrollmentId}:${change.status}`} change={change} onClose={onClose} onChanged={onChanged} />
        ) : null}
      </DialogContent>
    </Dialog>
  );
}

function ChangeForm({
  change,
  onClose,
  onChanged,
}: {
  change: EnrollmentStatusChange;
  onClose: () => void;
  onChanged: () => void;
}) {
  const copy = COPY[change.status];
  const reasonRequired = change.status === 'cancelled';
  const [reason, setReason] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (reasonRequired && !reason.trim()) return;
    setBusy(true);
    setError('');
    try {
      await setEnrollmentStatus(change.enrollmentId, change.status, reason.trim());
      onChanged();
      onClose();
    } catch (cause) {
      setError(errorMessage(cause, 'Could not update this enrolment.'));
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={(event) => void submit(event)} noValidate>
      <DialogHeader>
        <DialogTitle>{copy.title}</DialogTitle>
        <DialogDescription>{change.subject}</DialogDescription>
      </DialogHeader>
      <div className="space-y-4">
        {error ? <Alert variant="error">{error}</Alert> : null}
        <Alert variant={change.status === 'cancelled' ? 'warning' : 'info'}>{copy.consequence}</Alert>
        <Field
          label="Reason"
          htmlFor="enrollment-status-reason"
          hint={reasonRequired ? 'Required. Kept with the enrolment and in its history.' : 'Optional. Kept with the enrolment.'}
          required={reasonRequired}
        >
          <Input
            id="enrollment-status-reason"
            value={reason}
            maxLength={255}
            onChange={(event) => setReason(event.target.value)}
          />
        </Field>
      </div>
      <DialogFooter>
        <Button type="button" variant="outline" disabled={busy} onClick={onClose}>
          Keep enrolment
        </Button>
        <Button
          type="submit"
          variant={change.status === 'cancelled' ? 'destructive' : 'primary'}
          disabled={busy || (reasonRequired && !reason.trim())}
        >
          {busy ? copy.busy : copy.confirm}
        </Button>
      </DialogFooter>
    </form>
  );
}
