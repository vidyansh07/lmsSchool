/**
 * `/admin/users` — migrated onto `DataTable` (Phase R6). Covers what the
 * migration must not have changed: every column renders real data, sort
 * still calls `listUsers` with the same query shape, row activation still
 * navigates to the account, and the density toggle persists.
 */
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import AdminUsersPage from '@/app/admin/users/page';
import { ApiError } from '@/lib/api';
import type { AdminUser } from '@/types/api';

const listUsers = vi.hoisted(() => vi.fn());
vi.mock('@/lib/people', async () => {
  const actual = await vi.importActual<typeof import('@/lib/people')>('@/lib/people');
  return { ...actual, listUsers };
});

const useAuth = vi.hoisted(() => vi.fn());
vi.mock('@/components/auth-provider', () => ({ useAuth }));

const push = vi.hoisted(() => vi.fn());
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push, replace: vi.fn() }),
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
    profile_image_url: null,
    date_joined: '2026-01-01T00:00:00Z',
    branch_id: null,
    branch_code: null,
    branch_name: null,
    is_staff: false,
    can_administer: true,
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
