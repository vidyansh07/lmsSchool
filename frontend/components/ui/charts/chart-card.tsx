/**
 * The panel a chart sits in.
 *
 * Not a variant of `Card`, and the difference is deliberate. A `Card` is
 * 12px, hairline, no shadow, and around two hundred call sites depend on
 * that. A chart panel is a 300px-tall object with whitespace inside it,
 * which a hairline alone does not separate from the identically-white panel
 * 16px below -- so this one is 16px with a faint lift. `--shadow-panel`
 * exists for this component and nothing else; see `DESIGN_SYSTEM.md` rule 2
 * for why the "no card shadow" rule stops applying here.
 *
 * Two props are load-bearing:
 *
 * - **`subtitle` is required.** The product's own rule is that every metric
 *   carries its definition, and a plot is a metric with more ink. One line
 *   saying what the figure actually counts is the difference between a chart
 *   a person can act on and a chart they have to ask about. It renders with
 *   `data-testid="chart-definition"` so a test can assert the page has not
 *   shipped an undefined number.
 * - **`testId`** gives the panel a handle, which is what lets a page's test
 *   scope its Recharts queries to one card (`within(getByTestId(...))`)
 *   instead of counting `.recharts-area` across the whole document. Every
 *   dashboard test that counted globally had to be rewritten the first time
 *   a chart was added beside it; this is how that stops happening.
 */

import type { ReactNode } from 'react';
import type { LucideIcon } from 'lucide-react';

import { IconChip, type IconChipTone } from '@/components/ui/icon-chip';
import { cn } from '@/lib/utils';

export interface ChartCardLegendItem {
  label: string;
  /** A CSS colour -- normally a `var(--color-chart-N)` from `CHART_PALETTE`. */
  color: string;
  /** An optional figure, right-aligned, for the table-style legend. */
  value?: string;
}

export interface ChartCardProps {
  title: ReactNode;
  /** One line stating what the figure means. Required -- see above. */
  subtitle: ReactNode;
  icon?: LucideIcon;
  iconTone?: IconChipTone;
  /** A dot-and-label legend above the plot, for the series the chart draws
   *  itself. Use it when the legend should read before the plot does. */
  legend?: readonly ChartCardLegendItem[];
  /** Controls for this panel only -- a range switch, a unit toggle. At most
   *  one of them should be a filled button. */
  actions?: ReactNode;
  /** Normally the link to the rows behind the shape. */
  footer?: ReactNode;
  testId?: string;
  /** Heading level. Defaults to `h2`; pass `h3` inside a section that
   *  already has one, so the outline never skips a level. */
  as?: 'h2' | 'h3';
  children: ReactNode;
  className?: string;
}

export function ChartCard({
  title,
  subtitle,
  icon: Icon,
  iconTone = 'neutral',
  legend,
  actions,
  footer,
  testId,
  as: Heading = 'h2',
  children,
  className,
}: ChartCardProps) {
  return (
    <section
      data-testid={testId}
      className={cn(
        'flex h-full flex-col rounded-panel bg-surface p-5 ring-1 ring-line sm:p-6',
        'shadow-panel transition-shadow duration-150 hover:ring-line-strong',
        'animate-fade-in',
        className,
      )}
    >
      <div className="flex items-start gap-3">
        {Icon ? <IconChip icon={Icon} tone={iconTone} /> : null}
        <div className="min-w-0 flex-1">
          <Heading className="truncate text-lg font-semibold">{title}</Heading>
          <p data-testid="chart-definition" className="mt-0.5 text-xs text-ink-muted">
            {subtitle}
          </p>
        </div>
        {actions ? <div className="flex shrink-0 items-center gap-2">{actions}</div> : null}
      </div>

      {legend && legend.length > 0 ? (
        <ul className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1.5 text-2xs text-ink-muted">
          {legend.map((item) => (
            <li key={item.label} className="flex items-center gap-1.5">
              <span
                aria-hidden="true"
                className="size-2 shrink-0 rounded-full"
                style={{ backgroundColor: item.color }}
              />
              {item.label}
              {item.value ? (
                <span data-numeric className="font-medium text-ink">
                  {item.value}
                </span>
              ) : null}
            </li>
          ))}
        </ul>
      ) : null}

      <div className="mt-4 flex-1">{children}</div>

      {footer ? <div className="mt-4 border-t border-line pt-3 text-xs">{footer}</div> : null}
    </section>
  );
}
