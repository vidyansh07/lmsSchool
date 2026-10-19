/**
 * "Getting in": an account's way from invitation to first sign-in, the one
 * next step that helps, and an honest answer about whether its email went.
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { CapabilitiesCard, GettingInCard } from '@/components/admin/getting-in-card';
import type { AdminUserRecord } from '@/types/api';

const sendCredentialLink = vi.hoisted(() => vi.fn());
vi.mock('@/lib/people', () => ({ sendCredentialLink }));

function record(overrides: Partial<AdminUserRecord> = {}): AdminUserRecord {
  return {
    id: 'u-1',
    email: 'tara@example.test',
    first_name: 'Tara',
    last_name: '',
    full_name: 'Tara',
    phone: '',
    role: 'counsellor',
    custom_role: null,
    custom_role_name: null,
    is_active: true,
    is_email_verified: false,
    invitation_accepted: false,
    profile_image_url: null,
    date_joined: '2026-10-19T10:00:00Z',
    branch_id: null,
    branch_code: null,
    branch_name: null,
    is_staff: false,
    can_administer: true,
    allowed_role_transitions: [],
    profile_type: null,
    profile_id: null,
    last_login: null,
    email_verified_at: null,
    created_at: '2026-10-19T10:00:00Z',
    updated_at: '2026-10-19T10:00:00Z',
    mfa_enabled: false,
    invitation: { sent_at: '2026-10-19T10:00:00Z', expires_at: '2026-10-26T10:00:00Z', expired: false },
    last_account_email: null,
    capabilities: [
      { code: 'enquiry.view_any', label: 'View enquiries at the centre' },
      { code: 'fee.manage_any', label: 'Manage fees' },
    ],
    may_send_invitation: true,
    ...overrides,
  };
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe('GettingInCard', () => {
  it('shows a pending invitation and sends a new one, saying whether it went', async () => {
    sendCredentialLink.mockResolvedValue({ sent: true, detail: 'A new invitation to set a password was sent to tara@example.test.' });
    const onSent = vi.fn();
    render(<GettingInCard user={record()} mayManage onSent={onSent} />);
    expect(screen.getByText('Not set yet')).toBeInTheDocument();
    expect(screen.getByText(/^Sent .* works until/)).toBeInTheDocument();
    expect(screen.getByText('Never')).toBeInTheDocument();
    // No reset or verify link before they have a password: only the invitation.
    expect(screen.queryByRole('button', { name: /password-reset link/ })).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Send a new invitation' }));
    await waitFor(() => expect(sendCredentialLink).toHaveBeenCalledWith('u-1', 'password_reset'));
    expect(await screen.findByText(/new invitation to set a password was sent/)).toBeInTheDocument();
    expect(onSent).toHaveBeenCalled();
  });

  it('says plainly when the last email was not sent, and why', async () => {
    sendCredentialLink.mockResolvedValue({
      sent: false,
      detail: 'The email could not be sent: the mail service refused to send it.',
    });
    render(
      <GettingInCard
        user={record({
          last_account_email: {
            kind: 'invitation',
            kind_label: 'Invitation',
            sent: false,
            error: 'The mail service refused to send it: this environment is not allowed to email this address yet.',
            at: '2026-10-19T10:00:00Z',
          },
        })}
        mayManage
        onSent={vi.fn()}
      />,
    );
    expect(screen.getByText(/was not sent\. The mail service refused/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Send a new invitation' }));
    expect(await screen.findByText(/could not be sent: the mail service refused/)).toBeInTheDocument();
  });

  it('offers a reset and a verification link once they have a password', () => {
    render(
      <GettingInCard
        user={record({ invitation_accepted: true, invitation: null, may_send_invitation: false, last_login: '2026-10-19T12:00:00Z' })}
        mayManage
        onSent={vi.fn()}
      />,
    );
    expect(screen.getByText('Set by them')).toBeInTheDocument();
    expect(screen.getByText('Accepted')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Send a password-reset link' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Send a verification link' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /invitation/ })).not.toBeInTheDocument();
  });

  it('lets a peer who may only invite send the invitation, and nothing else', () => {
    render(
      <GettingInCard
        user={record({ can_administer: false, may_send_invitation: true })}
        mayManage={false}
        onSent={vi.fn()}
      />,
    );
    expect(screen.getByRole('button', { name: 'Send a new invitation' })).toBeInTheDocument();
  });
});

describe('CapabilitiesCard', () => {
  it('lists what the person can do on demand', () => {
    render(<CapabilitiesCard user={record({ custom_role_name: 'Admissions lead' })} />);
    expect(screen.getByText(/From the Admissions lead role\. 2 permissions\./)).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Show the list' }));
    expect(screen.getByText('Manage fees')).toBeInTheDocument();
  });
});
