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
  onJump,
}: {
  steps: WizardStep[];
  current: string;
  completed: Set<string>;
  onJump: (key: string) => void;
}) {
  return (
    <ol className="flex flex-wrap items-center gap-x-2 gap-y-3" aria-label="Registration steps">
      {steps.map((step, index) => {
        const isCurrent = step.key === current;
        const isDone = completed.has(step.key);
        const canJump = isDone || isCurrent;
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
