import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { UserAdministration } from '@/app/admin/users/[userId]/page';
import { ApiError } from '@/lib/api';
import type { AdminUserRecord } from '@/types/api';

const getUser = vi.hoisted(() => vi.fn());
const transitionUserRole = vi.hoisted(() => vi.fn());
const setUserActive = vi.hoisted(() => vi.fn());
vi.mock('@/lib/people', async () => {
  const actual = await vi.importActual<typeof import('@/lib/people')>('@/lib/people');
  return {
    ...actual,
    getUser,
    transitionUserRole,
    setUserActive,
    getUserAudit: vi.fn(),
  };
});

const stepUpWithPassword = vi.hoisted(() => vi.fn());
vi.mock('@/lib/roles', () => ({
  stepUpWithPassword,
  requestStepUpCode: vi.fn(),
  stepUpWithCode: vi.fn(),
  listRoles: vi.fn().mockResolvedValue([]),
  listScopeGrants: vi.fn().mockResolvedValue([]),
  grantScope: vi.fn(),
  revokeScope: vi.fn(),
}));
vi.mock('@/components/organisation/branch-field', () => ({
  useBranches: () => ({ branches: [], failed: false }),
}));

const useAuth = vi.hoisted(() => vi.fn());
vi.mock('@/components/auth-provider', () => ({ useAuth }));
const push = vi.hoisted(() => vi.fn());
vi.mock('next/navigation', () => ({ useRouter: () => ({ push }),
  useSearchParams: () => new URLSearchParams(window.location.search),
}));

function managedUser(): AdminUserRecord {
  return {
    id: 'manager-1',
    email: 'manager@example.com',
    first_name: 'Mira',
    last_name: 'Manager',
    full_name: 'Mira Manager',
    phone: '',
    role: 'manager',
    custom_role: null,
    custom_role_name: null,
    is_active: true,
    is_email_verified: true,
    invitation_accepted: true,
    mfa_enabled: false,
    invitation: null,
    last_account_email: null,
    capabilities: [],
    may_send_invitation: false,
    profile_image_url: null,
    date_joined: '2026-01-01T00:00:00Z',
    branch_id: 'branch-1',
    branch_code: 'MAIN',
    branch_name: 'Main centre',
    is_staff: false,
    can_administer: true,
    allowed_role_transitions: ['manager', 'counsellor'],
    profile_type: null,
    profile_id: null,
    last_login: null,
    email_verified_at: '2026-01-01T00:00:00Z',
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
  };
}

beforeEach(() => {
  vi.clearAllMocks();
  getUser.mockResolvedValue(managedUser());
  transitionUserRole.mockResolvedValue({});
  push.mockReset();
  useAuth.mockReturnValue({
    user: { id: 'admin-1', role: 'admin' },
    can: (capability: string) => capability === 'user.change_role',
  });
});

describe('administrator role transition', () => {
  it('requires a review and audit reason before calling the dedicated action', async () => {
    const user = userEvent.setup();
    render(<UserAdministration userId="manager-1" />);

    await waitFor(() => expect(screen.getByText('Role and permissions')).toBeInTheDocument());
    await user.selectOptions(screen.getByLabelText('System role'), 'counsellor');
    await user.click(screen.getByRole('button', { name: 'Review role change' }));

    expect(screen.getByRole('dialog', { name: /change this account.s role/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Change role' })).toBeDisabled();

    await user.type(screen.getByLabelText(/^Reason for change/), 'Moved to admissions.');
    await user.click(screen.getByRole('button', { name: 'Change role' }));

    await waitFor(() =>
      expect(transitionUserRole).toHaveBeenCalledWith('manager-1', {
        role: 'counsellor',
        custom_role: null,
        reason: 'Moved to admissions.',
        expected_updated_at: '2026-01-01T00:00:00Z',
      }),
    );
    expect(screen.getByRole('status')).toHaveTextContent(/sessions were ended/i);
  });

  it('asks the administrator to confirm it is them, then retries the same change', async () => {
    transitionUserRole
      .mockRejectedValueOnce(new ApiError(403, 'step_up_required', 'Confirm it is you.', 'req-1'))
      .mockResolvedValueOnce({});
    stepUpWithPassword.mockResolvedValue(undefined);
    const user = userEvent.setup();
    render(<UserAdministration userId="manager-1" />);

    await waitFor(() => expect(screen.getByText('Role and permissions')).toBeInTheDocument());
    await user.selectOptions(screen.getByLabelText('System role'), 'counsellor');
    await user.click(screen.getByRole('button', { name: 'Review role change' }));
    await user.type(screen.getByLabelText(/^Reason for change/), 'Moved to admissions.');
    await user.click(screen.getByRole('button', { name: 'Change role' }));

    expect(await screen.findByRole('dialog', { name: /confirm it is you/i })).toBeInTheDocument();
    await user.type(screen.getByLabelText(/^Password/), 'secret-pass');
    await user.click(screen.getByRole('button', { name: /^Confirm$/ }));

    await waitFor(() => expect(transitionUserRole).toHaveBeenCalledTimes(2));
    expect(transitionUserRole).toHaveBeenLastCalledWith('manager-1', {
      role: 'counsellor',
      custom_role: null,
      reason: 'Moved to admissions.',
      expected_updated_at: '2026-01-01T00:00:00Z',
    });
    expect(await screen.findByRole('status')).toHaveTextContent(/sessions were ended/i);
  });

  it('warns before navigating away from an unsaved role selection', async () => {
    const user = userEvent.setup();
    render(<UserAdministration userId="manager-1" />);

    await waitFor(() => expect(screen.getByText('Role and permissions')).toBeInTheDocument());
    await user.selectOptions(screen.getByLabelText('System role'), 'counsellor');
    await user.click(screen.getByRole('link', { name: 'All users' }));

    expect(push).not.toHaveBeenCalled();
    expect(screen.getByRole('alertdialog')).toHaveTextContent(
      'Discard unsaved account changes?',
    );
    await user.click(screen.getByRole('button', { name: 'Keep editing' }));
    expect(screen.getByLabelText('System role')).toHaveValue('counsellor');

    await user.click(screen.getByRole('link', { name: 'All users' }));
    await user.click(screen.getByRole('button', { name: 'Discard changes' }));
    expect(push).toHaveBeenCalledWith('/admin/users');
  });
});

describe('deactivating an account', () => {
  it('asks first and records a reason; activating does not ask', async () => {
    useAuth.mockReturnValue({
      user: { id: 'admin-1', role: 'admin' },
      can: (capability: string) => capability === 'user.set_active',
    });
    setUserActive.mockResolvedValue({});
    const user = userEvent.setup();
    render(<UserAdministration userId="manager-1" />);

    await user.click(await screen.findByRole('button', { name: 'Deactivate this account' }));
    expect(setUserActive).not.toHaveBeenCalled();
    const dialog = screen.getByRole('dialog', { name: /deactivate mira manager/i });
    expect(dialog).toHaveTextContent(/signed out of every device/i);
    expect(screen.getByRole('button', { name: 'Deactivate' })).toBeDisabled();

    await user.type(screen.getByLabelText(/^Reason/), 'Left the institute.');
    await user.click(screen.getByRole('button', { name: 'Deactivate' }));

    await waitFor(() =>
      expect(setUserActive).toHaveBeenCalledWith('manager-1', false, 'Left the institute.'),
    );
  });
});

describe('a manager who also teaches', () => {
  it('says so on the record and links the teaching profile', async () => {
    getUser.mockResolvedValue({ ...managedUser(), profile_type: 'trainer', profile_id: 'tp-1' });
    render(<UserAdministration userId="manager-1" />);

    expect(await screen.findByText('Also teaches')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Open teaching profile' })).toHaveAttribute(
      'href',
      '/manage/trainers/tp-1',
    );
    expect(screen.getByText(/this manager also teaches/i)).toBeInTheDocument();
  });
});

describe('an edit someone else overtook', () => {
  it('refuses to overwrite, says so, and reloads on request', async () => {
    transitionUserRole.mockRejectedValue(
      new ApiError(409, 'stale_write', 'Conflict.', 'r', {
        user: ['Someone else changed this since you opened it. Reload to see their changes, then make yours again.'],
      }),
    );
    const user = userEvent.setup();
    render(<UserAdministration userId="manager-1" />);

    await waitFor(() => expect(screen.getByText('Role and permissions')).toBeInTheDocument());
    await user.selectOptions(screen.getByLabelText('System role'), 'counsellor');
    await user.click(screen.getByRole('button', { name: 'Review role change' }));
    await user.type(screen.getByLabelText(/^Reason for change/), 'Moved.');
    await user.click(screen.getByRole('button', { name: 'Change role' }));

    expect(await screen.findByText(/Someone else changed this/)).toBeInTheDocument();
    const callsBefore = getUser.mock.calls.length;
    await user.click(screen.getByRole('button', { name: 'Reload this account' }));
    await waitFor(() => expect(getUser.mock.calls.length).toBe(callsBefore + 1));
  });
});
