import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { AppShell } from '@/components/app-shell';
import { homeFor } from '@/components/navigation';
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

const pathname = vi.hoisted(() => ({ value: '/' }));
vi.mock('next/navigation', () => ({
  usePathname: () => pathname.value,
  useRouter: () => ({ replace: vi.fn(), push: vi.fn() }),
  useSearchParams: () => new URLSearchParams(window.location.search),
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

  it('provides a skip link and main landmark without role navigation for a visitor', () => {
    mockAuth.value = { user: null, isLoading: false, signOut: vi.fn(), can: () => false };
    renderShell();

    expect(screen.getByRole('link', { name: /skip to content/i })).toBeInTheDocument();
    expect(screen.queryByRole('navigation', { name: 'Main' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Open navigation menu' })).not.toBeInTheDocument();
    expect(screen.getByRole('main')).toHaveAttribute('id', 'main-content');
    expect(screen.getByText('Content')).toBeInTheDocument();
  });

  it('makes the skip link target focusable so DOM focus actually lands there', async () => {
    mockAuth.value = { user: null, isLoading: false, signOut: vi.fn(), can: () => false };
    const user = userEvent.setup();
    renderShell();

    const skipLink = screen.getByRole('link', { name: /skip to content/i });
    const main = screen.getByRole('main');

    // A non-natively-focusable element like <main> only actually receives
    // DOM focus (rather than just a scroll / sequential-focus-navigation
    // starting point) when it carries tabIndex={-1}.
    expect(main).toHaveAttribute('tabindex', '-1');

    await user.click(skipLink);
    main.focus();
    expect(main).toHaveFocus();
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
    expect(screen.queryByRole('link', { name: 'User accounts' })).not.toBeInTheDocument();
  });

  it('hides management links from a user without the capability', () => {
    mockAuth.value = {
      user: { role: 'student', email: 's@example.test', full_name: 'Sam', capabilities: [] },
      isLoading: false,
      signOut: vi.fn(),
      can: () => false,
    };
    renderShell();

    expect(screen.queryByRole('link', { name: 'User accounts' })).not.toBeInTheDocument();
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

    expect(screen.getByRole('link', { name: 'User accounts' })).toBeInTheDocument();
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

  it('names the role workspace and lets expanded sections be collapsed persistently', async () => {
    const user = userEvent.setup();
    window.localStorage.setItem(SIDEBAR_STORAGE_KEY, 'expanded');
    // Groups start closed when nothing is stored; this test is about closing
    // an open one, so it says explicitly that none are closed yet.
    window.localStorage.setItem('grras.nav-groups-collapsed.admin', '[]');
    mockAuth.value = staffAuth();
    renderShell();

    expect(screen.getByText('Administrator workspace')).toBeInTheDocument();
    // The brand link goes where sign-in lands: the first page the sidebar offers.
    const home = homeFor(mockAuth.value.user as Parameters<typeof homeFor>[0]);
    expect(home).not.toBe('/');
    for (const link of screen.getAllByRole('link', { name: /Grras LMS/ })) {
      expect(link).toHaveAttribute('href', home);
    }

    const people = screen.getByRole('button', { name: 'People & records' });
    expect(people).toHaveAttribute('aria-expanded', 'true');
    expect(screen.getByRole('link', { name: 'User accounts' })).toBeInTheDocument();

    await user.click(people);

    expect(people).toHaveAttribute('aria-expanded', 'false');
    expect(screen.queryByRole('link', { name: 'User accounts' })).not.toBeInTheDocument();
    expect(window.localStorage.getItem('grras.nav-groups-collapsed.admin')).toContain(
      'People & records',
    );
  });

  it('still gives every collapsed nav item an accessible name', () => {
    mockAuth.value = staffAuth();
    renderShell(); // default state here is collapsed — see the describe-block note above.

    // The label text is visually hidden (`sr-only`) when collapsed, not
    // removed, so the accessible name — and the Tooltip's hover/focus
    // equivalent carrying the same text — survive exactly as before.
    expect(screen.getByRole('link', { name: 'User accounts' })).toBeInTheDocument();
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
    // Nav groups start closed when nothing is stored; this test is about the
    // drawer rendering the expanded tree, so it opens them explicitly.
    window.localStorage.setItem('grras.nav-groups-collapsed.admin', '[]');
    mockAuth.value = staffAuth();
    renderShell();

    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Open navigation menu' }));

    const dialog = await screen.findByRole('dialog');
    expect(within(dialog).getByRole('link', { name: 'User accounts' })).toBeInTheDocument();
    // The collapsed sidebar's own group boundaries render as a divider
    // (`<hr>`) instead of a text heading; the drawer's copy of the nav is
    // always the expanded one and should have none.
    expect(dialog.querySelectorAll('hr')).toHaveLength(0);
    // And the label text in the drawer is real, visible text — not the
    // collapsed sidebar's `sr-only` copy.
    const usersLabel = within(dialog).getByText('User accounts');
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

describe('AppShell — a sidebar and module tabs for each role', () => {
  beforeEach(() => {
    window.localStorage.clear();
    pathname.value = '/';
  });

  function signIn(role: string, capabilities: string[]) {
    mockAuth.value = {
      user: { role, email: `${role}@example.test`, full_name: role, capabilities },
      isLoading: false,
      signOut: vi.fn(),
      can: (capability: string) => capabilities.includes(capability),
    };
  }

  it("shows a counsellor the front desk, and the leads module's other screens as tabs", () => {
    signIn('counsellor', [
      Capability.enrolmentCreate,
      Capability.enquiryViewAny,
      Capability.formAssign,
      Capability.studentCreate,
    ]);
    pathname.value = '/enquiries';
    renderShell();

    const sidebar = screen.getAllByRole('navigation', { name: 'Main' })[0]!;
    const links = within(sidebar).getAllByRole('link');
    // The pipeline first, then leads — the counsellor's own order.
    expect(links[0]).toHaveAttribute('href', '/admissions/dashboard');
    expect(links.map((link) => link.getAttribute('href'))).toEqual(
      expect.arrayContaining(['/enquiries', '/forms/fill/enquiry', '/students/new']),
    );

    const tabs = screen.getByRole('navigation', { name: 'Leads' });
    expect(within(tabs).getByRole('link', { name: 'Enquiries' })).toHaveAttribute(
      'aria-current',
      'page',
    );
    expect(within(tabs).getByRole('link', { name: 'New enquiry' })).toHaveAttribute(
      'href',
      '/forms/fill/enquiry',
    );
    expect(within(tabs).getByRole('link', { name: 'Form inbox' })).toBeInTheDocument();
  });

  it('offers only the tabs a configured role still holds', () => {
    mockAuth.value = {
      user: {
        role: 'counsellor',
        custom_role: 'desk-only',
        email: 'd@example.test',
        full_name: 'Desk',
        capabilities: [Capability.enquiryViewAny],
      },
      isLoading: false,
      signOut: vi.fn(),
      can: () => false,
    };
    pathname.value = '/enquiries';
    renderShell();
    const tabs = screen.getByRole('navigation', { name: 'Leads' });
    expect(within(tabs).queryByRole('link', { name: 'New enquiry' })).not.toBeInTheDocument();
  });

  it("shows a manager the academics module's screens as tabs", () => {
    signIn('manager', [Capability.performanceViewAny, Capability.batchViewAny, Capability.dsrViewAny]);
    pathname.value = '/dsr';
    renderShell();
    const tabs = screen.getByRole('navigation', { name: 'Academics' });
    expect(within(tabs).getByRole('link', { name: 'Batches' })).toBeInTheDocument();
    expect(within(tabs).getByRole('link', { name: 'Batch review' })).toBeInTheDocument();
  });

  it('draws no tabs for a module with a single screen', () => {
    signIn('admin', [Capability.trainerViewAny]);
    pathname.value = '/manage/trainers';
    renderShell();
    expect(screen.queryByRole('navigation', { name: 'Trainers' })).not.toBeInTheDocument();
  });

  it('starts with every group closed, and still shows where you are', () => {
    // Fifty links on first sign-in is a wall. Nothing stored now means
    // everything closed; the group holding the current page opens anyway, so
    // a collapsed sidebar is never a sidebar with nothing in it.
    window.localStorage.setItem(SIDEBAR_STORAGE_KEY, 'expanded');
    window.localStorage.removeItem('grras.nav-groups-collapsed.admin');
    mockAuth.value = staffAuth();
    renderShell();

    const nav = screen.getByRole('navigation', { name: 'Main' });
    expect(within(nav).queryByRole('link', { name: 'User accounts' })).not.toBeInTheDocument();
    // The untitled first block has no heading to collapse, so it is always
    // there. "Needs attention" is ungated, so it survives any capability set.
    expect(within(nav).getByRole('link', { name: 'Needs attention' })).toBeInTheDocument();
  });
});
