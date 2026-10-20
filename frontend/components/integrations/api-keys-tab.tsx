'use client';

/**
 * Lead API keys: how Meritto, a website form or an ad platform posts leads
 * into the enquiry pipeline. A key is shown once; the list shows only its
 * prefix, what it has sent, and lets it be revoked.
 */

import { KeyRound, Plus } from 'lucide-react';
import { useCallback, useEffect, useState } from 'react';

import { CopyOnce } from '@/components/integrations/copy-once';
import { useBranches } from '@/components/organisation/branch-field';
import { EmptyState, ErrorState, LoadingState } from '@/components/states';
import { Alert } from '@/components/ui/alert';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
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
  createApiKey,
  leadEndpoint,
  listApiKeys,
  listIntakes,
  revokeApiKey,
} from '@/lib/integrations';
import { INTEGRATION_PRESET_LABEL, LEAD_SOURCE_OPTIONS } from '@/lib/labels';
import type { ApiKeyCreated, IntegrationApiKey, IntegrationPreset, LeadIntake } from '@/types/api';

const INTAKE_LABEL: Record<LeadIntake['status'], string> = {
  created: 'New enquiry',
  updated: 'Matched an open enquiry',
  rejected: 'Refused',
};
const INTAKE_VARIANT: Record<LeadIntake['status'], 'success' | 'info' | 'error'> = {
  created: 'success',
  updated: 'info',
  rejected: 'error',
};

function origin(): string {
  return typeof window === 'undefined' ? '' : window.location.origin;
}

function NewKeyDialog({
  open,
  onOpenChange,
  onCreated,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onCreated: () => void;
}) {
  const [name, setName] = useState('');
  const [preset, setPreset] = useState<IntegrationPreset>('meritto');
  const [branch, setBranch] = useState('');
  const [source, setSource] = useState('website');
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [message, setMessage] = useState('');
  const [saving, setSaving] = useState(false);
  const [created, setCreated] = useState<ApiKeyCreated | null>(null);
  const { branches } = useBranches(open);

  function close(next: boolean) {
    if (!next) {
      setName('');
      setPreset('meritto');
      setBranch('');
      setSource('website');
      setErrors({});
      setMessage('');
      setCreated(null);
    }
    onOpenChange(next);
  }

  async function save(event: React.FormEvent) {
    event.preventDefault();
    setSaving(true);
    setErrors({});
    setMessage('');
    try {
      const row = await createApiKey({
        name: name.trim(),
        preset,
        branch: branch || null,
        default_source: source,
      });
      setCreated(row);
      onCreated();
    } catch (cause) {
      const fields = fieldErrors(cause);
      setErrors(fields);
      if (!Object.keys(fields).length) setMessage(errorMessage(cause, 'Could not create the key.'));
    } finally {
      setSaving(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={close}>
      <DialogContent>
        {created ? (
          <>
            <DialogHeader>
              <DialogTitle>Key created</DialogTitle>
              <DialogDescription>
                Paste it into {created.preset === 'meritto' ? "Meritto's webhook settings" : 'the system sending leads'}{' '}
                as <code className="font-mono">Authorization: Bearer &lt;key&gt;</code>.
              </DialogDescription>
            </DialogHeader>
            <CopyOnce label={`API key for ${created.name}`} value={created.key} />
            <DialogFooter>
              <Button type="button" onClick={() => close(false)}>
                Done
              </Button>
            </DialogFooter>
          </>
        ) : (
          <form onSubmit={(event) => void save(event)} noValidate>
            <DialogHeader>
              <DialogTitle>New API key</DialogTitle>
              <DialogDescription>
                A key can do one thing: add or update enquiries at one centre. You can revoke it at
                any time.
              </DialogDescription>
            </DialogHeader>
            <div className="space-y-3">
              {message ? <Alert variant="error">{message}</Alert> : null}
              <Field label="Name" htmlFor="key-name" error={errors.name} required>
                <Input
                  value={name}
                  autoFocus
                  onChange={(event) => setName(event.target.value)}
                  placeholder="e.g. Meritto — Jaipur leads"
                />
              </Field>
              <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                <Field
                  label="Sent by"
                  htmlFor="key-preset"
                  hint="Meritto's own field names are understood."
                >
                  <Select
                    value={preset}
                    onChange={(event) => setPreset(event.target.value as IntegrationPreset)}
                  >
                    <option value="meritto">{INTEGRATION_PRESET_LABEL.meritto}</option>
                    <option value="generic">{INTEGRATION_PRESET_LABEL.generic}</option>
                  </Select>
                </Field>
                <Field
                  label="Source if the lead does not say"
                  htmlFor="key-source"
                  error={errors.default_source}
                >
                  <Select value={source} onChange={(event) => setSource(event.target.value)}>
                    {LEAD_SOURCE_OPTIONS.map((option) => (
                      <option key={option.value} value={option.value}>
                        {option.label}
                      </option>
                    ))}
                  </Select>
                </Field>
              </div>
              <Field
                label="Centre the leads go to"
                htmlFor="key-branch"
                error={errors.branch}
                hint="Leave empty for leads that belong to no centre yet."
              >
                <Select value={branch} onChange={(event) => setBranch(event.target.value)}>
                  <option value="">No centre</option>
                  {branches.map((row) => (
                    <option key={row.id} value={row.id}>
                      {row.name} ({row.code})
                    </option>
                  ))}
                </Select>
              </Field>
            </div>
            <DialogFooter>
              <Button type="button" variant="ghost" onClick={() => close(false)} disabled={saving}>
                Cancel
              </Button>
              <Button type="submit" disabled={saving || name.trim() === ''}>
                {saving ? 'Creating…' : 'Create key'}
              </Button>
            </DialogFooter>
          </form>
        )}
      </DialogContent>
    </Dialog>
  );
}

function IntakesList({ keyId }: { keyId: string }) {
  const [rows, setRows] = useState<LeadIntake[] | null>(null);
  const [error, setError] = useState('');

  useEffect(() => {
    let cancelled = false;
    listIntakes(keyId)
      .then((result) => {
        if (!cancelled) setRows(result);
      })
      .catch((cause: unknown) => {
        if (!cancelled) setError(errorMessage(cause, 'Could not load the leads.'));
      });
    return () => {
      cancelled = true;
    };
  }, [keyId]);

  if (error) return <ErrorState title="Could not load the leads" message={error} />;
  if (rows === null) return <LoadingState label="Loading leads…" rows={3} />;
  if (rows.length === 0) return <p className="text-sm text-ink-muted">Nothing received yet.</p>;
  return (
    <ul className="max-h-[60vh] divide-y divide-line overflow-y-auto rounded-lg border border-line">
      {rows.map((row) => (
        <li key={row.id} className="space-y-1 px-3 py-2 text-sm">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <span className="font-medium text-ink">
              {row.enquiry_name ?? (row.external_id || 'No enquiry')}
            </span>
            <Badge variant={INTAKE_VARIANT[row.status]}>{INTAKE_LABEL[row.status]}</Badge>
          </div>
          <p className="text-xs text-ink-muted">
            {formatDateTime(row.created_at)}
            {row.external_id ? ` · lead id ${row.external_id}` : ''}
          </p>
          {row.status === 'rejected' ? (
            <p className="text-xs text-danger">
              {Object.values(row.errors).flat().join(' ') || 'Refused.'}
            </p>
          ) : null}
        </li>
      ))}
    </ul>
  );
}

function IntakesDialog({ apiKey, onClose }: { apiKey: IntegrationApiKey | null; onClose: () => void }) {
  return (
    <Dialog open={apiKey !== null} onOpenChange={(open) => (open ? null : onClose())}>
      <DialogContent size="lg">
        <DialogHeader>
          <DialogTitle>Leads from {apiKey?.name}</DialogTitle>
          <DialogDescription>The last 100 requests, newest first.</DialogDescription>
        </DialogHeader>
        {apiKey ? <IntakesList key={apiKey.id} keyId={apiKey.id} /> : null}
      </DialogContent>
    </Dialog>
  );
}

export function ApiKeysTab() {
  const [rows, setRows] = useState<IntegrationApiKey[] | null>(null);
  const [error, setError] = useState('');
  const [creating, setCreating] = useState(false);
  const [viewing, setViewing] = useState<IntegrationApiKey | null>(null);
  const [revoking, setRevoking] = useState('');
  const [confirming, setConfirming] = useState<IntegrationApiKey | null>(null);
  const [notice, setNotice] = useState('');

  const load = useCallback(() => {
    listApiKeys()
      .then((result) => {
        setRows(result);
        setError('');
      })
      .catch((cause: unknown) => setError(errorMessage(cause, 'Could not load the keys.')));
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  async function revoke(row: IntegrationApiKey) {
    setRevoking(row.id);
    setNotice('');
    try {
      await revokeApiKey(row.id);
      setNotice(`${row.name} is revoked. Anything still using it now gets "401".`);
      load();
    } catch (cause) {
      setNotice(errorMessage(cause, 'Could not revoke the key.'));
    } finally {
      setRevoking('');
      setConfirming(null);
    }
  }

  const endpoint = leadEndpoint(origin());

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <KeyRound className="size-5 text-action" aria-hidden="true" />
            Leads from Meritto or your website
          </CardTitle>
          <CardDescription>
            Meritto manages your leads and sends each one here when it is ready to admit. It lands
            in “Ready to admit” at the key&apos;s centre, read-only, showing Meritto&apos;s stage
            and owner, for a counsellor to register. The same Meritto lead id (or mobile) again
            updates it rather than adding a second. A website key&apos;s leads are ordinary LMS
            enquiries instead.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-2 text-sm">
          <p>
            <span className="text-ink-muted">Address: </span>
            <code className="break-all font-mono text-xs">POST {endpoint}</code>
          </p>
          <pre className="overflow-x-auto rounded-control bg-sunken p-3 font-mono text-xs leading-relaxed">
            {`curl -X POST ${endpoint} \\
  -H "Authorization: Bearer grk_…" \\
  -H "Content-Type: application/json" \\
  -d '{"name": "Riya Sharma", "mobile": "9829011111", "course": "DevOps"}'`}
          </pre>
        </CardContent>
      </Card>

      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-lg font-semibold">API keys</h2>
        <Button size="sm" onClick={() => setCreating(true)}>
          <Plus className="size-4" aria-hidden="true" />
          New API key
        </Button>
      </div>
      {notice ? <Alert variant="info">{notice}</Alert> : null}

      {error ? (
        <ErrorState title="Could not load the keys" message={error} onRetry={load} />
      ) : rows === null ? (
        <LoadingState label="Loading keys…" rows={3} />
      ) : rows.length === 0 ? (
        <EmptyState
          title="No API keys yet"
          description="Create one for Meritto or your website to start receiving leads."
        />
      ) : (
        <TableWrapper>
          <Table>
            <thead>
              <tr>
                <Th>Name</Th>
                <Th>Key</Th>
                <Th>Sent by</Th>
                <Th>Centre</Th>
                <Th className="text-right">Leads</Th>
                <Th>Last used</Th>
                <Th>Status</Th>
                <Th className="text-right">Actions</Th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <Tr key={row.id} className={row.is_active ? undefined : 'text-ink-muted'}>
                  <Td className="font-medium">{row.name}</Td>
                  <Td className="font-mono text-xs">{row.display}</Td>
                  <Td>{INTEGRATION_PRESET_LABEL[row.preset]}</Td>
                  <Td>{row.branch_name ?? <span className="text-ink-faint">None</span>}</Td>
                  <Td className="text-right tabular-nums">{row.intake_count}</Td>
                  <Td className="whitespace-nowrap">
                    {row.last_used_at ? formatDateTime(row.last_used_at) : 'Never'}
                  </Td>
                  <Td>
                    <Badge variant={row.is_active ? 'success' : 'neutral'}>
                      {row.is_active ? 'Active' : 'Revoked'}
                    </Badge>
                  </Td>
                  <Td className="text-right">
                    <div className="flex justify-end gap-1">
                      <Button size="sm" variant="ghost" onClick={() => setViewing(row)}>
                        Recent leads
                      </Button>
                      {row.is_active ? (
                        <Button
                          size="sm"
                          variant="ghost"
                          className="text-danger"
                          disabled={revoking === row.id}
                          aria-label={`Revoke ${row.name}`}
                          onClick={() => setConfirming(row)}
                        >
                          {revoking === row.id ? 'Revoking…' : 'Revoke'}
                        </Button>
                      ) : null}
                    </div>
                  </Td>
                </Tr>
              ))}
            </tbody>
          </Table>
        </TableWrapper>
      )}

      <Dialog open={confirming !== null} onOpenChange={(open) => (open ? null : setConfirming(null))}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Revoke {confirming?.name}?</DialogTitle>
            <DialogDescription>
              Anything still sending leads with this key stops working at once. This cannot be
              undone; make a new key if it is needed again.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button type="button" variant="ghost" onClick={() => setConfirming(null)}>
              Keep it
            </Button>
            <Button
              type="button"
              variant="destructive"
              disabled={revoking !== ''}
              onClick={() => (confirming ? void revoke(confirming) : null)}
            >
              {revoking ? 'Revoking…' : 'Revoke key'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
      <NewKeyDialog open={creating} onOpenChange={setCreating} onCreated={load} />
      <IntakesDialog apiKey={viewing} onClose={() => setViewing(null)} />
    </div>
  );
}
