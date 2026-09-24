/**
 * One row per active session (ERP Phase 6, ADR-06) — shared between the
 * security settings screen's own-sessions list
 * (`components/settings/sessions-card.tsx`) and the admin sessions section of
 * a user's page (`components/admin/user-sessions-card.tsx`). Never shows a
 * session's key or its hash (rule §13), only what the server already reduced
 * it to.
 */
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { formatDateTime, formatRelative } from "@/lib/format";
import type { SessionRow } from "@/types/api";

export function SessionList({
  sessions,
  onRevoke,
  revokingId,
  showCurrentBadge = true,
}: {
  sessions: SessionRow[];
  /** Omitted entirely when the caller may not revoke at all. */
  onRevoke?: (session: SessionRow) => void;
  /** The id currently being revoked, to disable just that row's button. */
  revokingId?: string | null;
  /** False on the admin listing: `is_current` there compares against the
   *  *admin's* own session, not the one this row describes, so it is
   *  meaningless here and must not be rendered (API contract). */
  showCurrentBadge?: boolean;
}) {
  return (
    <ul className="space-y-2">
      {sessions.map((session) => {
        const isCurrent = showCurrentBadge && session.is_current;
        return (
          <li
            key={session.id}
            data-testid="session-row"
            className="flex flex-col gap-2 rounded-md border border-line p-3 sm:flex-row sm:items-center sm:justify-between"
          >
            <div>
              <p className="flex items-center gap-2 font-medium">
                {session.device_label}
                {isCurrent ? (
                  <Badge variant="success">This device</Badge>
                ) : null}
              </p>
              <p className="text-sm text-ink-muted">
                {session.ip ?? "Unknown location"} · First seen{" "}
                {formatDateTime(session.created_at)} · Last active{" "}
                {formatRelative(session.last_seen_at)}
              </p>
            </div>
            {isCurrent ? (
              <span className="text-xs text-ink-muted">
                Sign out instead to end this one.
              </span>
            ) : onRevoke ? (
              <Button
                type="button"
                variant="ghost"
                size="sm"
                disabled={revokingId === session.id}
                onClick={() => onRevoke(session)}
              >
                Revoke
              </Button>
            ) : null}
          </li>
        );
      })}
    </ul>
  );
}
