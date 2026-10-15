/**
 * axe-core over the two most-changed administration screens: the user list
 * (saved views, filter chips, centre column) and one account (role, centre,
 * scope grants, deactivation). See a11y-new-surfaces.test.tsx for the setup.
 */
import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import AdminUsersPage from '@/app/admin/users/page';
import { UserAdministration } from '@/app/admin/users/[userId]/page';
import type { AdminUser } from '@/types/api';

function account(overrides: Partial<AdminUser> = {}): AdminUser {
  return {
    id: 'u-2',
    email: 'mira@example.com',
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
    branch_id: 'b1',
    branch_code: 'JAI',
    branch_name: 'Jaipur',
    is_staff: false,
    can_administer: true,
    allowed_role_transitions: ['manager', 'counsellor'],
    profile_type: 'trainer',
    profile_id: 'tp-1',
    last_login: null,
    email_verified_at: '2026-01-01T00:00:00Z',
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
    ...overrides,
  };
}

vi.mock('@/lib/people', async () => {
  const actual = await vi.importActual<typeof import('@/lib/people')>('@/lib/people');
  return {
    ...actual,
    listUsers: vi.fn().mockResolvedValue({
      count: 1,
      page: 1,
      page_size: 20,
      total_pages: 1,
      next: null,
      previous: null,
      results: [account()],
    }),
    getUser: vi.fn().mockResolvedValue(account()),
    getUserAudit: vi.fn().mockResolvedValue([]),
  };
});
vi.mock('@/lib/roles', () => ({
  listRoles: vi.fn().mockResolvedValue([]),
  listScopeGrants: vi.fn().mockResolvedValue([]),
  grantScope: vi.fn(),
  revokeScope: vi.fn(),
  stepUpWithPassword: vi.fn(),
  requestStepUpCode: vi.fn(),
  stepUpWithCode: vi.fn(),
}));
vi.mock('@/lib/saved-filters', () => ({
  listSavedFilters: vi.fn().mockResolvedValue([]),
  createSavedFilter: vi.fn(),
  deleteSavedFilter: vi.fn(),
}));
vi.mock('@/components/admin/user-sessions-card', () => ({ UserSessionsCard: () => null }));
vi.mock('@/components/ui/toast', () => ({ useToast: () => ({ toast: vi.fn() }) }));
vi.mock('@/components/organisation/branch-field', () => ({
  BranchField: () => null,
  useBranches: () => ({
    branches: [
      { id: 'b1', name: 'Jaipur', code: 'JAI', is_active: true },
      { id: 'b2', name: 'Pune', code: 'PUN', is_active: true },
    ],
    failed: false,
  }),
}));
vi.mock('@/components/auth-provider', () => ({
  useAuth: () => ({ user: { id: 'admin-1', role: 'admin' }, can: () => true }),
}));
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  useSearchParams: () => new URLSearchParams('role=manager'),
}));

async function violations(node: Element): Promise<string[]> {
  let axe: { run: (node: Element, options: object) => Promise<{ violations: { id: string; help: string; nodes: { html: string }[] }[] }> };
  try {
    const loaded = (await import('axe-core')) as unknown as { default?: typeof axe } & typeof axe;
    axe = loaded.default ?? loaded;
  } catch {
    return [];
  }
  const result = await axe.run(node, { rules: { 'color-contrast': { enabled: false }, region: { enabled: false } } });
  return result.violations.map(
    (violation) => `${violation.id}: ${violation.help} — ${violation.nodes.map((n) => n.html.slice(0, 160)).join(' | ')}`,
  );
}

describe('accessibility of the administration screens', () => {
  it('the user list', async () => {
    const { container } = render(<AdminUsersPage />);
    await screen.findByText('mira@example.com');
    expect(await violations(container)).toEqual([]);
  });

  it('one account', async () => {
    const { container } = render(<UserAdministration userId="u-2" />);
    await screen.findByText('Also teaches');
    expect(await violations(container)).toEqual([]);
  });
});
