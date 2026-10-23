/**
 * Where a record has got to along a fixed path: the ribbon of chevrons the
 * reference CRM puts above a lead — "Unverified → Verified → Enrolled", the
 * reached part filled in.
 *
 * Read-only on purpose, and that is the whole difference from
 * `components/classpro/step-bar.tsx`. The step bar is a wizard's navigation:
 * numbered, clickable, and it says how much typing is left. This says where
 * something stands. Making it clickable would imply a stage can be set by
 * tapping it, which is never true here — a stage change is a decision with a
 * reason and an audit row behind it.
 *
 * Shape by `clip-path` rather than stacked borders, so it survives a theme
 * change and a zoom, the same way the step bar does it.
 *
 * Colour: `success` for the stages reached, because reaching them is the good
 * outcome the strip is reporting, and nothing else — a stage ahead is not a
 * warning, it is simply not there yet. A path that ended badly (a lost lead,
 * a cancelled admission) is not drawn as a half-finished trail at all: the
 * caller passes `endedLabel`, and the strip says so in `danger` instead of
 * implying the record is still moving.
 *
 * At phone width it scrolls sideways rather than wrapping, matching the step
 * bar and `data-table`.
 */
import { cn } from '@/lib/utils';

export interface StageTrailStep {
  key: string;
  label: string;
}

/** A flat left edge and a point on the right; the first strip is square. */
const CHEVRON = 'polygon(0 0, calc(100% - 1rem) 0, 100% 50%, calc(100% - 1rem) 100%, 0 100%)';
const CHEVRON_INSET =
  'polygon(0 0, calc(100% - 1rem) 0, 100% 50%, calc(100% - 1rem) 100%, 0 100%, 1rem 50%)';

export function StageTrail({
  steps,
  current,
  endedLabel,
  label = 'Progress',
  className,
}: {
  steps: StageTrailStep[];
  /** The stage it is on. A key not in `steps` leaves the trail unfilled. */
  current: string;
  /** Set when the record stopped short — "Not interested", "Cancelled". */
  endedLabel?: string;
  label?: string;
  className?: string;
}) {
  const currentIndex = steps.findIndex((step) => step.key === current);
  const reachedLabel = currentIndex >= 0 ? steps[currentIndex]?.label : endedLabel;

  return (
    <div className={cn('rounded-card border border-line bg-surface', className)}>
      <ol
        className="flex min-w-0 overflow-x-auto"
        // The name carries where it stands, because a screen reader cannot
        // see a filled chevron. `aria-description` would read better but the
        // `list` role does not support it, so it is simply dropped.
        aria-label={reachedLabel ? `${label}: now ${reachedLabel}` : label}
      >
        {steps.map((step, index) => {
          const reached = currentIndex >= 0 && index <= currentIndex;
          const isCurrent = index === currentIndex;
          return (
            <li
              key={step.key}
              aria-current={isCurrent ? 'step' : undefined}
              style={{ clipPath: index === 0 ? CHEVRON : CHEVRON_INSET }}
              className={cn(
                'relative -ml-2 shrink-0 py-2.5 pl-7 pr-8 text-center text-sm first:ml-0 first:pl-5',
                endedLabel
                  ? 'bg-sunken/60 text-ink-faint'
                  : reached
                    ? 'bg-success-wash text-success'
                    : 'bg-sunken/60 text-ink-faint',
                isCurrent && 'font-medium',
              )}
            >
              {step.label}
            </li>
          );
        })}
      </ol>
      {endedLabel ? (
        <p className="border-t border-line px-5 py-2 text-sm font-medium text-danger">
          {endedLabel}
        </p>
      ) : null}
    </div>
  );
}
