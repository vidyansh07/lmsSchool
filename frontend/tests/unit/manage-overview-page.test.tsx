/**
 * The manager overview (`app/manage/page.tsx`) — Phase R4's new screen,
 * replacing the bare `redirect('/manage/batches')` the old
 * `manage-redirect.test.tsx` covered (removed: that behaviour no longer
 * exists). Coverage follows the same shape `admin-overview-page.test.tsx`
 * set for Phase R2: loading, error-with-retry, real data rendering (KPI
 * tiles and the new chart), and — specific to this page — the capability
 * gate `/manage/reviews` already uses for the same dashboard.
 *
 * `ManagerAttentionStrip` self-fetches through `hooks/use-api`'s `useApi`
 * (the same hook `WarningsStrip` uses), so both are driven by one mocked
 * `useApi` here, differentiated by the path each actually requests — not a
 * single blanket return, since a `StaffWarning[]` and a `ManagerDashboard`
 * are not interchangeable shapes.
 */
import { render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import ManagePage from '@/app/manage/page';
import { ApiError } from '@/lib/api';
import { Capability } from '@/lib/capabilities';
import type { ManagerDashboard } from '@/lib/manage';

const getManagerDashboard = vi.hoisted(() => vi.fn());
const useApi = vi.hoisted(() => vi.fn());
const useAuthMock = vi.hoisted(() => ({ value: {} as Record<string, unknown> }));

vi.mock('@/lib/manage', async () => {
  const actual = await vi.importActual<typeof import('@/lib/manage')>('@/lib/manage');
  return { ...actual, getManagerDashboard };
});
vi.mock('@/hooks/use-api', () => ({ useApi }));
vi.mock('@/components/auth-provider', () => ({ useAuth: () => useAuthMock.value }));
vi.mock('next/navigation', () => ({
  useRouter: () => ({ replace: vi.fn(), push: vi.fn() }),
  usePathname: () => '/manage',
}));

function grantedAuth() {
  useAuthMock.value = {
    user: {
      id: 'u1',
      role: 'manager',
      capabilities: [Capability.performanceViewAny],
      full_name: 'Arjun Mehta',
      email: 'arjun@example.com',
    },
    isLoading: false,
    can: (capability: string) => capability === Capability.performanceViewAny,
  };
}

/** Real shape: exactly what `GET /api/v1/dashboards/manager/` returns. */
function dashboard(overrides: Partial<ManagerDashboard> = {}): ManagerDashboard {
  return {
    batches: { total: 42, active: 30, behind_schedule: 4, at_risk: 3 },
    students: { total: 610, active: 540, at_risk: 18 },
    trainers: { total: 22, with_overdue_dsr: 2 },
    attention: [],
    activities: { pending: 5, overdue: 1, under_review: 6 },
    risk: { critical: 3, warning: 9 },
    reviews_due: 4,
    as_of: '2026-09-18T09:00:00Z',
    ...overrides,
  };
}

/** `useApi` backs two independent self-fetching components on this page
 *  (`WarningsStrip` at `/warnings/`, `ManagerAttentionStrip` at
 *  `/api/v1/dashboards/manager/`) — resolved by the path each one actually
 *  requests, not one shared return value. */
function mockSharedFetches(data: ManagerDashboard) {
  useApi.mockImplementation((path: string) => {
    if (path.includes('dashboards/manager')) {
      return { data, error: null, isLoading: false, reload: vi.fn() };
    }
    return { data: [], error: null, isLoading: false, reload: vi.fn() };
  });
}

/** A `StatCard` KPI tile, found by its plain-text label — same helper shape
 *  `counsellor-dashboard-page.test.tsx` uses for the same component. */
function kpiTileFor(labelText: string | RegExp): HTMLElement {
  const label = screen.getByText(labelText);
  const tile = label.parentElement?.parentElement?.parentElement;
  if (!tile) throw new Error(`Could not locate the KPI tile for "${String(labelText)}"`);
  return tile as HTMLElement;
}

/** Reads the tile's figure. This used to read `NumberTicker`'s `aria-label`
 *  to avoid racing a ~900ms count-up; the tile no longer animates, so the
 *  rendered text is the value from the first render. */
function kpiValue(tile: HTMLElement, value: number): void {
  expect(tile.querySelector('[data-numeric]')).toHaveTextContent(value.toLocaleString());
}

function dataTable(): HTMLElement {
  return screen.getAllByRole('table', { hidden: true })[0] as HTMLElement;
}

beforeEach(() => {
  grantedAuth();
  // Deterministic chart render, same reasoning as `admin-overview-page
  // .test.tsx`: Recharts reveals a chart's shapes across animation frames
  // jsdom has no clock to advance past.
  vi.spyOn(window, 'matchMedia').mockImplementation(
    (query: string) =>
      ({
        matches: true,
        media: query,
        onchange: null,
        addEventListener: () => {},
        removeEventListener: () => {},
        addListener: () => {},
        removeListener: () => {},
        dispatchEvent: () => false,
      }) as unknown as MediaQueryList,
  );
});

describe('ManagePage — loading and error', () => {
  it('shows a loading state before the dashboard resolves', () => {
    getManagerDashboard.mockReturnValue(new Promise(() => {}));
    mockSharedFetches(dashboard());

    render(<ManagePage />);
    expect(screen.getByRole('status')).toBeInTheDocument();
  });

  it('shows a retryable error state when the fetch fails, and recovers on retry', async () => {
    getManagerDashboard
      .mockRejectedValueOnce(new ApiError(500, 'server_error', 'Manager overview is down.', 'req-1'))
      .mockResolvedValueOnce(dashboard());
    mockSharedFetches(dashboard());

    render(<ManagePage />);
    expect(await screen.findByText('Manager overview is down.')).toBeInTheDocument();

    const retry = screen.getByRole('button', { name: /try again/i });
    retry.click();

    expect(await screen.findByText('Manager overview')).toBeInTheDocument();
  });
});

describe('ManagePage — real data', () => {
  it('renders the totals KPI row from real, already-fetched data', async () => {
    mockSharedFetches(dashboard());
    getManagerDashboard.mockResolvedValue(
      dashboard({
        batches: { total: 42, active: 30, behind_schedule: 4, at_risk: 3 },
        students: { total: 610, active: 540, at_risk: 18 },
        trainers: { total: 22, with_overdue_dsr: 2 },
      }),
    );

    render(<ManagePage />);
    await screen.findByText('Manager overview');

    kpiValue(kpiTileFor('Total batches'), 42);
    kpiValue(kpiTileFor('Total students'), 610);
    kpiValue(kpiTileFor('Total trainers'), 22);

    // The `period` capability added to `StatCard` this phase — a totals row
    // that is not time-windowed the way the attention strip's figures are.
    expect(screen.getAllByText(/All-time/).length).toBeGreaterThan(0);
  });

  it('renders the attention-breakdown chart with real figures, not invented data', async () => {
    mockSharedFetches(dashboard());
    getManagerDashboard.mockResolvedValue(
      dashboard({
        batches: { total: 42, active: 30, behind_schedule: 4, at_risk: 3 },
        risk: { critical: 3, warning: 9 },
        reviews_due: 4,
      }),
    );

    render(<ManagePage />);
    // The card's own heading and the chart's visually-hidden caption
    // legitimately carry the same text — scoped to the heading role so the
    // two do not collide.
    await screen.findByRole('heading', { name: 'What needs attention, by kind' });

    await waitFor(() => expect(document.querySelector('.recharts-bar-rectangle')).toBeInTheDocument());

    // Two categories legitimately share a count (4, 3), so each row is read
    // by walking from its own label cell to its own value cell rather than
    // a bare `getByText` on the number.
    const table = within(dataTable());
    const rowValue = (label: string) =>
      table.getByText(label).closest('tr')?.querySelector('td:nth-child(2)')?.textContent;

    expect(rowValue('Behind schedule')).toBe('4');
    expect(rowValue('At-risk batches')).toBe('3');
    expect(rowValue('At-risk students')).toBe('18');
    expect(rowValue('Overdue DSRs')).toBe('2');
    expect(rowValue('Critical flags')).toBe('3');
    expect(rowValue('Reviews due')).toBe('4');
  });

  it('reuses ManagerAttentionStrip rather than a second copy of its KPI tiles', async () => {
    mockSharedFetches(
      dashboard({
        attention: [
          { kind: 'at_risk', label: 'Students at risk', count: 18, href: '/manage/batches?attention=at_risk', severity: 'high' },
        ],
      }),
    );
    getManagerDashboard.mockResolvedValue(dashboard());

    render(<ManagePage />);
    await screen.findByText('Manager overview');

    // The strip's own figures (from the mocked `useApi`, a separate fetch
    // from this page's own `getManagerDashboard` call above) are on the
    // page. "Students at risk" legitimately appears twice — the strip's own
    // KPI tile and its `AlertList` entry both name it — so this counts
    // rather than asserting a single match.
    expect(await screen.findByText('Active batches')).toBeInTheDocument();
    expect((await screen.findAllByText('Students at risk')).length).toBeGreaterThan(0);
  });

  it('links to both hub screens', async () => {
    mockSharedFetches(dashboard());
    getManagerDashboard.mockResolvedValue(dashboard());

    render(<ManagePage />);
    await screen.findByText('Manager overview');

    const links = screen.getAllByRole('link').map((link) => link.getAttribute('href'));
    expect(links).toContain('/manage/batches');
    expect(links).toContain('/manage/trainers');
  });
});

/** The design-pivot additions (R13): a time-of-day greeting, a real
 *  on-schedule-share gauge derived from `batches.active`/`behind_schedule`,
 *  and a real active/other students donut — both derived from data this
 *  page already fetches, no new endpoint. */
describe('ManagePage — design pivot additions', () => {
  it('greets the signed-in manager by name, derived from the mocked useAuth() user', async () => {
    mockSharedFetches(dashboard());
    getManagerDashboard.mockResolvedValue(dashboard());

    render(<ManagePage />);

    await screen.findByText('Manager overview');
    expect(screen.getByText(/Arjun Mehta/)).toBeInTheDocument();
  });

  it('renders a RadialProgress gauge for the on-schedule share, derived from batches.active and batches.behind_schedule', async () => {
    mockSharedFetches(dashboard());
    getManagerDashboard.mockResolvedValue(
      dashboard({ batches: { total: 42, active: 20, behind_schedule: 5, at_risk: 3 } }),
    );

    render(<ManagePage />);

    await screen.findByRole('heading', { name: 'Batches on schedule' });
    // (20 - 5) / 20 = 75%
    expect(await screen.findByText('75%')).toBeInTheDocument();
    expect(screen.getByText(/of batches on schedule/)).toBeInTheDocument();
  });

  it('renders a DonutChart of active vs. other students, a real exclusive partition of students.total', async () => {
    mockSharedFetches(dashboard());
    getManagerDashboard.mockResolvedValue(
      dashboard({ students: { total: 610, active: 540, at_risk: 18 } }),
    );

    render(<ManagePage />);

    await screen.findByRole('heading', { name: 'Students, active vs. other' });
    await waitFor(() => expect(document.querySelector('.recharts-pie')).toBeInTheDocument());

    const tables = screen.getAllByRole('table', { hidden: true });
    const donutTable = tables.find((table) => within(table).queryByText('Active students'));
    expect(donutTable).toBeTruthy();
    const scoped = within(donutTable as HTMLElement);
    expect(scoped.getByText('540')).toBeInTheDocument();
    expect(scoped.getByText('Other')).toBeInTheDocument();
    expect(scoped.getByText('70')).toBeInTheDocument();
  });
});

describe('ManagePage — capability gate', () => {
  it('hides the overview from a signed-in user without performance.view_any', () => {
    useAuthMock.value = {
      user: { id: 'u2', role: 'trainer', capabilities: [] },
      isLoading: false,
      can: () => false,
    };
    getManagerDashboard.mockReturnValue(new Promise(() => {}));
    mockSharedFetches(dashboard());

    render(<ManagePage />);
    expect(screen.queryByText('Manager overview')).not.toBeInTheDocument();
    expect(screen.getByText(/do not have access/i)).toBeInTheDocument();
  });
});
