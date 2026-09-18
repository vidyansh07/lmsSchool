import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { AppShell } from '@/components/app-shell';
import { Capability } from '@/lib/capabilities';

const SIDEBAR_STORAGE_KEY = 'grras.sidebar-collapsed';

function staffAuth() {
  const capabilities = [Capability.userViewAny];
  return {
    user: { role: 'admin', email: 'a@example.test', full_name: 'Amy Admin', capabilities },
    isLoading: false,
    signOut: vi.fn(),
    can: (capability: string) => (capabilities as string[]).includes(capability),
  };
}

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
  beforeEach(() => window.localStorage.clear());

  it('provides a skip link, navigation and a main landmark', () => {
    mockAuth.value = { user: null, isLoading: false, signOut: vi.fn(), can: () => false };
    renderShell();

    expect(screen.getByRole('link', { name: /skip to content/i })).toBeInTheDocument();
    expect(screen.getByRole('navigation', { name: 'Main' })).toBeInTheDocument();
    expect(screen.getByRole('main')).toHaveAttribute('id', 'main-content');
    expect(screen.getByText('Content')).toBeInTheDocument();
  });

  it('shows the environment badge outside production', () => {
    mockAuth.value = { user: null, isLoading: false, signOut: vi.fn(), can: () => false };
    renderShell();
    expect(screen.getByLabelText(/environment:/i)).toBeInTheDocument();
  });

  it('offers sign-in to a signed-out visitor', () => {
    mockAuth.value = { user: null, isLoading: false, signOut: vi.fn(), can: () => false };
    renderShell();
    expect(screen.getByRole('link', { name: /sign in/i })).toBeInTheDocument();
    expect(screen.queryByRole('link', { name: 'Users' })).not.toBeInTheDocument();
  });

  it('hides management links from a user without the capability', () => {
    mockAuth.value = {
      user: { role: 'student', email: 's@example.test', full_name: 'Sam', capabilities: [] },
      isLoading: false,
      signOut: vi.fn(),
      can: () => false,
    };
    renderShell();

    expect(screen.queryByRole('link', { name: 'Users' })).not.toBeInTheDocument();
    expect(screen.queryByRole('link', { name: 'Students' })).not.toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'My profile' })).toBeInTheDocument();
  });

  it('shows management links to a user who holds the capabilities', () => {
    const capabilities = [Capability.userViewAny, Capability.studentViewAny, Capability.trainerViewAny];
    mockAuth.value = {
      user: {
        role: 'admin',
        email: 'a@example.test',
        full_name: 'Amy',
        capabilities,
      },
      isLoading: false,
      signOut: vi.fn(),
      can: (capability: string) => (capabilities as string[]).includes(capability),
    };
    renderShell();

    expect(screen.getByRole('link', { name: 'Users' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Students' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Trainers' })).toBeInTheDocument();
  });
});

/**
 * The collapsed/icon-only sidebar state (Phase R3). `tests/setup.ts` stubs
 * `window.matchMedia` to answer `matches: false` for every query, so with no
 * stored preference the `xl:`-and-up check the shell uses for its breakpoint
 * default never matches — exactly the narrower, `lg:`-only viewport the
 * auto-collapse default is for, so these tests exercise the shell in its
 * default *collapsed* state unless a test says otherwise.
 */
describe('AppShell sidebar collapse', () => {
  beforeEach(() => window.localStorage.clear());

  it('defaults to collapsed with no stored preference, and the toggle switches state and persists the choice', async () => {
    const user = userEvent.setup();
    mockAuth.value = staffAuth();
    renderShell();

    expect(window.localStorage.getItem(SIDEBAR_STORAGE_KEY)).toBeNull();
    expect(screen.getByRole('button', { name: 'Expand navigation' })).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Expand navigation' }));

    expect(screen.getByRole('button', { name: 'Collapse navigation' })).toBeInTheDocument();
    expect(window.localStorage.getItem(SIDEBAR_STORAGE_KEY)).toBe('expanded');

    await user.click(screen.getByRole('button', { name: 'Collapse navigation' }));

    expect(screen.getByRole('button', { name: 'Expand navigation' })).toBeInTheDocument();
    expect(window.localStorage.getItem(SIDEBAR_STORAGE_KEY)).toBe('collapsed');
  });

  it('reads a previously stored preference back on the next mount', () => {
    window.localStorage.setItem(SIDEBAR_STORAGE_KEY, 'expanded');
    mockAuth.value = staffAuth();
    renderShell();

    expect(screen.getByRole('button', { name: 'Collapse navigation' })).toBeInTheDocument();
  });

  it('still gives every collapsed nav item an accessible name', () => {
    mockAuth.value = staffAuth();
    renderShell(); // default state here is collapsed — see the describe-block note above.

    // The label text is visually hidden (`sr-only`) when collapsed, not
    // removed, so the accessible name — and the Tooltip's hover/focus
    // equivalent carrying the same text — survive exactly as before.
    expect(screen.getByRole('link', { name: 'Users' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'My profile' })).toBeInTheDocument();
  });

  it('keeps every collapsed nav item keyboard-focusable', () => {
    mockAuth.value = staffAuth();
    renderShell();

    const nav = screen.getByRole('navigation', { name: 'Main' });
    const links = within(nav).getAllByRole('link');
    expect(links.length).toBeGreaterThan(0);
    for (const link of links) {
      link.focus();
      expect(link).toHaveFocus();
    }
  });

  it('leaves the below-lg drawer showing the full, expanded nav regardless of the sidebar collapse state', async () => {
    const user = userEvent.setup();
    // The sidebar itself is collapsed here; the drawer must not be.
    window.localStorage.setItem(SIDEBAR_STORAGE_KEY, 'collapsed');
    mockAuth.value = staffAuth();
    renderShell();

    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Open navigation menu' }));

    const dialog = await screen.findByRole('dialog');
    expect(within(dialog).getByRole('link', { name: 'Users' })).toBeInTheDocument();
    // The collapsed sidebar's own group boundaries render as a divider
    // (`<hr>`) instead of a text heading; the drawer's copy of the nav is
    // always the expanded one and should have none.
    expect(dialog.querySelectorAll('hr')).toHaveLength(0);
    // And the label text in the drawer is real, visible text — not the
    // collapsed sidebar's `sr-only` copy.
    const usersLabel = within(dialog).getByText('Users');
    expect(usersLabel).not.toHaveClass('sr-only');
  });
});

/**
 * A regression check for the drawer itself (`Sheet`): the modal behaviour
 * this file's docstring says must not change — focus trap, `Escape`,
 * backdrop — none of which Phase R3 touched. `sheet.tsx` already has its own
 * unit coverage for the mechanism; this only confirms `AppShell` still wires
 * it up exactly as before.
 */
describe('AppShell mobile drawer (unchanged by Phase R3)', () => {
  beforeEach(() => window.localStorage.clear());

  it('opens as a real modal dialog and closes on Escape', async () => {
    const user = userEvent.setup();
    mockAuth.value = staffAuth();
    renderShell();

    await user.click(screen.getByRole('button', { name: 'Open navigation menu' }));
    expect(await screen.findByRole('dialog')).toBeInTheDocument();

    await user.keyboard('{Escape}');
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
  });

  it('still offers the account card and sign-out inside the open drawer', async () => {
    const user = userEvent.setup();
    mockAuth.value = staffAuth();
    renderShell();

    await user.click(screen.getByRole('button', { name: 'Open navigation menu' }));
    const dialog = await screen.findByRole('dialog');
    expect(within(dialog).getByRole('button', { name: 'Sign out' })).toBeInTheDocument();
  });
});
