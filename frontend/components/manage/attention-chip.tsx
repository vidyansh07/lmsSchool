'use client';

/**
 * "Showing: batches running behind schedule ✕"
 *
 * The attention strip links into a hub with `?attention=…`, and the hub opens
 * narrowed to that. Without this chip the narrowing is invisible: a manager
 * arrives at a list of three batches with no sign that twenty are hidden, and
 * the URL bar is the only place the filter shows. The chip names the filter
 * in the same words the strip used, and one click clears it.
 */

import { X } from 'lucide-react';
import { usePathname, useRouter } from 'next/navigation';

import { Button } from '@/components/ui/button';

export const ATTENTION_LABELS: Record<string, string> = {
  behind_schedule: 'batches running behind schedule',
  at_risk: 'batches with students flagged at risk',
  review_missing: 'trainers with no performance review on file',
};

export function AttentionChip({ value, onClear }: { value: string; onClear: () => void }) {
  const router = useRouter();
  const pathname = usePathname();
  if (!value) return null;
  const label = ATTENTION_LABELS[value] ?? value.replace(/_/g, ' ');

  return (
    <div
      role="status"
      className="flex flex-wrap items-center gap-2 rounded-[var(--radius-card)] border border-primary/30 bg-accent px-3 py-2 text-sm"
    >
      <span>
        Showing <span className="font-semibold text-primary">{label}</span>
      </span>
      <Button
        type="button"
        variant="ghost"
        size="sm"
        className="h-7 gap-1 px-2 text-xs"
        onClick={() => {
          onClear();
          // Drop the parameter from the address bar too, so a refresh or a
          // shared link does not bring the filter back.
          router.replace(pathname);
        }}
      >
        <X className="size-3.5" aria-hidden="true" />
        Show all
      </Button>
    </div>
  );
}
