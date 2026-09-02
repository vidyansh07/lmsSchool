'use client';

import { Badge } from '@/components/ui/badge';
import type { RuleOutcome } from '@/types/api';

/**
 * The completion rules, as a student or an administrator reads them.
 *
 * Rules that are switched off are shown too, greyed rather than hidden: a
 * student is entitled to see where they stand on a condition that does not
 * currently gate anything, and hiding it is how people get surprised later.
 */
export function ProgressRules({ rules }: { rules: RuleOutcome[] }) {
  return (
    <ul className="space-y-2" data-testid="completion-rules">
      {rules.map((rule) => (
        <li
          key={rule.key}
          className="flex flex-wrap items-start gap-2 rounded-md border border-border p-3"
          data-testid={`rule-${rule.key}`}
        >
          <Badge
            variant={!rule.required ? 'neutral' : rule.met ? 'success' : 'error'}
          >
            {!rule.required ? 'Optional' : rule.met ? 'Met' : 'Not met'}
          </Badge>
          <div className="min-w-0 flex-1">
            <p className="text-sm font-medium">{rule.label}</p>
            <p className="text-sm text-muted-foreground">{rule.detail}</p>
          </div>
        </li>
      ))}
    </ul>
  );
}
