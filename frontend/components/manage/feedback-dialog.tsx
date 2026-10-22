'use client';

/**
 * Leaving one piece of feedback about a student: a line after a class, a
 * remark worth recording.
 *
 * `POST /performance/feedback/` has existed since the performance phase and
 * no screen ever called it — feedback could be read on the student's record
 * and on the student's own dashboard, and written only through the API. This
 * is that write, in the house dialog pattern (`ReviewDialog`,
 * `SetFeeDialog`): a controlled `open`, the form mounted only while open so
 * every opening starts blank, and the caller reloading its own list on
 * success.
 *
 * Feedback is deliberately lighter than a `PerformanceReview` — one remark,
 * no rating, no period, no snapshot — so this form is one textarea and one
 * decision: may the student read it. That second one is the field that keeps
 * feedback from being redundant with a review, and it is stated in the words
 * it means ("Show this to the student") rather than as the API's
 * `visible_to_subject`.
 *
 * Authority is `review.manage_any`, checked by the server on the way in. The
 * caller hides the button without it; this component does not re-check,
 * because a second client-side check in two places is two places to get it
 * wrong, and neither is the control.
 */
import { useState, type FormEvent } from 'react';

import { Alert } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import { Checkbox } from '@/components/ui/checkbox';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Field } from '@/components/ui/field';
import { Textarea } from '@/components/ui/input';
import { fieldErrors, unshownError } from '@/lib/api';
import { createFeedback } from '@/lib/manage';

const SHOWN_FIELDS = ['body', 'visible_to_subject'] as const;

export function FeedbackDialog({
  studentId,
  studentName,
  open,
  onClose,
  onSaved,
}: {
  studentId: string;
  /** Named in the dialog so somebody with two records open cannot write the
   *  remark onto the wrong student. */
  studentName?: string | null;
  open: boolean;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [body, setBody] = useState('');
  const [visible, setVisible] = useState(true);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    const text = body.trim();
    if (!text) {
      setErrors({ body: 'Write the feedback before saving.' });
      return;
    }
    setSaving(true);
    setErrors({});
    try {
      await createFeedback({ student: studentId, body: text, visibleToSubject: visible });
      setBody('');
      setVisible(true);
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
            <DialogTitle>
              {studentName ? `Feedback for ${studentName}` : 'Leave feedback'}
            </DialogTitle>
            <DialogDescription>
              One remark, not a formal review. Say what happened and what would help.
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-4 py-4">
            {stray ? <Alert variant="error">{stray}</Alert> : null}
            <Field label="Feedback" htmlFor="feedback-body" error={errors.body}>
              <Textarea
                id="feedback-body"
                rows={4}
                value={body}
                onChange={(event) => setBody(event.target.value)}
                placeholder="Asked good questions in today's class. Needs more practice with the shell."
              />
            </Field>
            <label className="flex items-start gap-2.5 text-sm">
              <Checkbox
                id="feedback-visible"
                checked={visible}
                onCheckedChange={(next) => setVisible(next === true)}
              />
              <span>
                Show this to the student
                <span className="block text-xs text-ink-muted">
                  Unticked, it stays on their record for staff only — a note for the next review
                  rather than something they read on their dashboard.
                </span>
              </span>
            </label>
          </div>

          <DialogFooter>
            <Button type="button" variant="ghost" onClick={onClose} disabled={saving}>
              Cancel
            </Button>
            <Button type="submit" disabled={saving}>
              {saving ? 'Saving…' : 'Save feedback'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
