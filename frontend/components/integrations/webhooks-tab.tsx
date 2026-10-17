'use client';

/**
 * Webhooks: addresses an automation rule's "Send to a webhook" action posts
 * to — a payment told to an accounts system, a registration to a sheet.
 * Generic JSON only: nothing is ever sent back to Meritto, which only sends
 * leads in (owner's decision, 17 October 2026).
 * Secrets and header values are write-only: the screen shows which headers
 * are set, never what they are.
 */

import { Link2, Plus, Trash2 } from 'lucide-react';
import { useCallback, useEffect, useState } from 'react';

import { CopyOnce } from '@/components/integrations/copy-once';
import { EmptyState, ErrorState, LoadingState } from '@/components/states';
import { Alert } from '@/components/ui/alert';
import { Badge } from '@/components/ui/badge';
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
import { Input, Select } from '@/components/ui/input';
import { Table, TableWrapper, Td, Th, Tr } from '@/components/ui/table';
import { errorMessage, fieldErrors } from '@/lib/api';
import { formatDateTime } from '@/lib/format';
import {
  createWebhook,
  listDeliveries,
  listWebhooks,
  testWebhook,
  updateWebhook,
} from '@/lib/integrations';
import type { Webhook, WebhookDelivery } from '@/types/api';

interface HeaderRow {
  name: string;
  value: string;
}

function HeaderRows({
  rows,
  onChange,
  disabled,
}: {
  rows: HeaderRow[];
  onChange: (rows: HeaderRow[]) => void;
  disabled: boolean;
}) {
  return (
    <fieldset className="space-y-2">
      <legend className="text-xs font-medium text-ink">Headers sent with every request</legend>
      {rows.map((row, index) => (
        <div key={index} className="flex gap-2">
          <Input
            aria-label={`Header ${index + 1} name`}
            className="w-40"
            value={row.name}
            disabled={disabled}
            placeholder="access-key"
            onChange={(event) =>
              onChange(rows.map((r, i) => (i === index ? { ...r, name: event.target.value } : r)))
            }
          />
          <Input
            aria-label={`Header ${index + 1} value`}
            type="password"
            autoComplete="off"
            className="min-w-0 flex-1"
            value={row.value}
            disabled={disabled}
            placeholder="value"
            onChange={(event) =>
              onChange(rows.map((r, i) => (i === index ? { ...r, value: event.target.value } : r)))
            }
          />
          <Button
            type="button"
            size="sm"
            variant="ghost"
            aria-label={`Remove header ${index + 1}`}
            disabled={disabled}
            onClick={() => onChange(rows.filter((_, i) => i !== index))}
          >
            <Trash2 className="size-4" aria-hidden="true" />
          </Button>
        </div>
      ))}
      <Button
        type="button"
        size="sm"
        variant="outline"
        disabled={disabled}
        onClick={() => onChange([...rows, { name: '', value: '' }])}
      >
        <Plus className="size-4" aria-hidden="true" />
        Add a header
      </Button>
    </fieldset>
  );
}

function headersObject(rows: HeaderRow[]): Record<string, string> {
  return Object.fromEntries(
    rows.filter((row) => row.name.trim()).map((row) => [row.name.trim(), row.value]),
  );
}

function WebhookDialog({
  webhook,
  open,
  onOpenChange,
  onSaved,
}: {
  webhook: Webhook | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSaved: () => void;
}) {
  const editing = webhook !== null;
  const [name, setName] = useState(webhook?.name ?? '');
  const [url, setUrl] = useState(webhook?.url ?? '');
  const [headers, setHeaders] = useState<HeaderRow[]>(
    (webhook?.header_names ?? []).map((header) => ({ name: header, value: '' })),
  );
  const [replaceHeaders, setReplaceHeaders] = useState(!editing);
  const [active, setActive] = useState(webhook?.is_active ?? true);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [message, setMessage] = useState('');
  const [saving, setSaving] = useState(false);
  const [secret, setSecret] = useState('');

  async function save(event: React.FormEvent) {
    event.preventDefault();
    setSaving(true);
    setErrors({});
    setMessage('');
    try {
      const saved = editing
        ? await updateWebhook(webhook.id, {
            name: name.trim(),
            url: url.trim(),
            is_active: active,
            ...(replaceHeaders ? { headers: headersObject(headers) } : {}),
          })
        : await createWebhook({
            name: name.trim(),
            preset: 'generic',
            url: url.trim(),
            headers: headersObject(headers),
          });
      onSaved();
      if (saved.secret) setSecret(saved.secret);
      else onOpenChange(false);
    } catch (cause) {
      const fields = fieldErrors(cause);
      setErrors(fields);
      if (!fields.url && !fields.name && !fields.headers) {
        setMessage(errorMessage(cause, 'Could not save the webhook.'));
      }
    } finally {
      setSaving(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent size="lg">
        {secret ? (
          <>
            <DialogHeader>
              <DialogTitle>Webhook saved</DialogTitle>
              <DialogDescription>
                Every request carries <code className="font-mono">X-Grras-Signature: sha256=…</code>
                , an HMAC of the body with this secret, so the receiver can check it came from here.
              </DialogDescription>
            </DialogHeader>
            <CopyOnce label="Signing secret" value={secret} />
            <DialogFooter>
              <Button type="button" onClick={() => onOpenChange(false)}>
                Done
              </Button>
            </DialogFooter>
          </>
        ) : (
          <form onSubmit={(event) => void save(event)} noValidate>
            <DialogHeader>
              <DialogTitle>{editing ? `Change ${webhook.name}` : 'New webhook'}</DialogTitle>
              <DialogDescription>
                An automation rule’s “Send to a webhook” action posts there. Only public https://
                addresses are accepted.
              </DialogDescription>
            </DialogHeader>
            <div className="space-y-3">
              {message ? <Alert variant="error">{message}</Alert> : null}
              <Field label="Name" htmlFor="hook-name" error={errors.name} required>
                <Input
                  value={name}
                  autoFocus
                  onChange={(event) => setName(event.target.value)}
                  placeholder="e.g. Accounts — payments"
                />
              </Field>
              <Field label="Address" htmlFor="hook-url" error={errors.url} required>
                <Input
                  type="url"
                  value={url}
                  onChange={(event) => setUrl(event.target.value)}
                  placeholder="https://"
                />
              </Field>
              {editing && !replaceHeaders ? (
                <div className="flex flex-wrap items-center justify-between gap-2 rounded-md bg-sunken/60 px-3 py-2 text-sm">
                  <span>
                    {webhook.header_names.length
                      ? `Headers set: ${webhook.header_names.join(', ')}`
                      : 'No extra headers.'}
                  </span>
                  <Button type="button" size="sm" variant="outline" onClick={() => setReplaceHeaders(true)}>
                    Replace headers
                  </Button>
                </div>
              ) : (
                <>
                  <HeaderRows rows={headers} onChange={setHeaders} disabled={saving} />
                  {errors.headers ? <p className="text-2xs font-medium text-danger">{errors.headers}</p> : null}
                </>
              )}
              {editing ? (
                <Field label="Status" htmlFor="hook-active">
                  <Select
                    value={active ? 'on' : 'off'}
                    onChange={(event) => setActive(event.target.value === 'on')}
                  >
                    <option value="on">On — rules may send to it</option>
                    <option value="off">Off — rules that send to it fail</option>
                  </Select>
                </Field>
              ) : null}
            </div>
            <DialogFooter>
              <Button type="button" variant="ghost" disabled={saving} onClick={() => onOpenChange(false)}>
                Cancel
              </Button>
              <Button type="submit" disabled={saving || !name.trim() || !url.trim()}>
                {saving ? 'Saving…' : editing ? 'Save changes' : 'Create webhook'}
              </Button>
            </DialogFooter>
          </form>
        )}
      </DialogContent>
    </Dialog>
  );
}

function DeliveriesList({ webhookId }: { webhookId: string }) {
  const [rows, setRows] = useState<WebhookDelivery[] | null>(null);
  const [error, setError] = useState('');

  useEffect(() => {
    let cancelled = false;
    listDeliveries(webhookId)
      .then((result) => {
        if (!cancelled) setRows(result);
      })
      .catch((cause: unknown) => {
        if (!cancelled) setError(errorMessage(cause, 'Could not load the deliveries.'));
      });
    return () => {
      cancelled = true;
    };
  }, [webhookId]);

  if (error) return <ErrorState title="Could not load the deliveries" message={error} />;
  if (rows === null) return <LoadingState label="Loading deliveries…" rows={3} />;
  if (rows.length === 0) return <p className="text-sm text-ink-muted">Nothing sent yet.</p>;
  return (
    <ul className="max-h-[60vh] divide-y divide-line overflow-y-auto rounded-lg border border-line">
      {rows.map((row) => (
        <li key={row.id} className="space-y-1 px-3 py-2 text-sm">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <span className="font-medium text-ink">
              {row.event}
              {row.rule_name ? ` · ${row.rule_name}` : ''}
            </span>
            <Badge variant={row.ok ? 'success' : 'error'}>
              {row.ok
                ? `Delivered (${row.status_code})`
                : row.status_code
                  ? `Refused (${row.status_code})`
                  : 'Not sent'}
            </Badge>
          </div>
          <p className="text-xs text-ink-muted">
            {formatDateTime(row.created_at)} · {row.duration_ms} ms
            {row.error ? ` · ${row.error}` : ''}
          </p>
        </li>
      ))}
    </ul>
  );
}

function DeliveriesDialog({ webhook, onClose }: { webhook: Webhook | null; onClose: () => void }) {
  return (
    <Dialog open={webhook !== null} onOpenChange={(open) => (open ? null : onClose())}>
      <DialogContent size="lg">
        <DialogHeader>
          <DialogTitle>Deliveries to {webhook?.name}</DialogTitle>
          <DialogDescription>The last 100, newest first.</DialogDescription>
        </DialogHeader>
        {webhook ? <DeliveriesList key={webhook.id} webhookId={webhook.id} /> : null}
      </DialogContent>
    </Dialog>
  );
}

export function WebhooksTab() {
  const [rows, setRows] = useState<Webhook[] | null>(null);
  const [error, setError] = useState('');
  const [editing, setEditing] = useState<Webhook | null | 'new'>(null);
  const [viewing, setViewing] = useState<Webhook | null>(null);
  const [testing, setTesting] = useState('');
  const [notice, setNotice] = useState<{ tone: 'success' | 'error'; text: string } | null>(null);

  const load = useCallback(() => {
    listWebhooks()
      .then((result) => {
        setRows(result);
        setError('');
      })
      .catch((cause: unknown) => setError(errorMessage(cause, 'Could not load the webhooks.')));
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  async function test(row: Webhook) {
    setTesting(row.id);
    setNotice(null);
    try {
      const delivery = await testWebhook(row.id);
      setNotice(
        delivery.ok
          ? { tone: 'success', text: `${row.name} answered ${delivery.status_code}.` }
          : {
              tone: 'error',
              text: `${row.name} did not accept the test: ${delivery.error || delivery.status_code}.`,
            },
      );
      load();
    } catch (cause) {
      setNotice({ tone: 'error', text: errorMessage(cause, 'Could not send the test.') });
    } finally {
      setTesting('');
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h2 className="flex items-center gap-2 text-lg font-semibold">
            <Link2 className="size-5 text-action" aria-hidden="true" />
            Webhooks
          </h2>
          <p className="text-sm text-ink-muted">
            Use one in an automation rule (“Send to a webhook”) to tell another system about a
            payment or a registration. Nothing is sent back to Meritto.
          </p>
        </div>
        <Button size="sm" onClick={() => setEditing('new')}>
          <Plus className="size-4" aria-hidden="true" />
          New webhook
        </Button>
      </div>
      {notice ? (
        <Alert variant={notice.tone === 'success' ? 'success' : 'error'}>{notice.text}</Alert>
      ) : null}

      {error ? (
        <ErrorState title="Could not load the webhooks" message={error} onRetry={load} />
      ) : rows === null ? (
        <LoadingState label="Loading webhooks…" rows={3} />
      ) : rows.length === 0 ? (
        <EmptyState
          title="No webhooks yet"
          description="Add the address of a system that should hear about events here."
        />
      ) : (
        <TableWrapper>
          <Table>
            <thead>
              <tr>
                <Th>Name</Th>
                <Th>Address</Th>
                <Th>Last delivery</Th>
                <Th>Status</Th>
                <Th className="text-right">Actions</Th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <Tr key={row.id}>
                  <Td className="font-medium">{row.name}</Td>
                  <Td className="max-w-xs truncate font-mono text-xs" title={row.url}>
                    {row.url}
                  </Td>
                  <Td className="whitespace-nowrap">
                    {row.last_delivery ? (
                      <Badge variant={row.last_delivery.ok ? 'success' : 'error'}>
                        {row.last_delivery.ok ? 'Delivered' : 'Failed'} ·{' '}
                        {formatDateTime(row.last_delivery.created_at)}
                      </Badge>
                    ) : (
                      'Never'
                    )}
                  </Td>
                  <Td>
                    <Badge variant={row.is_active ? 'success' : 'neutral'}>
                      {row.is_active ? 'On' : 'Off'}
                    </Badge>
                  </Td>
                  <Td className="text-right">
                    <div className="flex justify-end gap-1">
                      <Button
                        size="sm"
                        variant="ghost"
                        disabled={testing === row.id || !row.is_active}
                        aria-label={`Send a test to ${row.name}`}
                        onClick={() => void test(row)}
                      >
                        {testing === row.id ? 'Testing…' : 'Test'}
                      </Button>
                      <Button size="sm" variant="ghost" onClick={() => setViewing(row)}>
                        Deliveries
                      </Button>
                      <Button
                        size="sm"
                        variant="ghost"
                        aria-label={`Change ${row.name}`}
                        onClick={() => setEditing(row)}
                      >
                        Change
                      </Button>
                    </div>
                  </Td>
                </Tr>
              ))}
            </tbody>
          </Table>
        </TableWrapper>
      )}

      {editing !== null ? (
        <WebhookDialog
          key={editing === 'new' ? 'new' : editing.id}
          webhook={editing === 'new' ? null : editing}
          open
          onOpenChange={(open) => (open ? null : setEditing(null))}
          onSaved={load}
        />
      ) : null}
      <DeliveriesDialog webhook={viewing} onClose={() => setViewing(null)} />
    </div>
  );
}
