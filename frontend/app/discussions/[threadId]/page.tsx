'use client';

import { useParams } from 'next/navigation';
import { useCallback, useEffect, useState } from 'react';

import { RequireAuth } from '@/components/require-auth';
import { ErrorState, LoadingState } from '@/components/states';
import { Alert } from '@/components/ui/alert';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Field } from '@/components/ui/field';
import { Input, Textarea } from '@/components/ui/input';
import { ApiError, errorMessage } from '@/lib/api';
import { formatDateTime } from '@/lib/academic-labels';
import { getThread, hideReply, moderateThread, replyToThread } from '@/lib/communication';
import type { DiscussionThreadDetail } from '@/types/api';

/** One thread, its replies, and the moderation controls when they apply. */
function ThreadView({ threadId }: { threadId: string }) {
  const [thread, setThread] = useState<DiscussionThreadDetail | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [formError, setFormError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);
  const [body, setBody] = useState('');
  const [reasons, setReasons] = useState<Record<string, string>>({});

  const load = useCallback(async () => {
    setThread(await getThread(threadId));
  }, [threadId]);

  useEffect(() => {
    let cancelled = false;
    getThread(threadId)
      .then((data) => {
        if (!cancelled) setThread(data);
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
  }, [threadId]);

  async function run(key: string, action: () => Promise<unknown>) {
    setBusy(key);
    setFormError(null);
    try {
      await action();
      await load();
    } catch (cause) {
      setFormError(errorMessage(cause, 'That could not be done.'));
    } finally {
      setBusy(null);
    }
  }

  if (isLoading) return <LoadingState label="Loading the discussion…" rows={5} />;
  if (error) {
    return (
      <ErrorState
        title="Could not load this discussion"
        message={error.message}
        requestId={error.requestId || undefined}
      />
    );
  }
  if (!thread) return null;

  return (
    <div className="space-y-6">
      <div className="space-y-1">
        <div className="flex flex-wrap items-center gap-2">
          {thread.is_pinned ? <Badge variant="warning">Pinned</Badge> : null}
          {thread.is_closed ? <Badge variant="neutral">Closed</Badge> : null}
          <span className="font-mono text-xs text-muted-foreground">{thread.batch_code}</span>
        </div>
        <h1 className="text-2xl font-semibold tracking-tight">{thread.title}</h1>
        <p className="text-sm text-muted-foreground">
          {thread.author_name} · {formatDateTime(thread.created_at)} · {thread.course_title}
        </p>
      </div>

      {formError ? <Alert variant="error">{formError}</Alert> : null}

      <Card>
        <CardContent className="pt-6">
          <p className="whitespace-pre-wrap text-sm">{thread.body}</p>
        </CardContent>
      </Card>

      {thread.can_moderate ? (
        <div className="flex flex-wrap gap-2">
          <Button
            type="button"
            size="sm"
            variant="outline"
            disabled={busy === 'pin'}
            onClick={() =>
              run('pin', () => moderateThread(thread.id, { pinned: !thread.is_pinned }))
            }
          >
            {thread.is_pinned ? 'Unpin' : 'Pin'}
          </Button>
          <Button
            type="button"
            size="sm"
            variant="outline"
            disabled={busy === 'close'}
            onClick={() =>
              run('close', () => moderateThread(thread.id, { closed: !thread.is_closed }))
            }
          >
            {thread.is_closed ? 'Reopen' : 'Close'}
          </Button>
        </div>
      ) : null}

      <Card>
        <CardHeader>
          <CardTitle>Replies ({thread.replies.length})</CardTitle>
          <CardDescription>
            A trainer&apos;s answer is marked, so it is findable in a long thread.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          {thread.replies.map((item) => (
            <div
              key={item.id}
              data-testid="reply"
              className={`rounded-md border p-3 ${
                item.is_hidden ? 'border-dashed border-border opacity-70' : 'border-border'
              }`}
            >
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-sm font-medium">{item.author_name}</span>
                {item.is_trainer_response ? <Badge variant="success">Trainer</Badge> : null}
                {item.is_hidden ? <Badge variant="error">Hidden</Badge> : null}
                <span className="text-xs text-muted-foreground">
                  {formatDateTime(item.created_at)}
                </span>
              </div>
              <p className="mt-1 whitespace-pre-wrap text-sm">{item.body}</p>
              {item.is_hidden && item.hidden_reason ? (
                <p className="mt-1 text-xs text-muted-foreground">
                  Hidden: {item.hidden_reason}
                </p>
              ) : null}

              {thread.can_moderate && !item.is_hidden ? (
                <div className="mt-2 flex flex-wrap items-end gap-2">
                  <Field label="Reason" htmlFor={`reason-${item.id}`}>
                    <Input
                      id={`reason-${item.id}`}
                      value={reasons[item.id] ?? ''}
                      onChange={(event) =>
                        setReasons({ ...reasons, [item.id]: event.target.value })
                      }
                    />
                  </Field>
                  <Button
                    type="button"
                    size="sm"
                    variant="outline"
                    disabled={busy === item.id || !reasons[item.id]}
                    onClick={() =>
                      run(item.id, () => hideReply(item.id, reasons[item.id] ?? ''))
                    }
                  >
                    Hide
                  </Button>
                </div>
              ) : null}
            </div>
          ))}

          {thread.can_reply ? (
            <form
              className="space-y-2"
              onSubmit={(event) => {
                event.preventDefault();
                void run('reply', async () => {
                  await replyToThread(thread.id, body);
                  setBody('');
                });
              }}
            >
              <Field label="Your reply" htmlFor="reply-body">
                <Textarea
                  id="reply-body"
                  required
                  rows={3}
                  value={body}
                  onChange={(event) => setBody(event.target.value)}
                />
              </Field>
              <Button type="submit" size="sm" disabled={busy === 'reply' || !body.trim()}>
                {busy === 'reply' ? 'Posting…' : 'Reply'}
              </Button>
            </form>
          ) : (
            <p className="text-sm text-muted-foreground">
              {thread.is_closed
                ? 'This thread is closed.'
                : 'You are not on this batch.'}
            </p>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

export default function ThreadPage() {
  const params = useParams<{ threadId: string }>();
  return (
    <RequireAuth>
      <ThreadView threadId={params.threadId} />
    </RequireAuth>
  );
}
