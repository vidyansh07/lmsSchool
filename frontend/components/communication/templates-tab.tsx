'use client';

/**
 * The template list (`GET /templates/`) plus "New template", matching
 * `app/admin/automation/page.tsx`'s "ask only the identifying fields, hand
 * off to the detail route for everything else" shape: a template's body,
 * variables allowlist and approve/publish actions all live on
 * `app/admin/communication/templates/[key]/page.tsx`.
 */

import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useState } from 'react';
import { Plus } from 'lucide-react';

import { useAuth } from '@/components/auth-provider';
import { DataTable, type DataTableColumn } from '@/components/data-table';
import { Pagination } from '@/components/pagination';
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
import { useApi } from '@/hooks/use-api';
import { fieldErrors } from '@/lib/api';
import { Capability, can } from '@/lib/capabilities';
import { createTemplate } from '@/lib/communication';
import {
  COMMUNICATION_CHANNEL_LABEL,
  COMMUNICATION_CHANNEL_OPTIONS,
  TEMPLATE_STATUS_LABEL,
  TEMPLATE_STATUS_VARIANT,
} from '@/lib/labels';
import { formatDateTime } from '@/lib/format';
import type { CommunicationChannel, MessageTemplate, Paginated } from '@/types/api';

function NewTemplateDialog({
  open,
  onClose,
  onCreated,
}: {
  open: boolean;
  onClose: () => void;
  onCreated: (key: string) => void;
}) {
  const [key, setKey] = useState('');
  const [name, setName] = useState('');
  const [channel, setChannel] = useState<CommunicationChannel>('email');
  const [kind, setKind] = useState('');
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState(false);

  function reset() {
    setKey('');
    setName('');
    setChannel('email');
    setKind('');
    setErrors({});
  }

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setSaving(true);
    setErrors({});
    try {
      const created = await createTemplate({
        key: key.trim(),
        name: name.trim(),
        channel,
        kind: kind.trim(),
      });
      reset();
      onCreated(created.key);
    } catch (cause) {
      setErrors(fieldErrors(cause));
    } finally {
      setSaving(false);
    }
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        if (!next) {
          reset();
          onClose();
        }
      }}
    >
      <DialogContent>
        <form className="space-y-4" onSubmit={(event) => void submit(event)} noValidate>
          <DialogHeader>
            <DialogTitle>New template</DialogTitle>
            <DialogDescription>
              Starts with an empty draft version. Add the subject, body and variables allowlist
              on the next screen.
            </DialogDescription>
          </DialogHeader>
          {errors.__all__ ? <Alert variant="error">{errors.__all__}</Alert> : null}
          <Field label="Key" htmlFor="template-key" error={errors.key} required hint="A unique, stable identifier, e.g. batch_assigned.">
            <Input
              id="template-key"
              autoFocus
              value={key}
              onChange={(event) => setKey(event.target.value)}
            />
          </Field>
          <Field label="Name" htmlFor="template-name" error={errors.name} required>
            <Input id="template-name" value={name} onChange={(event) => setName(event.target.value)} />
          </Field>
          <Field label="Channel" htmlFor="template-channel" error={errors.channel} required>
            <Select
              id="template-channel"
              value={channel}
              onChange={(event) => setChannel(event.target.value as CommunicationChannel)}
            >
              {COMMUNICATION_CHANNEL_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </Select>
          </Field>
          <Field
            label="Kind"
            htmlFor="template-kind"
            error={errors.kind}
            required
            hint="The event this template answers, e.g. activity.assigned."
          >
            <Input id="template-kind" value={kind} onChange={(event) => setKind(event.target.value)} />
          </Field>
          <DialogFooter>
            <Button type="button" variant="ghost" onClick={onClose}>
              Cancel
            </Button>
            <Button type="submit" disabled={saving || !key.trim() || !name.trim() || !kind.trim()}>
              {saving ? 'Creating…' : 'Create template'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

export function TemplatesTab() {
  const router = useRouter();
  const { user } = useAuth();
  const mayManage = can(user?.capabilities, Capability.templateManage);
  const [page, setPage] = useState(1);
  const { data, error, isLoading, reload } = useApi<Paginated<MessageTemplate>>(
    `/api/v1/templates/?page=${page}`,
  );
  const [creating, setCreating] = useState(false);

  const rows = data?.results ?? [];

  if (isLoading) return <LoadingState label="Loading templates…" rows={6} />;
  if (error) {
    return (
      <ErrorState
        title="Could not load templates"
        message={error.message}
        requestId={error.requestId || undefined}
        onRetry={reload}
      />
    );
  }

  const columns: DataTableColumn<MessageTemplate>[] = [
    {
      key: 'key',
      header: 'Key',
      sticky: 'start',
      render: (row) => (
        <Link
          href={`/admin/communication/templates/${row.key}`}
          className="font-mono text-xs font-medium underline-offset-2 hover:underline"
        >
          {row.key}
        </Link>
      ),
    },
    { key: 'name', header: 'Name', render: (row) => row.name },
    { key: 'channel', header: 'Channel', render: (row) => COMMUNICATION_CHANNEL_LABEL[row.channel] },
    {
      key: 'status',
      header: 'Status',
      render: (row) => (
        <Badge variant={TEMPLATE_STATUS_VARIANT[row.status]}>{TEMPLATE_STATUS_LABEL[row.status]}</Badge>
      ),
    },
    {
      key: 'current_version',
      header: 'Published',
      render: (row) => (row.current_version ? `v${row.current_version.number}` : '—'),
    },
    {
      key: 'draft_version',
      header: 'In progress',
      render: (row) =>
        row.draft_version
          ? `v${row.draft_version.number}${row.draft_version.approved_at ? ' (approved)' : ''}`
          : '—',
    },
    { key: 'updated_at', header: 'Updated', render: (row) => formatDateTime(row.updated_at) },
  ];

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <p className="text-sm text-muted-foreground">
          A template with a published version overrides the code fallback for that key and
          channel. Everything here is rendered by substituting an explicit variable allowlist —
          never evaluated as code.
        </p>
        {mayManage ? (
          <Button type="button" onClick={() => setCreating(true)}>
            <Plus className="size-4" aria-hidden="true" />
            New template
          </Button>
        ) : null}
      </div>

      {rows.length === 0 ? (
        <EmptyState
          title="No templates yet"
          description="Create the first one to override a code fallback for a channel."
          action={
            mayManage ? (
              <Button type="button" onClick={() => setCreating(true)}>
                <Plus className="size-4" aria-hidden="true" />
                New template
              </Button>
            ) : undefined
          }
        />
      ) : (
        <DataTable
          columns={columns}
          rows={rows}
          getRowId={(row) => row.key}
          caption="Templates"
          densityStorageKey="grras.templates-density"
        />
      )}

      {data && data.count > 0 ? (
        <Pagination
          page={data.page}
          totalPages={data.total_pages}
          count={data.count}
          pageSize={data.page_size}
          onPageChange={setPage}
        />
      ) : null}

      <NewTemplateDialog
        open={creating}
        onClose={() => setCreating(false)}
        onCreated={(key) => {
          setCreating(false);
          router.push(`/admin/communication/templates/${key}`);
        }}
      />
    </div>
  );
}
