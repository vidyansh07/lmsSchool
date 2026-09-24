'use client';

/**
 * The delivery log (`GET /deliveries/`, `communication.view_any`) —
 * filterable by channel/state/recipient/template/date range, with a retry
 * button on `failed` rows and a cancel button on `queued` ones
 * (`COMMUNICATION_CATALOG.md` "Delivery log screen").
 */

import { useState } from 'react';

import { DataTable, type DataTableColumn } from '@/components/data-table';
import { Pagination } from '@/components/pagination';
import { Alert } from '@/components/ui/alert';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Field } from '@/components/ui/field';
import { Input, Select } from '@/components/ui/input';
import { useApi } from '@/hooks/use-api';
import { errorMessage, queryString } from '@/lib/api';
import { cancelDelivery, retryDelivery, type DeliveryFilters } from '@/lib/communication';
import {
  COMMUNICATION_CHANNEL_LABEL,
  COMMUNICATION_CHANNEL_OPTIONS,
  DELIVERY_STATE_LABEL,
  DELIVERY_STATE_OPTIONS,
  DELIVERY_STATE_VARIANT,
} from '@/lib/labels';
import { formatDateTime } from '@/lib/format';
import type { CommunicationChannel, Delivery, DeliveryState, Paginated } from '@/types/api';

const EMPTY_FILTERS: DeliveryFilters = {};

export function DeliveriesTab({ canAct }: { canAct: boolean }) {
  const [channel, setChannel] = useState<CommunicationChannel | ''>('');
  const [state, setState] = useState<DeliveryState | ''>('');
  const [recipient, setRecipient] = useState('');
  const [template, setTemplate] = useState('');
  const [since, setSince] = useState('');
  const [until, setUntil] = useState('');
  const [page, setPage] = useState(1);

  const [busy, setBusy] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  const filters: DeliveryFilters = {
    channel: channel || undefined,
    state: state || undefined,
    recipient: recipient.trim() || undefined,
    template: template.trim() || undefined,
    since: since || undefined,
    until: until || undefined,
    page,
  };

  // `useApi` (`hooks/use-api.ts`) owns the fetch/loading/error state — the
  // same "state is a pure function of the request identity" shape every
  // other filtered list in this app uses, which is also what avoids calling
  // `setState` synchronously from an effect body.
  const { data, error, isLoading, reload } = useApi<Paginated<Delivery>>(
    `/api/v1/deliveries/${queryString(filters)}`,
  );

  async function act(id: string, run: () => Promise<Delivery>) {
    setBusy(id);
    setActionError(null);
    try {
      await run();
      reload();
    } catch (cause) {
      setActionError(errorMessage(cause, 'That could not be done.'));
    } finally {
      setBusy(null);
    }
  }

  function resetFilters() {
    setChannel('');
    setState('');
    setRecipient('');
    setTemplate('');
    setSince('');
    setUntil('');
    setPage(1);
  }

  const rows = data?.results ?? [];
  const hasFilters = JSON.stringify(filters) !== JSON.stringify({ ...EMPTY_FILTERS, page });

  const columns: DataTableColumn<Delivery>[] = [
    { key: 'channel', header: 'Channel', render: (row) => COMMUNICATION_CHANNEL_LABEL[row.channel] },
    { key: 'recipient', header: 'Recipient', render: (row) => row.recipient_name ?? (row.address || '—') },
    {
      key: 'template_key',
      header: 'Template',
      render: (row) => <span className="font-mono text-xs">{row.template_key ?? '—'}</span>,
    },
    {
      key: 'state',
      header: 'State',
      render: (row) => (
        <>
          <Badge variant={DELIVERY_STATE_VARIANT[row.state]}>{DELIVERY_STATE_LABEL[row.state]}</Badge>
          {row.error ? <p className="mt-1 text-xs text-ink-muted">{row.error}</p> : null}
        </>
      ),
    },
    { key: 'attempts', header: 'Attempts', render: (row) => row.attempts },
    { key: 'updated_at', header: 'Updated', render: (row) => formatDateTime(row.updated_at) },
    ...(canAct
      ? [
          {
            key: 'actions',
            header: 'Actions',
            render: (row: Delivery) => (
              <div className="flex gap-2">
                {row.state === 'failed' ? (
                  <Button
                    type="button"
                    size="sm"
                    variant="outline"
                    disabled={busy === row.id}
                    onClick={() => void act(row.id, () => retryDelivery(row.id))}
                  >
                    {busy === row.id ? 'Retrying…' : 'Retry'}
                  </Button>
                ) : null}
                {row.state === 'queued' ? (
                  <Button
                    type="button"
                    size="sm"
                    variant="ghost"
                    disabled={busy === row.id}
                    onClick={() => void act(row.id, () => cancelDelivery(row.id))}
                  >
                    {busy === row.id ? 'Cancelling…' : 'Cancel'}
                  </Button>
                ) : null}
              </div>
            ),
          } satisfies DataTableColumn<Delivery>,
        ]
      : []),
  ];

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
        <Field label="Channel" htmlFor="delivery-filter-channel">
          <Select
            id="delivery-filter-channel"
            value={channel}
            onChange={(event) => {
              setChannel(event.target.value as CommunicationChannel | '');
              setPage(1);
            }}
          >
            <option value="">Any</option>
            {COMMUNICATION_CHANNEL_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </Select>
        </Field>
        <Field label="State" htmlFor="delivery-filter-state">
          <Select
            id="delivery-filter-state"
            value={state}
            onChange={(event) => {
              setState(event.target.value as DeliveryState | '');
              setPage(1);
            }}
          >
            <option value="">Any</option>
            {DELIVERY_STATE_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </Select>
        </Field>
        <Field
          label="Recipient ID"
          htmlFor="delivery-filter-recipient"
          hint="The exact user id — the server filters on it directly, not a name search."
        >
          <Input
            id="delivery-filter-recipient"
            value={recipient}
            onChange={(event) => {
              setRecipient(event.target.value);
              setPage(1);
            }}
          />
        </Field>
        <Field label="Template key" htmlFor="delivery-filter-template">
          <Input
            id="delivery-filter-template"
            value={template}
            onChange={(event) => {
              setTemplate(event.target.value);
              setPage(1);
            }}
          />
        </Field>
        <Field label="Since" htmlFor="delivery-filter-since">
          <Input
            id="delivery-filter-since"
            type="date"
            value={since}
            onChange={(event) => {
              setSince(event.target.value);
              setPage(1);
            }}
          />
        </Field>
        <Field label="Until" htmlFor="delivery-filter-until">
          <Input
            id="delivery-filter-until"
            type="date"
            value={until}
            onChange={(event) => {
              setUntil(event.target.value);
              setPage(1);
            }}
          />
        </Field>
      </div>
      {hasFilters ? (
        <Button type="button" variant="ghost" size="sm" onClick={resetFilters}>
          Clear filters
        </Button>
      ) : null}

      {actionError ? <Alert variant="error">{actionError}</Alert> : null}

      <DataTable
        columns={columns}
        rows={rows}
        getRowId={(row) => row.id}
        isLoading={isLoading}
        loadingLabel="Loading deliveries…"
        error={error ? { message: error.message, requestId: error.requestId } : null}
        errorTitle="Could not load deliveries"
        onRetry={reload}
        emptyTitle="No deliveries"
        emptyDescription={hasFilters ? 'No deliveries match these filters.' : 'Nothing has been sent yet.'}
        caption="Deliveries"
        densityStorageKey="grras.deliveries-density"
      />

      {data && data.count > 0 ? (
        <Pagination
          page={data.page}
          totalPages={data.total_pages}
          count={data.count}
          pageSize={data.page_size}
          onPageChange={setPage}
        />
      ) : null}
    </div>
  );
}
