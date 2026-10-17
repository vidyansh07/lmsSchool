/**
 * Integrations: a lead API key is shown once and can be revoked after a
 * confirmation; a webhook's signing secret is shown once, its header values
 * are never shown again, and a test send reports what the receiver said.
 * Webhooks are generic only — nothing is sent back to Meritto.
 */
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { ApiKeysTab } from '@/components/integrations/api-keys-tab';
import { WebhooksTab } from '@/components/integrations/webhooks-tab';
import type { IntegrationApiKey, Webhook } from '@/types/api';

const api = vi.hoisted(() => ({
  listApiKeys: vi.fn(),
  createApiKey: vi.fn(),
  revokeApiKey: vi.fn(),
  listIntakes: vi.fn(),
  listWebhooks: vi.fn(),
  createWebhook: vi.fn(),
  updateWebhook: vi.fn(),
  testWebhook: vi.fn(),
  listDeliveries: vi.fn(),
}));
vi.mock('@/lib/integrations', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/lib/integrations')>()),
  ...api,
}));
vi.mock('@/lib/organisation', () => ({
  listBranches: vi.fn().mockResolvedValue({
    count: 1,
    next: null,
    previous: null,
    results: [{ id: 'b-1', name: 'Jaipur', code: 'JPR', city: 'Jaipur', is_active: true }],
  }),
}));
vi.mock('@/components/auth-provider', () => ({
  useAuth: () => ({ user: { role: 'admin', capabilities: ['integration.manage'] } }),
}));

function key(overrides: Partial<IntegrationApiKey> = {}): IntegrationApiKey {
  return {
    id: 'k-1',
    name: 'Meritto Jaipur',
    preset: 'meritto',
    display: 'grk_ab12cd34_…',
    branch: 'b-1',
    branch_name: 'Jaipur',
    default_source: 'website',
    field_map: {},
    is_active: true,
    last_used_at: null,
    revoked_at: null,
    created_by_name: 'Amy Admin',
    created_at: '2026-10-17T10:00:00Z',
    intake_count: 3,
    ...overrides,
  };
}

function webhook(overrides: Partial<Webhook> = {}): Webhook {
  return {
    id: 'w-1',
    name: 'Accounts',
    preset: 'generic',
    url: 'https://accounts.example.test/in',
    header_names: ['x-token'],
    has_secret: true,
    is_active: true,
    created_at: '2026-10-17T10:00:00Z',
    updated_at: '2026-10-17T10:00:00Z',
    last_delivery: null,
    ...overrides,
  };
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe('ApiKeysTab', () => {
  it('shows a new key once and lists keys by prefix only', async () => {
    api.listApiKeys.mockResolvedValue([key()]);
    api.createApiKey.mockResolvedValue({ ...key({ id: 'k-2', name: 'Website' }), key: 'grk_ff_secret' });
    render(<ApiKeysTab />);

    expect(await screen.findByText('grk_ab12cd34_…')).toBeInTheDocument();
    expect(screen.getByText(/Ready to admit/)).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: /new api key/i }));
    const dialog = await screen.findByRole('dialog');
    fireEvent.change(within(dialog).getByLabelText(/^Name/), { target: { value: 'Website' } });
    await waitFor(() =>
      expect(within(dialog).getByRole('option', { name: 'Jaipur (JPR)' })).toBeInTheDocument(),
    );
    fireEvent.change(within(dialog).getByLabelText(/Centre the leads go to/), {
      target: { value: 'b-1' },
    });
    fireEvent.click(within(dialog).getByRole('button', { name: 'Create key' }));

    await waitFor(() =>
      expect(api.createApiKey).toHaveBeenCalledWith({
        name: 'Website',
        preset: 'meritto',
        branch: 'b-1',
        default_source: 'website',
      }),
    );
    expect(await within(dialog).findByText('grk_ff_secret')).toBeInTheDocument();
    expect(within(dialog).getByText(/will not be shown again/)).toBeInTheDocument();
  });

  it('asks before revoking a key', async () => {
    api.listApiKeys.mockResolvedValue([key()]);
    api.revokeApiKey.mockResolvedValue(key({ is_active: false }));
    render(<ApiKeysTab />);
    fireEvent.click(await screen.findByRole('button', { name: 'Revoke Meritto Jaipur' }));
    const confirm = await screen.findByRole('dialog');
    expect(within(confirm).getByText(/stops working at once/)).toBeInTheDocument();
    expect(api.revokeApiKey).not.toHaveBeenCalled();
    fireEvent.click(within(confirm).getByRole('button', { name: 'Revoke key' }));
    await waitFor(() => expect(api.revokeApiKey).toHaveBeenCalledWith('k-1'));
  });

  it('shows why a lead was refused', async () => {
    api.listApiKeys.mockResolvedValue([key()]);
    api.listIntakes.mockResolvedValue([
      {
        id: 'i-1',
        status: 'rejected',
        enquiry: null,
        enquiry_name: null,
        external_id: 'MER-9',
        payload: {},
        errors: { non_field_errors: ['An enquiry needs a name and a mobile number.'] },
        created_at: '2026-10-17T10:00:00Z',
      },
    ]);
    render(<ApiKeysTab />);
    fireEvent.click(await screen.findByRole('button', { name: 'Recent leads' }));
    expect(await screen.findByText('Refused')).toBeInTheDocument();
    expect(screen.getByText(/needs a name and a mobile/)).toBeInTheDocument();
  });
});

describe('WebhooksTab', () => {
  it('creates a generic webhook and shows its secret once', async () => {
    api.listWebhooks.mockResolvedValue([]);
    api.createWebhook.mockResolvedValue({ ...webhook(), secret: 'sig-secret' });
    render(<WebhooksTab />);
    expect(await screen.findByText(/Nothing is sent back to Meritto/)).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: /new webhook/i }));
    const dialog = await screen.findByRole('dialog');
    expect(within(dialog).queryByLabelText(/Sends to/)).not.toBeInTheDocument();
    fireEvent.change(within(dialog).getByLabelText(/^Name/), { target: { value: 'Accounts' } });
    fireEvent.change(within(dialog).getByLabelText(/^Address/), {
      target: { value: 'https://accounts.example.test/in' },
    });
    fireEvent.click(within(dialog).getByRole('button', { name: /add a header/i }));
    fireEvent.change(within(dialog).getByLabelText('Header 1 name'), { target: { value: 'x-token' } });
    fireEvent.change(within(dialog).getByLabelText('Header 1 value'), { target: { value: 'T-1' } });
    fireEvent.click(within(dialog).getByRole('button', { name: 'Create webhook' }));

    await waitFor(() =>
      expect(api.createWebhook).toHaveBeenCalledWith({
        name: 'Accounts',
        preset: 'generic',
        url: 'https://accounts.example.test/in',
        headers: { 'x-token': 'T-1' },
      }),
    );
    expect(await within(dialog).findByText('sig-secret')).toBeInTheDocument();
  });

  it('reports what the receiver said to a test', async () => {
    api.listWebhooks.mockResolvedValue([webhook()]);
    api.testWebhook.mockResolvedValue({
      id: 'd-1',
      event: 'test',
      rule: null,
      rule_name: null,
      ok: false,
      status_code: 422,
      error: 'The receiver answered 422.',
      response_excerpt: '',
      duration_ms: 40,
      created_at: '2026-10-17T10:00:00Z',
    });
    render(<WebhooksTab />);
    fireEvent.click(await screen.findByRole('button', { name: 'Send a test to Accounts' }));
    expect(await screen.findByText(/did not accept the test: The receiver answered 422/)).toBeInTheDocument();
  });

  it('never shows saved header values when changing a webhook', async () => {
    api.listWebhooks.mockResolvedValue([webhook()]);
    render(<WebhooksTab />);
    fireEvent.click(await screen.findByRole('button', { name: 'Change Accounts' }));
    const dialog = await screen.findByRole('dialog');
    expect(within(dialog).getByText('Headers set: x-token')).toBeInTheDocument();
    expect(within(dialog).queryByLabelText('Header 1 value')).not.toBeInTheDocument();
  });
});
