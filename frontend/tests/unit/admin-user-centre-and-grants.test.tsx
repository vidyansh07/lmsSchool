/**
 * The user screen's Centre and Scope grants cards: a failed move keeps what
 * was typed, a move is confirmed first, a failed grants read is an error with
 * Retry (never "No direct grants."), and a batch is granted by searching for
 * it rather than by pasting its id.
 */
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { UserAdministration } from '@/app/admin/users/[userId]/page';
import { ApiError } from '@/lib/api';
import type { AdminUser } from '@/types/api';

const getUser = vi.hoisted(() => vi.fn());
vi.mock('@/lib/people', async () => {
  const actual = await vi.importActual<typeof import('@/lib/people')>('@/lib/people');
  return { ...actual, getUser, getUserAudit: vi.fn() };
});
const listScopeGrants = vi.hoisted(() => vi.fn());
const grantScope = vi.hoisted(() => vi.fn());
vi.mock('@/lib/roles', () => ({
  listRoles: vi.fn().mockResolvedValue([]),
  listScopeGrants,
  grantScope,
  revokeScope: vi.fn(),
  stepUpWithPassword: vi.fn(),
  requestStepUpCode: vi.fn(),
  stepUpWithCode: vi.fn(),
}));
const listBatches = vi.hoisted(() => vi.fn());
vi.mock('@/lib/batches', async () => {
  const actual = await vi.importActual<typeof import('@/lib/batches')>('@/lib/batches');
  return { ...actual, listBatches };
});
const moveUserToBranch = vi.hoisted(() => vi.fn());
vi.mock('@/lib/organisation', async () => {
  const actual = await vi.importActual<typeof import('@/lib/organisation')>('@/lib/organisation');
  return { ...actual, moveUserToBranch };
});
vi.mock('@/components/organisation/branch-field', () => ({
  useBranches: () => ({
    branches: [
      { id: 'branch-1', name: 'Jaipur', code: 'JAI' },
      { id: 'branch-2', name: 'Pune', code: 'PUN' },
    ],
    failed: false,
  }),
}));
const useAuth = vi.hoisted(() => vi.fn());
vi.mock('@/components/auth-provider', () => ({ useAuth }));
vi.mock('next/navigation', () => ({ useRouter: () => ({ push: vi.fn() }),
  useSearchParams: () => new URLSearchParams(window.location.search),
}));

function counsellor(): AdminUser {
  return {
    id: 'c-1',
    email: 'c@example.com',
    first_name: 'Chitra',
    last_name: 'Counsellor',
    full_name: 'Chitra Counsellor',
    phone: '',
    role: 'counsellor',
    custom_role: null,
    custom_role_name: null,
    is_active: true,
    is_email_verified: true,
    profile_image_url: null,
    date_joined: '2026-01-01T00:00:00Z',
    branch_id: 'branch-1',
    branch_code: 'JAI',
    branch_name: 'Jaipur',
    is_staff: false,
    can_administer: true,
    allowed_role_transitions: ['counsellor'],
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
  getUser.mockResolvedValue(counsellor());
  listScopeGrants.mockResolvedValue([]);
  useAuth.mockReturnValue({
    user: { id: 'admin-1', role: 'admin' },
    can: (capability: string) => capability === 'organisation.assign_users',
  });
});

describe('Centre card', () => {
  it('confirms the move, and keeps the choice and reason when it fails', async () => {
    moveUserToBranch.mockRejectedValueOnce(
      new ApiError(400, 'validation_error', 'Invalid.', 'r', { branch_id: ['That centre is closed.'] }),
    );
    const user = userEvent.setup();
    render(<UserAdministration userId="c-1" />);

    await user.selectOptions(await screen.findByLabelText('Move to'), 'branch-2');
    await user.type(screen.getByLabelText(/^Reason/, { selector: '#user-branch-reason' }), 'Relocated.');
    await user.click(screen.getByRole('button', { name: 'Move' }));

    const confirm = screen.getByRole('alertdialog');
    expect(confirm).toHaveTextContent('Move Chitra Counsellor to Pune?');
    expect(moveUserToBranch).not.toHaveBeenCalled();
    await user.click(within(confirm).getByRole('button', { name: 'Move' }));

    expect(await screen.findByText('That centre is closed.')).toBeInTheDocument();
    expect(screen.getByLabelText('Move to')).toHaveValue('branch-2');
    expect(screen.getByDisplayValue('Relocated.')).toBeInTheDocument();
  });
});

describe('Scope grants card', () => {
  it('shows a failed read as an error with Retry, never as "No direct grants."', async () => {
    listScopeGrants.mockRejectedValueOnce(new ApiError(500, 'internal_error', 'Server error.', 'req-7'));
    const user = userEvent.setup();
    render(<UserAdministration userId="c-1" />);

    expect(await screen.findByText('Could not load the scope grants')).toBeInTheDocument();
    expect(screen.queryByText('No direct grants.')).not.toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Try again' }));
    expect(await screen.findByText('No direct grants.')).toBeInTheDocument();
  });

  it('grants a batch found by searching its code', async () => {
    listBatches.mockResolvedValue({
      count: 1,
      page: 1,
      page_size: 8,
      total_pages: 1,
      results: [
        { id: 'batch-9', code: 'DEVOPS-JAN', name: 'DevOps January', course_title: 'DevOps', status: 'active' },
      ],
    });
    grantScope.mockResolvedValue({});
    const user = userEvent.setup();
    render(<UserAdministration userId="c-1" />);

    await user.type(await screen.findByLabelText('Grant a batch'), 'DEVOPS');
    const option = await screen.findByRole('option', { name: /DEVOPS-JAN · DevOps January/ });
    await user.selectOptions(screen.getByRole('listbox'), option);

    await waitFor(() => expect(grantScope).toHaveBeenCalledWith('c-1', { batch: 'batch-9' }));
  });
});
