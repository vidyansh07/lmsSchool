'use client';

/**
 * Writing a trainer performance review, inline on the trainer's own page.
 *
 * Collapsed to a single button by default: this form has seven fields, which
 * is exactly the "multi-field" case the brief reserves for a full screen
 * rather than a one-click inline action — but the trainer's own page *is*
 * that full screen here, since the brief also says writing a review happens
 * on this page specifically. Expanding in place keeps the reviewer looking at
 * the same performance figures the review is about while they write it,
 * rather than losing that context to a separate route.
 */
import { useState, type FormEvent } from 'react';

import { Alert } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import { Field } from '@/components/ui/field';
import { Input, Textarea } from '@/components/ui/input';
import { fieldErrors } from '@/lib/api';
import { createTrainerReview } from '@/lib/manage';
import { cn } from '@/lib/utils';

const RATING_VALUES = [1, 2, 3, 4, 5] as const;

function emptyForm() {
  return {
    period_start: '',
    period_end: '',
    rating: 3,
    summary: '',
    strengths: '',
    concerns: '',
    actions: '',
  };
}

export function TrainerReviewForm({ trainerId, onSaved }: { trainerId: string; onSaved: () => void }) {
  const [isOpen, setIsOpen] = useState(false);
  const [form, setForm] = useState(emptyForm());
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [isSaving, setIsSaving] = useState(false);

  if (!isOpen) {
    return (
      <Button type="button" variant="outline" size="sm" onClick={() => setIsOpen(true)}>
        Write a review
      </Button>
    );
  }

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setIsSaving(true);
    setErrors({});
    try {
      await createTrainerReview({ trainer: trainerId, ...form });
      setForm(emptyForm());
      setIsOpen(false);
      onSaved();
    } catch (cause) {
      setErrors(fieldErrors(cause));
    } finally {
      setIsSaving(false);
    }
  }

  return (
    <form
      onSubmit={(event) => void onSubmit(event)}
      aria-label="Write a review"
      className="animate-rise-in space-y-4 rounded-[var(--radius-card)] border border-border p-4"
    >
      {errors.__all__ ? <Alert variant="error">{errors.__all__}</Alert> : null}

      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="Period start" htmlFor="review-period-start" error={errors.period_start} required>
          <Input
            type="date"
            value={form.period_start}
            onChange={(event) => setForm({ ...form, period_start: event.target.value })}
          />
        </Field>
        <Field label="Period end" htmlFor="review-period-end" error={errors.period_end} required>
          <Input
            type="date"
            value={form.period_end}
            onChange={(event) => setForm({ ...form, period_end: event.target.value })}
          />
        </Field>
      </div>

      <fieldset>
        <legend className="mb-1.5 text-sm font-medium">Rating</legend>
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
                  ? 'border-primary bg-primary text-primary-foreground'
                  : 'border-border hover:bg-muted',
              )}
            >
              {value}
            </button>
          ))}
        </div>
        {errors.rating ? <p className="mt-1 text-xs text-destructive">{errors.rating}</p> : null}
      </fieldset>

      <Field label="Summary" htmlFor="review-summary" error={errors.summary}>
        <Textarea
          rows={3}
          value={form.summary}
          onChange={(event) => setForm({ ...form, summary: event.target.value })}
        />
      </Field>
      <Field label="Strengths" htmlFor="review-strengths" error={errors.strengths}>
        <Textarea
          rows={2}
          value={form.strengths}
          onChange={(event) => setForm({ ...form, strengths: event.target.value })}
        />
      </Field>
      <Field label="Concerns" htmlFor="review-concerns" error={errors.concerns}>
        <Textarea
          rows={2}
          value={form.concerns}
          onChange={(event) => setForm({ ...form, concerns: event.target.value })}
        />
      </Field>
      <Field label="Agreed actions" htmlFor="review-actions" error={errors.actions}>
        <Textarea
          rows={2}
          value={form.actions}
          onChange={(event) => setForm({ ...form, actions: event.target.value })}
        />
      </Field>

      <div className="flex gap-2">
        <Button type="submit" disabled={isSaving}>
          {isSaving ? 'Saving…' : 'Save review'}
        </Button>
        <Button type="button" variant="outline" disabled={isSaving} onClick={() => setIsOpen(false)}>
          Cancel
        </Button>
      </div>
    </form>
  );
}
