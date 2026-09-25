/**
 * A small tinted square holding one icon.
 *
 * The tint is the *state* the thing is in -- four tones, the same four the
 * rest of the product uses -- and not one decorative hue per metric. That
 * distinction is the whole reason this component can exist without
 * reopening a settled decision: the previous design system assigned a hue
 * per dashboard tile from a palette of six, which made a screen read as six
 * colours competing before a number had been read, and removing it was the
 * point of the rebuild.
 *
 * Every pair it can produce is already measured: `theme-contrast.test.ts`
 * asserts each state colour on its own wash at 4.5:1.
 *
 * `label` is for the rare chip that carries meaning no adjacent text does.
 * Normally the heading beside it says everything and the icon is decoration,
 * so the default is `aria-hidden`.
 */

import type { LucideIcon } from 'lucide-react';

import { cn } from '@/lib/utils';

export type IconChipTone = 'neutral' | 'info' | 'success' | 'warning' | 'danger';

const TONES: Record<IconChipTone, string> = {
  neutral: 'bg-sunken text-ink-muted',
  info: 'bg-info-wash text-info',
  success: 'bg-success-wash text-success',
  warning: 'bg-warning-wash text-warning',
  danger: 'bg-danger-wash text-danger',
};

export function IconChip({
  icon: Icon,
  tone = 'neutral',
  label,
  className,
}: {
  icon: LucideIcon;
  tone?: IconChipTone;
  /** An accessible name, when the icon is the only thing carrying it. */
  label?: string;
  className?: string;
}) {
  return (
    <span
      className={cn(
        'flex size-8 shrink-0 items-center justify-center rounded-control',
        TONES[tone],
        className,
      )}
      role={label ? 'img' : undefined}
      aria-label={label}
      aria-hidden={label ? undefined : true}
    >
      <Icon className="size-4" strokeWidth={1.75} />
    </span>
  );
}
