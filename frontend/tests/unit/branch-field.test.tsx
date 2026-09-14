/**
 * The centre picker asks only the people it applies to: an unbounded
 * superadmin sees the select and must choose; a bounded manager sees nothing,
 * because the server forces their own centre and ignores a submitted one.
 */
import { render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { BranchField, isUnbounded } from '@/components/organisation/branch-field';
import type { User } from '@/types/api';

const listBranches = vi.hoisted(() => vi.fn());
const useAuthMock = vi.hoisted(() => ({ value: {} as Record<string, unknown> }));

vi.mock('@/lib/organisation', () => ({ listBranches }));
vi.mock('@/components/auth-provider', () => ({ useAuth: () => useAuthMock.value }));

function user(overrides: Partial<User>): User {
  return {
    id: 'u1',
    email: 'someone@example.test',
    first_name: 'Some',
    last_name: 'One',
    full_name: 'Some One',
    phone: '',
    role: 'manager',
    is_active: true,
    is_email_verified: true,
    profile_image_url: null,
    branch_id: 'b1',
    branch_code: 'JPR',
    branch_name: 'Jaipur',
    date_joined: '2026-01-01T00:00:00Z',
    ...overrides,
  };
}

describe('isUnbounded', () => {
  it('is true only for a superadmin with no centre', () => {
    expect(isUnbounded(user({ role: 'superadmin', branch_id: null }))).toBe(true);
    expect(isUnbounded(user({ role: 'superadmin', branch_id: 'b1' }))).toBe(false);
    expect(isUnbounded(user({ role: 'admin', branch_id: null }))).toBe(false);
    expect(isUnbounded(null)).toBe(false);
  });
});

describe('BranchField', () => {
  it('renders nothing for a bounded caller and never asks for the list', () => {
    useAuthMock.value = { user: user({}) };
    render(<BranchField value="" onChange={vi.fn()} />);
    expect(screen.queryByLabelText(/centre/i)).not.toBeInTheDocument();
    expect(listBranches).not.toHaveBeenCalled();
  });

  it('lists the open centres for a superadmin', async () => {
    useAuthMock.value = {
      user: user({ role: 'superadmin', branch_id: null, branch_code: null, branch_name: null }),
    };
    listBranches.mockResolvedValue({
      count: 2,
      page: 1,
      page_size: 100,
      total_pages: 1,
      next: null,
      previous: null,
      results: [
        {
          id: 'b1',
          code: 'JPR',
          name: 'Jaipur',
          city: 'Jaipur',
          is_active: true,
          created_at: '',
          updated_at: '',
        },
        {
          id: 'b2',
          code: 'OLD',
          name: 'Closed one',
          city: '',
          is_active: false,
          created_at: '',
          updated_at: '',
        },
      ],
    });
    render(<BranchField value="" onChange={vi.fn()} />);
    await screen.findByLabelText(/centre/i);
    await waitFor(() =>
      expect(screen.getByRole('option', { name: /Jaipur \(JPR\)/ })).toBeInTheDocument(),
    );
    expect(screen.queryByRole('option', { name: /Closed one/ })).not.toBeInTheDocument();
  });
});
