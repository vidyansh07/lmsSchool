import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { RequireAuth } from '@/components/require-auth';
import { Capability } from '@/lib/capabilities';

const mockAuth = vi.hoisted(() => ({ value: {} as Record<string, unknown> }));

vi.mock('next/navigation', () => ({
  useRouter: () => ({ replace: vi.fn(), push: vi.fn() }),
  usePathname: () => '/',
}));

vi.mock('@/components/auth-provider', () => ({
  useAuth: () => mockAuth.value,
}));

describe('RequireAuth', () => {
  it('renders children for a user holding the capability', () => {
    mockAuth.value = {
      user: { id: '1', capabilities: [Capability.userViewAny] },
      isLoading: false,
      can: () => true,
    };
    render(
      <RequireAuth capability={Capability.userViewAny}>
        <p>Admin content</p>
      </RequireAuth>,
    );
    expect(screen.getByText('Admin content')).toBeInTheDocument();
  });

  it('hides the page from a user without the capability', () => {
    mockAuth.value = {
      user: { id: '1', capabilities: [] },
      isLoading: false,
      can: () => false,
    };
    render(
      <RequireAuth capability={Capability.userViewAny}>
        <p>Admin content</p>
      </RequireAuth>,
    );
    expect(screen.queryByText('Admin content')).not.toBeInTheDocument();
    expect(screen.getByText(/do not have access/i)).toBeInTheDocument();
  });

  it('shows a loading state while the session is being resolved', () => {
    mockAuth.value = { user: null, isLoading: true, can: () => false };
    render(
      <RequireAuth>
        <p>Content</p>
      </RequireAuth>,
    );
    expect(screen.getByRole('status')).toBeInTheDocument();
    expect(screen.queryByText('Content')).not.toBeInTheDocument();
  });
});
