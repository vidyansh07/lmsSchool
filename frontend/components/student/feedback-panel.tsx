/**
 * Feedback written about this student — a trainer's note after a class, or a
 * manager's remark, whichever the author chose to make visible to them.
 *
 * The API does not carry the author's role, only their name (see the
 * docstring on `lib/performance.ts`'s `listMyFeedback`), so this cannot be
 * split into separate "trainer" and "manager" lists the way the product brief
 * names them — doing so would mean guessing a role from a name string, which
 * is worse than not guessing. One feed, newest first, author named on each
 * line, is the honest version of that requirement.
 */
import { MessageSquareText } from 'lucide-react';

import { ErrorState, LoadingState } from '@/components/states';
import { fallback, formatDateTime } from '@/lib/format';
import type { PerformanceFeedback } from '@/lib/performance';

export function FeedbackPanel({
  feedback,
  isLoading,
  error,
  onRetry,
}: {
  feedback: PerformanceFeedback[];
  isLoading?: boolean;
  error?: { message: string; requestId?: string } | null;
  onRetry?: () => void;
}) {
  if (isLoading) return <LoadingState label="Loading your feedback…" rows={2} />;
  if (error) {
    return <ErrorState message={error.message} requestId={error.requestId} onRetry={onRetry} />;
  }

  if (feedback.length === 0) {
    return (
      <p className="rounded-[var(--radius-card)] border border-dashed border-border px-4 py-6 text-center text-sm text-muted-foreground">
        No feedback has been shared with you yet.
      </p>
    );
  }

  return (
    <ul className="space-y-3">
      {feedback.map((item) => (
        <li key={item.id} className="rounded-[var(--radius-card)] border border-border p-3">
          <div className="flex items-start gap-2.5">
            <MessageSquareText className="mt-0.5 size-4 shrink-0 text-muted-foreground" aria-hidden="true" />
            <div className="min-w-0 flex-1">
              <p className="whitespace-pre-wrap text-sm">{item.body}</p>
              <p className="mt-1 text-xs text-muted-foreground">
                {fallback(item.author_name, 'Unknown')} · {formatDateTime(item.created_at)}
                {item.batch_code ? ` · ${item.batch_code}` : ''}
              </p>
            </div>
          </div>
        </li>
      ))}
    </ul>
  );
}
