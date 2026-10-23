'use client';

/**
 * The numbered step bar across the top of the admissions wizard:
 * "1. Student Details  2. Guardian Details  3. Admission Details …".
 *
 * Chevrons, as the original draws them — each step is a strip with a notch
 * cut from its right edge, made with `clip-path` rather than the stacked
 * borders that trick is usually done with, so the shape survives a theme
 * change and a zoom.
 *
 * A step is a button only once it can be reached. Steps ahead of the one the
 * person is on are `disabled` rather than hidden: the bar's job is to say how
 * long this is going to take, which it cannot do if it only shows what has
 * been done. A screen reader is told the same thing — `aria-current` on the
 * step they are on, `aria-disabled` on the ones they cannot open yet.
 *
 * At phone width the strip scrolls sideways rather than wrapping, matching
 * `data-table`'s own convention for anything that cannot shrink further.
 */
import { ChevronLeft, ChevronRight } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';

export interface WizardStep {
  key: string;
  label: string;
}

/** The notch: a flat left edge and a point on the right. The first strip is
 *  square on its left so the bar does not start with a wedge. */
const CHEVRON = 'polygon(0 0, calc(100% - 1.25rem) 0, 100% 50%, calc(100% - 1.25rem) 100%, 0 100%)';
const CHEVRON_INSET =
  'polygon(0 0, calc(100% - 1.25rem) 0, 100% 50%, calc(100% - 1.25rem) 100%, 0 100%, 1.25rem 50%)';

export function StepBar({
  steps,
  current,
  furthest,
  onSelect,
  onPrevious,
  onNext,
  nextLabel = 'Next',
}: {
  steps: WizardStep[];
  current: string;
  /** How far they have got. Steps beyond it cannot be opened yet. */
  furthest: string;
  onSelect: (key: string) => void;
  onPrevious?: () => void;
  onNext?: () => void;
  nextLabel?: string;
}) {
  const currentIndex = steps.findIndex((step) => step.key === current);
  const furthestIndex = steps.findIndex((step) => step.key === furthest);

  return (
    <div className="flex flex-col gap-3 border-b border-line bg-surface sm:flex-row sm:items-center sm:justify-between">
      <ol className="flex min-w-0 flex-1 overflow-x-auto" aria-label="Registration steps">
        {steps.map((step, index) => {
          const isCurrent = index === currentIndex;
          const reachable = index <= furthestIndex;
          return (
            <li key={step.key} className="shrink-0">
              <button
                type="button"
                onClick={() => (reachable ? onSelect(step.key) : undefined)}
                disabled={!reachable}
                aria-current={isCurrent ? 'step' : undefined}
                aria-disabled={!reachable}
                style={{ clipPath: index === 0 ? CHEVRON : CHEVRON_INSET }}
                className={cn(
                  'relative -ml-3 py-3.5 pl-8 pr-9 text-sm transition-colors first:ml-0 first:pl-5',
                  isCurrent
                    ? 'bg-surface font-medium text-action'
                    : reachable
                      ? 'bg-sunken/60 text-action hover:bg-sunken'
                      : 'bg-sunken/60 text-ink-faint',
                )}
              >
                {index + 1}. {step.label}
              </button>
            </li>
          );
        })}
      </ol>

      {onPrevious || onNext ? (
        <div className="flex shrink-0 gap-2 px-4 pb-3 sm:pb-0 sm:pr-4">
          <Button variant="outline" size="sm" onClick={onPrevious} disabled={!onPrevious}>
            <ChevronLeft className="size-4" aria-hidden="true" />
            Previous
          </Button>
          <Button variant="outline" size="sm" onClick={onNext} disabled={!onNext}>
            {nextLabel}
            <ChevronRight className="size-4" aria-hidden="true" />
          </Button>
        </div>
      ) : null}
    </div>
  );
}
