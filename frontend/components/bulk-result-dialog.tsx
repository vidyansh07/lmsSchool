'use client';

/**
 * What a bulk action actually did: "12 done, 3 skipped" and, for each skipped
 * row, who and why — "Already accepted their invitation", "A student stays at
 * the centre they were admitted to". A bare "Done" over a partial result is
 * how somebody believes fourteen invitations went out when eleven did.
 */

import { Alert } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { formatCount } from '@/lib/format';
import type { BulkResult } from '@/lib/bulk';

export function BulkResultDialog({
  result,
  title,
  doneLabel,
  itemNoun,
  onClose,
}: {
  result: BulkResult | null;
  title: string;
  /** Past tense of the action, e.g. "invitation sent" / "moved". */
  doneLabel: string;
  itemNoun: string;
  onClose: () => void;
}) {
  return (
    <Dialog open={result !== null} onOpenChange={(open) => (open ? null : onClose())}>
      <DialogContent size="md" className="max-h-[calc(100vh-2rem)] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          <DialogDescription>
            {result
              ? `${formatCount(result.done, itemNoun)} ${doneLabel}${
                  result.skipped.length > 0 ? `, ${result.skipped.length} skipped` : ''
                }.`
              : null}
          </DialogDescription>
        </DialogHeader>
        {result && result.done === 0 && result.skipped.length > 0 ? (
          <Alert variant="warning">Nothing was changed. Every row was skipped for the reason shown.</Alert>
        ) : null}
        {result && result.skipped.length > 0 ? (
          <div className="space-y-2">
            <h3 className="text-sm font-medium">Skipped</h3>
            <ul className="divide-y divide-line rounded-control border border-line text-sm">
              {result.skipped.map((row) => (
                <li key={row.id} className="px-3 py-2">
                  <p className="font-medium">{row.label || 'Unknown row'}</p>
                  <p className="text-ink-muted">{row.reason}</p>
                </li>
              ))}
            </ul>
          </div>
        ) : null}
        <DialogFooter>
          <Button type="button" onClick={onClose}>
            Close
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
