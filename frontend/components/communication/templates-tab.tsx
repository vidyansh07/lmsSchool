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
import { Bell, Mail, MessageCircle, MessageSquare, Plus } from 'lucide-react';

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
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { Field } from '@/components/ui/field';
import { Input, Select } from '@/components/ui/input';
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { useApi } from '@/hooks/use-api';
import { fieldErrors } from '@/lib/api';
import { Capability, can } from '@/lib/capabilities';
import { createTemplate } from '@/lib/communication';
import {
  COMMUNICATION_CHANNEL_LABEL,
  COMMUNICATION_CHANNEL_OPTIONS,
  TEMPLATE_CATEGORY_LABEL,
  TEMPLATE_STATUS_LABEL,
  TEMPLATE_STATUS_VARIANT,
} from '@/lib/labels';
import { formatDateTime } from '@/lib/format';
import {
  UNWIRED_CHANNELS,
  type CommunicationChannel,
  type MessageTemplate,
  type Paginated,
  type TemplateCategory,
} from '@/types/api';

function NewTemplateDialog({
  open,
  startChannel,
  onClose,
  onCreated,
}: {
  open: boolean;
  /** Which channel the Create Template menu was opened on. */
  startChannel: CommunicationChannel;
  onClose: () => void;
  onCreated: (key: string) => void;
}) {
  const [key, setKey] = useState('');
  const [name, setName] = useState('');
  const [channel, setChannel] = useState<CommunicationChannel>(startChannel);
  const [kind, setKind] = useState('');
  const [category, setCategory] = useState<TemplateCategory>('transactional');

  // The menu picks the channel; opening it again on a different one starts
  // there. Reset by key during render rather than from an effect, the
  // convention the activity-types form already uses.
  const resetKey = `${open}#${startChannel}`;
  const [openedFor, setOpenedFor] = useState(resetKey);
  if (openedFor !== resetKey) {
    setChannel(startChannel);
    setOpenedFor(resetKey);
  }
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState(false);

  function reset() {
    setKey('');
    setName('');
    setChannel(startChannel);
    setKind('');
    setCategory('transactional');
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
        category,
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
            label="Category"
            htmlFor="template-category"
            error={errors.category}
            required
            hint="Promotional messages need consent and respect quiet hours; transactional ones — a receipt, a cancellation — may always go."
          >
            <Select
              id="template-category"
              value={category}
              onChange={(event) => setCategory(event.target.value as TemplateCategory)}
            >
              {(Object.keys(TEMPLATE_CATEGORY_LABEL) as TemplateCategory[]).map((value) => (
                <option key={value} value={value}>
                  {TEMPLATE_CATEGORY_LABEL[value]}
                </option>
              ))}
            </Select>
          </Field>
          {UNWIRED_CHANNELS.includes(channel) ? (
            <Alert variant="warning">
              {COMMUNICATION_CHANNEL_LABEL[channel]} has no gateway connected yet. The template
              and its approvals are real; a send on this channel is recorded and fails saying so,
              rather than looking delivered.
            </Alert>
          ) : null}
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

/** View All / Active / InActive / Draft, and what each one means here.
 *
 *  The reference product's four shelves map onto this system's three
 *  template statuses: *Active* is a published template (the one actually in
 *  use), *InActive* is one approved but never published — ready, not live —
 *  and *Draft* is still being written. */
const SHELVES = [
  { key: 'all', label: 'View All', status: '' },
  { key: 'active', label: 'Active', status: 'published' },
  { key: 'inactive', label: 'InActive', status: 'approved' },
  { key: 'draft', label: 'Draft', status: 'draft' },
] as const;

const CHANNEL_ICON: Record<CommunicationChannel, typeof Mail> = {
  email: Mail,
  whatsapp: MessageCircle,
  sms: MessageSquare,
  in_app: Bell,
};

export function TemplatesTab() {
  const router = useRouter();
  const { user } = useAuth();
  const mayManage = can(user?.capabilities, Capability.templateManage);
  const [page, setPage] = useState(1);
  const [shelf, setShelf] = useState<string>('all');
  const { data, error, isLoading, reload } = useApi<Paginated<MessageTemplate>>(
    `/api/v1/templates/?page=${page}`,
  );
  const [creating, setCreating] = useState<CommunicationChannel | null>(null);

  const all = data?.results ?? [];
  const wanted = SHELVES.find((item) => item.key === shelf)?.status ?? '';
  const rows = wanted ? all.filter((row) => row.status === wanted) : all;

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
      key: 'name',
      header: 'Template Name',
      sticky: 'start',
      render: (row) => {
        const Icon = CHANNEL_ICON[row.channel];
        return (
          <span className="flex items-center gap-2">
            <Icon className="size-4 shrink-0 text-ink-muted" aria-hidden="true" />
            <span className="min-w-0">
              <Link
                href={`/admin/communication/templates/${row.key}`}
                className="font-medium underline-offset-2 hover:underline"
              >
                {row.name}
              </Link>
              <span className="block font-mono text-2xs text-ink-muted">{row.key}</span>
            </span>
          </span>
        );
      },
    },
    {
      key: 'subject',
      header: 'Subject Line',
      render: (row) => row.current_version?.subject || row.draft_version?.subject || '—',
    },
    {
      key: 'channel',
      header: 'Campaign Type',
      render: (row) => (
        <span className="flex flex-wrap items-center gap-1.5">
          <Badge>{COMMUNICATION_CHANNEL_LABEL[row.channel]}</Badge>
          {UNWIRED_CHANNELS.includes(row.channel) ? (
            <Badge variant="warning">No gateway</Badge>
          ) : null}
        </span>
      ),
    },
    { key: 'kind', header: 'Applicable For', render: (row) => row.kind },
    {
      key: 'status',
      header: 'Status',
      render: (row) => (
        <Badge variant={TEMPLATE_STATUS_VARIANT[row.status]}>
          {TEMPLATE_STATUS_LABEL[row.status]}
        </Badge>
      ),
    },
    {
      key: 'category',
      header: 'Category',
      render: (row) => TEMPLATE_CATEGORY_LABEL[row.category],
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
        <p className="max-w-prose text-sm text-ink-muted">
          A template with a published version overrides the code fallback for that key and
          channel. Everything here is rendered by substituting an explicit variable allowlist —
          never evaluated as code.
        </p>
        {mayManage ? (
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button type="button">
                <Plus className="size-4" aria-hidden="true" />
                Create Template
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              {COMMUNICATION_CHANNEL_OPTIONS.map((option) => (
                <DropdownMenuItem
                  key={option.value}
                  onSelect={() => setCreating(option.value)}
                >
                  {option.label}
                </DropdownMenuItem>
              ))}
            </DropdownMenuContent>
          </DropdownMenu>
        ) : null}
      </div>

      <Tabs value={shelf} onValueChange={setShelf}>
        <TabsList>
          {SHELVES.map((item) => (
            <TabsTrigger key={item.key} value={item.key}>
              {item.label}
            </TabsTrigger>
          ))}
        </TabsList>
      </Tabs>

      {rows.length === 0 ? (
        <EmptyState
          title={all.length === 0 ? 'No templates yet' : 'Nothing on this shelf'}
          description={
            all.length === 0
              ? 'Create the first one to override a code fallback for a channel.'
              : 'Every template is on another shelf.'
          }
          action={
            mayManage && all.length === 0 ? (
              <Button type="button" onClick={() => setCreating('email')}>
                <Plus className="size-4" aria-hidden="true" />
                Create Template
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
        open={creating !== null}
        startChannel={creating ?? 'email'}
        onClose={() => setCreating(null)}
        onCreated={(key) => {
          setCreating(null);
          router.push(`/admin/communication/templates/${key}`);
        }}
      />
    </div>
  );
}
