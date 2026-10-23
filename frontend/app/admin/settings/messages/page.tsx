'use client';

/**
 * Message Setting — who hears about what, and how.
 *
 * One tab per group of events, and under it a row per event with a column
 * per recipient and a box per channel. The matrix is the whole screen: there
 * is nothing else to say about an event except who is told and how.
 *
 * Three things the screen is careful about:
 *
 * * **It draws what the server sends.** The tabs, the events, the recipients
 *   and the channels all arrive with the data, so adding an event on the
 *   server adds a row here without anybody editing this file.
 * * **A box is saved when it is clicked**, not on a Save button. There are
 *   thirty of them and a person changes one; a form that makes you hunt for
 *   Save after each is a form people leave half-saved.
 * * **SMS is labelled honestly.** The rule is stored and the audience is
 *   resolved, and there is no SMS provider wired yet — so the column says so
 *   rather than letting an institute believe texts are going out.
 */

import { Fragment, useCallback, useEffect, useState } from 'react';

import { RequireAuth } from '@/components/require-auth';
import { ErrorState, LoadingState } from '@/components/states';
import { Alert } from '@/components/ui/alert';
import { Card, CardContent } from '@/components/ui/card';
import { PageHeader } from '@/components/ui/layout';
import { ApiError } from '@/lib/api';
import { Capability } from '@/lib/capabilities';
import {
  getMessageSettings,
  setMessageRules,
  type MessageMatrix,
} from '@/lib/message-settings';

function cellKey(event: string, recipient: string, channel: string): string {
  return `${event}|${recipient}|${channel}`;
}

export function MessageSettingsScreen() {
  const [matrix, setMatrix] = useState<MessageMatrix | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [tab, setTab] = useState(0);
  const [saving, setSaving] = useState<string | null>(null);

  const load = useCallback(() => {
    let cancelled = false;
    getMessageSettings()
      .then((found) => {
        if (!cancelled) {
          setMatrix(found);
          setError(null);
        }
      })
      .catch((cause: unknown) => {
        if (!cancelled) setError(cause instanceof ApiError ? cause : null);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => load(), [load]);

  const enabled = new Set(
    (matrix?.rules ?? [])
      .filter((rule) => rule.is_enabled)
      .map((rule) => cellKey(rule.event, rule.recipient, rule.channel)),
  );

  async function toggle(event: string, recipient: string, channel: string, next: boolean) {
    const key = cellKey(event, recipient, channel);
    setSaving(key);
    try {
      const updated = await setMessageRules([
        { event, recipient, channel, is_enabled: next },
      ]);
      setMatrix(updated);
    } catch (cause) {
      setError(cause instanceof ApiError ? cause : null);
    } finally {
      setSaving(null);
    }
  }

  if (error && matrix === null) {
    return (
      <ErrorState
        title="Could not load the message settings"
        message={error.message}
        requestId={error.requestId || undefined}
        onRetry={load}
      />
    );
  }
  if (matrix === null) return <LoadingState label="Loading message settings…" rows={6} />;

  const current = matrix.tabs[tab] ?? matrix.tabs[0];

  return (
    <div className="space-y-5">
      <PageHeader
        title="Message Setting"
        meta="When and how the institute writes to students, guardians and the counsellor who owns them."
      />

      {error ? <Alert variant="error">{error.message}</Alert> : null}

      <Alert variant="info">
        SMS rules are stored and the audience is worked out, but no SMS provider is connected
        yet — nothing is actually texted. E-Mail and Notification are live.
      </Alert>

      <nav className="flex flex-wrap gap-1" aria-label="Message settings">
        {matrix.tabs.map((entry, index) => (
          <button
            key={entry.title}
            type="button"
            onClick={() => setTab(index)}
            aria-current={index === tab ? 'page' : undefined}
            className={
              index === tab
                ? 'rounded-control bg-action px-3 py-1.5 text-sm font-medium text-action-fg'
                : 'rounded-control px-3 py-1.5 text-sm text-action hover:bg-sunken'
            }
          >
            {entry.title}
          </button>
        ))}
      </nav>

      <Card>
        <CardContent className="overflow-x-auto pt-5">
          <table className="w-full min-w-[40rem] text-sm">
            <caption className="sr-only">
              Which channels each event reaches each recipient on
            </caption>
            <thead>
              <tr className="border-b border-line text-left">
                <th scope="col" className="py-2 pr-4 font-semibold text-ink">
                  {current?.title}
                </th>
                {matrix.channels.map((channel) => (
                  <th key={channel.key} scope="col" className="px-3 py-2 text-center font-medium">
                    {channel.label}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {(current?.events ?? []).map((event) => (
                // The key belongs on the fragment: each event renders a
                // heading row plus one row per recipient, and keying the
                // first `tr` instead leaves the rest unkeyed.
                <Fragment key={event.key}>
                  <tr className="border-b border-line bg-sunken/40">
                    <th
                      scope="rowgroup"
                      colSpan={matrix.channels.length + 1}
                      className="py-2 pr-4 text-left font-semibold text-ink"
                    >
                      {event.label}
                    </th>
                  </tr>
                  {matrix.recipients.map((recipient) => (
                    <tr key={`${event.key}-${recipient.key}`} className="border-b border-line">
                      <th scope="row" className="py-2 pr-4 text-left font-normal text-ink-muted">
                        {recipient.label}
                      </th>
                      {matrix.channels.map((channel) => {
                        const key = cellKey(event.key, recipient.key, channel.key);
                        return (
                          <td key={channel.key} className="px-3 py-2 text-center">
                            <input
                              type="checkbox"
                              checked={enabled.has(key)}
                              disabled={saving === key}
                              onChange={(change) =>
                                void toggle(
                                  event.key,
                                  recipient.key,
                                  channel.key,
                                  change.target.checked,
                                )
                              }
                              aria-label={`${event.label}: ${recipient.label} by ${channel.label}`}
                              className="size-4 accent-[var(--color-action)]"
                            />
                          </td>
                        );
                      })}
                    </tr>
                  ))}
                </Fragment>
              ))}
            </tbody>
          </table>
        </CardContent>
      </Card>
    </div>
  );
}

export default function MessageSettingsPage() {
  return (
    <RequireAuth capability={Capability.settingsManage}>
      <MessageSettingsScreen />
    </RequireAuth>
  );
}
