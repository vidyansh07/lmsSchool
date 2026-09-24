'use client';

/**
 * Manual send (`POST /communication/send/`, `communication.send`):
 * channel + published template + a recipient spec, a server-resolved
 * recipient COUNT shown before anything is sent, an explicit confirmation
 * naming that exact count, then the real send with `confirm_count`.
 *
 * The count is never computed here — `previewCommunicationCount`
 * (`lib/communication.ts`) always asks the server, because a client-side
 * count of "students in this batch" could be stale, wrongly scoped, or
 * simply wrong the moment a roster changes underneath it, and this is the
 * one screen in the app whose entire safety property is "the number you
 * confirmed is the number of people this actually reaches".
 *
 * State machine: idle → (Preview count) → reviewing countN → (Send, confirmed)
 * → sent | staleCount(newCountN) → back to reviewing with the fresh number.
 * A stale-count 409 is never shown as a generic error — the contract is
 * explicit that this is an expected, named outcome ("the roster changed
 * between preview and confirm"), so this state gets its own message and its
 * own "review the new count" action rather than folding into `failure`.
 */

import { useState } from 'react';

import { Alert } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Field } from '@/components/ui/field';
import { Input, Select } from '@/components/ui/input';
import { useApi } from '@/hooks/use-api';
import { ApiError, errorMessage } from '@/lib/api';
import {
  previewCommunicationCount,
  sendCommunication,
  type SendCommunicationPayload,
} from '@/lib/communication';
import { COMMUNICATION_CHANNEL_OPTIONS, ROLE_OPTIONS } from '@/lib/labels';
import { search } from '@/lib/search';
import type {
  BatchListRow,
  CommunicationChannel,
  MessageTemplate,
  Paginated,
} from '@/types/api';

type RecipientMode = 'students' | 'batch' | 'role';
type Phase = 'idle' | 'reviewing' | 'sending' | 'sent' | 'stale';

export function ManualSend() {
  const [channel, setChannel] = useState<CommunicationChannel>('email');
  const { data: templatePage } = useApi<Paginated<MessageTemplate>>(
    `/api/v1/templates/?channel=${channel}&status=published`,
  );
  const templates = (templatePage?.results ?? []).filter((row) => row.channel === channel);
  const [templateKey, setTemplateKey] = useState('');

  const [mode, setMode] = useState<RecipientMode>('batch');
  const [batchId, setBatchId] = useState('');
  const { data: batchPage } = useApi<Paginated<BatchListRow>>('/api/v1/batches/?page_size=100');
  const [role, setRole] = useState(ROLE_OPTIONS[0]?.value ?? '');
  const [studentQuery, setStudentQuery] = useState('');
  const [studentOptions, setStudentOptions] = useState<{ id: string; title: string }[]>([]);
  const [isSearchingStudents, setIsSearchingStudents] = useState(false);
  const [selectedStudents, setSelectedStudents] = useState<{ id: string; title: string }[]>([]);

  const activeTemplate = templates.find((row) => row.key === templateKey) ?? null;
  const templateVariables = activeTemplate?.current_version?.variables ?? [];
  const [variables, setVariables] = useState<Record<string, string>>({});

  const [phase, setPhase] = useState<Phase>('idle');
  const [count, setCount] = useState<number | null>(null);
  const [failure, setFailure] = useState<string | null>(null);
  const [isChecking, setIsChecking] = useState(false);
  const [isSending, setIsSending] = useState(false);

  function recipients(): SendCommunicationPayload['recipients'] {
    if (mode === 'batch') return { batch: batchId };
    if (mode === 'role') return { role };
    return { students: selectedStudents.map((entry) => entry.id) };
  }

  function recipientsReady(): boolean {
    if (mode === 'batch') return Boolean(batchId);
    if (mode === 'role') return Boolean(role);
    return selectedStudents.length > 0;
  }

  const canCheck = Boolean(templateKey) && recipientsReady();

  async function runStudentSearch(query: string) {
    setStudentQuery(query);
    if (query.trim().length < 2) {
      setStudentOptions([]);
      return;
    }
    setIsSearchingStudents(true);
    try {
      const response = await search({ q: query, types: ['students'] });
      const group = response.groups.find((entry) => entry.type === 'students');
      setStudentOptions((group?.results ?? []).map((item) => ({ id: item.id, title: item.title })));
    } catch {
      setStudentOptions([]);
    } finally {
      setIsSearchingStudents(false);
    }
  }

  function addStudent(option: { id: string; title: string }) {
    if (selectedStudents.some((entry) => entry.id === option.id)) return;
    setSelectedStudents([...selectedStudents, option]);
    setStudentQuery('');
    setStudentOptions([]);
  }

  function removeStudent(id: string) {
    setSelectedStudents(selectedStudents.filter((entry) => entry.id !== id));
  }

  async function checkCount() {
    setIsChecking(true);
    setFailure(null);
    try {
      const resolved = await previewCommunicationCount({
        channel,
        template: templateKey,
        recipients: recipients(),
        variables,
      });
      setCount(resolved);
      setPhase('reviewing');
    } catch (cause) {
      setFailure(errorMessage(cause, 'Could not resolve the recipient count.'));
    } finally {
      setIsChecking(false);
    }
  }

  async function confirmSend() {
    if (count == null) return;
    setIsSending(true);
    setFailure(null);
    try {
      await sendCommunication({
        channel,
        template: templateKey,
        recipients: recipients(),
        variables,
        confirm_count: count,
      });
      setPhase('sent');
    } catch (cause) {
      if (cause instanceof ApiError && cause.status === 409) {
        // The roster changed since the count above was shown — never retry
        // silently with the stale number; hand the person a fresh one to
        // look at and confirm again.
        setPhase('stale');
      } else {
        setFailure(errorMessage(cause, 'Could not send.'));
      }
    } finally {
      setIsSending(false);
    }
  }

  async function recheckAfterStale() {
    setPhase('idle');
    setCount(null);
    await checkCount();
  }

  function startOver() {
    setPhase('idle');
    setCount(null);
    setFailure(null);
  }

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <CardTitle>Send a message</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <Field label="Channel" htmlFor="send-channel">
            <Select
              id="send-channel"
              value={channel}
              disabled={phase !== 'idle'}
              onChange={(event) => {
                setChannel(event.target.value as CommunicationChannel);
                setTemplateKey('');
                startOver();
              }}
            >
              {COMMUNICATION_CHANNEL_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </Select>
          </Field>

          <Field label="Template" htmlFor="send-template" hint="Only published templates on this channel can be sent.">
            <Select
              id="send-template"
              value={templateKey}
              disabled={phase !== 'idle'}
              onChange={(event) => {
                setTemplateKey(event.target.value);
                setVariables({});
                startOver();
              }}
            >
              <option value="">Choose a template…</option>
              {templates.map((row) => (
                <option key={row.key} value={row.key}>
                  {row.name}
                </option>
              ))}
            </Select>
          </Field>

          <Field label="Send to" htmlFor="send-mode">
            <Select
              id="send-mode"
              value={mode}
              disabled={phase !== 'idle'}
              onChange={(event) => {
                setMode(event.target.value as RecipientMode);
                startOver();
              }}
            >
              <option value="batch">A batch</option>
              <option value="role">Everyone in a role</option>
              <option value="students">Specific students</option>
            </Select>
          </Field>

          {mode === 'batch' ? (
            <Field label="Batch" htmlFor="send-batch">
              <Select
                id="send-batch"
                value={batchId}
                disabled={phase !== 'idle'}
                onChange={(event) => {
                  setBatchId(event.target.value);
                  startOver();
                }}
              >
                <option value="">Choose a batch…</option>
                {(batchPage?.results ?? []).map((batch) => (
                  <option key={batch.id} value={batch.id}>
                    {batch.code} · {batch.name}
                  </option>
                ))}
              </Select>
            </Field>
          ) : null}

          {mode === 'role' ? (
            <Field label="Role" htmlFor="send-role">
              <Select
                id="send-role"
                value={role}
                disabled={phase !== 'idle'}
                onChange={(event) => {
                  setRole(event.target.value);
                  startOver();
                }}
              >
                {ROLE_OPTIONS.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </Select>
            </Field>
          ) : null}

          {mode === 'students' ? (
            <div className="space-y-2">
              <Field label="Add a student" htmlFor="send-student-search">
                <Input
                  id="send-student-search"
                  disabled={phase !== 'idle'}
                  value={studentQuery}
                  placeholder="Search by name…"
                  onChange={(event) => void runStudentSearch(event.target.value)}
                />
              </Field>
              {isSearchingStudents ? <p className="text-xs text-ink-muted">Searching…</p> : null}
              {studentOptions.length > 0 ? (
                <ul className="rounded-md border border-line">
                  {studentOptions.map((option) => (
                    <li key={option.id}>
                      <button
                        type="button"
                        className="w-full px-3 py-2 text-left text-sm hover:bg-sunken"
                        onClick={() => addStudent(option)}
                      >
                        {option.title}
                      </button>
                    </li>
                  ))}
                </ul>
              ) : null}
              <div className="flex flex-wrap gap-2">
                {selectedStudents.map((entry) => (
                  <span
                    key={entry.id}
                    className="inline-flex items-center gap-1 rounded-full bg-sunken px-2.5 py-0.5 text-xs"
                  >
                    {entry.title}
                    {phase === 'idle' ? (
                      <button
                        type="button"
                        aria-label={`Remove ${entry.title}`}
                        onClick={() => removeStudent(entry.id)}
                        className="rounded-full transition-colors hover:bg-line hover:text-ink"
                      >
                        ×
                      </button>
                    ) : null}
                  </span>
                ))}
              </div>
            </div>
          ) : null}

          {templateVariables.length > 0 ? (
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              {templateVariables.map((name) => (
                <Field key={name} label={name} htmlFor={`send-var-${name}`}>
                  <Input
                    id={`send-var-${name}`}
                    disabled={phase !== 'idle'}
                    value={variables[name] ?? ''}
                    onChange={(event) => setVariables({ ...variables, [name]: event.target.value })}
                  />
                </Field>
              ))}
            </div>
          ) : null}

          {failure ? <Alert variant="error">{failure}</Alert> : null}

          {phase === 'idle' ? (
            <Button type="button" disabled={!canCheck || isChecking} onClick={() => void checkCount()}>
              {isChecking ? 'Checking…' : 'Check recipient count'}
            </Button>
          ) : null}

          {phase === 'reviewing' && count != null ? (
            <Alert variant="warning" data-testid="send-count-confirm">
              <p>
                This will reach <strong>{count}</strong> recipient{count === 1 ? '' : 's'}. Sending
                cannot be undone.
              </p>
              <div className="mt-2 flex gap-2">
                <Button type="button" disabled={isSending} onClick={() => void confirmSend()}>
                  {isSending ? 'Sending…' : `Send to ${count}`}
                </Button>
                <Button type="button" variant="ghost" onClick={startOver}>
                  Cancel
                </Button>
              </div>
            </Alert>
          ) : null}

          {phase === 'stale' ? (
            <Alert variant="error" data-testid="send-count-stale">
              <p>
                The recipient count changed since you last checked — sending was refused so you do
                not confirm a number that is no longer accurate. Review the new count before
                sending.
              </p>
              <Button type="button" size="sm" className="mt-2" onClick={() => void recheckAfterStale()}>
                Review again
              </Button>
            </Alert>
          ) : null}

          {phase === 'sent' ? (
            <Alert variant="success" role="status">
              Queued for {count} recipient{count === 1 ? '' : 's'}.
              <Button type="button" variant="ghost" size="sm" className="ml-2" onClick={startOver}>
                Send another
              </Button>
            </Alert>
          ) : null}
        </CardContent>
      </Card>
    </div>
  );
}
