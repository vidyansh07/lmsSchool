/**
 * The delivery log (`components/communication/deliveries-tab.tsx`): filters
 * drive the request, and row actions (retry/cancel) are gated by the row's
 * own state, never offered on a row they would be refused for.
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { DeliveriesTab } from '@/components/communication/deliveries-tab';
import type { Delivery, Paginated } from '@/types/api';

const useApi = vi.hoisted(() => vi.fn());
vi.mock('@/hooks/use-api', () => ({ useApi }));

const retryDelivery = vi.hoisted(() => vi.fn());
const cancelDelivery = vi.hoisted(() => vi.fn());
vi.mock('@/lib/communication', async () => {
  const actual = await vi.importActual<typeof import('@/lib/communication')>('@/lib/communication');
  return { ...actual, retryDelivery, cancelDelivery };
});

function delivery(overrides: Partial<Delivery> = {}): Delivery {
  return {
    id: 'd-1',
    channel: 'email',
    recipient: 'user-1',
    recipient_name: 'Aisha Khan',
    address: 'aisha@example.com',
    template_version: 'v-1',
    template_key: 'batch_assigned',
    variables: {},
    state: 'failed',
    attempts: 3,
    next_attempt_at: null,
    provider_message_id: '',
    error: 'SMTP timeout',
    requested_by: null,
    requested_by_name: null,
    created_at: '2026-09-01T00:00:00Z',
    updated_at: '2026-09-02T00:00:00Z',
    ...overrides,
  };
}

function page(results: Delivery[]): Paginated<Delivery> {
  return { count: results.length, page: 1, page_size: 25, total_pages: 1, next: null, previous: null, results };
}

let lastPath = '';
function mockUseApi(data: Paginated<Delivery> | null, reload = vi.fn()) {
  useApi.mockImplementation((path: string) => {
    lastPath = path;
    return { data, error: null, isLoading: false, reload };
  });
  return reload;
}

beforeEach(() => {
  vi.clearAllMocks();
  lastPath = '';
});

describe('DeliveriesTab — row actions gated by state', () => {
  it('offers Retry only on a failed row, and Cancel only on a queued one', () => {
    mockUseApi(page([delivery({ id: 'd-failed', state: 'failed' }), delivery({ id: 'd-queued', state: 'queued' }), delivery({ id: 'd-sent', state: 'sent' })]));
    render(<DeliveriesTab canAct />);

    expect(screen.getAllByRole('button', { name: /^retry$/i })).toHaveLength(1);
    expect(screen.getAllByRole('button', { name: /^cancel$/i })).toHaveLength(1);
  });

  it('hides every row action when the caller cannot act', () => {
    mockUseApi(page([delivery({ state: 'failed' })]));
    render(<DeliveriesTab canAct={false} />);
    expect(screen.queryByRole('button', { name: /^retry$/i })).not.toBeInTheDocument();
    expect(screen.queryByText('Actions')).not.toBeInTheDocument();
  });

  it('retries a failed row and reloads the list', async () => {
    const reload = mockUseApi(page([delivery({ id: 'd-failed', state: 'failed' })]));
    retryDelivery.mockResolvedValue(delivery({ id: 'd-failed', state: 'queued' }));
    render(<DeliveriesTab canAct />);

    fireEvent.click(screen.getByRole('button', { name: /^retry$/i }));
    await waitFor(() => expect(retryDelivery).toHaveBeenCalledWith('d-failed'));
    await waitFor(() => expect(reload).toHaveBeenCalled());
  });
});

describe('DeliveriesTab — filters', () => {
  it('includes a chosen channel and state in the request', () => {
    mockUseApi(page([]));
    render(<DeliveriesTab canAct={false} />);

    fireEvent.change(screen.getByLabelText('Channel'), { target: { value: 'whatsapp' } });
    fireEvent.change(screen.getByLabelText('State'), { target: { value: 'failed' } });

    expect(lastPath).toContain('channel=whatsapp');
    expect(lastPath).toContain('state=failed');
  });

  it('includes a recipient id and a template key filter', () => {
    mockUseApi(page([]));
    render(<DeliveriesTab canAct={false} />);

    fireEvent.change(screen.getByLabelText('Recipient ID'), { target: { value: 'user-1' } });
    fireEvent.change(screen.getByLabelText('Template key'), { target: { value: 'batch_assigned' } });

    expect(lastPath).toContain('recipient=user-1');
    expect(lastPath).toContain('template=batch_assigned');
  });

  it('shows an empty state naming the active filters', () => {
    mockUseApi(page([]));
    render(<DeliveriesTab canAct={false} />);
    fireEvent.change(screen.getByLabelText('Channel'), { target: { value: 'whatsapp' } });
    expect(screen.getByText(/no deliveries match these filters/i)).toBeInTheDocument();
  });
});
