'use client';

/**
 * The comment thread on one payment or one instalment.
 *
 * A fee row that is not settled always has a story — a cheque sitting with the
 * bank, a father who asked for the 15th, a brother paying for both — and the
 * two places that writing could already go are both the wrong shape for it.
 * The payment's own `note` is one line written at the counter and printed on
 * the receipt; the History card records what the system was told to change.
 * This is the third thing: colleagues telling each other why one row looks
 * the way it does.
 *
 * A thread, not a field, because a field is overwritten by whoever typed last
 * and the sentence that explained the arrangement would be gone. So nothing
 * here edits or deletes: messages are added, oldest at the top, and stay.
 *
 * `CommentCountButton` is the affordance in a table row — the count, or a
 * quiet "Comment" when there is nothing yet, so a row with a thread is
 * visible at a glance down the column.
 *
 * Internal to the institute. A student's own fee screen never renders this,
 * and the endpoints behind it need a staff capability, so a desk can write
 * "says he will pay after the exam, chasing is pointless" without composing it
 * for the student to read.
 */

import { useEffect, useState } from 'react';
import { MessageSquare } from 'lucide-react';

import { ErrorState, LoadingState } from '@/components/states';
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
import { Field } from '@/components/ui/field';
import { Textarea } from '@/components/ui/input';
import { errorMessage, fieldErrors } from '@/lib/api';
import {
  addInstalmentComment,
  addPaymentComment,
  listInstalmentComments,
  listPaymentComments,
} from '@/lib/fees';
import { formatDateTime } from '@/lib/format';
import type { FeeComment } from '@/types/api';

/** What the thread hangs off: one payment, or one instalment. */
export type CommentTarget = { kind: 'payment' | 'instalment'; id: string };

/** The longest a comment may be, matching `FeeComment.body` on the server. */
export const COMMENT_MAX_LENGTH = 1000;

export function CommentCountButton({
  count,
  label,
  onClick,
}: {
  count: number;
  /** Which row this is, for the accessible name — a column of identical
   *  "Comments" buttons tells a screen reader nothing. */
  label: string;
  onClick: () => void;
}) {
  return (
    <Button
      type="button"
      variant="ghost"
      size="sm"
      onClick={onClick}
      aria-label={count > 0 ? `Comments on ${label} (${count})` : `Comment on ${label}`}
    >
      <MessageSquare className="size-4" aria-hidden="true" />
      <span className="tabular-nums">{count > 0 ? count : 'Comment'}</span>
    </Button>
  );
}

export function CommentThreadDialog({
  open,
  target,
  title,
  description,
  canWrite,
  onClose,
  onAdded,
}: {
  open: boolean;
  /** Null while no row is chosen; the dialog renders closed. */
  target: CommentTarget | null;
  title: string;
  description: string;
  canWrite: boolean;
  onClose: () => void;
  /** Called after a comment lands, so the row's count can move without a
   *  reload of the whole fee card. */
  onAdded?: (target: CommentTarget) => void;
}) {
  const [comments, setComments] = useState<FeeComment[] | null>(null);
  const [loadFailure, setLoadFailure] = useState<string | null>(null);
  const [body, setBody] = useState('');
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);

  const key = target ? `${target.kind}:${target.id}` : '';
  // A different row starts afresh: reset by key during render rather than
  // from an effect, as the other dialogs in this app do.
  const [shownFor, setShownFor] = useState(key);
  if (shownFor !== key) {
    setComments(null);
    setLoadFailure(null);
    setBody('');
    setFailure(null);
    setShownFor(key);
  }

  // Retrying bumps this rather than calling a loader, so every state change
  // from the read happens in a promise callback: setting state synchronously
  // inside an effect body is what `react-hooks/set-state-in-effect` is for,
  // and the rest of this app loads the same way (`FeeEmails`).
  const [attempt, setAttempt] = useState(0);
  const kind = target?.kind;
  const id = target?.id;

  useEffect(() => {
    if (!open || !kind || !id) return undefined;
    let cancelled = false;
    const read = kind === 'payment' ? listPaymentComments : listInstalmentComments;
    read(id)
      .then((rows) => {
        if (!cancelled) setComments(rows);
      })
      .catch((cause: unknown) => {
        if (!cancelled) setLoadFailure(errorMessage(cause, 'The thread could not be read.'));
      });
    return () => {
      cancelled = true;
    };
  }, [open, kind, id, attempt]);

  async function submit() {
    if (!target) return;
    const text = body.trim();
    if (!text) {
      setFailure('Write something first.');
      return;
    }
    setBusy(true);
    setFailure(null);
    try {
      const comment =
        target.kind === 'payment'
          ? await addPaymentComment(target.id, text)
          : await addInstalmentComment(target.id, text);
      setComments((rows) => [...(rows ?? []), comment]);
      setBody('');
      onAdded?.(target);
    } catch (cause) {
      // `fieldErrors` flattens each field to one string, so this is the
      // message itself — not an array to index into.
      const fields = fieldErrors(cause);
      setFailure(fields.body ?? errorMessage(cause, 'The comment could not be saved.'));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Dialog open={open && target !== null} onOpenChange={(next) => (next ? undefined : onClose())}>
      <DialogContent className="max-h-[85vh] max-w-xl overflow-y-auto">
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          <DialogDescription>{description}</DialogDescription>
        </DialogHeader>

        {loadFailure ? (
          <ErrorState
            message={loadFailure}
            onRetry={() => {
              setLoadFailure(null);
              setAttempt((value) => value + 1);
            }}
          />
        ) : comments === null ? (
          <LoadingState label="Reading the thread" />
        ) : comments.length === 0 ? (
          <p className="text-sm text-ink-muted">
            Nothing written about this one yet.
          </p>
        ) : (
          <ol className="space-y-3">
            {comments.map((comment) => (
              <li key={comment.id} className="rounded-card border border-line px-3 py-2">
                <p className="whitespace-pre-wrap text-sm">{comment.body}</p>
                <p className="mt-1 text-2xs text-ink-faint">
                  {comment.author ?? 'A former colleague'} · {formatDateTime(comment.created_at)}
                </p>
              </li>
            ))}
          </ol>
        )}

        {canWrite ? (
          <>
            {failure ? <Alert variant="error">{failure}</Alert> : null}
            <Field
              label="Add a comment"
              htmlFor="fee-comment-body"
              hint="Kept for the next person who opens this row. Nothing here is sent to the student, and a comment cannot be edited once added."
            >
              <Textarea
                id="fee-comment-body"
                rows={3}
                maxLength={COMMENT_MAX_LENGTH}
                value={body}
                onChange={(event) => setBody(event.target.value)}
              />
            </Field>
          </>
        ) : null}

        <DialogFooter>
          <Button type="button" variant="ghost" onClick={onClose}>
            Close
          </Button>
          {canWrite ? (
            <Button type="button" disabled={busy || body.trim().length === 0} onClick={() => void submit()}>
              {busy ? 'Adding…' : 'Add comment'}
            </Button>
          ) : null}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
