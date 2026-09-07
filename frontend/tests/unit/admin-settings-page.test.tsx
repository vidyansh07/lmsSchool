import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import InstitutionSettingsPage from '@/app/admin/settings/page';
import { ApiError } from '@/lib/api';
import { Capability } from '@/lib/capabilities';
import type { SystemSettings } from '@/lib/settings';

const getSettings = vi.hoisted(() => vi.fn());
const updateSettings = vi.hoisted(() => vi.fn());
vi.mock('@/lib/settings', async () => {
  const actual = await vi.importActual<typeof import('@/lib/settings')>('@/lib/settings');
  return { ...actual, getSettings, updateSettings };
});

const mockAuth = vi.hoisted(() => ({
  value: { user: { id: 'u1', role: 'admin' }, isLoading: false, can: () => true } as {
    user: unknown;
    isLoading: boolean;
    can: (capability: string) => boolean;
  },
}));
vi.mock('@/components/auth-provider', () => ({ useAuth: () => mockAuth.value }));
vi.mock('next/navigation', () => ({
  useRouter: () => ({ replace: vi.fn(), push: vi.fn() }),
  usePathname: () => '/admin/settings',
}));

function settings(overrides: Partial<SystemSettings> = {}): SystemSettings {
  return {
    institution_name: 'Sunrise Academy',
    support_email: 'help@sunrise.example.test',
    support_phone: '+91 141 000 0000',
    notification_email_enabled: true,
    export_retention_days: 14,
    resource_upload_max_mb: 25,
    updated_by_name: 'Alia Admin',
    updated_at: '2026-09-01T10:00:00Z',
    ...overrides,
  };
}

beforeEach(() => {
  getSettings.mockReset();
  updateSettings.mockReset();
  mockAuth.value = { user: { id: 'u1', role: 'admin' }, isLoading: false, can: () => true };
});

describe('InstitutionSettingsPage', () => {
  it('names what it is loading rather than saying "Loading…"', () => {
    getSettings.mockReturnValue(new Promise(() => {}));
    render(<InstitutionSettingsPage />);

    expect(screen.getByText("Loading the institution's settings…")).toBeInTheDocument();
  });

  it('shows the failure with its request id and reloads when asked to try again', async () => {
    getSettings.mockRejectedValueOnce(new ApiError(500, 'server_error', 'Could not load.', 'req-77'));
    getSettings.mockResolvedValueOnce(settings());
    const user = userEvent.setup();
    render(<InstitutionSettingsPage />);

    await waitFor(() => expect(screen.getByText('Could not load.')).toBeInTheDocument());
    expect(screen.getByText('req-77')).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: /try again/i }));

    await waitFor(() =>
      expect(screen.getByLabelText('Institution name')).toHaveValue('Sunrise Academy'),
    );
  });

  it('renders the stored values with nothing undefined or NaN leaking through', async () => {
    getSettings.mockResolvedValue(settings());
    render(<InstitutionSettingsPage />);

    await waitFor(() =>
      expect(screen.getByLabelText('Institution name')).toHaveValue('Sunrise Academy'),
    );
    expect(screen.getByLabelText('Keep exports for (days)')).toHaveValue(14);
    expect(screen.getByLabelText('Largest upload (MB)')).toHaveValue(25);
    expect(document.body.textContent).not.toMatch(/\bNaN\b/);
    expect(document.body.textContent).not.toMatch(/undefined/);
  });

  it('sends only the fields the operator actually changed', async () => {
    getSettings.mockResolvedValue(settings());
    updateSettings.mockResolvedValue(settings({ institution_name: 'Sunrise Institute' }));
    const user = userEvent.setup();
    render(<InstitutionSettingsPage />);
    await waitFor(() => expect(screen.getByLabelText('Institution name')).toBeInTheDocument());

    await user.clear(screen.getByLabelText('Institution name'));
    await user.type(screen.getByLabelText('Institution name'), 'Sunrise Institute');
    await user.click(screen.getByRole('button', { name: 'Save settings' }));

    expect(updateSettings).toHaveBeenCalledWith({ institution_name: 'Sunrise Institute' });
  });

  it('confirms a successful save in a live region', async () => {
    getSettings.mockResolvedValue(settings());
    updateSettings.mockResolvedValue(settings({ support_phone: '+91 141 555 0199' }));
    const user = userEvent.setup();
    render(<InstitutionSettingsPage />);
    await waitFor(() => expect(screen.getByLabelText('Support phone')).toBeInTheDocument());

    await user.clear(screen.getByLabelText('Support phone'));
    await user.type(screen.getByLabelText('Support phone'), '+91 141 555 0199');
    await user.click(screen.getByRole('button', { name: 'Save settings' }));

    await waitFor(() => expect(screen.getByRole('status')).toHaveTextContent(/Settings saved/i));
  });

  it('wires a server field error to its own input, not merely onto the page', async () => {
    getSettings.mockResolvedValue(settings());
    updateSettings.mockRejectedValue(
      new ApiError(400, 'validation_error', 'The submitted data is invalid.', 'req-9', {
        export_retention_days: ['Keep exports for between 1 and 365 days.'],
      }),
    );
    const user = userEvent.setup();
    render(<InstitutionSettingsPage />);
    await waitFor(() => expect(screen.getByLabelText('Keep exports for (days)')).toBeInTheDocument());

    await user.clear(screen.getByLabelText('Keep exports for (days)'));
    await user.type(screen.getByLabelText('Keep exports for (days)'), '900');
    await user.click(screen.getByRole('button', { name: 'Save settings' }));

    const input = await screen.findByLabelText('Keep exports for (days)');
    const message = screen.getByText('Keep exports for between 1 and 365 days.');
    expect(input).toHaveAttribute('aria-describedby', message.id);
    expect(input).toHaveAttribute('aria-invalid', 'true');
  });

  it('renders a failure with no field of its own as an alert above the form', async () => {
    getSettings.mockResolvedValue(settings());
    updateSettings.mockRejectedValue(
      new ApiError(500, 'server_error', 'The server could not save this.', ''),
    );
    const user = userEvent.setup();
    render(<InstitutionSettingsPage />);
    await waitFor(() => expect(screen.getByLabelText('Support email')).toBeInTheDocument());

    await user.clear(screen.getByLabelText('Support email'));
    await user.type(screen.getByLabelText('Support email'), 'new@sunrise.example.test');
    await user.click(screen.getByRole('button', { name: 'Save settings' }));

    await waitFor(() =>
      expect(screen.getByRole('alert')).toHaveTextContent('The server could not save this.'),
    );
  });

  it('disables the submit button and says what it is doing while saving', async () => {
    getSettings.mockResolvedValue(settings());
    updateSettings.mockReturnValue(new Promise(() => {}));
    const user = userEvent.setup();
    render(<InstitutionSettingsPage />);
    await waitFor(() => expect(screen.getByLabelText('Support phone')).toBeInTheDocument());

    await user.clear(screen.getByLabelText('Support phone'));
    await user.type(screen.getByLabelText('Support phone'), '+91 141 555 0199');
    await user.click(screen.getByRole('button', { name: 'Save settings' }));

    expect(await screen.findByRole('button', { name: 'Saving…' })).toBeDisabled();
  });

  it('refuses somebody without the capability instead of showing them the form', async () => {
    getSettings.mockResolvedValue(settings());
    mockAuth.value = { user: { id: 'u2', role: 'manager' }, isLoading: false, can: () => false };
    render(<InstitutionSettingsPage />);

    expect(await screen.findByText(/do not have access/i)).toBeInTheDocument();
    expect(screen.queryByLabelText('Institution name')).not.toBeInTheDocument();
  });

  it('says who last changed the settings, and stays silent when nobody has', async () => {
    getSettings.mockResolvedValueOnce(settings({ updated_by_name: null, updated_at: null }));
    const { unmount } = render(<InstitutionSettingsPage />);

    await waitFor(() => expect(screen.getByLabelText('Institution name')).toBeInTheDocument());
    expect(screen.queryByText(/last changed by/i)).not.toBeInTheDocument();
    unmount();

    getSettings.mockResolvedValueOnce(settings());
    render(<InstitutionSettingsPage />);

    expect(await screen.findByText(/Last changed by Alia Admin on/)).toBeInTheDocument();
  });

  it('mirrors the backend capability string exactly', () => {
    // A mistyped mirror constant would hide this screen from everybody forever,
    // on every role, with no error anywhere.
    expect(Capability.settingsManage).toBe('settings.manage');
  });
});
