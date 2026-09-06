import { Check } from 'lucide-react';

import { cn } from '@/lib/utils';

export interface WizardStep {
  key: string;
  label: string;
}

/**
 * Where the counsellor is in the registration sequence.
 *
 * The whole flow lives on one page precisely so nobody navigates away between
 * steps, so this is the only thing telling them where they are and what is
 * still ahead. Completed steps are also buttons: state is kept for every step
 * the whole time the wizard is open, so jumping back costs nothing and loses
 * no work.
 */
export function StepIndicator({
  steps,
  current,
  completed,
  reachable,
  onJump,
}: {
  steps: WizardStep[];
  current: string;
  completed: Set<string>;
  /**
   * Steps the counsellor has already been on, which may be more than the ones
   * they finished.
   *
   * Without this, "completed or current" was the only way back, and stepping
   * back became a trap: you could return to the student details from the batch
   * step and then had no way forward again, because the batch step was neither
   * finished nor current. Losing a half-typed batch that way, mid-registration,
   * is worse than not offering the jump at all.
   *
   * Defaults to `completed`, so a caller that does not track visits keeps the
   * old behaviour rather than silently opening every step.
   */
  reachable?: Set<string>;
  onJump: (key: string) => void;
}) {
  const openSteps = reachable ?? completed;
  return (
    <ol className="flex flex-wrap items-center gap-x-2 gap-y-3" aria-label="Registration steps">
      {steps.map((step, index) => {
        const isCurrent = step.key === current;
        const isDone = completed.has(step.key);
        const canJump = isDone || isCurrent || openSteps.has(step.key);
        return (
          <li key={step.key} className="flex items-center gap-2">
            <button
              type="button"
              aria-current={isCurrent ? 'step' : undefined}
              disabled={!canJump}
              onClick={() => onJump(step.key)}
              className={cn(
                'flex items-center gap-2 rounded-full border px-3 py-1.5 text-sm font-medium transition-colors',
                'focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary',
                'disabled:cursor-not-allowed disabled:opacity-50',
                isCurrent
                  ? 'border-primary bg-primary text-primary-foreground'
                  : isDone
                    ? 'border-success/40 bg-success/10 text-foreground hover:bg-success/20'
                    : 'border-border bg-muted text-muted-foreground',
              )}
            >
              <span
                className={cn(
                  'flex size-5 shrink-0 items-center justify-center rounded-full text-xs',
                  isCurrent ? 'bg-primary-foreground/20' : 'bg-transparent',
                )}
                aria-hidden="true"
              >
                {isDone && !isCurrent ? <Check className="size-3.5" /> : index + 1}
              </span>
              {step.label}
            </button>
            {index < steps.length - 1 ? (
              <span aria-hidden="true" className="text-muted-foreground">
                →
              </span>
            ) : null}
          </li>
        );
      })}
    </ol>
  );
}
