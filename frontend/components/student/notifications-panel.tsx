/**
 * The dashboard's notification preview.
 *
 * The dashboard endpoint itself carries a `notifications` field, but it is a
 * fixed, permanent placeholder — `StudentDashboardView` in
 * `apps/dashboards/views.py` returns `[]` for it with a comment saying the
 * shape is frozen for a future feature to fill in. That feature already
 * exists one app over (`apps.notifications`, reachable at
 * `/api/v1/notifications/`), so this panel reads the real endpoint instead of
 * waiting on the placeholder to catch up.
 */
import Link from 'next/link';
import { Bell } from 'lucide-react';

import { ErrorState, LoadingState } from '@/components/states';
import { formatRelative } from '@/lib/format';
import type { AppNotification } from '@/types/api';

export function NotificationsPanel({
  notifications,
  unreadCount,
  isLoading,
  error,
  onRetry,
}: {
  notifications: AppNotification[];
  unreadCount: number;
  isLoading?: boolean;
  error?: { message: string; requestId?: string } | null;
  onRetry?: () => void;
}) {
  if (isLoading) return <LoadingState label="Loading your notifications…" rows={2} />;
  if (error) {
    return <ErrorState message={error.message} requestId={error.requestId} onRetry={onRetry} />;
  }

  return (
    <div className="space-y-3">
      <p aria-live="polite" className="flex items-center gap-1.5 text-sm">
        <Bell className="size-4 text-muted-foreground" aria-hidden="true" />
        {unreadCount > 0 ? (
          <span>
            <span className="font-semibold tabular-nums">{unreadCount}</span> unread
          </span>
        ) : (
          <span className="text-muted-foreground">You&apos;re all caught up.</span>
        )}
      </p>

      {notifications.length > 0 ? (
        <ul className="space-y-2">
          {notifications.map((item) => {
            const body = (
              <>
                <p className="truncate text-sm font-medium">{item.title || 'Notification'}</p>
                <p className="text-xs text-muted-foreground">{formatRelative(item.created_at)}</p>
              </>
            );
            return (
              <li key={item.id} className="rounded-[var(--radius-card)] border border-border p-2.5">
                {item.link_path ? (
                  <Link href={item.link_path} className="block hover:text-primary">
                    {body}
                  </Link>
                ) : (
                  body
                )}
              </li>
            );
          })}
        </ul>
      ) : null}

      <Link href="/notifications" className="inline-block text-sm underline hover:text-foreground">
        All notifications
      </Link>
    </div>
  );
}
