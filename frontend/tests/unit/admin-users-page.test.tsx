/**
 * `/admin/users` — migrated onto `DataTable` (Phase R6). Covers what the
 * migration must not have changed: every column renders real data, sort
 * still calls `listUsers` with the same query shape, row activation still
 * navigates to the account, and the density toggle persists.
 */
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import AdminUsersPage from '@/app/admin/users/page';
import { ApiError } from '@/lib/api';
import type { AdminUser } from '@/types/api';

const listUsers = vi.hoisted(() => vi.fn());
// Saved views load from the server; these tests are about the list itself.
vi.mock('@/lib/saved-filters', () => ({
  listSavedFilters: vi.fn().mockResolvedValue([]),
  createSavedFilter: vi.fn(),
  deleteSavedFilter: vi.fn(),
}));
vi.mock('@/lib/people', async () => {
  const actual = await vi.importActual<typeof import('@/lib/people')>('@/lib/people');
  return { ...actual, listUsers, createUser };
});

const useAuth = vi.hoisted(() => vi.fn());
vi.mock('@/components/auth-provider', () => ({ useAuth }));

const createUser = vi.hoisted(() => vi.fn());
vi.mock('@/components/organisation/branch-field', () => ({
  useBranches: () => ({
    branches: [
      { id: 'b-jai', name: 'Jaipur', code: 'JAI', city: 'Jaipur', is_active: true },
      { id: 'b-pun', name: 'Pune', code: 'PUN', city: 'Pune', is_active: true },
    ],
    failed: false,
  }),
  BranchField: () => null,
}));

const toast = vi.hoisted(() => vi.fn());
vi.mock('@/components/ui/toast', () => ({ useToast: () => ({ toast }) }));

const bulkUsers = vi.hoisted(() => vi.fn());
vi.mock('@/lib/bulk', async () => {
  const actual = await vi.importActual<typeof import('@/lib/bulk')>('@/lib/bulk');
  return { ...actual, bulkUsers };
});

const push = vi.hoisted(() => vi.fn());
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push, replace: vi.fn() }),
  useSearchParams: () => new URLSearchParams(window.location.search),
}));

function page(results: AdminUser[]) {
  return { count: results.length, page: 1, page_size: 20, total_pages: 1, next: null, previous: null, results };
}

function userRow(overrides: Partial<AdminUser> = {}): AdminUser {
  return {
    id: 'u-1',
    email: 'asha@example.com',
    first_name: 'Asha',
    last_name: 'Rao',
    full_name: 'Asha Rao',
    phone: '',
    role: 'student',
    is_active: true,
    is_email_verified: true,
    invitation_accepted: true,
    profile_image_url: null,
    date_joined: '2026-01-01T00:00:00Z',
    branch_id: null,
    branch_code: null,
    branch_name: null,
    is_staff: false,
    can_administer: true,
    allowed_role_transitions: ['student'],
    profile_type: 'student',
    profile_id: 'student-1',
    last_login: null,
    email_verified_at: null,
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
    ...overrides,
  };
}

beforeEach(() => {
  vi.clearAllMocks();
  useAuth.mockReturnValue({
    user: { id: 'u-admin', role: 'admin', capabilities: ['user.view_any'] },
    isLoading: false,
    can: (capability: string) => capability === 'user.view_any',
  });
});

describe('AdminUsersPage', () => {
  it('renders every column with real data', async () => {
    listUsers.mockResolvedValue(page([userRow()]));
    render(<AdminUsersPage />);
    await waitFor(() => expect(screen.getByText('asha@example.com')).toBeInTheDocument());
    expect(screen.getByText('Asha Rao')).toBeInTheDocument();
    expect(screen.getAllByText('Active').length).toBeGreaterThan(0);
  });

  it('renders a placeholder account — no join date, a role outside the six — without "Invalid Date" or a blank badge', async () => {
    listUsers.mockResolvedValue(
      page([userRow({ date_joined: null as unknown as string, role: 'auditor' as AdminUser['role'] })]),
    );
    render(<AdminUsersPage />);
    await waitFor(() => expect(screen.getByText('asha@example.com')).toBeInTheDocument());
    expect(screen.getByText('Not available')).toBeInTheDocument();
    expect(screen.getByText('Auditor')).toBeInTheDocument();
    expect(document.body.textContent).not.toMatch(/Invalid Date/);
  });

  it('sends the same sort field on the same server request', async () => {
    listUsers.mockResolvedValue(page([userRow()]));
    render(<AdminUsersPage />);
    await waitFor(() => expect(screen.getByText('asha@example.com')).toBeInTheDocument());
    const user = userEvent.setup();
    await user.click(screen.getByRole('button', { name: /^role$/i }));
    await waitFor(() =>
      expect(listUsers).toHaveBeenLastCalledWith(expect.objectContaining({ ordering: 'role' }), expect.anything()),
    );
  });

  it('navigates to the account on row activation', async () => {
    listUsers.mockResolvedValue(page([userRow()]));
    render(<AdminUsersPage />);
    await waitFor(() => expect(screen.getByText('asha@example.com')).toBeInTheDocument());
    const user = userEvent.setup();
    await user.click(screen.getByText('asha@example.com'));
    expect(push).toHaveBeenCalledWith('/admin/users/u-1');
  });

  it('shows an error with retry on failure', async () => {
    listUsers.mockRejectedValue(new ApiError(500, 'server_error', 'Could not load.', 'req-1'));
    render(<AdminUsersPage />);
    await waitFor(() => expect(screen.getByText('Could not load users')).toBeInTheDocument());
    expect(screen.getByRole('button', { name: /try again/i })).toBeInTheDocument();
  });

  it('persists the density toggle across a re-render', async () => {
    listUsers.mockResolvedValue(page([userRow()]));
    const { unmount } = render(<AdminUsersPage />);
    await waitFor(() => expect(screen.getByText('asha@example.com')).toBeInTheDocument());
    const user = userEvent.setup();
    await user.click(screen.getByRole('button', { name: /compact view/i }));
    expect(window.localStorage.getItem('grras.admin-users-density')).toBe('compact');
    unmount();

    render(<AdminUsersPage />);
    await waitFor(() => expect(screen.getByText('asha@example.com')).toBeInTheDocument());
    expect(screen.getByRole('button', { name: /comfortable view/i })).toBeInTheDocument();
  });
});

describe('AdminUsersPage — centres and adding staff', () => {
  it('lets an administrator, who sees every centre, filter by one', async () => {
    useAuth.mockReturnValue({
      user: { id: 'admin-1', role: 'admin', branch_name: null },
      can: () => true,
    });
    listUsers.mockResolvedValue(page([userRow({ branch_name: 'Jaipur' })]));
    const user = userEvent.setup();
    render(<AdminUsersPage />);

    expect(await screen.findByRole('cell', { name: 'Jaipur' })).toBeInTheDocument();
    await user.selectOptions(screen.getByLabelText('Centre'), 'b-pun');
    await waitFor(() =>
      expect(listUsers).toHaveBeenLastCalledWith(
        expect.objectContaining({ branch: 'b-pun' }),
        expect.anything(),
      ),
    );
  });

  it('adds a staff account and opens it', async () => {
    useAuth.mockReturnValue({
      user: { id: 'admin-1', role: 'admin', branch_name: null },
      can: () => true,
    });
    listUsers.mockResolvedValue(page([]));
    createUser.mockResolvedValue(userRow({ id: 'new-1', role: 'counsellor' }));
    const user = userEvent.setup();
    render(<AdminUsersPage />);

    await user.click(await screen.findByRole('button', { name: 'Add staff account' }));
    const dialog = screen.getByRole('dialog', { name: 'Add a staff account' });
    expect(dialog).toHaveTextContent('Adding a trainer?');
    await user.type(within(dialog).getByLabelText(/^Email/), 'chitra@example.com');
    await user.type(within(dialog).getByLabelText(/^First name/), 'Chitra');
    await user.selectOptions(within(dialog).getByLabelText(/^Role/), 'counsellor');
    await user.click(screen.getByRole('button', { name: 'Add and send invitation' }));

    await waitFor(() =>
      expect(createUser).toHaveBeenCalledWith(
        expect.objectContaining({ email: 'chitra@example.com', first_name: 'Chitra', role: 'counsellor' }),
      ),
    );
    expect(push).toHaveBeenCalledWith('/admin/users/new-1?created=1');
  });
});

describe('AdminUsersPage — acting on many accounts', () => {
  function signInAsAdmin() {
    useAuth.mockReturnValue({
      user: { id: 'admin-1', role: 'admin', branch_name: null },
      can: () => true,
    });
  }

  it('resends invitations to the ticked accounts and says which were skipped and why', async () => {
    signInAsAdmin();
    listUsers.mockResolvedValue(
      page([
        userRow({ id: 'u-1', email: 'one@example.com', full_name: 'One', is_email_verified: false }),
        userRow({ id: 'u-2', email: 'two@example.com', full_name: 'Two' }),
      ]),
    );
    bulkUsers.mockResolvedValue({
      action: 'resend_invitation',
      total: 2,
      done: 1,
      skipped: [{ id: 'u-2', label: 'Two', reason: 'They have already accepted their invitation.' }],
    });
    const user = userEvent.setup();
    render(<AdminUsersPage />);

    await screen.findByText('one@example.com');
    await user.click(screen.getByRole('checkbox', { name: 'Select One' }));
    await user.click(screen.getByRole('checkbox', { name: 'Select Two' }));
    const bar = screen.getByRole('region', { name: 'Bulk actions' });
    expect(bar).toHaveTextContent('2 accounts selected');
    await user.click(within(bar).getByRole('button', { name: 'Resend invitations' }));
    await user.click(screen.getByRole('button', { name: 'Send invitations' }));

    await waitFor(() =>
      expect(bulkUsers).toHaveBeenCalledWith({ ids: ['u-1', 'u-2'], action: 'resend_invitation' }),
    );
    const result = await screen.findByRole('dialog', { name: 'Invitations' });
    expect(result).toHaveTextContent('1 account invited again, 1 skipped');
    expect(result).toHaveTextContent('They have already accepted their invitation.');
  });

  it('"select all matching" sends the filters, not a page of ids', async () => {
    signInAsAdmin();
    window.history.replaceState(null, '', '/admin/users?role=counsellor');
    listUsers.mockResolvedValue({
      ...page([userRow({ id: 'u-1', role: 'counsellor' })]),
      count: 45,
      total_pages: 3,
    });
    bulkUsers.mockResolvedValue({ action: 'move_centre', total: 45, done: 45, skipped: [] });
    const user = userEvent.setup();
    render(<AdminUsersPage />);

    await screen.findByText('asha@example.com');
    await user.click(screen.getByRole('checkbox', { name: 'Select Asha Rao' }));
    await user.click(screen.getByRole('button', { name: /select all 45 accounts matching/i }));
    await user.click(screen.getByRole('button', { name: 'Move to a centre' }));
    const dialog = screen.getByRole('dialog', { name: /move 45 accounts to a centre/i });
    await user.selectOptions(within(dialog).getByLabelText(/^Centre/), 'b-pun');
    await user.type(within(dialog).getByLabelText(/^Reason/), 'Opening Pune');
    await user.click(within(dialog).getByRole('button', { name: 'Move 45 accounts' }));

    await waitFor(() =>
      expect(bulkUsers).toHaveBeenCalledWith({
        filters: { role: 'counsellor' },
        action: 'move_centre',
        branch_id: 'b-pun',
        reason: 'Opening Pune',
      }),
    );
    window.history.replaceState(null, '', '/');
  });

  it('offers no account actions to somebody who may only read accounts', async () => {
    listUsers.mockResolvedValue(page([userRow()]));
    const user = userEvent.setup();
    render(<AdminUsersPage />);
    await screen.findByText('asha@example.com');
    await user.click(screen.getByRole('checkbox', { name: 'Select Asha Rao' }));
    const bar = screen.getByRole('region', { name: 'Bulk actions' });
    expect(within(bar).queryByRole('button', { name: 'Resend invitations' })).not.toBeInTheDocument();
    expect(within(bar).queryByRole('button', { name: 'Move to a centre' })).not.toBeInTheDocument();
  });
});
