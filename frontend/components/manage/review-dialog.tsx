'use client';

/**
 * Writing and reading `PerformanceReview`s (Phase 12) about one trainer or
 * one student, embedded on that person's own detail page.
 *
 * Replaces the old `TrainerReviewForm` (create-only, trainer-only, and read
 * from `TrainerOverview.reviews` — a lean projection `apps.reporting
 * .dashboards.trainer_overview` bakes for that one screen, missing
 * `review_type`/`score`/`recommendations`/`next_review_at`/`status`). This
 * reads and writes the actual register instead
 * (`GET/POST/PATCH /performance/reviews/`, `lib/performance.ts`), so the
 * same component serves a trainer's page and a student's, and an existing
 * review can be edited, not only ever appended to.
 *
 * The dialog is the house pattern for a single-record create/edit form
 * (`components/fees/fee-ledger.tsx`'s `SetFeeDialog`/`SetFeeForm`): a
 * controlled `open` boolean, the record being edited or `null` for create,
 * and the form itself mounted only while open so every opening starts from
 * that record as it is now.
 *
 * `weaknesses` and `concerns` are one field, not two
 * (`_merge_weaknesses_alias` on the backend rejects a write naming both with
 * different values) — this form binds a single "Weaknesses" textarea and
 * always sends it under the `weaknesses` key, never `concerns`.
 */
import { useState, type FormEvent } from 'react';

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
import { errorMessage, fieldErrors } from '@/lib/api';
import { REVIEW_STATUS_OPTIONS, REVIEW_TYPE_OPTIONS } from '@/lib/labels';
import { createReview, updateReview } from '@/lib/performance';
import { cn } from '@/lib/utils';
import type { PerformanceReview, PerformanceSubjectType, ReviewStatus, ReviewType } from '@/types/api';

const RATING_VALUES = [1, 2, 3, 4, 5] as const;

interface FormState {
  review_type: ReviewType;
  period_start: string;
  period_end: string;
  rating: number;
  score: string;
  summary: string;
  strengths: string;
  weaknesses: string;
  actions: string;
  recommendations: string;
  next_review_at: string;
  status: ReviewStatus;
}

function today(): string {
  return new Date().toISOString().slice(0, 10);
}

function formFromReview(review: PerformanceReview | null): FormState {
  if (!review) {
    return {
      review_type: 'monthly',
      period_start: '',
      period_end: '',
      rating: 3,
      score: '',
      summary: '',
      strengths: '',
      weaknesses: '',
      actions: '',
      recommendations: '',
      next_review_at: '',
      status: 'draft',
    };
  }
  return {
    review_type: review.review_type,
    period_start: review.period_start,
    period_end: review.period_end,
    rating: review.rating,
    score: review.score ?? '',
    summary: review.summary,
    strengths: review.strengths,
    weaknesses: review.weaknesses,
    actions: review.actions,
    recommendations: review.recommendations,
    next_review_at: review.next_review_at ?? '',
    status: review.status,
  };
}

interface ReviewFormProps {
  subjectType: PerformanceSubjectType;
  subjectId: string;
  review: PerformanceReview | null;
  onOpenChange: (open: boolean) => void;
  onSaved: () => void;
}

function ReviewForm({ subjectType, subjectId, review, onOpenChange, onSaved }: ReviewFormProps) {
  const [form, setForm] = useState<FormState>(() => formFromReview(review));
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [message, setMessage] = useState('');
  const [isSaving, setIsSaving] = useState(false);
  const isEdit = review !== null;

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setIsSaving(true);
    setErrors({});
    setMessage('');
    const shared = {
      review_type: form.review_type,
      period_start: form.period_start,
      period_end: form.period_end,
      rating: form.rating,
      score: form.score.trim() === '' ? null : form.score.trim(),
      summary: form.summary,
      strengths: form.strengths,
      weaknesses: form.weaknesses,
      actions: form.actions,
      recommendations: form.recommendations,
      next_review_at: form.next_review_at.trim() === '' ? null : form.next_review_at,
    };
    try {
      if (isEdit) {
        await updateReview(review.id, { ...shared, status: form.status });
      } else {
        await createReview({
          ...shared,
          [subjectType]: subjectId,
        });
      }
      onOpenChange(false);
      onSaved();
    } catch (cause) {
      const fields = fieldErrors(cause);
      setErrors(fields);
      if (Object.keys(fields).length === 0) {
        setMessage(errorMessage(cause, 'The review could not be saved.'));
      }
    } finally {
      setIsSaving(false);
    }
  }

  return (
    <form onSubmit={(event) => void onSubmit(event)} noValidate>
      <DialogHeader>
        <DialogTitle>{isEdit ? 'Edit review' : 'New review'}</DialogTitle>
        <DialogDescription>
          {isEdit
            ? 'Change the judgement recorded. The subject and reviewer never change.'
            : 'Recorded against this record, with you as the reviewer.'}
        </DialogDescription>
      </DialogHeader>
      <div className="max-h-[70vh] space-y-4 overflow-y-auto pr-1">
        {message ? <Alert variant="error">{message}</Alert> : null}
        {errors.__all__ ? <Alert variant="error">{errors.__all__}</Alert> : null}

        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <Field label="Review type" htmlFor="review-type" error={errors.review_type}>
            <Select
              id="review-type"
              value={form.review_type}
              onChange={(event) => setForm({ ...form, review_type: event.target.value as ReviewType })}
            >
              {REVIEW_TYPE_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </Select>
          </Field>
          {isEdit ? (
            <Field label="Status" htmlFor="review-status" error={errors.status}>
              <Select
                id="review-status"
                value={form.status}
                onChange={(event) => setForm({ ...form, status: event.target.value as ReviewStatus })}
              >
                {REVIEW_STATUS_OPTIONS.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </Select>
            </Field>
          ) : null}
        </div>

        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <Field label="Period start" htmlFor="review-period-start" error={errors.period_start} required>
            <Input
              id="review-period-start"
              type="date"
              value={form.period_start}
              onChange={(event) => setForm({ ...form, period_start: event.target.value })}
            />
          </Field>
          <Field label="Period end" htmlFor="review-period-end" error={errors.period_end} required>
            <Input
              id="review-period-end"
              type="date"
              value={form.period_end}
              onChange={(event) => setForm({ ...form, period_end: event.target.value })}
            />
          </Field>
        </div>

        <fieldset>
          <legend className="mb-1.5 text-sm font-medium">
            Rating<span className="ml-1 text-danger" aria-hidden="true">*</span>
          </legend>
          <div role="radiogroup" aria-label="Rating, 1 to 5" className="flex gap-1.5">
            {RATING_VALUES.map((value) => (
              <button
                key={value}
                type="button"
                role="radio"
                aria-checked={form.rating === value}
                onClick={() => setForm((current) => ({ ...current, rating: value }))}
                className={cn(
                  'flex size-9 items-center justify-center rounded-md border text-sm font-medium',
                  form.rating === value
                    ? 'border-action bg-action text-action-fg'
                    : 'border-line hover:bg-sunken',
                )}
              >
                {value}
              </button>
            ))}
          </div>
          {errors.rating ? <p className="mt-1 text-xs text-danger">{errors.rating}</p> : null}
        </fieldset>

        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <Field label="Score" htmlFor="review-score" error={errors.score} hint="Out of 100, if this review scores one.">
            <Input
              id="review-score"
              type="number"
              inputMode="decimal"
              step="0.1"
              min={0}
              max={100}
              value={form.score}
              onChange={(event) => setForm({ ...form, score: event.target.value })}
            />
          </Field>
          <Field label="Next review due" htmlFor="review-next-review-at" error={errors.next_review_at}>
            <Input
              id="review-next-review-at"
              type="date"
              min={today()}
              value={form.next_review_at}
              onChange={(event) => setForm({ ...form, next_review_at: event.target.value })}
            />
          </Field>
        </div>

        <Field label="Summary" htmlFor="review-summary" error={errors.summary}>
          <Textarea
            id="review-summary"
            rows={3}
            value={form.summary}
            onChange={(event) => setForm({ ...form, summary: event.target.value })}
          />
        </Field>
        <Field label="Strengths" htmlFor="review-strengths" error={errors.strengths}>
          <Textarea
            id="review-strengths"
            rows={2}
            value={form.strengths}
            onChange={(event) => setForm({ ...form, strengths: event.target.value })}
          />
        </Field>
        <Field label="Weaknesses" htmlFor="review-weaknesses" error={errors.weaknesses || errors.concerns}>
          <Textarea
            id="review-weaknesses"
            rows={2}
            value={form.weaknesses}
            onChange={(event) => setForm({ ...form, weaknesses: event.target.value })}
          />
        </Field>
        <Field label="Recommendations" htmlFor="review-recommendations" error={errors.recommendations}>
          <Textarea
            id="review-recommendations"
            rows={2}
            value={form.recommendations}
            onChange={(event) => setForm({ ...form, recommendations: event.target.value })}
          />
        </Field>
        <Field label="Agreed actions" htmlFor="review-actions" error={errors.actions}>
          <Textarea
            id="review-actions"
            rows={2}
            value={form.actions}
            onChange={(event) => setForm({ ...form, actions: event.target.value })}
          />
        </Field>
      </div>
      <DialogFooter>
        <Button type="button" variant="ghost" disabled={isSaving} onClick={() => onOpenChange(false)}>
          Cancel
        </Button>
        <Button
          type="submit"
          disabled={isSaving || form.period_start.trim() === '' || form.period_end.trim() === ''}
        >
          {isSaving ? 'Saving…' : 'Save review'}
        </Button>
      </DialogFooter>
    </form>
  );
}

export interface ReviewDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  subjectType: PerformanceSubjectType;
  subjectId: string;
  /** `null` opens the dialog in "new review" mode; a review opens it for edit. */
  review: PerformanceReview | null;
  onSaved: () => void;
}

/**
 * `key={review?.id ?? 'new'}` remounts the form whenever the dialog opens on
 * a different review (or on "new" after having just edited one) — the same
 * reason `SetFeeForm` mounts only while its dialog is open: a fresh
 * component instance means fresh state seeded from `review` as it is right
 * now, never a stale draft from whatever was open last.
 */
export function ReviewDialog({ open, onOpenChange, subjectType, subjectId, review, onSaved }: ReviewDialogProps) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        {open ? (
          <ReviewForm
            key={review?.id ?? 'new'}
            subjectType={subjectType}
            subjectId={subjectId}
            review={review}
            onOpenChange={onOpenChange}
            onSaved={onSaved}
          />
        ) : null}
      </DialogContent>
    </Dialog>
  );
}
