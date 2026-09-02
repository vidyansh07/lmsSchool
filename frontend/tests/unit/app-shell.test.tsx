import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { AppShell } from '@/components/app-shell';
import { Capability } from '@/lib/capabilities';

const mockAuth = vi.hoisted(() => ({ value: {} as Record<string, unknown> }));

vi.mock('next/navigation', () => ({
  usePathname: () => '/',
  useRouter: () => ({ replace: vi.fn(), push: vi.fn() }),
}));

vi.mock('@/components/auth-provider', () => ({
  useAuth: () => mockAuth.value,
}));

function renderShell() {
  return render(
    <AppShell>
      <p>Content</p>
    </AppShell>,
  );
}

describe('AppShell', () => {
  it('provides a skip link, navigation and a main landmark', () => {
    mockAuth.value = { user: null, isLoading: false, signOut: vi.fn() };
    renderShell();

    expect(screen.getByRole('link', { name: /skip to content/i })).toBeInTheDocument();
    expect(screen.getByRole('navigation', { name: 'Main' })).toBeInTheDocument();
    expect(screen.getByRole('main')).toHaveAttribute('id', 'main-content');
    expect(screen.getByText('Content')).toBeInTheDocument();
  });

  it('shows the environment badge outside production', () => {
    mockAuth.value = { user: null, isLoading: false, signOut: vi.fn() };
    renderShell();
    expect(screen.getByLabelText(/environment:/i)).toBeInTheDocument();
  });

  it('offers sign-in to a signed-out visitor', () => {
    mockAuth.value = { user: null, isLoading: false, signOut: vi.fn() };
    renderShell();
    expect(screen.getByRole('link', { name: /sign in/i })).toBeInTheDocument();
    expect(screen.queryByRole('link', { name: 'Users' })).not.toBeInTheDocument();
  });

  it('hides management links from a user without the capability', () => {
    mockAuth.value = {
      user: { role: 'student', email: 's@example.test', full_name: 'Sam', capabilities: [] },
      isLoading: false,
      signOut: vi.fn(),
    };
    renderShell();

    expect(screen.queryByRole('link', { name: 'Users' })).not.toBeInTheDocument();
    expect(screen.queryByRole('link', { name: 'Students' })).not.toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'My profile' })).toBeInTheDocument();
  });

  it('shows management links to a user who holds the capabilities', () => {
    mockAuth.value = {
      user: {
        role: 'admin',
        email: 'a@example.test',
        full_name: 'Amy',
        capabilities: [
          Capability.userViewAny,
          Capability.studentViewAny,
          Capability.trainerViewAny,
        ],
      },
      isLoading: false,
      signOut: vi.fn(),
    };
    renderShell();

    expect(screen.getByRole('link', { name: 'Users' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Students' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Trainers' })).toBeInTheDocument();
  });
});
