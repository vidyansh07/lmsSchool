/**
 * The risk flags on a roster row or a student's own page.
 *
 * Every flag carries both an icon and its own text label — never colour
 * alone — and an empty list reads as a positive result ("On track", with a
 * check mark) rather than rendering nothing, which on a table row is
 * indistinguishable from "this cell failed to load".
 */
import { AlertTriangle, CheckCircle2 } from 'lucide-react';

import { describeRiskFlag } from '@/lib/manage';

export function RiskFlags({ flags }: { flags: string[] }) {
  if (flags.length === 0) {
    return (
      <span className="inline-flex items-center gap-1 text-xs text-success">
        <CheckCircle2 className="size-3.5" aria-hidden="true" />
        On track
      </span>
    );
  }

  return (
    <ul className="flex flex-wrap gap-1">
      {flags.map((flag) => (
        <li
          key={flag}
          className="inline-flex items-center gap-1 rounded-full border border-warning/40 bg-warning/10 px-2 py-0.5 text-xs font-medium text-foreground"
        >
          <AlertTriangle className="size-3 shrink-0 text-warning" aria-hidden="true" />
          {describeRiskFlag(flag)}
        </li>
      ))}
    </ul>
  );
}
