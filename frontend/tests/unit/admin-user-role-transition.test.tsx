import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { UserAdministration } from '@/app/admin/users/[userId]/page';
import type { AdminUser } from '@/types/api';

const getUser = vi.hoisted(() => vi.fn());
const transitionUserRole = vi.hoisted(() => vi.fn());
vi.mock('@/lib/people', async () => {
  const actual = await vi.importActual<typeof import('@/lib/people')>('@/lib/people');
  return {
    ...actual,
    getUser,
    transitionUserRole,
    getUserAudit: vi.fn(),
  };
});

vi.mock('@/lib/roles', () => ({
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
vi.mock('next/navigation', () => ({ useRouter: () => ({ push }) }));

function managedUser(): AdminUser {
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
      }),
    );
    expect(screen.getByRole('status')).toHaveTextContent(/sessions were ended/i);
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
