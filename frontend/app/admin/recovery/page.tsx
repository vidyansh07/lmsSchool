'use client';

/**
 * The recycle bin — `/admin/recovery`, fixing the "Deleted records" 404 in
 * the Institution group of the sidebar.
 *
 * A soft delete that nothing ever shows again is only half-reversible in
 * practice, whatever the database still holds — see `apps.common.recovery`'s
 * own docstring for the same point made about the backend. This screen is
 * the other half: pick a kind, see what is gone from it, bring one back or
 * (rarely, and only for a superadmin) destroy it for good.
 *
 * One page, two views, no second route
 * -------------------------------------
 * The brief's own scope for this fix is a single page file, and a bin with a
 * kind for every soft-deletable model in the project is not large enough to
 * need a URL per kind — `selected` is local state, not a route param, so
 * picking a kind never leaves `/admin/recovery` and the back action is
 * "clear this state", not a navigation. `DeletedRecordsTable` is keyed by the
 * selected label specifically so switching kinds discards that table's own
 * page/loading state instead of carrying page 3 of "batches" over to
 * "students" by accident — see that component's docstring.
 *
 * Restoring or destroying a record changes two things this page shows: that
 * record's own row, and the count next to its kind on the page underneath.
 * `reloadKinds` is threaded down as `onChanged` so both stay honest without
 * this component polling anything — the kind list simply asks again once a
 * child reports something happened.
 */
import { useCallback, useEffect, useState } from 'react';
import { Undo2 } from 'lucide-react';

import { DeletedRecordsTable } from '@/components/recovery/deleted-records-table';
import { RecoveryKindList } from '@/components/recovery/kind-list';
import { RequireAuth } from '@/components/require-auth';
import { Button } from '@/components/ui/button';
import { ApiError } from '@/lib/api';
import { Capability } from '@/lib/capabilities';
import { listRecoveryKinds, type BinSummary } from '@/lib/recovery';

export function RecoveryBin() {
  const [kinds, setKinds] = useState<BinSummary[] | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [selected, setSelected] = useState<BinSummary | null>(null);

  const load = useCallback(() => {
    let cancelled = false;
    listRecoveryKinds()
      .then((result) => {
        if (!cancelled) {
          setKinds(result);
          setError(null);
        }
      })
      .catch((cause: unknown) => {
        if (!cancelled) setError(cause instanceof ApiError ? cause : null);
      })
      .finally(() => {
        if (!cancelled) setIsLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => load(), [load]);

  if (selected) {
    return (
      <div className="space-y-6">
        <Button type="button" variant="ghost" size="sm" className="-ml-3" onClick={() => setSelected(null)}>
          <Undo2 className="size-3.5" aria-hidden="true" />
          All kinds
        </Button>

        <div className="space-y-1">
          <h1 className="text-2xl font-semibold tracking-tight capitalize">{selected.verbose_name}</h1>
          <p className="text-sm text-muted-foreground">
            {selected.deleted_count === 1 ? '1 deleted record.' : `${selected.deleted_count} deleted records.`} Restore
            brings one back exactly as it was; purge does not exist as an option unless your role permits it, and does
            not undo.
          </p>
        </div>

        <DeletedRecordsTable key={selected.label} label={selected.label} onChanged={load} />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="space-y-1">
        <h1 className="text-2xl font-semibold tracking-tight">Deleted records</h1>
        <p className="text-sm text-muted-foreground">
          Everything currently removed, grouped by kind. A kind with nothing deleted in it is not listed.
        </p>
      </div>

      <RecoveryKindList
        kinds={kinds ?? []}
        isLoading={isLoading}
        error={error ? { message: error.message, requestId: error.requestId } : null}
        onRetry={load}
        onSelect={setSelected}
      />
    </div>
  );
}

export default function AdminRecoveryPage() {
  return (
    <RequireAuth capability={Capability.recordViewDeleted}>
      <RecoveryBin />
    </RequireAuth>
  );
}
